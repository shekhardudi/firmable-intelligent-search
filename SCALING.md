# Scaling Strategy & Performance

## Current Performance Targets

### Search Tier
- **Basic Structured Search**: 60+ RPS (Requests Per Second)
  - Latency p50: 45ms
  - Latency p99: 150ms
  - Throughput: 1.8M searches/hour

### AI/LLM Tier
- **Intelligent Search**: 30 RPS maximum
  - Latency p50: 2000ms (including LLM call)
  - Latency p99: 5000ms
  - Throughput: 108K inquiries/hour

### Combined Load
- **Total System**: 60 RPS with mixed workload
- **Concurrent Operations**: 60 searches + 60 filters simultaneously

---

## Architecture for Scaling

### 1. Request Routing Strategy

```
Client Requests (60 RPS)
        ↓
    [API Gateway]
        ↓
    ┌───┴────────────┐
    ↓                ↓
[Fast Track]    [AI Track]
(50 RPS)        (10 RPS)
    ↓                ↓
[OpenSearch]    [LLM Queue]
Only            → [OpenAI]
    ↓                ↓
[Cache Check]   [Process]
    ↓                ↓
[Return]        [Return]
```

### 2. Load Distribution

**Per Pod (6 RPS capacity)**:
- 4 RPS: Structured search (1 worker)
- 1.5 RPS: Semantic search (0.5 worker available)
- 0.5 RPS: LLM calls (shared thread pool)

**Horizontal Pods Required**:
```
60 RPS ÷ 6 RPS/pod = 10 pods (minimum)
Recommended: 12-15 pods for headroom
Max scale: 50 pods for 10x growth
```

### 3. Request Queuing

For peak loads exceeding capacity:

```python
queue_config = {
    "max_size": 1000,
    "max_wait_time": "1s",
    "priority_levels": 3,
    "overflow_policy": "reject_gracefully"
}
```

**Queue Tiers**:
1. **Priority 1** (P1): Basic search - immediate
2. **Priority 2** (P2): Intelligent search - 500ms wait
3. **Priority 3** (P3): Agentic search - 2000ms+ acceptable

### 4. Caching Layers

#### L1: Redis (In-Memory) - 1 minute TTL
```
Hit Rate Target: 30-40% for repeated queries
- Popular searches (trending)
- Recent results (same user)
- Common filters
```

**Memory requirement**: ~10GB for 1M cached results
```python
cache_config = {
    "ttl": 60,  # seconds
    "max_entries": 1_000_000,
    "eviction_policy": "lru"
}
```

#### L2: OpenSearch Query Cache
```
Hit Rate Target: 50-60% for filter combinations
- Index-level caching
- Aggregation results
- Filter combinations
```

#### L3: CDN (Cloudflare/CloudFront) - 5 minutes
```
Popular static results
Popular company profiles
Industry statistics
```

### 5. Database Scaling

#### Read Replicas for Tags/Users
```
Primary (Write) → Replica 1 (Read)
                → Replica 2 (Read)
                → Replica 3 (Read)
                
Replication lag: <100ms
```

#### Connection Pooling
```python
db_pool = {
    "pool_size": 20,
    "max_overflow": 40,
    "pool_timeout": 30,
    "pool_recycle": 3600
}
```

---

## OpenSearch Scaling

### Index Configuration
```yaml
settings:
  number_of_shards: 12          # For 60 RPS
  number_of_replicas: 2         # HA + read scaling
  enable_vector_search: true
  refresh_interval: 30s         # Balance between freshness & performance
```

### Node Configuration

**Data Nodes** (7 nodes minimum):
```
- Heap: 16GB each
- Memory: 32GB total
- Disk: 1TB SSD each (7TB total)
- Network: dedicated network interfaces
```

**Coordinating Nodes** (3 nodes):
```
- Handles search/indexing traffic
- Heap: 8GB each
- Memory: 16GB total
```

**Master Nodes** (3 nodes):
```
- Cluster state management
- Smaller instances acceptable
- Heap: 4GB each
```

### Sharding Strategy

**For 7 Million Companies**:
```
- Doc count per shard: ~600K (7M ÷ 12)
- Index size: ~15GB
- Per shard: ~1.25GB
- Replica overhead: 2x (total: 45GB)

Total storage needed: 45GB + buffers = 60GB across cluster
```

### Write Performance

**Bulk Indexing Pipeline**:
```python
bulk_config = {
    "batch_size": 10_000,
    "max_concurrent_batches": 5,
    "timeout": "30s",
    "refresh": False  # Bulk refresh after complete
}
```

**Expected throughput**: 50,000-100,000 docs/second

---

## LLM/AI Scaling Strategy

### Rate Limiting at OpenAI

**Subscription limits**:
- Standard: 1,500 RPM (Requests Per Minute)
- Enterprise: Unlimited (negotiate)

**Our usage**:
```
30 RPS × 60 = 1,800 RPM (need Enterprise plan)
```

### Batching Strategy

