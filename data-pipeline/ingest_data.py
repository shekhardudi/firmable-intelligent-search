"""
Data ingestion pipeline for company dataset.
Handles reading CSV data and indexing into OpenSearch.
"""
from datetime import datetime

import pandas as pd
import logging
import sys
from pathlib import Path
from opensearchpy import OpenSearch, helpers
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Load environment variables
load_dotenv(Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# Industry taxonomy: maps raw CSV labels → search-friendly synonym tags
# ---------------------------------------------------------------------------
INDUSTRY_TAXONOMY: dict[str, list[str]] = {
    "information technology and services": ["technology", "tech", "IT", "software", "computing", "digital", "cloud"],
    "computer software": ["software", "tech", "SaaS", "programming", "applications", "technology"],
    "internet": ["internet", "online", "web", "digital", "e-commerce", "tech"],
    "financial services": ["finance", "banking", "fintech", "investment", "capital", "financial"],
    "banking": ["banking", "finance", "financial", "fintech", "credit"],
    "insurance": ["insurance", "finance", "risk", "financial services"],
    "hospital & health care": ["healthcare", "health", "medical", "clinical", "hospital"],
    "medical devices": ["medtech", "medical devices", "health", "healthcare"],
    "pharmaceuticals": ["pharma", "drugs", "biotech", "life sciences", "healthcare"],
    "biotechnology": ["biotech", "life sciences", "pharma", "health", "medical research"],
    "oil & energy": ["energy", "oil", "gas", "petroleum", "utilities"],
    "renewables & environment": ["clean energy", "green", "sustainability", "solar", "wind", "environmental", "energy"],
    "utilities": ["utilities", "energy", "power", "water", "infrastructure"],
    "telecommunications": ["telecom", "wireless", "communications", "networking", "broadband"],
    "retail": ["retail", "e-commerce", "consumer goods", "shopping"],
    "consumer goods": ["consumer goods", "FMCG", "retail", "products"],
    "real estate": ["real estate", "property", "realty", "construction"],
    "construction": ["construction", "engineering", "infrastructure", "real estate"],
    "education management": ["education", "edtech", "learning", "university", "training"],
    "e-learning": ["edtech", "online learning", "education", "training"],
    "management consulting": ["consulting", "advisory", "professional services", "strategy"],
    "staffing and recruiting": ["staffing", "recruiting", "HR", "talent", "employment"],
    "human resources": ["HR", "human resources", "people", "talent"],
    "marketing and advertising": ["marketing", "advertising", "digital marketing", "media"],
    "media production": ["media", "content", "entertainment", "publishing"],
    "entertainment": ["entertainment", "media", "gaming", "content"],
    "automotive": ["automotive", "cars", "vehicles", "transportation"],
    "transportation/trucking/railroad": ["transportation", "logistics", "trucking", "freight"],
    "logistics and supply chain": ["logistics", "supply chain", "warehousing", "shipping", "transportation"],
    "aviation & aerospace": ["aerospace", "aviation", "defense", "aircraft"],
    "defense & space": ["defense", "aerospace", "military", "government"],
    "food & beverages": ["food", "beverages", "FMCG", "consumer goods"],
    "restaurants": ["food", "restaurants", "hospitality", "dining"],
    "hospitality": ["hospitality", "hotels", "travel", "tourism"],
    "leisure, travel & tourism": ["travel", "tourism", "hospitality", "leisure"],
    "architecture & planning": ["architecture", "design", "planning", "engineering"],
    "civil engineering": ["civil engineering", "construction", "infrastructure"],
    "mechanical or industrial engineering": ["engineering", "manufacturing", "industrial"],
    "electrical/electronic manufacturing": ["electronics", "manufacturing", "hardware", "tech"],
    "semiconductors": ["semiconductors", "chips", "hardware", "tech", "electronics"],
    "hardware": ["hardware", "electronics", "tech", "devices"],
    "nanotechnology": ["nanotech", "science", "tech", "research"],
    "research": ["research", "science", "R&D"],
    "government administration": ["government", "public sector", "administration"],
    "non-profit organization management": ["non-profit", "NGO", "charity"],
    "law practice": ["legal", "law", "legal services", "professional services"],
    "accounting": ["accounting", "finance", "audit", "professional services"],
    "venture capital & private equity": ["venture capital", "VC", "private equity", "investment", "finance"],
    "investment management": ["investment", "asset management", "finance", "wealth"],
    "security and investigations": ["security", "cybersecurity", "safety"],
    "computer & network security": ["cybersecurity", "security", "tech", "IT"],
    "information services": ["data", "analytics", "information", "tech"],
    "market research": ["market research", "analytics", "data", "insights"],
    "environmental services": ["environment", "sustainability", "green", "ecology"],
    "mining & metals": ["mining", "metals", "resources", "materials"],
    "chemicals": ["chemicals", "materials", "industrial", "science"],
    "textiles": ["textiles", "fashion", "apparel", "manufacturing"],
    "apparel & fashion": ["fashion", "apparel", "retail", "clothing"],
    "sporting goods": ["sports", "fitness", "retail", "consumer goods"],
    "health, wellness and fitness": ["wellness", "fitness", "health", "sports"],
}


def get_industry_tags(industry: str) -> list[str]:
    """Return synonym tags for a given industry label."""
    return INDUSTRY_TAXONOMY.get(industry.lower().strip(), [])


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
            logger.info(f"Connected to OpenSearch at {opensearch_host}:{opensearch_port}")
        except Exception as e:
            logger.error(f"Failed to connect to OpenSearch: {e}")
            raise
        
        self.index_name = "companies-new"
        
        # Initialize embedding model (768-dim model optimized for search)
        try:
            logger.info("Loading SentenceTransformer model...")
            self.embedding_model = SentenceTransformer('./msmarco-distilbert-base-tas-b')
            logger.info("Embedding model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
    
    def create_index(self):
        """Create the companies index with proper mappings"""
        try:
            # Check if index exists
            if self.client.indices.exists(self.index_name):
                logger.info(f"Index '{self.index_name}' already exists. Deleting and recreating...")
                self.client.indices.delete(index=self.index_name)
        except Exception as e:
            logger.error(f"Error checking/deleting existing index: {e}")
            raise
        
        index_body = {
            "settings": {
                "index": {
                    "number_of_shards": 2, 
                    "number_of_replicas": 0, # 0 during ingestion for speed; change to 1 after
                    "knn": True,
                    "refresh_interval": "60s" # Minimizes disk I/O during heavy load
                },
                "analysis": {
                    "normalizer": {
                        "lowercase_normalizer": {
                            "type": "custom",
                            "filter": ["lowercase"]
                        }
                    },
                    "analyzer": {
                        "edge_ngram_analyzer": {
                            "type": "custom",
                            "tokenizer": "edge_ngram_tokenizer",
                            "filter": ["lowercase"]
                        }
                    },
                    "tokenizer": {
                        "edge_ngram_tokenizer": {
                            "type": "edge_ngram",
                            "min_gram": 1,
                            "max_gram": 20,
                            "token_chars": ["letter", "digit"]
                        }
                    }
                }
            },
            "mappings": {
                "_source": {"excludes": ["vector_embedding"]},
                "properties": {
                    "company_id": {"type": "keyword"},
                    "name": {
                        "type": "text",
                        "fields": {
                            "keyword": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                            "edge_ngram": {"type": "text", "analyzer": "edge_ngram_analyzer"}
                        }
                    },
                    "domain": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                    "year_founded": {"type": "integer"},
                    "industry": {
                        "type": "text",
                        "fields": { "keyword": {"type": "keyword", "normalizer": "lowercase_normalizer"} }
                    },
                    "country": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                    "locality": {"type": "text"},
                    "indexed_at": {"type": "date"},
                    "current_employee_estimate": {"type": "long"},
                    "total_employee_estimate": {"type": "long"},
                    "size_range": {"type": "keyword"},
                    "city": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                    "state": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                    "industry_tags": {"type": "keyword", "normalizer": "lowercase_normalizer"},
                    "searchable_text": {"type": "text", "analyzer": "standard"},
                    "vector_embedding": {
                        "type": "knn_vector",
                        "dimension": 768,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "faiss",
                            "parameters": {
                                "m": 16,
                                "ef_construction": 128
                            }
                        }
                    }
                }
            }
        }
        
        # Create index
        try:
            self.client.indices.create(
                index=self.index_name,
                body=index_body
            )
            logger.info(f"Index '{self.index_name}' created successfully")
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise
    
    def data_generator(self, file_path: str, chunk_size: int = 10000, embedding_batch_size: int = 512):
        """Streaming generator to process 7M rows in chunks with batch embedding generation."""
        # Validate file exists
        if not Path(file_path).exists():
            logger.error(f"CSV file not found: {file_path}")
            raise FileNotFoundError(f"CSV file not found: {file_path}")
        
        logger.info(f"Starting to read CSV: {file_path}")
        
        try:
            reader = pd.read_csv(file_path, chunksize=chunk_size)
        except Exception as e:
            logger.error(f"Failed to open CSV file {file_path}: {e}")
            raise
        
        for chunk in reader:
            try:
                # --- CLEANING LOGIC ---
                chunk['year founded'] = pd.to_numeric(chunk['year founded'], errors='coerce').fillna(0).astype(int)
                chunk['industry'] = chunk['industry'].fillna("Unknown").str.strip()
                chunk['country'] = chunk['country'].fillna("Unknown").str.strip()
                chunk['locality'] = chunk['locality'].fillna('').str.strip()
            except Exception as e:
                logger.error(f"Error cleaning chunk: {e}")
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
                size = row.get('size range', '')
                parsed.append((industry, locality, city, state, tags, size))

            # Process embeddings in batches for efficiency
            for i in range(0, len(records), embedding_batch_size):
                batch_records = records[i:i + embedding_batch_size]
                batch_parsed = parsed[i:i + embedding_batch_size]
                logger.info(f"Processing batch {i // embedding_batch_size + 1} with {len(batch_records)} records...")

                # Build embedding texts using pre-computed values — no redundant calls
                texts = [
                    f"search_document: company: {row.get('name', '')}. "
                    f"industry: {industry} {' '.join(tags)}. "
                    f"size: {size}. "
                    f"location: {locality}, {state + ', ' if state else ''}{row.get('country', 'Unknown')}"
                    for row, (industry, locality, _, state, tags, size) in zip(batch_records, batch_parsed)
                ]
                try:
                    embeddings = self.embedding_model.encode(texts, batch_size=64, show_progress_bar=False).tolist()
                except Exception as e:
                    logger.error(f"Failed to generate batch embeddings: {e}")
                    embeddings = [[0.0] * 768 for _ in batch_records]

                for row, (industry, locality, city, state, tags, size), vector_embedding in zip(batch_records, batch_parsed, embeddings):
                    # Safe field extraction with defaults
                    company_id = str(row.get('Unnamed: 0', ''))
                    year_founded = int(row.get('year founded', 0))
                    current_employees = int(row.get('current employee estimate', 0))
                    total_employees = int(row.get('total employee estimate', 0))

                    searchable_text = " ".join(filter(None, [
                        row.get('name', ''), industry, " ".join(tags),
                        locality, city, state, row.get('country', ''), size
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
                            "locality": locality,
                            "city": city,
                            "state": state,
                            "searchable_text": searchable_text,
                            "current_employee_estimate": current_employees,
                            "total_employee_estimate": total_employees,
                            "vector_embedding": vector_embedding,
                            "indexed_at": indexed_at
                        }
                    }

    def ingest_from_csv(self, csv_path: str = None, chunk_size: int = 50000, bulk_chunk_size: int = 500):
        """Start ingestion using parallel bulk API for CSV data.
        
        chunk_size: rows per pandas read chunk (controls RAM usage).
        bulk_chunk_size: documents per OpenSearch bulk request. Keep low (~500)
                         because each doc carries a 768-float vector (~3 KB),
                         so 500 docs ≈ 1.5 MB per request — well within limits.
        """
        if not csv_path:
            raise ValueError("csv_path is required for ingestion")
        
        try:
            logger.info("Starting ingestion...")
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
                        logger.info(f"Indexed {success_count} documents...")
                else:
                    failed_count += 1
                    logger.error(f"Failure: {info}")
            logger.info(f"Ingestion complete. Total indexed: {success_count}, Failed: {failed_count}")
        except Exception as e:
            logger.error(f"CSV ingestion failed: {e}")
            raise
        finally:
            self._finalize_index()

    def _finalize_index(self):
        """Reset ingestion-time settings and merge segments for optimal knn performance."""
        try:
            logger.info("Resetting index settings post-ingestion...")
            self.client.indices.put_settings(
                index=self.index_name,
                body={"index": {"refresh_interval": "1s", "number_of_replicas": 1}}
            )
            self.client.indices.refresh(index=self.index_name)
            # Force-merge to reduce HNSW segment count — critical for knn recall and query speed.
            # max_num_segments=5 balances merge time vs. query performance.
            logger.info("Running forcemerge (this may take several minutes for large indices)...")
            self.client.indices.forcemerge(index=self.index_name, max_num_segments=5)
            logger.info("Index finalized.")
        except Exception as e:
            logger.warning(f"Post-ingestion finalization failed (non-fatal): {e}")


    
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
                size = row.get("size_range", "")
                parsed.append((industry, locality, city, state, tags, size))

            texts = [
                f"search_document: company: {row.get('name', '')}. "
                f"industry: {industry} {' '.join(tags)}. "
                f"size: {size}. "
                f"location: {locality}, {state + ', ' if state else ''}{row.get('country', 'Unknown')}"
                for row, (industry, locality, _, state, tags, size) in zip(batch_records, parsed)
            ]
            try:
                embeddings = self.embedding_model.encode(texts, batch_size=64, show_progress_bar=False).tolist()
            except Exception as e:
                logger.error(f"Failed to generate batch embeddings: {e}")
                embeddings = [[0.0] * 768 for _ in batch_records]

            for idx, (row, (industry, locality, city, state, tags, size), vector_embedding) in enumerate(
                zip(batch_records, parsed, embeddings)
            ):
                searchable_text = " ".join(filter(None, [
                    row.get("name", ""), industry, " ".join(tags),
                    locality, city, state, row.get("country", ""), size
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
        logger.info(f"Starting ingestion of {total_records} records...")
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
                    logger.info(f"Indexed {success_count}/{total_records} documents...")
            else:
                failed_count += 1
                logger.error(f"Failure: {info}")
        logger.info(f"Ingestion complete. Total indexed: {success_count}, Failed: {failed_count}")
    

    def load_sample_data(self, sample_size=10000) -> pd.DataFrame:
        """Load sample data (create synthetic data for demo)"""
        logger.info(f"Generating sample data with {sample_size} companies...")
        
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
            logger.info(f"Loading sample data ({sample_size} companies)...")
            df = self.load_sample_data(sample_size)
            self.start_ingestion_from_dataframe(df, batch_size=1000)
        except Exception as e:
            logger.error(f"Sample data ingestion failed: {e}")
            raise

    def get_index_stats(self):
        """Get index statistics"""
        try:
            stats = self.client.indices.stats(index=self.index_name)
            doc_count = stats["indices"][self.index_name]["primaries"]["docs"]["count"]
            size_bytes = stats["indices"][self.index_name]["primaries"]["store"]["size_in_bytes"]
            
            logger.info(f"Index stats: {doc_count} documents, {size_bytes / 1024 / 1024:.2f} MB")
            return {"documents": doc_count, "size_mb": size_bytes / 1024 / 1024}
            
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
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
            logger.error(f"Failed to initialize pipeline: {e}")
            sys.exit(1)
        
        # Create or reset index
        try:
            if args.reset:
                logger.info("Creating index...")
                pipeline.create_index()
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            sys.exit(1)
        
        # Ingest data
        try:
            if args.csv:
                logger.info(f"Ingesting from CSV: {args.csv}")
                pipeline.ingest_from_csv(csv_path=args.csv)
            else:
                logger.info(f"Ingesting sample data ({args.sample} records)")
                pipeline.ingest_sample_data(args.sample)
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
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
