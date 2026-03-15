"""
Data ingestion pipeline for company dataset.
Handles reading CSV data and indexing into OpenSearch.
"""
from datetime import datetime

import json
import pandas as pd
import sys
import yaml
from pathlib import Path
from observability import configure_logging, generate_trace_id
from opensearchpy import OpenSearch, helpers
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# Setup structured JSON logging — same format as the backend
configure_logging()
import structlog
logger = structlog.get_logger(__name__)
# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Load pipeline config
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).parent / "ingest_config.yaml"
with _CONFIG_PATH.open() as _fh:
    INGEST_CONFIG: dict = yaml.safe_load(_fh)

# ---------------------------------------------------------------------------
# Industry taxonomy: maps raw CSV labels → search-friendly synonym tags
# ---------------------------------------------------------------------------
_TAXONOMY_PATH = Path(__file__).parent / "industry_taxonomy.json"
with _TAXONOMY_PATH.open() as _fh:
    INDUSTRY_TAXONOMY: dict[str, list[str]] = json.load(_fh)


def get_industry_tags(industry: str) -> list[str]:
    """Return synonym tags for a given industry label."""
    return INDUSTRY_TAXONOMY.get(industry.lower().strip(), [])


# ---------------------------------------------------------------------------
# Country taxonomy: maps country names → regional/alias tags for enriched search
# ---------------------------------------------------------------------------
_COUNTRY_TAXONOMY_PATH = Path(__file__).parent / "country_taxonomy.json"
with _COUNTRY_TAXONOMY_PATH.open() as _fh:
    COUNTRY_TAXONOMY: dict[str, list[str]] = json.load(_fh)


def get_country_tags(country: str) -> list[str]:
    """Return regional/alias tags for a given country label."""
    return COUNTRY_TAXONOMY.get(country.lower().strip(), [])


def parse_locality(locality: str) -> tuple[str, str]:
    """
    Split 'San Francisco, California' → (city='san francisco', state='california').
    Returns empty strings if parsing fails.
    """
    parts = [p.strip().lower() for p in str(locality or "").split(",") if p.strip()]
    city = parts[0] if parts else ""
    state = parts[-1] if len(parts) > 1 else ""
    return city, state

