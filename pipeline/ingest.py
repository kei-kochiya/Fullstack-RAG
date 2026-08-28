import logging
import os
import sys
import tempfile
from typing import List

import boto3
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from qdrant_client.models import SparseVectorParams
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("rag.pipeline")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:password123@localhost:5432/ragdb")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "admin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "password123")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "rag-documents")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "knowledge_base")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

s3_client = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
)


def ensure_qdrant_collection(client: QdrantClient, collection_name: str) -> None:
    if not client.collection_exists(collection_name):
        logger.info(f"Creating Qdrant collection '{collection_name}'")
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            sparse_vectors_config={"langchain-sparse": SparseVectorParams()},
        )


def load_and_split(local_path: str, filename: str) -> List:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        loader = PyPDFLoader(local_path)
    else:
        loader = TextLoader(local_path, encoding="utf-8")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=100,
        separators=["\n\n", "\n", " ", ""],
    )
    docs = loader.load()
    return splitter.split_documents(docs)


def process_documents() -> None:
    db = SessionLocal()
    try:
        query = text("SELECT id, filename FROM documents WHERE status = :status")
        pending_docs = db.execute(query, {"status": "uploaded"}).fetchall()

        if not pending_docs:
            logger.info("No documents pending processing")
            return

        logger.info(f"Found {len(pending_docs)} document(s) to process")

        qclient = QdrantClient(url=QDRANT_URL)
        ensure_qdrant_collection(qclient, QDRANT_COLLECTION)

        embeddings = OllamaEmbeddings(
            model=OLLAMA_EMBED_MODEL,
            base_url=OLLAMA_BASE_URL,
        )
        sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

        for doc_id, filename in pending_docs:
            logger.info(f"Processing document {doc_id}: {filename}")
            
            # Set status to processing
            db.execute(
                text("UPDATE documents SET status = :status WHERE id = :id"),
                {"status": "processing", "id": doc_id},
            )
            db.commit()

            temp_path = os.path.join(tempfile.gettempdir(), f"ingest_{filename}")
            try:
                s3_client.download_file(S3_BUCKET_NAME, filename, temp_path)
                chunks = load_and_split(temp_path, filename)
                
                if chunks:
                    for chunk in chunks:
                        chunk.metadata["source_filename"] = filename
                        chunk.metadata["doc_id"] = doc_id

                    QdrantVectorStore.from_documents(
                        chunks,
                        embeddings,
                        sparse_embedding=sparse_embeddings,
                        retrieval_mode="hybrid",
                        url=QDRANT_URL,
                        collection_name=QDRANT_COLLECTION,
                    )

                db.execute(
                    text(
                        "UPDATE documents "
                        "SET status = :status, chunk_count = :chunk_count, error_message = NULL "
                        "WHERE id = :id"
                    ),
                    {"status": "embedded", "chunk_count": len(chunks), "id": doc_id},
                )
                db.commit()
                logger.info(f"Successfully embedded document {doc_id} with {len(chunks)} chunks")

            except Exception as exc:
                db.rollback()
                logger.error(f"Failed to process document {doc_id} ({filename}): {exc}", exc_info=True)
                db.execute(
                    text(
                        "UPDATE documents "
                        "SET status = :status, error_message = :error_message "
                        "WHERE id = :id"
                    ),
                    {"status": "failed", "error_message": str(exc), "id": doc_id},
                )
                db.commit()
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

    finally:
        db.close()


if __name__ == "__main__":
    process_documents()
