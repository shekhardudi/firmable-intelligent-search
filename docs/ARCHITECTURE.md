# System Architecture - Deep Dive

## Table of Contents
1. [System Overview](#system-overview)
2. [Component Details](#component-details)
3. [Data Flow](#data-flow)
4. [Query Execution Paths](#query-execution-paths)
5. [Deployment Architecture](#deployment-architecture)

---

## System Overview

### High-Level Architecture Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                      Client Browser/App                        │
└─────────────────────────┬──────────────────────────────────────┘
                          │ HTTPS
        ┌─────────────────┴──────────────────┐
        │                                     │
┌───────▼──────────────┐           ┌─────────▼───────────┐
│  Frontend (React)    │           │  API Gateway / LB   │
│  - SearchBar         │           │  - Route requests   │
│  - Filters           │           │  - Load balance     │
│  - Results Display   │           │  - Rate limit       │
└───────┬──────────────┘           └─────────┬───────────┘
        │                                     │
        └──────────────────┬──────────────────┘
                           │
                    ┌──────▼────────┐
                    │  GET /api/... │
                    │  POST /api/.. │
                    └──────┬────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
    ┌───▼─────────────────────────┐  ┌──────▼──────────────┐
    │    FastAPI Backend Service  │  │  Request Logger     │
    │                             │  │  (Structured JSON)  │
    │  ┌─────────────────────┐    │  └─────────────────────┘
    │  │ /api/search/*       │    │
    │  │ - basic search      │    │
    │  │ - intelligent       │    │
    │  │ - semantic          │    │
    │  │ - agentic           │    │
    │  └─────────────────────┘    │
    │                             │
    │  ┌──────────────────────┐   │
    │  │ Request Validator    │   │
    │  │ (Pydantic Models)    │   │
    │  └──────────────────────┘   │
    │                             │
    │  ┌──────────────────────┐   │
    │  │Middleware Stack:     │   │
    │  │ - Auth (if enabled)  │   │
    │  │ - CORS               │   │
    │  │ - Rate Limiting      │   │
    │  │ - Timing             │   │
    │  └──────────────────────┘   │
    └───┬─────────────────────────┘
        │
    ┌───┴────────────────────────────────────────────┐
    │                                                │
    │  Service Layer (Business Logic)                │
    │                                                │
    │  ┌──────────────┐  ┌──────────────┐           │
    │  │SearchService ├──┤ QueryClassif+│           │
    │  │              │  │   -ier (LLM) │           │
    │  └──────┬───────┘  └──────────────┘           │
    │         │                                     │
    │  ┌──────▼──────────────┐                     │
    │  │FilterProcessor      │  ┌────────────────┐ │
    │  │- Apply constraints  │  │SemanticSearch  │ │
    │  │- Build queries      │  │- Vector ops    │ │
    │  └──────┬──────────────┘  │- Similarity    │ │
    │         │                  └────────────────┘ │
    │  ┌──────▼──────────────┐                     │
    │  │ResultProcessor      │  ┌────────────────┐ │
    │  │- Format results     │  │LLMService      │ │
    │  │- Add explanations   │  │- Query models  │ │
    │  │- Pagination        │  │- Embeddings    │ │
    │  └─────────────────────┘  └────────────────┘ │
    │                                                │
    └──────────────────┬─────────────────────────────┘
                       │
         ┌─────────────┼────────────────────┐
         │             │                    │
    ┌────▼──────┐ ┌───▼────────┐ ┌────────▼──┐
    │ OpenSearch │ │ PostgreSQL │ │   Redis   │
    │ (Primary)  │ │ (User DB)  │ │  (Cache)  │
    │            │ │            │ │           │
    │ - Companies│ │- User tags │ │- Results  │
    │   index    │ │- User prefs│ │- Sessions │
    │ - Vector   │ │- Search    │ │- LLM call │
    │   embeddin │ │  history   │ │  cache    │
    │ - BM25     │ │            │ │           │
    │   scoring  │ │            │ │           │
    └────────────┘ └────────────┘ └───────────┘
         │             │                │
         └─────────────┼────────────────┘
                       │
    ┌──────────────────┴──────────────────┐
    │                                     │
    │  External Services (Optional)       │
    │                                     │
┌───┴──────────────┐  ┌─────────────────┴────┐
│  OpenAI API      │  │  Anthropic Claude    │
│  - Embeddings    │  │  - Agentic reasoning │
│  - Classification│  │  - Complex queries   │
│  - Explanations  │  │  - Multi-step tasks  │
└──────────────────┘  └──────────────────────┘
```

---

## Component Details

### 1. FastAPI Backend Service

**Framework Choose Rationale**:
- Async/await for handling 60+ concurrent requests
- Built-in OpenAPI docs
- Pydantic validation
- Middleware support
- Type hints for reliability

**Main Components**:

```python
# Entry point
app/main.py
├── Lifespan management
├── Middleware stack
├── Route registration
└── Error handlers

# API Routes
app/api/routes.py
├── /api/search/companies      # Basic structured search
├── /api/search/intelligent    # AI-powered search
├── /api/search/semantic       # Vector similarity
├── /api/search/agentic        # Multi-step reasoning
├── /api/search/health         # Health check
└── /api/search/autocomplete   # Suggestions
```

### 2. Search Service (Core Business Logic)

**SearchService** - Orchestrates all search operations:

```python
SearchService
├── basic_search()           # Structured queries
│   ├── _build_filter_query()
│   ├── _build_aggregations()
│   ├── _process_search_results()
│   └── _process_facets()
│
├── intelligent_search()      # LLM + structured
│   ├── _classify_and_understand_query()
│   ├── _build_search_request_from_understanding()
│   └── _enhance_results_with_explanations()
│
└── semantic_search()         # Vector-based
    ├── Generate embeddings
    ├── Vector search in OpenSearch
    └── Score and rank results
```

**Decision Tree for Query Routing**:

```
Query Input
    ↓
Query Classification
    ├─ Simple text → Basic search only
    ├─ Filters present → Structured search  
    ├─ Entity references → Semantic + structured
    └─ Complex → LLM enhancement
    ↓
Feature Flag Checks
    ├─ Enable LLM? → Run classifier
    ├─ Enable semantic? → Generate embeddings
    └─ Enable caching? → Check Redis first
    ↓
Execute Search Pipeline
    └─ Return results
```

### 3. OpenSearch Integration

**Index Structure**:

```
companies index
├── name                      # Text field
│   ├─ analyzed for search
│   ├─ keyword for exact
│   └─ edge_ngram for autocomplete
│
├── industry                  # Keyword + text
├── country                   # Keyword
├── locality                  # Text + keyword
├── year_founded             # Numeric (range)
├── size_range               # Keyword
│
├── vector_embedding         # Dense vector (8192)
│   └─ HNSW for approximation
│
└── metadata
    ├─ linkedin_url
    ├─ employee_estimate
    └─ indexed_at
```

**Query Pipeline**:

```
User Input
    ↓
Parse filters/text
    ↓
Build bool query
    ├─ must: text search
    ├─ filter: categorical filters
    └─ range: numeric filters
    ↓
Execute with aggregations
    ├─ topN terms aggregation
    └─ range aggregation
    ↓
Score & rank
    ├─ BM25 (text relevance)
    ├─ Boost (name > domain > industry)
    └─ Custom scoring (optional)
    ↓
Format & return
```

### 4. LLM Service (OpenAI Integration)

**Capabilities**:

| Operation | Model | Tokens | Latency | Cost |
|-----------|-------|--------|---------|------|
| Classify query | GPT-4 Turbo | ~200 | 500-1000ms | $0.0002 |
| Extract entities | GPT-4 Turbo | ~150 | 400-800ms | $0.00015 |
| Generate embedding | text-embedding-3-large | ~10 | 50-100ms | $0.000001 |
| Semantic explanation | GPT-4 Turbo | ~100 | 300-600ms | $0.0001 |

**Caching Strategy for LLM Calls**:

```
LLM Request
    ↓
Hash(query, operation)
    ↓
Check Redis
    ├─ HIT: Return cached result
    └─ MISS: 
        ↓
        Call OpenAI API
        ↓
        Validate response
        ↓
        Cache 1 hour
        ↓
        Return result
```

---

## Data Flow Examples

### Example 1: Basic Search Flow

```
User Input: "tech companies in California"

Request
    ↓
[Route Handler]
    ↓
Parse filters:
{
  "q": "tech companies",
  "country": "United States", 
  "locality": "California"
}
    ↓
[SearchService.basic_search()]
    ↓
Build OpenSearch query:
{
  "bool": {
    "must": [
      {
        "multi_match": {
          "query": "tech companies",
          "fields": ["name^3", "domain", ...]
        }
      }
    ],
    "filter": [
      {"term": {"country.keyword": "United States"}},
      {"match": {"locality": "California"}}
    ]
  }
}
    ↓
[OpenSearch API]
    ↓
Get results (51 matches, 247ms)
    ↓
Process results:
- Extract company data
- Normalize scores (0-1)
- Build facets
- Pagination
    ↓
Return Response
{
  "total": 2847,
  "results": [...],
  "facets": {...},
  "search_time_ms": 247
}
```

### Example 2: Intelligent Search Flow

```
User Input: "Find tech startups in California founded in the last 5 years"

Request
    ↓
[Route Handler]
    ↓
[LLM Classification]
{
  "intent": "filtered_company_search",
  "entities": {
    "industries": ["technology", "software"],
    "locations": ["California", "United States"],
    "year_range": [2021, 2026],
    "confidence": 0.94
  }
}
    ↓
Convert to structured request:
{
  "q": "tech startup",
  "industry": ["Information Technology"],
  "country": "United States",
  "locality": "California",
  "year_from": 2021,
  "year_to": 2026,
  "limit": 50
}
    ↓
[SearchService.basic_search()]
    ↓
Execute OpenSearch query with extracted filters
(47 matches, 150ms)
    ↓
Enhance results:
For top 10 results, add semantic explanations:
    ↓
[LLM Generate Explanation]
"Matched as tech startup: YC-backed AI company founded 2023"
    ↓
Return IntelligentSearchResponse
{
  "query_understanding": {...},
  "results": [
    {
      "company": {...},
      "matching_reason": "Matched as...",
      "relevance_score": 0.89
    }
  ],
  "search_time_ms": 1847  # Includes LLM calls
}
```

### Example 3: Semantic Search Flow

```
User Input: "companies like Stripe"

Request
    ↓
[SemanticSearchRequest Handler]
    ↓
[LLM: Generate Embedding]
Query: "companies like Stripe"
    ↓
Call OpenAI text-embedding-3-large
    ↓
Embedding: [0.234, -0.156, ..., 0.089]  # 8192 dims
    ↓
[OpenSearch KNN Search]
{
  "knn": {
    "vector_embedding": {
      "vector": [0.234, -0.156, ...],
      "k": 20
    }
  }
}
    ↓
OpenSearch HNSW Algorithm:
- Start from random node
- Explore neighbors
- Climb to most similar
- Return top 20
    ↓
Results (18 matches, 750ms):
[
  {
    "company": "Square (now Block)",
    "similarity_score": 0.89
  },
  {
    "company": "Adyen",
    "similarity_score": 0.87
  },
  ...
]
    ↓
Format and return
```

---

## Query Execution Paths

### Fast Path: Keyword Search (50% of queries)
```
Request → InputValidation → CacheCheck (HIT/MISS)
    ↓
If HIT: Return immediately (5ms)
If MISS:
    ↓
OpenSearch BM25 search → Format results → Cache → Return (50ms)
```

### Medium Path: Filtered Search (30% of queries)
```
Request → InputValidation → CacheCheck
    ↓
If MISS:
    ↓
Build complex bool query with multiple filters
    ↓
OpenSearch execution with aggregations → Format → Cache (100ms)
```

### Slow Path: Intelligent Search (15% of queries)
```
Request → LLM Classification (500-1000ms)
    ↓
Convert to filters
    ↓
OpenSearch search (100ms)
    ↓
LLM Explanations for top 10 (500-1000ms)
    ↓
Format and return (~2000ms total)
```

### Complex Path: Agentic Search (5% of queries)
```
Request → LLM Reasoning Step 1 (500ms)
    ↓
Execute search/fetch data (100ms)
    ↓
Analyze results, determine next step
    ↓
Repeat 2-5 steps
    ↓
Aggregate findings and return (2-5s total)
```

---

## Deployment Architecture

### Development Environment (Docker Compose)

```
Single host running:
├─ OpenSearch container (1 node, 512MB heap)
├─ PostgreSQL container
├─ Redis container
├─ FastAPI container (uvicorn)
├─ React dev server (npm dev)
└─ Shared network (search-network)

Resource usage: ~4GB RAM, suitable for local dev
```

### Production Environment (Kubernetes)

```
Kubernetes Cluster
├─ Namespace: default
├─ Pod replicas: 12-15 (configurable)
│
├─ Deployments
│  ├─ backend (12-15 pods)
│  ├─ frontend (2-3 pods)
│  └─ data-pipeline (1 pod)
│
├─ StatefulSets
│  ├─ OpenSearch (6+ data nodes)
│  ├─ PostgreSQL (1 primary + 3 replicas)
│  └─ Redis (1 instance or cluster)
│
├─ Services
│  ├─ backend-service (ClusterIP)
│  ├─ opensearch-service (ClusterIP)
│  ├─ postgres-service (ClusterIP)
│  ├─ redis-service (ClusterIP)
│  └─ frontend-service (LoadBalancer)
│
├─ Ingress
│  └─ Route /api/* → backend service
│  └─ Route /* → frontend service
│
├─ ConfigMaps
│  └─ app-config (settings, env variables)
│
├─ Secrets
│  └─ api-keys (OpenAI, etc.)
│
├─ PersistentVolumes
│  ├─ opensearch-data
│  ├─ postgres-data
│  └─ redis-data
│
└─ Autoscaling
   └─ HPA (Horizontal Pod Autoscaler)
      - Target: 70% CPU, 80% memory
      - Min: 5 pods, Max: 50 pods
```

---

## Security Architecture

### Data Protection
- **In Transit**: HTTPS/TLS 1.3
- **At Rest**: OpenSearch encryption, DB encryption
- **Keys**: Rotated quarterly, stored in secure vaults

### Access Control
- **API**: Rate limiting, API key validation
- **Database**: User isolation via row-level security
- **Infrastructure**: VPC, security groups, firewalls

### Audit & Compliance
- All API calls logged with request/response metadata
- Search queries encrypted in logs
- 90-day retention for audit trails

---

## Monitoring & Observability

### Metrics Collected
```
Application Layer:
  - Request latency (p50, p95, p99)
  - Request count by endpoint
  - Error rates
  - Cache hit/miss ratios

Search Layer:
  - OpenSearch query latency
  - Index size and growth
  - Shard distribution
  - Query throughput

AI/LLM Layer:
  - API call latency
  - Token consumption
  - Error rates and types
  - Cost tracking

Infrastructure:
  - CPU/Memory utilization
  - Disk usage
  - Network I/O
  - Pod restart counts
```

### Alerting

```
Critical Alerts:
- API unavailable (500 errors > 5%)
- OpenSearch unavailable
- Database unavailable
- High error rate (> 1%)

Warning Alerts:
- High latency (p99 > 500ms)
- Cache hit ratio drops below 20%
- QueueDepth > 100
- Disk usage > 80%

Info Events:
- Auto-scaling triggered
- Index optimization completed
- Backup succeeded/failed
```

---

## See Also
- [Scaling Guide](SCALING.md)
- [API Reference](API.md)
- [Deployment Guide](DEPLOYMENT.md)
