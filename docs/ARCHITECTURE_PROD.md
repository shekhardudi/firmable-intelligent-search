# AWS Architecture — Production Deployment

## Overview

Production-grade deployment targeting **60 RPS** sustained throughput with
auto-scaling, managed data stores, and full observability. All compute runs
inside a VPC with private subnets; only the ALB is internet-facing.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AWS Production Architecture                        │
│                                                                             │
│   Internet                                                                  │
│      │                                                                      │
│      ▼                                                                      │
│   Route 53  (DNS, health-check failover)                                    │
│      │                                                                      │
│      ▼                                                                      │
│   ACM (TLS certificate)                                                     │
│      │                                                                      │
│      ▼                                                                      │
│   ┌──────────────────────────────────────────────────────────┐              │
│   │  Application Load Balancer  (internet-facing)            │              │
│   │  Listener: HTTPS :443 → Target Group (backend ECS)       │              │
│   └─────────────────────────┬────────────────────────────────┘              │
│                             │                                               │
│   ┌─────────────────────────▼──────────────────────────────────────────┐   │
│   │  VPC  (private subnets, multi-AZ)                                  │   │
│   │                                                                    │   │
│   │  ┌────────────────────────────────────────────────────────────┐   │   │
│   │  │  ECS Cluster (Fargate)                                      │   │   │
│   │  │                                                             │   │   │
│   │  │  ┌──────────────────────────────────────────────────┐      │   │   │
│   │  │  │  Backend Service  (FastAPI)                        │      │   │   │
│   │  │  │  Tasks: 4–20  (target CPU 60%, scale on p95 lat)  │      │   │   │
│   │  │  │  CPU: 2 vCPU   Memory: 4 GB                       │      │   │   │
│   │  │  │  ThreadPoolExecutor(128) per task                  │      │   │   │
│   │  │  └──────────┬─────────────────┬────────────────┬─────┘      │   │   │
│   │  │             │                 │                │             │   │   │
│   │  │             ▼                 ▼                ▼             │   │   │
│   │  │  ┌─────────────────┐  ┌───────────┐  ┌────────────────┐    │   │   │
│   │  │  │ Intent Queries  │  │  Regular/ │  │ Agentic Queries│    │   │   │
│   │  │  │ (OpenAI API)    │  │ Semantic  │  │ → SQS Queue    │    │   │   │
│   │  │  │ (external)      │  │  Queries  │  └───────┬────────┘    │   │   │
│   │  │  └─────────────────┘  └─────┬─────┘          │             │   │   │
│   │  │                             │                 │             │   │   │
│   │  │  ┌──────────────────────────▼──────────┐     │             │   │   │
│   │  │  │  Agentic Worker Service  (Fargate)  │◄────┘             │   │   │
│   │  │  │  Tasks: 2–10  (scale on SQS depth)  │                   │   │   │
│   │  │  │  CPU: 2 vCPU   Memory: 4 GB         │                   │   │   │
│   │  │  │  LangChain Agent + Tavily + OpenAI  │                   │   │   │
│   │  │  └─────────────────────────────────────┘                   │   │   │
│   │  │                                                             │   │   │
│   │  └─────────────────────────────────────────────────────────────┘   │   │
│   │                                                                    │   │
│   │  ┌──────────────────────┐   ┌────────────────────────────────┐   │   │
│   │  │  Amazon OpenSearch   │   │  ElastiCache (Redis OSS)       │   │   │
│   │  │  Service             │   │  Cluster mode, 2 shards        │   │   │
│   │  │  3-node data cluster │   │  (intent classifier cache,     │   │   │
│   │  │  (r6g.large.search)  │   │   query result cache)          │   │   │
│   │  │  768-dim kNN index   │   └────────────────────────────────┘   │   │
│   │  └──────────────────────┘                                         │   │
│   │                                                                    │   │
│   │  ┌──────────────────────┐   ┌────────────────────────────────┐   │   │
│   │  │  Amazon SQS          │   │  AWS Secrets Manager           │   │   │
│   │  │  agentic-query-queue │   │  OPENAI_API_KEY                │   │   │
│   │  │  (FIFO, deduplication│   │  TAVILY_API_KEY                │   │   │
│   │  │   by query hash)     │   │  OPENSEARCH credentials        │   │   │
│   │  └──────────────────────┘   └────────────────────────────────┘   │   │
│   │                                                                    │   │
│   └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  Observability                                                       │  │
│   │                                                                      │  │
│   │  ECS Tasks ──OTLP──▶ AWS Distro for OTel (ADOT) Collector (sidecar) │  │
│   │                              │                                       │  │
│   │               ┌──────────────┼──────────────────┐                   │  │
│   │               ▼              ▼                  ▼                   │  │
│   │        CloudWatch        X-Ray                CloudWatch            │  │
│   │        Metrics (EMF)     Traces               Container             │  │
│   │        + Logs            (distributed         Insights              │  │
│   │                           tracing)            (dashboards)          │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │  CI/CD & Container Registry                                          │  │
│   │                                                                      │  │
│   │  GitHub Actions ──push──▶ ECR (backend + worker images)             │  │
│   │                  ──deploy──▶ ECS rolling update (blue/green)        │  │
│   │                                                                      │  │
│   │  Embedding model (msmarco-distilbert-base-tas-b) is baked into the  │  │
│   │  Docker image at build time (COPY . . in Dockerfile). No S3         │  │
│   │  download at container start — zero cold-start penalty.             │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Capacity Model (60 RPS)

