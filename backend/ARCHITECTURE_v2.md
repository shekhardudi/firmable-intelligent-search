# Firmable Intelligent Search - Architecture v2.0

## Overview

The refactored backend implements a sophisticated 3-bucket intent classifier that intelligently routes queries to specialized search strategies. This document describes the architecture, design patterns, and implementation details.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          FastAPI Application                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     HTTP Endpoints                            │   │
│  │                  /api/search/intelligent                      │   │
│  │                  /api/search/batch                            │   │
│  │                  /api/search/health                           │   │
│  └──────────────────────────────────┬──────────────────────────┘   │
│                                      │                               │
│  ┌──────────────────────────────────▼──────────────────────────┐   │
│  │              Search Orchestrator (Router)                   │   │
│  │         Coordinates entire 3-bucket pipeline                │   │
│  └──────────────────────────────────┬──────────────────────────┘   │
│                                      │                               │
│                    ┌─────────────────┼─────────────────┐            │
│                    │                 │                 │            │
│  ┌─────────────────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐     │
│  │ Intent Classifier      │  │ Strategies  │  │ Observability│    │
│  │ (GPT-4o-mini)          │  │ Executor    │  │ Service     │    │
│  │ - Classify intent      │  │             │  │ - Tracing   │    │
│  │ - Extract filters      │  │ Dispatches  │  │ - Metrics   │    │
│  │ - Generate reasoning   │  │ to strategy │  │ - Logging   │    │
│  └────────────────────────┘  └─────────────┘  └─────────────┘    │
│                                      │                               │
│         ┌────────────────────────────┼────────────────────────┐    │
│         │                            │                        │    │
│  ┌──────▼──────────┐  ┌──────────────▼──────┐  ┌────────────▼──┐ │
│  │ REGULAR SEARCH  │  │ SEMANTIC SEARCH    │  │ AGENTIC SEARCH │ │
│  │ (Bucket 1)      │  │ (Bucket 2)         │  │ (Bucket 3)     │ │
│  │                 │  │                    │  │                │ │
│  │ BM25 Lexical    │  │ Vector k-NN +      │  │ External Tools │ │
│  │ Fast Path       │  │ Hybrid RRF         │  │ Complex Logic  │ │
│  │ 10-50ms         │  │ 50-200ms           │  │ 100-500+ms     │ │
│  └────────┬────────┘  └─────────────┬──────┘  └────────┬───────┘ │
│           │                         │                  │           │
│           │                 ┌───────▼────────┐        │           │
│           │                 │                │        │           │
│           │                 │ Embeddings     │        │           │
│           │                 │ Service        │        │           │
│           │                 │ (msmarco)      │        │           │
│           │                 │                │        │           │
│           │                 └────────────────┘        │           │
│           │                                           │           │
│           └───────────────────────┬───────────────────┘           │
│                                   │                               │
│  ┌────────────────────────────────▼──────────────────────────┐   │
│  │              OpenSearch Backend                            │   │
│  │  - BM25 Index (regular)                                   │   │
│  │  - Vector Index (semantic)                                │   │
│  │  - Document storage                                       │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Intent Classifier Service
**File**: `app/services/intent_classifier.py`

**Purpose**: Automatically classify user queries into one of three buckets.

**Model**: GPT-4o-mini (via Instructor)

**Inputs**:
- User query (string, up to 500 chars)
- Optional trace ID for observability

**Outputs**: `QueryIntent` Pydantic model with:
```python
class QueryIntent(BaseModel):
    category: SearchIntent  # regular, semantic, agentic
    confidence: float       # 0.0-1.0
    filters: Dict[str, Any] # location, industry, year, etc.
    search_query: str       # Optimized for OpenSearch
    needs_external_data: bool
    external_data_type: Optional[str]  # news, funding, events
    reasoning: str         # Classification explanation
```

**Classification Logic**:
- **REGULAR**: Specific names, acronyms, single keywords
  - Example: "IBM", "Apple Inc", "2022 tech companies"
- **SEMANTIC**: Conceptual, synonyms, natural language
  - Example: "green energy companies", "fintech startups"
- **AGENTIC**: Time-sensitive, external data, complex queries
  - Example: "recent funding announcements", "trending startups"

**Key Design Patterns**:
- Instructor pattern for deterministic LLM output
- Singleton with lazy initialization
- Dependency injection for OpenAI client

---

### 2. Search Strategies (Strategy Pattern)
**File**: `app/services/search_strategies.py`

**Abstract Base Class**: `SearchStrategy`

**Implementation Pattern**:
```python
class SearchStrategy(ABC):
    @abstractmethod
    def search(self, context: SearchContext) -> tuple[List[SearchResult], Dict]:
        pass
```

#### Strategy 1: Regular Search
**Class**: `RegularSearchStrategy`

**Mechanism**: BM25 Lexical Search
- Fast, predictable performance
- Boost name field heavily (3x weight)
- Support for fuzzy matching

**Fields Searched**:
1. name (weight 3) - Company name
2. domain (weight 2) - Domain name
3. industry - Industry term
4. locality - Location

