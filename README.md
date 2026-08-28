# Fullstack RAG Platform

A high-performance, production-ready Retrieval-Augmented Generation (RAG) system combining local LLM inference, hybrid vector search, cross-encoder re-ranking, and analytics.

---

## Architecture Overview

```
                                  ┌────────────────────────┐
                                  │   Next.js 16 Frontend  │
                                  │   (SSE Streaming / UI) │
                                  └───────────┬────────────┘
                                              │ HTTP / SSE
                                  ┌───────────▼────────────┐
                                  │   FastAPI Backend API  │
                                  └─┬───────┬────────────┬─┘
                                    │       │            │
             ┌──────────────────────┘       │            └──────────────────────┐
             │                              │                                   │
┌────────────▼────────────┐   ┌─────────────▼────────────┐   ┌──────────────────▼──────────────────┐
│   PostgreSQL Relational │   │   MinIO Object Storage   │   │         Qdrant Vector Database      │
│   (History / Documents) │   │   (Raw Document Lake)    │   │      (Hybrid Dense + BM25 Sparse)   │
└─────────────────────────┘   └──────────────────────────┘   └──────────────────┬──────────────────┘
                                                                                │
                                                                   ┌────────────▼────────────┐
                                                                   │ Ollama & Cross-Encoder  │
                                                                   │ (Gemma 2 / Nomic / LM)  │
                                                                   └─────────────────────────┘
```

### Components

- **Backend (FastAPI & Python)**:
  - Asynchronous event-loop offloading for heavy ML inference and Cross-Encoder re-ranking.
  - Server-Sent Events (`/chat/stream`) with real-time token delivery and conversational memory.
  - S3-compatible document upload with strict MIME/size validation.
  - PCA dimensionality reduction and K-Means clustering endpoints for system analytics.
- **Retrieval & Reranking Engine**:
  - **Hybrid Search**: Dense vectors (Nomic Embed) paired with sparse BM25 indices in Qdrant.
  - **Cross-Encoder Re-Ranking**: Filters retrieved candidates through `cross-encoder/ms-marco-MiniLM-L-6-v2` for precise relevance scoring.
  - **Query Rewriting**: Converts multi-turn conversational follow-ups into self-contained standalone search queries.
- **Frontend (Next.js 16 & React 19)**:
  - Responsive dark-mode dashboard and chat interface.
  - Resilient SSE buffer decoder resilient to packet fragmentation.
  - Visualizations via Recharts (PCA 2D vector scatter plot, topic cluster distribution).
- **Ingestion Pipeline**:
  - Batch document processor for `.pdf`, `.txt`, `.md`, `.json`.
  - Recursive chunking with metadata tracking and per-document transaction isolation.

---

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.10+ & `uv` package manager
- Node.js 18+

### 1. Infrastructure Setup
Start PostgreSQL, MinIO, Qdrant, and Ollama:
```bash
cd infra
docker compose up -d
```

Pull Ollama models (if not already cached):
```bash
docker exec -it rag_ollama ollama pull nomic-embed-text
docker exec -it rag_ollama ollama pull gemma2:2b
```

### 2. Backend Setup
```bash
cd backend
uv sync
uv run python main.py
```
Backend runs on `http://localhost:8000`. Interactive API docs available at `http://localhost:8000/docs`.

### 3. Pipeline Ingestion
Process pending documents uploaded to the MinIO data lake:
```bash
cd pipeline
uv sync
uv run python ingest.py
```

### 4. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Frontend runs on `http://localhost:3000`.

---

## Running Tests

Run backend unit tests with mocked fixtures:
```bash
cd backend
uv run python -m unittest test_main.py
```

Build and validate the Next.js frontend:
```bash
cd frontend
npm run build
```

---

## Environment Configuration

Copy `.env.example` to `.env` to override defaults:
```ini
DATABASE_URL=postgresql://admin:password123@localhost:5432/ragdb
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=admin
S3_SECRET_KEY=password123
S3_BUCKET_NAME=rag-documents
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=knowledge_base
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_LLM_MODEL=gemma2:2b
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```
