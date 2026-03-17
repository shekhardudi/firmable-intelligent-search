# Firmable — Intelligent Company Search

An AI-powered company search platform that automatically classifies queries and
routes them through the optimal search strategy: lexical (BM25), semantic
(kNN vector), or agentic (LLM with live web search). Built for a dataset of
**7 million companies** .

---

## How It Works

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Regex Pre-Classifier  (zero-cost, deterministic)   │
│  Catches obvious patterns: quoted names, domains,   │
│  company suffixes (Inc, Ltd, GmbH, …)               │
└──────────────┬───────────────────────┬──────────────┘
               │ matched → REGULAR     │ not matched
               ▼                       ▼
          BM25 Search       ┌────────────────────────┐
                            │  LLM Intent Classifier │
                            │  (GPT-4o-mini via      │
                            │   Instructor)          │
                            └───┬──────────┬─────────┘
                                │          │
              ┌─────────────────┘          └──────────────────┐
              ▼                                               ▼
     Semantic Search                                  Agentic Search
     (kNN + BM25 hybrid                              (LangChain agent
      via Reciprocal Rank                              + Tavily web search
      Fusion)                                          + LinkedIn enrichment)
              │                                               │
              └──────────────┬────────────────────────────────┘
                             ▼
                   Normalise, paginate, cache
                             │
                             ▼
                   JSON response + headers
                   (X-Trace-ID, X-Search-Logic,
                    X-Confidence, X-Response-Time-MS)
```

---

## Features

- **Three-tier search** — Regular (BM25), Semantic (384-dim kNN + RRF), Agentic (LLM + web tools)
- **Automatic intent classification** — regex fast path + GPT-4o-mini with structured output via [Instructor](https://github.com/jxnl/instructor)
- **Filter extraction** — classifier extracts country, industry, size, year range from natural language
- **User-applied filters** — UI filters merge with classifier filters (user selection wins on conflict)
- **PII guard** — blocks queries containing emails, phone numbers, card numbers, SSNs
- **Circuit breaker** — graceful degradation when OpenAI or OpenSearch is unhealthy
- **Caching** — Redis with 10 s TTL for query results and classifier responses; in-memory fallback
- **Full observability** — OpenTelemetry traces/metrics/logs — zero code change between local and AWS
- **Faceted search** — basic search endpoint returns industry, country, size, year aggregations

---

## Tech Stack

| Layer             | Technology                                                         |
|-------------------|--------------------------------------------------------------------|
| Frontend          | React 18, TypeScript, Vite                                         |
| Backend           | FastAPI, Python 3.12, Uvicorn                                      |
| Search Engine     | OpenSearch 2.x (BM25 + kNN HNSW, fp16 scalar quantisation, FAISS) |
| Embeddings        | SentenceTransformer `all-MiniLM-L6-v2` (384 dimensions)           |
| LLM (classifier)  | OpenAI GPT-4o-mini via Instructor (structured Pydantic output)    |
| LLM (agentic)    | OpenAI GPT-4o via LangChain tool-calling agent                     |
| Web Search        | Tavily API (used by agentic strategy)                              |
| Cache             | Redis 7 Alpine — 10 s TTL                                         |
| Observability     | OpenTelemetry → Jaeger + Prometheus + Grafana (local)              |
|                   | OpenTelemetry → ADOT sidecar → X-Ray + CloudWatch (AWS)           |
| Infrastructure    | Docker Compose (local) · Terraform + ECS Fargate (AWS)             |

---


### Prerequisites

- Docker & Docker Compose
- An OpenAI API key (`OPENAI_API_KEY`)
- Tavily API key (`TAVILY_API_KEY`)for agentic web search

### Run with Docker Compose

```bash
git clone https://github.com/shekhardudi/firmable-intelligent-search.git
cd firmable-intelligent-search

# Configure environment
cp .env.example backend/.env
cp .env.example data-pipeline/.env
# Edit both .env files — set OPENAI_API_KEY (and optionally TAVILY_API_KEY)

