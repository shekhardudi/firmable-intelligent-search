# Local Architecture — Docker Compose Stack

## Overview

Single-machine development environment. All services run as Docker containers
connected via the `search-network` bridge network.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                   Local Development Stack (Docker Compose)                   │
│                                                                              │
│  Developer Browser                                                           │
│       │                                                                      │
│       │  HTTP :5173                                                          │
│       ▼                                                                      │
│  ┌──────────────────────────────────┐                                        │
│  │  Frontend (React + Vite)         │  :5173 / :5174                         │
│  │  VITE_API_URL=http://localhost:8000 │                                     │
│  └────────────────┬─────────────────┘                                        │
│                   │  REST /api/search/*                                      │
│                   ▼                                                          │
│  ┌──────────────────────────────────────────────────────────┐                │
│  │  Backend (FastAPI + Uvicorn, Python 3.11)  :8000         │                │
│  │                                                          │                │
│  │  ┌─────────────────┐  ┌──────────────────┐              │                │
│  │  │ Intent Classifier│  │ Orchestrator     │              │                │
│  │  │ (GPT-4o-mini)    │  │ (strategy router)│              │                │
│  │  └────────┬────────┘  └────────┬─────────┘              │                │
│  │           │                    │                          │                │
│  │           │         ┌──────────┼────────────┐            │                │
│  │           │         ▼          ▼            ▼            │                │
│  │           │   ┌──────────┐ ┌────────┐ ┌──────────────┐  │                │
│  │           │   │ Regular  │ │Semantic│ │   Agentic    │  │                │
│  │           │   │ (BM25)   │ │(kNN+  │ │ (LangChain   │  │                │
│  │           │   │          │ │ RRF)  │ │  Agent)      │  │                │
│  │           │   └────┬─────┘ └───┬───┘ └──────┬───────┘  │                │
│  │           │        │           │             │           │                │
│  └───────────┼────────┼───────────┼─────────────┼───────────┘                │
│              │        │           │             │                            │
│    ┌─────────▼──────────────────────────────────▼──────┐                    │
│    │  OpenSearch (single-node)  :9200 / :9600           │                    │
│    │  ┌────────────────────────────────────────────┐    │                    │
│    │  │  companies index (BM25 + kNN, 768-dim)     │    │                    │
│    │  └────────────────────────────────────────────┘    │                    │
│    └────────────────────────┬───────────────────────────┘                    │
│                             │ Kibana-style UI                                │
│                ┌────────────▼──────────────┐                                 │
│                │  OpenSearch Dashboards     │  :5601                         │
│                └───────────────────────────┘                                 │
│                                                                              │
│    ┌────────────────────┐      External APIs (internet)                      │
│    │  Redis :6379        │      ┌────────────────────────────────────┐        │
│    │  (classifier cache) │      │  OpenAI API (classifier + agent)   │        │
│    └────────────────────┘      │  Tavily Search API (agentic tool)  │        │
│                                └────────────────────────────────────┘        │
│                                                                              │
│  ─── Observability ──────────────────────────────────────────────────────   │
│                                                                              │
│    Backend ──OTLP gRPC──▶ OTel Collector :4317                               │
│                                │                                             │
│                    ┌───────────┼────────────┐                                │
│                    ▼           ▼            ▼                                │
│             ┌─────────┐ ┌──────────┐ ┌──────────────┐                       │
│             │  Jaeger  │ │Prometheus│ │   Grafana    │                       │
│             │ :16686   │ │  :9090   │ │    :3001     │                       │
│             │(traces)  │ │(metrics) │ │(dashboards)  │                       │
│             └─────────┘ └──────────┘ └──────────────┘                       │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Port Reference

| Service              | Host Port | Purpose                      |
|----------------------|-----------|------------------------------|
| Frontend             | 5173      | React dev server (Vite HMR)  |
| Backend API          | 8000      | FastAPI / Uvicorn             |
| OpenSearch           | 9200      | REST query & index API        |
| OpenSearch Dashboards| 5601      | Index browser / dev UI        |
| Redis                | 6379      | Intent classifier LRU cache   |
| OTel Collector (gRPC)| 4317      | Trace / metric ingestion      |
| OTel Collector (HTTP)| 4318      | HTTP fallback for OTLP        |
| Prometheus           | 9090      | Metrics scrape + query        |
| Jaeger UI            | 16686     | Distributed trace viewer      |
| Grafana              | 3001      | Metrics dashboards            |

## Data Flow — Intelligent Search Request

```
POST /api/search/intelligent
        │
        ▼  (ThreadPoolExecutor, 128 workers — routes.py)
  IntentClassifier.classify()
        │  GPT-4o-mini → SearchIntent(category, filters, search_query)
        ▼
  Orchestrator.search()
        │
  ┌─────┴──────────────────────────────────────────────┐
  │   Route by category                                 │
  ▼             ▼                   ▼                   │
BM25          Hybrid              Agentic               │
Search        kNN+BM25            LangChain             │
(regular)     (semantic)          Agent                 │
  │             │                   │                   │
  └─────────────┴───────────────────┘                   │
        │                                               │
        ▼  post-filters, normalise, paginate            │
  SearchResponse ──────────────────────────────────────►┘
        │
        ▼
  HTTP 200 JSON  +  X-Trace-ID / X-Search-Logic / X-Confidence headers
```

## Volumes

| Volume            | Service         | Contents                        |
|-------------------|-----------------|---------------------------------|
| `opensearch-data` | OpenSearch      | Index segments, WAL             |
| `redis-data`      | Redis           | AOF persistence                 |
| `prometheus-data` | Prometheus      | TSDB blocks                     |
| `grafana-data`    | Grafana         | Dashboards, datasource config   |