**Typical Latency**: 10-50ms
**Use Case**: Exact name matches, structured queries

#### Strategy 2: Semantic Search
**Class**: `SemanticSearchStrategy`

**Mechanism**: Hybrid Search with Reciprocal Rank Fusion (RRF)
- Combines BM25 and Vector scores
- Uses msmarco-distilbert embeddings (768-dim)
- RRF merges rankings from both methods

**Score Formula**:
```
FinalScore = α * BM25_Score + (1-α) * Vector_Score
Default: α = 0.4 (lexical weight), (1-α) = 0.6 (semantic weight)
```

**Workflow**:
1. User query → Embed with msmarco
2. Run two parallel searches:
   - BM25 on text fields
   - k-NN on vector_embedding field
3. Combine with RRF ranking

**Typical Latency**: 50-200ms
**Use Case**: Conceptual queries, exploration, synonyms

#### Strategy 3: Agentic Search
**Class**: `AgenticSearchStrategy`

**Mechanism**: Tool-Based External Search
1. Query external tool (news API, funding DB, etc.)
2. Extract company identifiers
3. Filter OpenSearch results by IDs

**Current Implementation**: Mock (placeholder for real APIs)

**Typical Latency**: 100-500+ms
**Use Case**: Time-sensitive data, trend analysis

---

### 3. Embedding Service
**File**: `app/services/embedding_service.py`

**Model**: `sentence-transformers/msmarco-distilbert-base-tas-b`
- Lightweight: ~270MB on disk
- Fast: ~1000 embeddings/sec on CPU
- Output dimension: 768
- Optimized for information retrieval

**Key Methods**:
- `embed(text)` - Single text embedding
- `embed_batch(texts, batch_size=32)` - Efficient batch processing
- `get_embedding_dimension()` - Get vector size

**Local Model Loading**:
- Searches workspace for local model directory
- Falls back to HuggingFace download if not found
- Singleton pattern for reusability

---

### 4. Search Orchestrator
**File**: `app/services/orchestrator.py`

**Purpose**: Main coordinator of the entire pipeline

**Key Responsibilities**:
1. Call Intent Classifier
2. Select appropriate strategy
3. Execute strategy
4. Manage observability
5. Format response with headers

**Workflow**:
```
Input Query
    ↓
[1] Intent Classification
    ├─ Category determination
    ├─ Filter extraction
    └─ Confidence scoring
    ↓
[2] Strategy Selection
    ├─ Regular → RegularSearchStrategy
    ├─ Semantic → SemanticSearchStrategy
    └─ Agentic → AgenticSearchStrategy
    ↓
[3] Strategy Execution
    ├─ Build context
    ├─ Run search
    └─ Process results
    ↓
[4] Response Assembly
    ├─ Format results
    ├─ Add metadata
    ├─ Generate headers
    └─ Log observability
    ↓
Output: IntelligentSearchResponse with headers
```

**Fallback Mechanism**:
- If primary strategy fails, fall back to semantic search
- Log fallback event for debugging

**Batch Search Support**:
```python
def batch_search(queries: List[str], limit: int) -> List[Response]
```

---

### 5. Observability Service
**File**: `app/services/observability.py`

**Integrations**:
- **LangSmith**: Query classification and execution tracking
- **OpenTelemetry**: Distributed tracing
- **Structured Logging**: Via structlog

**Key Classes**:
- `TraceCollector`: Accumulates trace events
- `TraceEvent`: Single event with metadata
- `ObservabilityService`: Manages integrations

**Response Headers** (Transparency):
```
X-Trace-ID: Unique request ID
X-Search-Logic: Which method was used
X-Confidence: 0.0-1.0
X-Response-Time-MS: Milliseconds
X-Total-Results: Result count
```

---

## Data Flow Analysis

### Regular Query Flow
```
User: "Apple Inc"
    ↓
Classifier: 
  category=REGULAR, confidence=0.98, search_query="Apple Inc"
    ↓
RegularSearchStrategy:
  BM25 search on {name, domain, industry}
    ↓
Results: [Apple Inc, Apple Services, Apple Inc subsidiaries...]
Response Time: ~30ms
```

### Semantic Query Flow
```
User: "companies in sustainable energy"
    ↓
Classifier:
  category=SEMANTIC, confidence=0.92, search_query="sustainable energy"
  filters={industry: "clean_energy"}
    ↓
SemanticSearchStrategy:
  1. Embed query → [768-dim vector]
  2. Run BM25 on "sustainable energy" → [Results with BM25 score]
  3. Run k-NN on vector → [Results with similarity score]
  4. Merge with RRF → [Final ranked results]
    ↓
Results: [Tesla, NextEra Energy, Nextera...] + reasoning
Response Time: ~150ms
```

### Agentic Query Flow
```
User: "startups that raised funding recently"
    ↓
Classifier:
  category=AGENTIC, confidence=0.89, needs_external_data=true
  external_data_type="funding"
    ↓
AgenticSearchStrategy:
  1. Call external tool (news/funding API)
  2. Get company IDs: [comp1_id, comp2_id, ...]
  3. Filter OpenSearch by IDs
  4. Return results with tool attribution
    ↓
Results: [Companies from external source] + source info
Response Time: ~300ms+ (depends on external API)
```