```python
batch_processor = {
    "max_batch_size": 100,
    "wait_time": 100,  # ms
    "parallel_batches": 5,
    "timeout": 30  # seconds
}
```

**Token consumption**:
- Query classification: ~100 tokens
- Entity extraction: ~150 tokens
- Semantic explanation: ~80 tokens
- Embedding generation: ~10 tokens (not counted toward rate limits)

**Monthly estimate** (at 30 RPS):
```
Requests/month: 30 × 60 × 60 × 24 × 30 = 77.76M
Avg tokens/request: ~150
Total tokens: 11.66B

Cost at GPT-4 Turbo: $0.01/1K input = $116,600/month
Cost at GPT-3.5: $0.001/1K input = $11,660/month
```

### Fallback Strategy

If LLM unavailable:
```
- Return to basic search with extracted keywords
- Confidence score drops to reflect uncertainty
- Cache results regardless (expires sooner)
- Queue for retry when service recovers
```

---

## 10x Growth Planning (600 RPS)

### Infrastructure Scaling

From **12-15 pods** to **120-150 pods**:

```
Kubernetes autoscaling:
- Target CPU: 70%
- Target Memory: 80%
- Min pods: 50
- Max pods: 200
- Scale-up time: 30 seconds
- Scale-down time: 5 minutes
```

### OpenSearch Expansion

From **7 data nodes** to **40+ data nodes**:

```
allocation_awareness:
  zone_and_rack_id:
    - us-east-1a
    - us-east-1b
    - us-east-1c
    - us-west-2a
    - us-west-2b
```

**Multi-region deployment**:
- Hot (primary): US-East (60% traffic)
- Warm (regional): US-West (30% traffic)
- Cold (backup): EU (10% traffic + DR)

### Database Scaling

From **1 primary + 3 replicas** to **sharding**:

```
Sharding key: company_id
- Shard 0: company_id % 16 == 0
- Shard 1: company_id % 16 == 1
- ...
- Shard 15: company_id % 16 == 15

Each shard: 1 primary + 3 replicas
```

### Cache Expansion

From **10GB Redis** to **100GB+ Redis**:

```
Redis Cluster:
- 16 nodes (3x replication)
- 100GB total memory
- 6 shards × 3 replicas
```

---

## Performance Monitoring

### Key Metrics

```prometheus
# Search latency
histogram_quantile(0.99, search_request_duration_ms)
histogram_quantile(0.95, search_request_duration_ms)

# Throughput
rate(search_requests_total[1m])

# Error rate
rate(search_errors_total[1m])

# Cache hit ratio
cache_hits / (cache_hits + cache_misses)

# Queue depth
search_queue_size

# API response time
api_request_duration_ms
```

### Alerting Rules

```yaml
alerts:
  - name: HighLatencyP99
    threshold: 200ms
    window: 5m
    
  - name: HighErrorRate
    threshold: 1%
    window: 5m
    
  - name: QueueStaled
    threshold: 100 requests
    window: 2m
    
  - name: LLMServiceDown
    threshold: failed requests
    window: 1m
```

---

## Capacity Planning

### Monthly Growth Forecast

|  Month | RPS | Pods | Data | Cache | DB Size |
|--------|-----|------|------|-------|---------|
| Month 1 | 60 | 12 | 60GB | 10GB | 5GB |
| Month 6 | 120 | 25 | 120GB | 20GB | 10GB |
| Month 12 | 300 | 60 | 300GB | 50GB | 25GB |
| Month 24 | 600 | 120 | 600GB | 100GB | 50GB |

---

## Cost Optimization

### Reserved Capacity

- **For steady state**: Reserve 70% of max expected load
- **Savings**: 40% vs on-demand pricing
- **Flexibility**: Bursting up to 2x reserved capacity

### Spot Instances

- **Non-critical workloads**: 60-70% cost savings
- **Fault tolerance**: Multi-AZ deployment with auto-failover
- **Use for**: Batch processing, cold data indexing

### Right-sizing

- Monitor CPU/Memory utilization
- Scale down underutilized instances
- Compress indexes periodically

---

## Regional Expansion

As traffic grows to 10x+, consider multi-region:

```
Global Load Balancer
        ↓
    ┌───┴────────────────────┐
    ↓                        ↓
[US-East]              [EU-West]
(Primary 60%)          (Regional 30%)
    ↓                        ↓
[OpenSearch Cluster]  [OpenSearch Cluster]
[DB Replica]          [DB Primary]

(Auto-failover if primary down)
```

---

## Disaster Recovery

### RTO/RPO Targets
- **RTO** (Recovery Time Objective): 5 minutes
- **RPO** (Recovery Point Objective): 1 minute

### Backup Strategy

```
Every 6 hours:
  - Full OpenSearch snapshot → S3
  - PostgreSQL backup → S3
  - Redis AOF file → S3

Every 24 hours:
  - Full system backup
```

### Failover Testing

- Monthly failover drills
- Document runbooks
- Test restore procedures
- Verify data integrity

---

