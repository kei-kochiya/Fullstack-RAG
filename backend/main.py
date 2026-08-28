import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import Base, SessionLocal, engine, get_db
import models
from services.rag import RAGService
from services.storage import StorageService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("rag.backend")

settings = get_settings()
storage_service: Optional[StorageService] = None
rag_service: Optional[RAGService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage_service, rag_service
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning(f"Database schema initialization warning: {exc}")

    storage_service = StorageService(settings)
    try:
        storage_service.ensure_bucket()
    except Exception as exc:
        logger.warning(f"S3 bucket check warning: {exc}")

    rag_service = RAGService(settings)
    yield


app = FastAPI(title="RAG Backend API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins if settings.allowed_origins else ["*"],
    allow_credentials=True if settings.allowed_origins != ["*"] else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_rag_service() -> RAGService:
    global rag_service
    if rag_service is None:
        rag_service = RAGService(settings)
    return rag_service


def get_storage_service() -> StorageService:
    global storage_service
    if storage_service is None:
        storage_service = StorageService(settings)
    return storage_service


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str = Field(default="default_session", max_length=128)


ALLOWED_EXTENSIONS = {".txt", ".pdf", ".md", ".csv", ".json"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided")

    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    file_bytes = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.max_upload_size_mb}MB",
        )

    unique_filename = f"{uuid.uuid4()}{ext}"

    try:
        from io import BytesIO
        storage.upload_fileobj(
            BytesIO(file_bytes),
            unique_filename,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as exc:
        logger.error(f"S3 upload failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store document in object storage",
        )

    db_doc = models.Document(
        filename=unique_filename,
        original_name=file.filename,
        file_size_bytes=len(file_bytes),
        status="uploaded",
    )
    try:
        db.add(db_doc)
        db.commit()
        db.refresh(db_doc)
    except Exception as exc:
        db.rollback()
        storage.delete_file(unique_filename)
        logger.error(f"Database record creation failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record document metadata",
        )

    return {
        "message": "Successfully uploaded document",
        "filename": unique_filename,
        "original_name": file.filename,
        "db_id": db_doc.id,
    }


@app.post("/chat")
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    rag: RAGService = Depends(get_rag_service),
):
    start_time = time.time()

    history_records = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.session_id == request.session_id)
        .order_by(models.ChatHistory.timestamp.asc())
        .limit(10)
        .all()
    )
    history_text = "\n".join([f"{r.role.capitalize()}: {r.content}" for r in history_records])

    search_query = await rag.rewrite_query(request.question, history_text)
    _, context = await rag.retrieve_contexts(search_query, candidate_k=10, final_k=2)

    prompt = rag.format_prompt(request.question, history_text, context)
    answer = await rag.generate_answer(prompt)

    latency = time.time() - start_time

    user_msg = models.ChatHistory(
        session_id=request.session_id,
        role="user",
        content=request.question,
    )
    ai_msg = models.ChatHistory(
        session_id=request.session_id,
        role="assistant",
        content=answer,
        latency=latency,
    )
    db.add_all([user_msg, ai_msg])
    db.commit()

    return {"answer": answer, "context_used": context}


@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    db: Session = Depends(get_db),
    rag: RAGService = Depends(get_rag_service),
):
    history_records = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.session_id == request.session_id)
        .order_by(models.ChatHistory.timestamp.asc())
        .limit(10)
        .all()
    )
    history_text = "\n".join([f"{r.role.capitalize()}: {r.content}" for r in history_records])

    search_query = await rag.rewrite_query(request.question, history_text)
    _, context = await rag.retrieve_contexts(search_query, candidate_k=10, final_k=2)
    prompt = rag.format_prompt(request.question, history_text, context)

    async def event_generator():
        start_time = time.time()
        yield f"data: {json.dumps({'context_used': context})}\n\n"

        full_answer = ""
        try:
            async for chunk in rag.stream_answer(prompt):
                full_answer += chunk
                yield f"data: {json.dumps({'token': chunk})}\n\n"
        except Exception as exc:
            logger.error(f"Streaming failed: {exc}")
            yield f"data: {json.dumps({'error': 'Stream generation error'})}\n\n"
            return

        latency = time.time() - start_time

        try:
            with SessionLocal() as local_db:
                local_db.add_all([
                    models.ChatHistory(
                        session_id=request.session_id,
                        role="user",
                        content=request.question,
                    ),
                    models.ChatHistory(
                        session_id=request.session_id,
                        role="assistant",
                        content=full_answer,
                        latency=latency,
                    ),
                ])
                local_db.commit()
        except Exception as exc:
            logger.error(f"Failed to persist streamed chat history: {exc}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/analytics/vectors")