| Path       | Avg latency | Concurrency needed | Fargate tasks |
|------------|-------------|-------------------|---------------|
| Regular    | 120 ms      | 60 × 0.12 = 7     | 2 (burst 4)   |
| Semantic   | 200 ms      | 60 × 0.20 = 12    | 2 (burst 4)   |
| Agentic    | 8–15 s      | 5% × 60 × 10 = 30 | 4 (burst 10)  |
| **Total**  |             | **~50 threads**    | **4 min → 20 max** |

ThreadPoolExecutor(128) per backend task gives headroom for 64 RPS at 2s average without blocking the event loop.

## Scaling Triggers

| Metric                        | Scale-out threshold | Scale-in threshold |
|-------------------------------|---------------------|--------------------|
| ECS CPU utilisation           | > 60%               | < 30%              |
| ALB p95 target response time  | > 2 000 ms          | < 500 ms           |
| SQS agentic queue depth       | > 50 messages       | < 5 messages       |
| ElastiCache memory            | > 75%               | —                  |

## Network Topology

```
  Public Subnets (2 AZs)         Private Subnets (2 AZs)
  ┌───────────────────┐          ┌───────────────────────────────────┐
  │  ALB (internet-   │          │  ECS Backend tasks                │
  │  facing)          │──────────│  ECS Agentic Worker tasks         │
  │  NAT Gateway      │          │  OpenSearch Service domain        │
  └───────────────────┘          │  ElastiCache subnet group         │
                                 │  VPC Interface Endpoints:         │
                                 │    SQS, SecretsManager, ECR,      │
                                 │    CloudWatch Logs, X-Ray         │
                                 │  VPC Gateway Endpoint: S3         │
                                 └───────────────────────────────────┘
```

## Key AWS Services

NAT Gateway is still required for external HTTPS calls (OpenAI, Tavily). All
AWS-internal service calls use VPC Endpoints, eliminating the $0.045/GB NAT
data-processing charge on those traffic paths.

## Observability: Zero Code Changes Between Environments

The app always sends `OTLP/gRPC` to `localhost:4317` (env var `OTLP_ENDPOINT`,
default `http://localhost:4317`).

| Environment | What listens on localhost:4317            | Backends                                        |
|-------------|------------------------------------------|-------------------------------------------------|
| Local dev   | OTel Collector (docker-compose service)  | Prometheus + Jaeger → Grafana                   |
| AWS ECS     | ADOT sidecar (same task network ns)      | X-Ray (traces) + CloudWatch EMF (metrics/logs)  |

The ADOT sidecar uses the AWS-managed default config
(`/etc/ecs/ecs-default-config.yaml`), which handles OTLP→X-Ray protocol
translation automatically. For custom attribute enrichment or metric filtering,
see `infrastructure/otel-collector/otelcol-config-aws.yaml`.

**Why not X-Ray SDK directly?** Requires SDK-specific instrumentation calls
instead of vendor-neutral OTel spans — swapping backends would then require
code changes. ADOT sidecar gives full backend flexibility with zero app coupling.

**Why CloudWatch over AMP+AMG?** At this scale, CloudWatch Container Insights
costs less to operate and needs no extra workspace provisioning. AMP+AMG becomes
worthwhile above ~500 RPS or when cross-account metric federation is needed.


| Component              | AWS Service                      | Notes                                          |
|------------------------|----------------------------------|------------------------------------------------|
| Load balancer          | ALB                              | HTTP/2, connection draining 30 s              |
| Container orchestration| ECS Fargate                     | No EC2 management; isolated per task           |
| Search engine          | Amazon OpenSearch Service        | 3-node data cluster, UltraWarm for cold data   |
| Cache                  | ElastiCache for Redis OSS        | Cluster mode; 2 shards, 1 replica each         |
| Async queue            | SQS FIFO                         | Deduplication by SHA-256(query)                |
| Secrets                | AWS Secrets Manager              | Rotated API keys; ECS task IAM role            |
| Container registry     | Amazon ECR                       | Image scanning enabled                         |
| Tracing                | AWS X-Ray via ADOT sidecar       | OTLP→X-Ray, zero app-code changes              |
| Metrics                | CloudWatch Metrics (EMF)         | Pushed by ADOT sidecar, Container Insights     |
| Dashboards             | CloudWatch Container Insights    | Latency, CPU, memory, error rate               |
| Logs                   | CloudWatch Logs                  | Structured JSON via structlog + awslogs driver |
| DNS                    | Route 53                         | Latency-based routing, health-check failover   |
| TLS                    | ACM (auto-renew)                 | SNI on ALB                                     |
| VPC Endpoints          | Interface (SQS/ECR/CW/SM/X-Ray) + Gateway (S3) | Eliminate NAT cost for AWS-internal traffic |
