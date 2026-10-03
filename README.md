# CiteBase Pro

> **Enterprise Retrieval-Augmented Generation (RAG) platform that provides strictly grounded answers derived exclusively from a workspace's own documents, with verifiable citations, multi-tenant isolation, streaming SSE, and measurable evaluation.**

---

## 🌟 Key Features

- **Strict Grounding & Verifiable Citations**: Every claim links directly to its source chunk, document filename, and page number with clickable inline pills `[1]`.
- **Hybrid Retrieval + Reciprocal Rank Fusion (RRF)**: Combines dense vector search (`pgvector`) with sparse full-text search (`tsvector` + GIN trigger) using constant $k=60$ fusion.
- **Cross-Encoder Precision Reranking**: Uses `ms-marco-MiniLM-L-6-v2` for cross-encoder reranking to ensure high precision at top positions.
- **Grounded Refusal**: Detects when evidence is weak or missing and returns a transparent refusal instead of hallucinating.
- **Tenant Isolation**: Strict `workspace_id` filtering enforced across vector ANN searches, full-text indexes, and semantic cache.
- **Semantic Answer Caching**: Fast exact-hash and ANN semantic cache with automatic invalidation upon document ingestion or deletion.
- **Agentic Query Understanding**: Automatic query rewriting and decomposition for compound questions.
- **Document Ingestion Worker**: Asynchronous background pipeline with PyMuPDF, python-docx, and markdown parsers, deduplication via SHA-256 content hashes, and scanned-PDF detection.
- **Modern React 19 Frontend**: Dark glassmorphic interface, real-time SSE token streaming, interactive citation slide-out inspector, and document management.
- **Model Context Protocol (MCP) Server**: Connects Cursor, Claude Desktop, or AI agents directly to your workspace knowledge base.
- **Built-in Evaluation Harness**: Automated calculation of Recall@k, Mean Reciprocal Rank (MRR), Faithfulness, and Token F1 against golden datasets.

---

## 🏗️ Architecture

```
User / IDE / MCP Client
         │
         ▼
┌──────────────────┐       ┌───────────────────────────────┐
│   Vite React     │ <───> │        FastAPI Backend        │
│   Frontend SPA   │       │   (Auth, Routing, SSE Stream) │
└──────────────────┘       └──────────────┬────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            ▼                             ▼                             ▼
┌───────────────────────┐   ┌───────────────────────────┐   ┌───────────────────────┐
│  PostgreSQL 16        │   │  Redis 7                  │   │  OpenAI-Compatible    │
│  - pgvector (HNSW)    │   │  - Job Queues (RQ)        │   │  LLM Engine           │
│  - tsvector (FTS GIN) │   │  - Rate Limiting          │   │  (Streaming & Judge)  │
│  - Semantic Cache     │   │  - Background Tasks       │   └───────────────────────┘
└───────────────────────┘   └─────────────┬─────────────┘
                                          ▼
                            ┌───────────────────────────┐
                            │  RQ Background Worker     │
                            │  (Ingestion & Eval Jobs)  │
                            └───────────────────────────┘
```

---

## 🚀 Quickstart

### 1. Prerequisites
- Docker & Docker Compose **OR** Python 3.10+ and Node.js 20+

### 2. Environment Setup
```bash
cp .env.example .env
```
Ensure `SECRET_KEY` is set to at least 32 characters.

### 3. Run with Docker Compose
```bash
docker compose up --build
```
- **Frontend**: http://localhost:5173
- **Backend API & Swagger Docs**: http://localhost:8000/docs
- **PostgreSQL**: `localhost:5432`
- **Redis**: `localhost:6379`

### 4. Run Locally (Development Mode)

#### Backend
```bash
cd backend
pip install -r requirements.txt aiosqlite
# Run migrations (Postgres)
alembic upgrade head
# Start server
uvicorn app.main:app --reload --port 8000
```

#### Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 Testing

The test suite contains **73 comprehensive unit and integration tests** covering RBAC, tenant isolation, RRF fusion, deduplication, prompt injection defense, semantic caching, and evaluation metrics:

```bash
cd backend
python -m pytest tests/ -v
```

---

## 🔌 Model Context Protocol (MCP) Server

CiteBase Pro includes an MCP server compatible with Cursor, Claude Desktop, and Antigravity:

```bash
python -m mcp_server.server
```

**Exposed Tools:**
- `search_docs(workspace_id, query, top_k)`
- `ask_workspace(workspace_id, question)`

---

## 📋 Evaluation Benchmark

To run the built-in evaluation harness against the golden benchmark dataset:

```bash
curl -X POST "http://localhost:8000/api/v1/workspaces/{workspace_id}/eval/runs" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "name": "benchmark_run",
      "golden_dataset_path": "sample_dataset.jsonl",
      "hybrid_enabled": true,
      "reranker_enabled": true
    }
  }'
```