---

## Configuration

### Environment Variables (app/config.py)

**Intent Classifier**:
```python
OPENAI_MINI_MODEL = "gpt-4o-mini"
CLASSIFIER_CONFIDENCE_THRESHOLD = 0.7
CLASSIFIER_TIMEOUT = 10
```

**Hybrid Search**:
```python
LEXICAL_WEIGHT = 0.4  # BM25
SEMANTIC_WEIGHT = 0.6  # Vector
MIN_SEMANTIC_SCORE = 0.3
```

**Observability**:
```python
ENABLE_TRACING = True
ENABLE_LANGSMITH = False  # Set to True to connect LangSmith
LANGSMITH_PROJECT = "firmable-search"
LANGSMITH_API_KEY = "..."  # Required if ENABLE_LANGSMITH=True
```

---

## API Endpoints

### POST /api/search/intelligent

**Request**:
```json
{
    "query": "sustainable energy companies in Europe",
    "limit": 20,
    "page": 1,
    "include_reasoning": true,
    "include_trace": false
}
```

**Response**:
```json
{
    "query": "sustainable energy companies in Europe",
    "results": [
        {
            "id": "company_123",
            "name": "NextEra Energy",
            "domain": "nexteraenergy.com",
            "industry": "Utilities",
            "country": "United States",
            "locality": "Florida",
            "relevance_score": 0.92,
            "search_method": "semantic",
            "ranking_source": "hybrid",
            "matching_reason": "Strong semantic match on sustainable energy focus"
        }
    ],
    "metadata": {
        "trace_id": "trace_abc123def456",
        "query_classification": {
            "category": "semantic",
            "confidence": 0.92,
            "reasoning": "Conceptual query about industry sector"
        },
        "search_execution": {
            "strategy": "semantic",
            "total_hits": 247,
            "returned": 20,
            "execution_time_ms": 145
        },
        "total_results": 20,
        "response_time_ms": 152,
        "page": 1,
        "limit": 20
    },
    "status": "success"
}
```

**Response Headers**:
```
X-Trace-ID: trace_abc123def456
X-Search-Logic: Semantic-Hybrid-RRF
X-Confidence: 0.92
X-Response-Time-MS: 152
X-Total-Results: 20
```

### POST /api/search/batch

**Request**:
```json
{
    "queries": [
        "Apple",
        "green energy companies",
        "recent funding announcements"
    ],
    "limit": 10
}
```

**Response**:
```json
{
    "total_queries": 3,
    "successful": 3,
    "failed": 0,
    "results": [
        {
            "query": "Apple",
            "results": [...],
            "metadata": {...}
        }
    ]
}
```

---

## Testing & Debugging

### Health Check
```bash
curl http://localhost:8000/api/search/health
```

### Features Discovery
```bash
curl http://localhost:8000/api/search/features
```

### Test Queries
```bash
# Regular query
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{"query": "Apple Inc"}'

# Semantic query
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{"query": "sustainable energy companies"}'

# With trace ID
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -H "X-Trace-ID: my_trace_123" \
  -d '{"query": "fintech startups"}'
```

---

## Performance Characteristics

| Strategy | Latency | Accuracy | Use Case |
|----------|---------|----------|----------|
| Regular | 10-50ms | High (exact) | Names, acronyms |
| Semantic | 50-200ms | High (conceptual) | Natural language |
| Agentic | 100-500+ms | Variable | Time-sensitive |

---

## Design Patterns Used

1. **Strategy Pattern**: Different search implementations
2. **Singleton Pattern**: Service initialization
3. **Dependency Injection**: FastAPI dependencies
4. **Observer Pattern**: Observability hooks
5. **Factory Pattern**: Service creation
6. **Decorator Pattern**: Middleware for tracing

---

## Future Enhancements

1. **Real External APIs**: Implement funding, news, events APIs
2. **Response Caching**: Cache results for popular queries
3. **Learning from Feedback**: Improve classifier over time
4. **Advanced Filtering**: More sophisticated entity extraction
5. **Batch Optimization**: Parallel processing for batch operations
6. **Custom Weights**: User-configurable lexical/semantic weights
7. **Multi-language Support**: Expand beyond English
8. **Result Explanations**: Detailed why-this-result explanations

---

## Troubleshooting

**Issue**: Intent classification is slow
- **Solution**: Check OpenAI API latency, consider caching

**Issue**: Semantic search returning poor results
- **Solution**: Verify OpenSearch has vector field indexed, check embedding quality

**Issue**: Agentic search not working
- **Solution**: Implement real external tool callbacks

**Issue**: High memory usage
- **Solution**: Reduce embedding batch size, enable result streaming

---

## Production Considerations

1. **API Rate Limiting**: Add rate limits per API key
2. **Result Caching**: Implement Redis caching layer
3. **Monitoring**: Set up metrics collection
4. **Error Handling**: Add circuit breakers for external APIs
5. **Versioning**: Support multiple classifier versions
6. **A/B Testing**: Route subset of traffic to new strategies

