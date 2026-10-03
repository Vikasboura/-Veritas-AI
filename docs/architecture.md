# CiteBase Pro — Architecture Specification

## Overview

CiteBase Pro is an enterprise Retrieval-Augmented Generation (RAG) platform that provides strictly grounded answers derived exclusively from workspace-owned documents, featuring verifiable citations, multi-tenant isolation, agentic query retry, and rigorous evaluation benchmarking.

---

## 🏗️ System Architecture

```mermaid
graph TD
    User([User / Browser]) <--> |HTTP / SSE| Frontend[Vite React SPA]
    Frontend <--> |REST API / SSE| API[FastAPI Application]
    API <--> Cache[(PostgreSQL Semantic Cache)]
    API <--> DB[(PostgreSQL + pgvector)]
    API <--> Redis[(Redis Queue & Cache)]
    Redis <--> Worker[RQ Background Worker]
    Worker <--> Ingestion[PyMuPDF / Docx / Embedder]
    Worker <--> DB
    API <--> LLM[OpenAI-Compatible LLM]
    MCP[MCP Client / IDE] <--> |JSON-RPC stdio| MCPServer[CiteBase MCP Server]
    MCPServer <--> API
```

---

## 🔄 Retrieval & Generation Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant FE as Frontend SPA
    participant API as FastAPI Router
    participant Cache as Semantic Cache
    participant R as Retrieval Service
    participant LLM as LLM Engine
    participant DB as Postgres (pgvector + FTS)

    U->>FE: Ask question
    FE->>API: POST /workspaces/{id}/chat (SSE)
    API->>Cache: Check cached answer (workspace-scoped)
    alt Cache Hit
        Cache-->>API: Return cached answer + citations
        API-->>FE: Stream cached response
    else Cache Miss
        API->>R: Hybrid Retrieval (Vector + FTS)
        R->>DB: Cosine ANN search (HNSW)
        R->>DB: Full-text search (tsvector)
        DB-->>R: Top candidates
        R->>R: Reciprocal Rank Fusion (k=60)
        R->>R: Cross-Encoder Rerank (ms-marco)
        R-->>API: Top N Ranked Chunks
        API->>API: Refusal Threshold Evaluation
        alt Confidence < Threshold
            API-->>FE: Refusal Message ("Evidence weak")
        else Confidence >= Threshold
            API->>LLM: Generate Answer with Citations
            LLM-->>API: Stream tokens
            API-->>FE: Stream SSE deltas & citation pills
            API->>Cache: Store answer in cache
        end
    end
```

---

## 🧱 Key Components

| Component | Technology | Role |
|---|---|---|
| **Backend API** | FastAPI, Python 3.10+ | Authentication, workspace tenancy, streaming SSE endpoints, telemetry |
| **Database** | PostgreSQL 16 + pgvector | Chunk embeddings (384-dim), full-text search (GIN tsvector trigger), ORM models |
| **Worker Queue** | Redis + RQ | Asynchronous document ingestion, OCR/scanned PDF detection, eval benchmark runs |
| **Embedding Engine** | sentence-transformers | `bge-small-en-v1.5` / `all-MiniLM-L6-v2` dense vector representations |
| **Reranker** | CrossEncoder | `ms-marco-MiniLM-L-6-v2` precision candidate reranking |
| **Frontend** | React 19, TypeScript, Vite | Modern glassmorphic dark UI, streaming chat, inline citation tags, slide-out inspector |
| **MCP Server** | Python stdio JSON-RPC | Model Context Protocol tools for Cursor, Claude Desktop, and AI agents |