class DataIngestionPipeline:
    """Pipeline for ingesting company data into OpenSearch"""
    
    def __init__(self, opensearch_host="localhost", opensearch_port=443, 
                 opensearch_user="admin", opensearch_password="MySecurePassword123!"):
        """Initialize the ingestion pipeline"""
        try:
            self.client = OpenSearch(
                hosts=[{
                    "host": opensearch_host,
                    "port": opensearch_port
                }],
                http_auth=(opensearch_user, opensearch_password),
                use_ssl=True,
                verify_certs=False,
                timeout=30
            )
            logger.info("opensearch_connected", host=opensearch_host, port=opensearch_port)
        except Exception as e:
            logger.error("opensearch_connection_failed", error=str(e))
            raise
        
        self.index_name = INGEST_CONFIG["index_name"]
        self.batch_trace_id = generate_trace_id()
        logger.info("pipeline_initialised", index=self.index_name, batch_trace_id=self.batch_trace_id)

        # Initialize embedding model
        _model_name = INGEST_CONFIG["embedding"]["model"]
        try:
            logger.info("loading_embedding_model", model=_model_name)
            self.embedding_model = SentenceTransformer(_model_name)
            logger.info("embedding_model_loaded")
        except Exception as e:
            logger.error("embedding_model_load_failed", error=str(e))
            raise
    
    def create_index(self):
        """Create the companies index with proper mappings"""
        try:
            # Check if index exists
            if self.client.indices.exists(self.index_name):
                logger.info("index_exists_recreating", index=self.index_name)
                self.client.indices.delete(index=self.index_name)
        except Exception as e:
            logger.error("index_check_failed", error=str(e))
            raise
        
        _mapping_path = Path(__file__).parent / "index_mapping.json"
        with _mapping_path.open() as _fh:
            index_body = json.load(_fh)
        
        # Create index
        try:
            self.client.indices.create(
                index=self.index_name,
                body=index_body
            )
            logger.info("index_created", index=self.index_name)
        except Exception as e:
            logger.error("index_creation_failed", error=str(e))
            raise
    
    def data_generator(self, file_path: str,
                        chunk_size: int = None,
                        embedding_batch_size: int = None):
        """Streaming generator to process rows in chunks with batch embedding generation."""
        chunk_size = chunk_size or INGEST_CONFIG.get("chunk_size", 10000)
        embedding_batch_size = embedding_batch_size or INGEST_CONFIG.get("embedding_batch_size", 512)
        emb_dim = INGEST_CONFIG.get("embedding", {}).get("dimension", 768)
        # Validate file exists
        if not Path(file_path).exists():
            logger.error("csv_not_found", path=file_path)
            raise FileNotFoundError(f"CSV file not found: {file_path}")
        
        logger.info("csv_read_started", path=file_path)
        
        try:
            reader = pd.read_csv(file_path, chunksize=chunk_size)
        except Exception as e:
            logger.error("csv_open_failed", path=file_path, error=str(e))
            raise
        
        for chunk in reader:
            try:
                # --- CLEANING LOGIC ---
                chunk['year_founded'] = pd.to_numeric(chunk['year_founded'], errors='coerce').fillna(0).astype(int)
                chunk['industry'] = chunk['industry'].fillna("Unknown").str.strip()
                chunk['country'] = chunk['country'].fillna("Unknown").str.strip()
                chunk['locality'] = chunk['locality'].fillna('').str.strip()
            except Exception as e:
                logger.error("chunk_clean_failed", error=str(e))
                continue  # Skip this chunk and continue with next
            
            records = chunk.to_dict('records')
            # Single timestamp for the whole chunk — avoids datetime.now() per document
            indexed_at = datetime.now().isoformat()

            # Pre-compute derived fields once per row to avoid duplicating work
            # inside embedding text-building and document construction.
            parsed = []
            for row in records:
                industry = row.get('industry', 'Unknown')
                locality = row.get('locality', '')
                city, state = parse_locality(locality)
                tags = get_industry_tags(industry)
                ctags = get_country_tags(row.get('country', ''))
                size = row.get('size_range', '')
                parsed.append((industry, locality, city, state, tags, size, ctags))

            # Process embeddings in batches for efficiency
            for i in range(0, len(records), embedding_batch_size):
                batch_records = records[i:i + embedding_batch_size]
                batch_parsed = parsed[i:i + embedding_batch_size]
                logger.info("embedding_batch_processing",
                            batch_num=i // embedding_batch_size + 1,
                            batch_size=len(batch_records),
                            batch_trace_id=self.batch_trace_id)

                # Build embedding texts — BGE documents use plain text, no prefix.
                # Format: "<name>. <industry> <tags>. <size>. <location> <country_tags>".
                texts = [
                    f"company: {row.get('name', '')}. "
                    f"industry: {industry} {' '.join(tags)}. "
                    f"size: {size}. "
                    f"location: {locality}, {state + ', ' if state else ''}{row.get('country', 'Unknown')} {' '.join(ctags)}"
                    for row, (industry, locality, _, state, tags, size, ctags) in zip(batch_records, batch_parsed)
                ]
                try:
                    embeddings = self.embedding_model.encode(
                        texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True
                    ).tolist()
                except Exception as e:
                    logger.error("embedding_batch_failed", error=str(e))
                    embeddings = [[0.0] * emb_dim for _ in batch_records]

                for row, (industry, locality, city, state, tags, size, ctags), vector_embedding in zip(batch_records, batch_parsed, embeddings):
                    # Safe field extraction with defaults
                    company_id = str(row.get('Unnamed: 0', ''))
                    year_founded = int(row.get('year_founded', 0))
                    current_employees = int(row.get('current_employee_estimate', 0))
                    total_employees = int(row.get('total_employee_estimate', 0))

                    searchable_text = " ".join(filter(None, [
                        row.get('name', ''), industry, " ".join(tags),
                        locality, city, state, row.get('country', ''), size, " ".join(ctags)
                    ]))
                    yield {
                        "_index": self.index_name,
                        "_id": company_id if company_id else None,
                        "_source": {
                            "company_id": company_id,
                            "name": row.get('name', ''),
                            "domain": row.get('domain', ''),
                            "year_founded": year_founded,
                            "industry": industry,
                            "industry_tags": tags,
                            "size_range": size,
                            "country": row.get('country', 'Unknown'),
                            "country_tags": ctags,
                            "locality": locality,
                            "city": city,
                            "state": state,
                            "searchable_text": searchable_text,
                            "current_employee_estimate": current_employees,
                            "total_employee_estimate": total_employees,
                            "vector_embedding": vector_embedding,
                            "indexed_at": indexed_at,
                            "ingestion_batch_id": self.batch_trace_id,
                        }
                    }

    def ingest_from_csv(self, csv_path: str = None,
                         chunk_size: int = None,
                         bulk_chunk_size: int = None):
        """Start ingestion using parallel bulk API for CSV data."""
        chunk_size = chunk_size or INGEST_CONFIG.get("chunk_size", 10000)
        bulk_chunk_size = bulk_chunk_size or INGEST_CONFIG.get("bulk_chunk_size", 500)
        if not csv_path:
            raise ValueError("csv_path is required for ingestion")
        
        try:
            logger.info("ingestion_started", batch_trace_id=self.batch_trace_id)
            success_count = 0
            failed_count = 0
            # queue_size > thread_count lets producers pre-fill the queue so
            # HTTP threads never sit idle waiting for the next batch.
            for success, info in helpers.parallel_bulk(
                self.client,
                self.data_generator(csv_path, chunk_size),
                thread_count=4,
                chunk_size=bulk_chunk_size,
                queue_size=8,
                request_timeout=600  # Higher timeout for heavy vector indexing
            ):
                if success:
                    success_count += 1
                    if success_count % 5000 == 0:
                        logger.info("ingestion_progress", indexed=success_count,
                                    batch_trace_id=self.batch_trace_id)
                else:
                    failed_count += 1
                    logger.error("document_index_failed", info=info)
            logger.info("ingestion_complete", indexed=success_count, failed=failed_count,
                        batch_trace_id=self.batch_trace_id)
        except Exception as e:
            logger.error("csv_ingestion_failed", error=str(e))
            raise
        finally:
            self._finalize_index()

    def _finalize_index(self):
        """Reset ingestion-time settings and merge segments for optimal knn performance."""
        try:
            logger.info("index_finalizing", index=self.index_name)
            self.client.indices.put_settings(
                index=self.index_name,
                body={"index": {"refresh_interval": "1s", "number_of_replicas": 1}}
            )
            self.client.indices.refresh(index=self.index_name)
            # Force-merge to reduce HNSW segment count — critical for knn recall and query speed.
            # max_num_segments=5 balances merge time vs. query performance.
            logger.info("index_forcemerge_started", index=self.index_name)
            self.client.indices.forcemerge(index=self.index_name, max_num_segments=5)
            logger.info("index_finalized", index=self.index_name)
        except Exception as e:
            logger.warning("index_finalization_failed", error=str(e))


    
    def _df_doc_generator(self, df: pd.DataFrame, embedding_batch_size: int = 512):
        """Yield individual OpenSearch action dicts from a DataFrame.

        Processes the model in batches of `embedding_batch_size` for efficiency,
        then yields one doc at a time so parallel_bulk controls HTTP batching.
        """
        records = df.to_dict('records')
        indexed_at = datetime.now().isoformat()

        for i in range(0, len(records), embedding_batch_size):
            batch_records = records[i:i + embedding_batch_size]

            parsed = []
            for row in batch_records:
                industry = row.get("industry", "")
                locality = str(row.get("locality") or "")
                city, state = parse_locality(locality)
                tags = get_industry_tags(industry)
                ctags = get_country_tags(row.get("country", ""))
                size = row.get("size_range", "")
                parsed.append((industry, locality, city, state, tags, size, ctags))

            texts = [
                f"search_document: company: {row.get('name', '')}. "
                f"industry: {industry} {' '.join(tags)}. "
                f"size: {size}. "
                f"location: {locality}, {state + ', ' if state else ''}{row.get('country', 'Unknown')} {' '.join(ctags)}"
                for row, (industry, locality, _, state, tags, size, ctags) in zip(batch_records, parsed)
            ]
            try:
                embeddings = self.embedding_model.encode(texts, batch_size=64, show_progress_bar=False).tolist()
            except Exception as e:
                logger.error(f"Failed to generate batch embeddings: {e}")
                embeddings = [[0.0] * 768 for _ in batch_records]

            for idx, (row, (industry, locality, city, state, tags, size, ctags), vector_embedding) in enumerate(
                zip(batch_records, parsed, embeddings)
            ):
                searchable_text = " ".join(filter(None, [
                    row.get("name", ""), industry, " ".join(tags),
                    locality, city, state, row.get("country", ""), size, " ".join(ctags)
                ]))
                yield {
                    "_index": self.index_name,
                    "_id": str(row.get("id", i + idx)),
                    "_source": {
                        "name": row.get("name", ""),
                        "domain": row.get("domain", ""),
                        "year_founded": int(row["year_founded"]) if pd.notna(row.get("year_founded")) else None,
                        "industry": industry,
                        "industry_tags": tags,
                        "size_range": size,
                        "country": row.get("country", ""),
                        "country_tags": ctags,
                        "locality": locality,
                        "city": city,
                        "state": state,
                        "searchable_text": searchable_text,
                        "linkedin_url": row.get("linkedin_url"),
                        "current_employee_estimate": int(row["current_employee_estimate"]) if pd.notna(row.get("current_employee_estimate")) else None,
                        "total_employee_estimate": int(row["total_employee_estimate"]) if pd.notna(row.get("total_employee_estimate")) else None,
                        "indexed_at": indexed_at,
                        "vector_embedding": vector_embedding
                    }
                }

    def start_ingestion_from_dataframe(self, df: pd.DataFrame, embedding_batch_size: int = 512, bulk_chunk_size: int = 500):
        """Index a DataFrame into OpenSearch using parallel_bulk.

        embedding_batch_size: rows fed to the model per forward pass.
        bulk_chunk_size: docs per OpenSearch bulk HTTP request.
        """
        total_records = len(df)
        logger.info("df_ingestion_started", total_records=total_records)
        success_count = 0
        failed_count = 0
        for success, info in helpers.parallel_bulk(
            self.client,
            self._df_doc_generator(df, embedding_batch_size),
            thread_count=4,
            chunk_size=bulk_chunk_size,
            queue_size=8,
            request_timeout=600
        ):
            if success:
                success_count += 1
                if success_count % 5000 == 0:
                        logger.info("df_ingestion_progress", indexed=success_count, total=total_records)
            else:
                failed_count += 1
                logger.error("document_index_failed", info=str(info))
        logger.info("df_ingestion_complete", indexed=success_count, failed=failed_count)
    

    def load_sample_data(self, sample_size=10000) -> pd.DataFrame:
        """Load sample data (create synthetic data for demo)"""
        logger.info("sample_data_generating", sample_size=sample_size)
        
        industries = [
            "Information Technology and Services",
            "Software Development",
            "Financial Services",
            "Healthcare",
            "Retail",
            "Manufacturing",
            "Telecommunications",
            "Education",
            "Real Estate",
            "Transportation and Logistics"
        ]
        
        countries = ["United States", "India", "United Kingdom", "Canada", "Australia", 
                    "Germany", "France", "Japan", "Brazil", "Mexico"]
        
        cities = {
            "United States": ["San Francisco, California", "New York, New York", "Boston, Massachusetts", "Seattle, Washington"],
            "India": ["Bangalore, Karnataka", "Mumbai, Maharashtra", "New Delhi, Delhi"],
            "United Kingdom": ["London, England"],
            "Canada": ["Toronto, Ontario", "Vancouver, British Columbia"],
            "Australia": ["Sydney, New South Wales", "Melbourne, Victoria"],
        }
        
        data = []
        for i in range(sample_size):
            country = countries[i % len(countries)]
            
            data.append({
                "id": str(5000000 + i),
                "name": f"Company {i+1}",
                "domain": f"company{i+1}.com",
                "year_founded": 1950 + (i % 74),
                "industry": industries[i % len(industries)],
                "size_range": ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000", "10001+"][i % 8],
                "country": country,
                "locality": cities.get(country, ["Unknown"])[i % len(cities.get(country, ["Unknown"]))],
                "linkedin_url": f"linkedin.com/company/company{i+1}",
                "current_employee_estimate": (i + 1) * 100 % 50000 + 100,
                "total_employee_estimate": (i + 1) * 150 % 75000 + 150
            })
        
        return pd.DataFrame(data)
    
    def ingest_sample_data(self, sample_size: int = 10000):
        """Ingest sample data"""
        try:
            logger.info("sample_data_loading", sample_size=sample_size)
            df = self.load_sample_data(sample_size)
            self.start_ingestion_from_dataframe(df, batch_size=1000)
        except Exception as e:
            logger.error("sample_ingestion_failed", error=str(e))
            raise

    def get_index_stats(self):
        """Get index statistics"""
        try:
            stats = self.client.indices.stats(index=self.index_name)
            doc_count = stats["indices"][self.index_name]["primaries"]["docs"]["count"]
            size_bytes = stats["indices"][self.index_name]["primaries"]["store"]["size_in_bytes"]
            
            logger.info("index_stats", documents=doc_count,
                        size_mb=round(size_bytes / 1024 / 1024, 2))
            return {"documents": doc_count, "size_mb": size_bytes / 1024 / 1024}
            
        except Exception as e:
            logger.error("index_stats_failed", error=str(e))
            return {}


