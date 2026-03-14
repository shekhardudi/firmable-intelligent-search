# Quick Start Guide - 5 Minutes to Running Demo

## Fastest Path to Demo

### Option 1: With Docker (Easiest - 5 minutes)

```bash
# 1. Clone to local directory
cd /Users/lucifer/Documents/ai-workspace/firmable-intelligent-search

# 2. Copy environment template
cp .env.example .env

# 3. Add your API key (REQUIRED)
# Edit .env and set:
# OPENAI_API_KEY=sk_your_key_here

# 4. Start all services
docker-compose up -d

# 5. Wait for services to be healthy (30-60 seconds)
docker-compose ps
# All should show "Up" and passing healthchecks

# 6. Ingest sample data
python3 data-pipeline/ingest_data.py --sample 10000

# 7. Access the application
# Frontend:  http://localhost:5173
# API Docs:  http://localhost:8000/docs
# OpenSearch: https://localhost:9200 (admin:MySecurePassword123!)
```

### Option 2: Local Development (10 minutes)

```bash
# Prerequisites installed:
# - Python 3.11+, Node 18+
# - OpenSearch running locally on 9200
# - PostgreSQL running on 5432
# - Redis running on 6379

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload

# Open another terminal
cd frontend
npm install
npm run dev

# Backend API: http://localhost:8000/docs
# Frontend: http://localhost:5173

# Data ingestion
cd data-pipeline
python ingest_data.py --sample 10000
```

### Option 3: Quick Demo (Minimal Setup - 2 minutes)

If you just need to see the code and structure:

```bash
# Just view the docs without running
cat README.md                    # Main guide
cat docs/ARCHITECTURE.md          # How it works
cat docs/SCALING.md              # Performance details

# Explore the code structure
ls -la backend/app/              # Backend code
ls -la frontend/src/             # Frontend code
```

---

## What You Get

### After Step 4 (Docker starts):
- ✅ FastAPI backend running on port 8000
- ✅ OpenSearch search engine on port 9200
- ✅ PostgreSQL db on port 5432
- ✅ Redis cache on port 6379
- ✅ React frontend on port 5173

### After Step 6 (Data loaded):
- ✅ 10,000 sample companies indexed
- ✅ Ready for search queries
- ✅ Semantic search enabled
- ✅ LLM integration ready

---

## Test It

### Via Web UI
1. Open http://localhost:5173
2. Try:
   - Search: "Microsoft"
   - Filters: Country=US, Industry=Information Technology
   - AI Search mode: "tech companies in california"

### Via API
```bash
# Basic search
curl -X GET "http://localhost:8000/api/search/companies?q=tech&country=US&limit=10"

# Intelligent search
curl -X POST http://localhost:8000/api/search/intelligent \
  -H "Content-Type: application/json" \
  -d '{"query": "tech companies in California", "llm_enhanced": true}'

# View API docs
open http://localhost:8000/docs
```

---

## Troubleshooting

### Issue: OpenSearch won't start

```bash
# Logs
docker-compose logs opensearch

# Increase Docker memory to 4GB+
# Restart
docker-compose down
docker-compose up -d opensearch
```

### Issue: Backend can't connect to OpenSearch

```bash
# Check OpenSearch is ready
curl -u admin:MySecurePassword123! \
  https://localhost:9200/ --insecure

# Restart backend
docker-compose restart backend
```

### Issue: No OPENAI_API_KEY error

```bash
# Must be set in .env file
echo "OPENAI_API_KEY=sk_your_actual_key" >> .env

# Restart backend
docker-compose restart backend
```

### Issue: Slow initial startup

- OpenSearch needs time to initialize (~30-60s)
- PostgreSQL needs to start
- First index creation takes a moment
- Just wait and check: `docker-compose ps`

---

## Project Structure

```
firmable-intelligent-search/
├── README.md                    ← Start here
├── docker-compose.yml           ← One command to start everything
├── .env.example                 ← Copy to .env and add API key
│
├── backend/                     ← Python FastAPI server
│   ├── app/
│   │   ├── main.py             ← FastAPI app entry
│   │   ├── api/routes.py        ← All endpoints
│   │   ├── services/
│   │   │   ├── search_service.py     ← Core search logic
│   │   │   ├── opensearch_service.py ← Index operations
│   │   │   └── llm_service.py        ← OpenAI calls
│   │   └── models/
│   │       └── search.py        ← Data models
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                    ← React web UI
│   ├── src/
│   │   ├── App.tsx             ← Main component
│   │   ├── components/         ← UI components
│   │   ├── services/
│   │   │   └── api.ts          ← API calls
│   │   └── App.css             ← Styling
│   ├── package.json
│   ├── index.html
│   └── Dockerfile
│
├── data-pipeline/               ← Data ingestion
│   ├── ingest_data.py          ← Load data script
│   └── requirements.txt
│
├── docs/                        ← Documentation
│   ├── ARCHITECTURE.md         ← System design
│   ├── SCALING.md              ← Performance & scaling
│   └── API.md                  ← API reference
│
└── infrastructure/
    └── docker-compose.yml   ← Already at root
```

---

## Performance Expectations

| Operation | Time | Throughput |
|-----------|------|-----------|
| Basic search | 50ms | 60+ RPS |
| Intelligent search | 2s | 30 RPS |
| Semantic search | 500ms | 40 RPS |
| Index 10K docs | 10s | 1K docs/sec |

---

## Next Steps

1. **Explore API**: Visit http://localhost:8000/docs for interactive docs
2. **Try searches**: Use the web UI to test different queries
3. **Read code**: Start with `backend/app/main.py` and `backend/app/services/search_service.py`
4. **Scale up**: Load full 7M dataset (see data-pipeline/README)
5. **Deploy**: See docs/DEPLOYMENT.md for prod setup

---

## Key Files to Understand

### Core Search Logic
- `backend/app/services/search_service.py` (400 lines)
  - `basic_search()` - structured filters
  - `intelligent_search()` - LLM + structured
  - `semantic_search()` - vector similarity

### API Endpoints
- `backend/app/api/routes.py` (300 lines)
  - Defines POST/GET endpoints
  - Request validation
  - Response formatting

### Frontend
- `frontend/src/App.tsx` (150 lines) - main UI
- `frontend/src/components/` - search bar, filters, results
- `frontend/src/services/api.ts` - API client

---

## For Production

1. Replace `.env.example` values with prod credentials
2. increase OpenSearch nodes from 1 to 3+
3. Set PostgreSQL replicas
4. Configure Kubernetes manifests in `infrastructure/`
5. See docs/DEPLOYMENT.md for full guide

---

## Support

- **API Reference**: `docs/API.md`
- **Architecture**: `docs/ARCHITECTURE.md`
- **Scaling**: `docs/SCALING.md`
- **Main Guide**: `README.md`

---

**You're ready to demo!** 🚀
