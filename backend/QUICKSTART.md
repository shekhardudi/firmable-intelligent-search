# Quick Start Guide - Firmable Intelligent Search v2.0

## Installation & Setup

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Set Environment Variables
```bash
export OPENAI_API_KEY="your-api-key-here"
export OPENSEARCH_HOST="localhost"
export OPENSEARCH_PORT="9200"
export OPENSEARCH_USER="admin"
export OPENSEARCH_PASSWORD="MySecurePassword123!"
```

### 3. Start OpenSearch
```bash
# If using Docker
docker run -d -p 9200:9200 -p 9600:9600 \
  -e "discovery.type=single-node" \
  opensearchproject/opensearch:latest
```

### 4. Start the Application
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI Schema: http://localhost:8000/openapi.json

---

## Basic Usage

### Example 1: Regular Query (Exact Match)
```bash
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Apple Inc",
    "limit": 5
  }'
```

**Response**: Fast search for exact company name
```json
{
  "query": "Apple Inc",
  "results": [
    {
      "id": "ABC123",
      "name": "Apple Inc",
      "domain": "apple.com",
      "relevance_score": 0.99,
      "search_method": "regular",
      "ranking_source": "bm25"
    }
  ],
  "metadata": {
    "trace_id": "trace_xyz",
    "query_classification": {
      "category": "regular",
      "confidence": 0.98
    },
    "response_time_ms": 35
  }
}
```

### Example 2: Semantic Query (Conceptual)
```bash
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{
    "query": "cloud computing companies in silicon valley",
    "limit": 10
  }'
```

**Response**: Semantic search with vector embeddings
```json
{
  "query": "cloud computing companies in silicon valley",
  "results": [
    {
      "id": "XYZ789",
      "name": "Salesforce",
      "domain": "salesforce.com",
      "relevance_score": 0.87,
      "search_method": "semantic",
      "ranking_source": "hybrid",
      "matching_reason": "Strong semantic match on cloud computing"
    }
  ],
  "metadata": {
    "query_classification": {
      "category": "semantic",
      "confidence": 0.91
    },
    "response_time_ms": 142
  }
}
```

### Example 3: Agentic Query (Time-Sensitive)
```bash
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{
    "query": "companies that announced funding this month",
    "limit": 10
  }'
```

**Response**: Uses external data sources
```json
{
  "query": "companies that announced funding this month",
  "results": [
    {
      "id": "NEW001",
      "name": "StartupXYZ",
      "domain": "startupxyz.io",
      "relevance_score": 1.0,
      "search_method": "agentic",
      "ranking_source": "tool",
      "matching_reason": "Found in recent funding announcements"
    }
  ],
  "metadata": {
    "query_classification": {
      "category": "agentic",
      "confidence": 0.85,
      "needs_external_data": true,
      "external_data_type": "funding"
    },
    "response_time_ms": 320
  }
}
```

---

## Understanding the Response

### Response Headers (Enable via X-Trace-ID)
```
X-Trace-ID: trace_abc123def456     # Unique request ID for tracking
X-Search-Logic: Semantic-Hybrid-RRF # Which search method was used
X-Confidence: 0.91                 # How confident the classifier was
X-Response-Time-MS: 142            # Total execution time
X-Total-Results: 10                # Number of results returned
```

### Metadata Breakdown
- **trace_id**: Unique identifier for this search (for debugging/tracing)
- **query_classification**: How the system classified your query
  - `category`: regular, semantic, or agentic
  - `confidence`: 0.0-1.0 confidence score
- **search_execution**: Details of the actual search
  - `strategy`: Which strategy was used
  - `execution_time_ms`: How long the search took
  - `total_hits`: Total matches in database

### Result Fields
- **relevance_score**: 0.0-1.0 relevance to query
- **search_method**: regular/semantic/agentic
- **ranking_source**: bm25/knn/hybrid/tool
- **matching_reason**: Why this result is relevant

---

## Advanced Usage