# Start everything (OpenSearch, Redis, Backend, Frontend, Observability)
docker compose up -d
```

Docker Compose spins up all 9 services automatically:

| Service               | URL                          |
|-----------------------|------------------------------|
| **Frontend (UI)**     | http://localhost:5173         |
| **Backend (API)**     | http://localhost:8000         |
| **Swagger Docs**      | http://localhost:8000/docs    |
| **OpenSearch**        | https://localhost:9200        |
| **OpenSearch Dashboards** | http://localhost:5601     |
| **Jaeger (Traces)**   | http://localhost:16686        |
| **Prometheus**        | http://localhost:9090         |
| **Grafana**           | http://localhost:3001 (admin/admin) |

### Ingest Data

After services are up, ingest the company dataset:
Download the dataset from here - [7 million company dataset](https://www.kaggle.com/datasets/peopledatalabssf/free-7-million-company-dataset/code/data)
```bash
cd data-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python data_ingestion_pipeline.py
```

Open **http://localhost:5173** and start searching.

---

## Project Structure

```
firmable-intelligent-search/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py              # All API endpoints
│   │   ├── models/
│   │   │   └── search.py              # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── orchestrator.py        # Query routing (regex → LLM → strategy)
│   │   │   ├── intent_classifier.py   # GPT-4o-mini intent classification
│   │   │   ├── search_strategies.py   # Regular / Semantic / Agentic strategies
│   │   │   ├── agent_service.py       # LangChain agentic agent + tools
│   │   │   ├── tool_service.py        # Agentic tool definitions
│   │   │   ├── embedding_service.py   # SentenceTransformer embeddings
│   │   │   ├── opensearch_service.py  # OpenSearch client
│   │   │   ├── cache_service.py       # Redis cache (graceful fallback)
│   │   │   ├── circuit_breaker.py     # Circuit breaker (CLOSED/OPEN/HALF_OPEN)
│   │   │   ├── pii_service.py         # PII detection
│   │   │   ├── search_service.py      # Basic/faceted search
│   │   │   └── prompt_loader.py       # Load prompt templates from disk
│   │   ├── prompts/
│   │   │   ├── intent_classifier_system.txt
│   │   │   ├── agent_system.txt
│   │   │   ├── agent_extraction.txt
│   │   │   └── agent_linkedin_extraction.txt
│   │   ├── observability/
│   │   │   ├── logging.py             # structlog + JSON
│   │   │   ├── tracing.py             # OTel tracing
│   │   │   ├── metrics.py             # OTel metrics
│   │   │   └── events.py              # Custom event logging
│   │   ├── utils/
│   │   │   └── cache.py               # BoundedDict LRU
│   │   ├── config.py                  # Pydantic Settings (env vars + YAML)
│   │   └── main.py                    # FastAPI app, lifespan, middleware
│   ├── tests/                         # pytest suite
│   ├── search_config.yaml             # Search tuning (RRF, boosts, agentic)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # Main component (search + AI thinking panel)
│   │   ├── App.css
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── SearchBar.tsx
│   │   │   ├── FilterPanel.tsx
│   │   │   └── ResultsList.tsx
│   │   └── services/
│   │       └── api.ts                 # Axios client + TypeScript interfaces
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── data-pipeline/
│   ├── data_ingestion_pipeline.py     # ETL: CSV → clean → embed → bulk index
│   ├── ingest_config.yaml             # Chunk sizes, model, dimensions
│   ├── index_mapping.json             # OpenSearch mapping (384-dim kNN)
│   ├── companies_sorted.csv           # 7 M company dataset
│   ├── country_taxonomy.json
│   ├── industry_taxonomy.json
│   ├── observability.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
├── infrastructure/
│   ├── grafana/                       # Dashboard + datasource provisioning
│   ├── otel-collector/                # Collector configs (local + AWS)
│   ├── prometheus/                    # Scrape config
│   └── terraform/demo/               # AWS ECS Fargate infra (Terraform)
├── docs/
│   ├── ARCHITECTURE_LOCAL.md
│   ├── ARCHITECTURE_DEMO.md
│   └── ARCHITECTURE_PROD.md
├── docker-compose.yml                 # 9 services (full local dev stack)
├── .env.example                       # Template for backend/.env
├── QUICKSTART.md
├── SCALING.md
└── README.md
```

---

## API

All search traffic flows through a single intelligent endpoint that classifies
and routes automatically.

### `POST /api/search/intelligent`
**Mock Examples**

**Request:**

```json
{
  "query": "sustainable energy companies in Germany with 50-200 employees",
  "limit": 20,
  "page": 1,
  "include_reasoning": true,
  "filters": {
    "country": "Germany",
    "size_range": "51-200"
  }
}
```

**Response:**

```json
{
  "query": "sustainable energy companies in Germany with 50-200 employees",
  "results": [
    {
      "id": "abc123",
      "name": "SolarEdge Technologies",
      "domain": "solaredge.com",
      "industry": "Renewables & Environment",
      "country": "Germany",
      "locality": "Munich, Bavaria",
      "relevance_score": 0.91,
      "search_method": "semantic",
      "ranking_source": "knn",
      "matching_reason": "Semantic match on sustainable energy + location filter Germany",
      "year_founded": 2006,
      "size_range": "51-200",
      "current_employee_estimate": 150
    }
  ],
  "metadata": {
    "trace_id": "a1b2c3d4e5f6",
    "query_classification": {
      "category": "semantic",
      "confidence": 0.92,
      "reasoning": "Natural language query about a concept with filters"
    },
    "search_execution": {
      "strategy": "SemanticSearchStrategy",
      "opensearch_took_ms": 85,
      "score_range": { "min": 0.72, "max": 0.91 }
    },
    "total_results": 20,
    "response_time_ms": 245,
    "page": 1,
    "limit": 20
  },
  "status": "success"
}
```

**Response Headers:**

| Header               | Example                | Description                         |
|----------------------|------------------------|-------------------------------------|
| `X-Trace-ID`        | `a1b2c3d4e5f6`         | Request trace ID (Jaeger / X-Ray)   |
| `X-Search-Logic`    | `Semantic-Hybrid-RRF`  | Search method used                  |
| `X-Confidence`      | `0.92`                 | Classifier confidence               |
| `X-Response-Time-MS`| `245`                  | Total response time in ms           |
| `X-Total-Results`   | `20`                   | Result count                        |



### `GET /api/search/health`

```json
{ "status": "healthy", "service": "search-orchestrator", "version": "2.0.0" }
```

### Interactive Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Search Strategies

### Regular (BM25)

Triggered for exact company lookups — quoted names, domain lookups, names with
company suffixes (Inc, Ltd, GmbH, Pty Ltd, etc.).

- OpenSearch BM25 with configurable field boosts (`name: 2.0`, `domain: 2.0`)
- Phrase boost on exact name matches (`name_phrase_boost: 10.0`)
- Popularity boost: `score × (1 + factor × log(1 + employee_count))`

### Semantic (kNN + RRF)

Triggered for conceptual, natural-language queries ("AI startups in Europe").

- Encodes query with `all-MiniLM-L6-v2` (384 dimensions)
- Searches the `vector_embedding` field (HNSW, FAISS engine, fp16 scalar quantisation)
- Configurable mode: pure `knn` or hybrid `rrf` (Reciprocal Rank Fusion merging BM25 + kNN)
- Classifier-extracted filters (country, industry, year, size) applied as OpenSearch post-filters

### Agentic (LLM + Tools)

Triggered for time-sensitive or external-data queries ("companies that raised
Series B funding recently").

- LangChain tool-calling agent powered by GPT-4o
- Tools: `web_search` (Tavily), `lookup_names` (OpenSearch), `linkedin_profile`, `submit_results`
- Extracts company names from web results, resolves against OpenSearch index
- Latency: ~2–8 s

---

## Data Pipeline

The ingestion pipeline (`data-pipeline/data_ingestion_pipeline.py`) processes
company CSV data into OpenSearch with vector embeddings:

1. **Load** — Read CSV (supports S3 URI or local path)
2. **Clean** — Normalise fields, deduplicate
3. **Enrich** — Generate `searchable_text`, map industry/country via taxonomy JSONs
4. **Embed** — Batch-encode `searchable_text` with SentenceTransformer
5. **Index** — Bulk-index into OpenSearch with kNN mapping

```bash
cd data-pipeline
python data_ingestion_pipeline.py
```

The OpenSearch index mapping (`data-pipeline/index_mapping.json`) defines:
- BM25 text fields with edge-ngram for autocomplete
- `knn_vector` field: 384 dimensions, HNSW (m=16, ef_construction=128), fp16 SQ, FAISS engine
- Keyword fields with lowercase normaliser for exact-match filters

---

## Observability

### Local (Docker Compose)

| Service        | Port  | Purpose                        |
|----------------|-------|--------------------------------|
| Jaeger         | 16686 | Distributed traces             |
| Prometheus     | 9090  | Metrics scraping               |
| Grafana        | 3001  | Dashboards (admin / admin)     |
| OTel Collector | 4317  | OTLP gRPC receiver             |

Backend → OTLP/gRPC → OTel Collector → Jaeger (traces) + Prometheus (metrics).

### AWS (ECS Fargate)

Same `OTLP_ENDPOINT=http://localhost:4317` — the ADOT sidecar runs in the same
task network namespace. Traces → X-Ray, metrics → CloudWatch EMF, logs →
CloudWatch Logs via `awslogs` driver. No code changes between environments.