def get_vectors(rag: RAGService = Depends(get_rag_service)):
    try:
        from sklearn.decomposition import PCA
        import numpy as np

        records, _ = rag.qdrant_client.scroll(
            collection_name=settings.qdrant_collection,
            limit=500,
            with_vectors=True,
            with_payload=True,
        )

        if not records:
            return {"points": []}

        vectors = []
        payloads = []
        for r in records:
            if isinstance(r.vector, dict):
                vec = r.vector.get("", r.vector.get("default", []))
            else:
                vec = r.vector

            if vec and len(vec) > 0:
                vectors.append(vec)
                payload_content = (r.payload or {}).get("page_content", "")
                payloads.append(payload_content[:100] + "..." if len(payload_content) > 100 else payload_content)

        if len(vectors) < 2:
            points = [
                {"x": 0.0, "y": 0.0, "content": payloads[0] if payloads else "Single Document"}
            ] if vectors else []
            return {"points": points}

        pca = PCA(n_components=2)
        vectors_2d = pca.fit_transform(np.array(vectors))

        points = [
            {"x": float(vectors_2d[i][0]), "y": float(vectors_2d[i][1]), "content": payloads[i]}
            for i in range(len(vectors_2d))
        ]
        return {"points": points}
    except Exception as exc:
        logger.warning(f"Vectors retrieval failed: {exc}")
        return {"points": [], "error": str(exc)}


@app.get("/analytics/topics")
def get_topics(
    db: Session = Depends(get_db),
    rag: RAGService = Depends(get_rag_service),
):
    try:
        from sklearn.cluster import KMeans
        import numpy as np

        user_msgs = (
            db.query(models.ChatHistory)
            .filter(models.ChatHistory.role == "user")
            .order_by(models.ChatHistory.timestamp.desc())
            .limit(50)
            .all()
        )
        questions = list({msg.content.strip() for msg in user_msgs if msg.content and msg.content.strip()})

        if len(questions) < 3:
            return {"clusters": []}

        question_vectors = rag.embeddings.embed_documents(questions)
        n_clusters = min(3, len(questions))

        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(np.array(question_vectors))

        clusters = {i: [] for i in range(n_clusters)}
        for idx, label in enumerate(labels):
            clusters[int(label)].append(questions[idx])

        results = [
            {
                "cluster": f"Topic {cluster_id + 1}",
                "count": len(qs),
                "samples": qs[:3],
            }
            for cluster_id, qs in clusters.items()
            if qs
        ]
        return {"clusters": results}
    except Exception as exc:
        logger.warning(f"Topic clustering failed: {exc}")
        return {"clusters": [], "error": str(exc)}


@app.get("/analytics/stats")
def get_stats(db: Session = Depends(get_db)):
    doc_count = db.query(models.Document).count()
    embedded_count = db.query(models.Document).filter(models.Document.status == "embedded").count()
    total_messages = db.query(models.ChatHistory).count()
    active_sessions = db.query(models.ChatHistory.session_id).distinct().count()

    avg_latency = (
        db.query(func.avg(models.ChatHistory.latency))
        .filter(models.ChatHistory.latency.isnot(None))
        .scalar()
    )

    return {
        "total_documents": doc_count,
        "embedded_documents": embedded_count,
        "total_messages": total_messages,
        "active_sessions": active_sessions,
        "avg_latency_seconds": round(float(avg_latency), 2) if avg_latency else 0.0,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