def main():
    """Main ingestion script"""
    import argparse
    
    try:
        parser = argparse.ArgumentParser(description="Ingest company data into OpenSearch")
        parser.add_argument("--csv", default="companies_sorted.csv", help="CSV file path to ingest")
        parser.add_argument("--sample", type=int, default=10000, help="Number of sample records to generate and ingest")
        parser.add_argument("--reset", action="store_true", help="Reset index before ingestion")
        parser.add_argument("--host", default="localhost", help="OpenSearch host")
        parser.add_argument("--port", type=int, default=9200, help="OpenSearch port")
        
        args = parser.parse_args()
        
        # Initialize pipeline
        try:
            pipeline = DataIngestionPipeline(
                opensearch_host=args.host,
                opensearch_port=args.port
            )
        except Exception as e:
            logger.error("pipeline_init_failed", error=str(e))
            sys.exit(1)
        
        # Always ensure the index exists with the correct settings.
        # --reset (or first run) will delete and recreate it; without --reset
        # it is only created if it does not already exist.
        try:
            if args.reset or not pipeline.client.indices.exists(pipeline.index_name):
                logger.info("creating_index")
                pipeline.create_index()
        except Exception as e:
            logger.error("index_create_failed", error=str(e))
            sys.exit(1)
        
        # Ingest data
        try:
            if args.csv:
                logger.info("csv_ingestion_starting", csv=args.csv)
                pipeline.ingest_from_csv(csv_path=args.csv)
            else:
                logger.info("sample_ingestion_starting", sample_size=args.sample)
                pipeline.ingest_sample_data(args.sample)
        except Exception as e:
            logger.error("ingestion_failed", error=str(e))
            sys.exit(1)
        
        # Show stats
        stats = pipeline.get_index_stats()
        
        print("\n" + "="*50)
        print("Ingestion Complete!")
        print("="*50)
        print(f"Documents indexed: {stats.get('documents', 'N/A')}")
        print(f"Index size: {stats.get('size_mb', 'N/A'):.2f} MB")
        print("\nYou can now query the API:")
        print("  http://localhost:8000/docs")
        print("="*50)
        
    except KeyboardInterrupt:
        logger.info("Ingestion interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