---

## Docker Compose Services

| # | Service               | Image                                    | Port(s)          |
|---|----------------------|------------------------------------------|------------------|
| 1 | OpenSearch            | opensearchproject/opensearch:latest       | 9200, 9600       |
| 2 | OpenSearch Dashboards | opensearchproject/opensearch-dashboards   | 5601             |
| 3 | Redis                 | redis:7-alpine                            | 6379             |
| 4 | Backend (FastAPI)     | ./backend Dockerfile                     | 8000             |
| 5 | Frontend (Vite)       | ./frontend Dockerfile                    | 5173             |
| 6 | OTel Collector        | otel/opentelemetry-collector-contrib      | 4317, 4318, 8888 |
| 7 | Prometheus            | prom/prometheus:v2.52.0                   | 9090             |
| 8 | Jaeger                | jaegertracing/all-in-one:1.58             | 16686            |
| 9 | Grafana               | grafana/grafana:10.4.0                    | 3001             |

---

## Deployment

| Target     | Stack                    | Guide                                                        |
|------------|--------------------------|--------------------------------------------------------------|
| AWS Demo   | Terraform + ECS Fargate  | [docs/ARCHITECTURE_DEMO.md](docs/ARCHITECTURE_DEMO.md)       |
| AWS Prod   | Terraform + ECS (hardened)| [docs/ARCHITECTURE_PROD.md](docs/ARCHITECTURE_PROD.md)       |