### Batch Searching
Search multiple queries at once:
```bash
curl -X POST http://localhost:8000/api/search/batch \
  -H "Content-Type: application/json" \
  -d '{
    "queries": [
      "Apple Inc",
      "sustainable energy companies",
      "recent AI funding"
    ],
    "limit": 5
  }'
```

### With Trace ID Header
Include your own trace ID for request correlation:
```bash
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -H "X-Trace-ID: my_request_123" \
  -d '{"query": "fintech startups"}'
```

### Programmatic Usage (Python)
```python
import httpx

client = httpx.Client()

response = client.post(
    "http://localhost:8000/api/search/intelligent",
    json={
        "query": "AI companies in London",
        "limit": 20,
        "include_reasoning": True
    },
    headers={"X-Trace-ID": "my_trace_001"}
)

data = response.json()
print(f"Found {data['metadata']['total_results']} results")
print(f"Classification: {data['metadata']['query_classification']['category']}")
print(f"Response time: {data['metadata']['response_time_ms']}ms")

for result in data['results']:
    print(f"  - {result['name']} ({result['relevance_score']:.2f})")
```

---

## System Features

### Check Service Health
```bash
curl http://localhost:8000/api/search/health
```

### Get Available Features
```bash
curl http://localhost:8000/api/search/features
```

Response shows:
- Enabled features (classification, semantic search, etc.)
- Available models and dimensions
- Search strategies and typical latencies

---

## Common Patterns

### Pattern 1: Search with Specific Country Filter
The classifier automatically extracts location filters:
```bash
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{"query": "tech companies in Canada"}'
```

### Pattern 2: Industry-Specific Search
```bash
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{"query": "biotech companies founded in 2020"}'
```

### Pattern 3: Similarity Search
```bash
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{"query": "companies similar to Netflix"}'
```

---

## Performance Tips

1. **Use Regular Queries for Exact Matches**
   - "IBM" will be faster than "companies like IBM"

2. **Batch Process Multiple Queries**
   - Use `/api/search/batch` instead of multiple requests

3. **Set Appropriate Limits**
   - Default limit=20 is reasonable
   - Max limit=100

4. **Monitor Response Times**
   - Regular: 10-50ms
   - Semantic: 50-200ms
   - Agentic: 100-500+ms

---

## Debugging

### Enable Detailed Logging
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check Trace Logs
Use the trace ID from response to find logs:
```bash
grep "trace_abc123def456" app.log
```

### Test Intent Classification
Check if your query is being classified correctly:
```python
from app.services.intent_classifier import get_intent_classifier

classifier = get_intent_classifier()
intent = classifier.classify("sustainable energy companies")
print(f"Category: {intent.category}")
print(f"Confidence: {intent.confidence}")
print(f"Reasoning: {intent.reasoning}")
```

---

## Troubleshooting

### Problem: "OPENAI_API_KEY not found"
**Solution**: Set the environment variable
```bash
export OPENAI_API_KEY="sk-..."
```

### Problem: OpenSearch connection failed
**Solution**: Check OpenSearch is running
```bash
curl -u admin:MySecurePassword123! https://localhost:9200
```

### Problem: Slow semantic searches
**Solution**: 
- Check network latency to OpenSearch
- Verify embedding service is initialized
- Check OpenSearch has vector indices

### Problem: Poor semantic search results
**Solution**:
- Verify query is conceptual (not just keywords)
- Check result reasoning explains the match
- Try searching by concept not by keywords

---

## Next Steps

1. **Read ARCHITECTURE_v2.md** for detailed design information
2. **Explore /docs** endpoint for interactive API testing
3. **Set up monitoring** with traces and metrics
4. **Configure LangSmith** for production tracing
5. **Implement result caching** for frequent queries
6. **Add custom external tools** for agentic search

---

## Support

For issues or questions:
1. Check ARCHITECTURE_v2.md
2. Review response headers (X-Trace-ID, X-Search-Logic)
3. Check application logs with trace ID
4. Use /api/search/features to verify configuration

