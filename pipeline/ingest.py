import os
import tempfile

import boto3
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore
from langchain_text_splitters import CharacterTextSplitter
from pyspark.sql import SparkSession
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from qdrant_client.models import SparseVectorParams
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 1. Setup Postgres Connection
engine = create_engine("postgresql://admin:password123@localhost:5432/ragdb")
SessionLocal = sessionmaker(bind=engine)

# 2. Setup MinIO Client
s3_client = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="admin",
    aws_secret_access_key="password123",
)
BUCKET = "rag-documents"


def process_documents():
    db = SessionLocal()

    # 3. Find all documents awaiting processing
    result = db.execute(
        text("SELECT id, filename FROM documents WHERE status = 'uploaded'")
    )
    pending_docs = result.fetchall()

    if not pending_docs:
        print("No new documents to process in the Data Lake.")
        return

    print("Starting Spark Session...")
    spark = (
        SparkSession.builder.appName("RAG_Ingestion").master("local[*]").getOrCreate()
    )

    print("Initializing Nomic Embeddings & Qdrant...")
    embeddings = OllamaEmbeddings(
        model="nomic-embed-text", base_url="http://localhost:11434"
    )
    qclient = QdrantClient("http://localhost:6333")
    collection = "knowledge_base"

    if not qclient.collection_exists(collection):
        qclient.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            sparse_vectors_config={"langchain-sparse": SparseVectorParams()},
        )

    sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

    # Note: Increased chunk size to 500 for better context with real PDFs
    text_splitter = CharacterTextSplitter(
        chunk_size=500, chunk_overlap=50, separator="\n"
    )

    # 4. Process each pending document
    for doc in pending_docs:
        doc_id = doc[0]
        filename = doc[1]
        print(f"\nProcessing {filename}...")

        # Download from MinIO to a temporary file
        temp_dir = tempfile.gettempdir()
        local_path = os.path.join(temp_dir, filename)
        s3_client.download_file(BUCKET, filename, local_path)

        # Load PDF or Text
        ext = filename.split(".")[-1].lower()
        if ext == "pdf":
            loader = PyPDFLoader(local_path)
        else:
            loader = TextLoader(local_path)

        docs = loader.load()
        chunks = text_splitter.split_documents(docs)
        print(f"Extracted {len(chunks)} chunks from document.")

        # Upload chunks to Qdrant
        QdrantVectorStore.from_documents(
            chunks,
            embeddings,
            sparse_embedding=sparse_embeddings,
            retrieval_mode="hybrid",
            url="http://localhost:6333",
            collection_name=collection,
        )

        # 5. Update status in Postgres to mark as complete
        db.execute(
            text(f"UPDATE documents SET status = 'embedded' WHERE id = {doc_id}")
        )
        db.commit()

        # Cleanup
        os.remove(local_path)
        print(f"Successfully embedded {filename}!")

    spark.stop()
    db.close()


if __name__ == "__main__":
    process_documents()