---

## Configuration

Search behaviour is tunable via `backend/search_config.yaml`:

```yaml
rrf:
  k: 60
  knn_k: 100
  fetch_multiplier: 4

semantic:
  # Search mode for the semantic strategy.
  #   "knn" — pure k-NN vector search only (faster, no BM25 leg)
  #   "rrf" — hybrid Reciprocal Rank Fusion merging BM25 + k-NN (better precision)
  mode: "knn"

field_boosts:
  defaults:                 # SemanticSearchStrategy._DEFAULT_FIELD_BOOSTS
    name: 2.0
    domain: 1.0
    searchable_text: 1.0
    industry: 1.0
    locality: 1.0
  bm25_regular:             # RegularSearchStrategy _build_bm25_query field weights
    name: 2.0
    domain: 2.0
    searchable_text: 1.0
    industry: 1.0
    locality: 1.0
    name_phrase_boost: 10.0
    # Popularity boost: multiplies BM25 score by (1 + factor * log(1 + employee_count)).
    # Set to 0 to disable. Typical range: 0.1 – 0.5
    popularity_boost_factor: 2.0

cache:
  embedding_maxsize: 512
  classifier_maxsize: 256

embedding:
  # Sentence-transformers model name or local path.
  # Override with EMBEDDING_MODEL env var or by editing here.
  model: all-MiniLM-L6-v2
  # Vector dimension produced by the model.
  dimension: 384
  # Asymmetric retrieval prefix added to queries (not documents).
  # Set to empty string "" for symmetric models (e.g. all-MiniLM).
  query_prefix: "Represent this sentence for searching relevant passages: "

agentic:
  # LLM model used by the tool-calling agent.
  # Any OpenAI chat model that supports tool/function calling:
  #   gpt-4o-mini  (fast, cheap, good for most queries)
  #   gpt-4o       (best reasoning, use for complex multi-step queries)
  #   gpt-4-turbo  (balanced)
  model: "gpt-4o"
  # Maximum agent iterations before giving up
  agent_max_iterations: 5
  # Maximum company names the LLM may return per extraction call
  max_company_names: 20
  # Token budget for the LLM event-extraction call
  llm_max_tokens: 1200
  # OpenSearch candidates to fetch per resolved company name
  resolve_per_name: 5
  # Minimum OpenSearch score to accept a resolved company (avoids false matches)
  min_resolve_score: 0.5
  # Tavily web-search max results (only used when TAVILY_API_KEY is set)
  tavily_max_results: 10
  # Tavily HTTP request timeout in seconds
  tavily_timeout_s: 8

```

Environment variables are documented in [.env.example](.env.example).

---

## Testing

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v --cov=app
```

Tests cover: orchestrator routing, intent classification, search strategies,
caching, configuration, embedding service, and API routes.

---

## Architecture Docs

- [Local Architecture](docs/ARCHITECTURE_LOCAL.md) — Docker Compose stack and port map
- [Demo Architecture](docs/ARCHITECTURE_DEMO.md) — Single-AZ AWS (Terraform + ECS)
- [Production Architecture](docs/ARCHITECTURE_PROD.md) — Multi-AZ hardened AWS deployment

---

## License

MIT
