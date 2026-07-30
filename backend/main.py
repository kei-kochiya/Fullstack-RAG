import json
import uuid

import boto3
import models
from database import engine, get_db
from fastapi import Depends, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder
from sqlalchemy.orm import Session

app = FastAPI(title="RAG Backend API")
models.Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

qdrant_client = QdrantClient("http://localhost:6333")
embeddings = OllamaEmbeddings(
    model="nomic-embed-text", base_url="http://localhost:11434"
)

sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")

vector_store = QdrantVectorStore(
    client=qdrant_client,
    collection_name="knowledge_base",
    embedding=embeddings,
    sparse_embedding=sparse_embeddings,
    retrieval_mode="hybrid",
)

print("Loading Re-ranker model...")
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

llm = OllamaLLM(model="gemma2:2b", base_url="http://localhost:11434")

prompt_template = PromptTemplate.from_template("""
You are a highly intelligent assistant. Use the following context to answer the user's question. 
If you cannot answer using the context provided, politely say that you don't have enough information.

Chat History:
{history}

Context:
{context}

Question:
{question}

Answer:
""")


class ChatRequest(BaseModel):
    question: str
    session_id: str = "default_session"


# --- MinIO Setup ---
s3_client = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="admin",
    aws_secret_access_key="password123",
)
BUCKET_NAME = "rag-documents"

# Ensure the bucket exists
try:
    s3_client.head_bucket(Bucket=BUCKET_NAME)
except Exception:
    s3_client.create_bucket(Bucket=BUCKET_NAME)


# --- Upload Endpoint ---
@app.post("/upload")
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Create a unique filename so we don't overwrite files with the same name
    file_extension = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"

    # 2. Upload the raw file to MinIO
    s3_client.upload_fileobj(file.file, BUCKET_NAME, unique_filename)

    # 3. Save a record of this document into PostgreSQL
    db_doc = models.Document(filename=unique_filename, status="uploaded")
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)

    return {
        "message": "Successfully uploaded to Data Lake!",
        "filename": unique_filename,
        "db_id": db_doc.id,
    }


@app.post("/chat")
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    print(f"Received question: {request.question}")

    # 1. Fetch past conversation history from Postgres
    history_records = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.session_id == request.session_id)
        .order_by(models.ChatHistory.timestamp.asc())
        .limit(10)
        .all()
    )

    # Format the history into a single string for the prompt
    history_text = "\n".join(
        [f"{r.role.capitalize()}: {r.content}" for r in history_records]
    )
    if not history_text:
        history_text = "No prior history."

    # 2. Save the user's new question to the database
    db_user_msg = models.ChatHistory(
        session_id=request.session_id, role="user", content=request.question
    )
    db.add(db_user_msg)

    # 2.5 Hybrid Search: Rewrite query for better RAG results
    if history_text != "No prior history.":
        rewrite_prompt = PromptTemplate.from_template(
            "Given the chat history, rewrite the user's question into a standalone question. Do not answer it, just rewrite it.\n\n"
            "History:\n{history}\n\n"
            "Question: {question}\n\n"
            "Standalone Question:"
        )
        search_query = llm.invoke(
            rewrite_prompt.format(history=history_text, question=request.question)
        ).strip()
        print(f"Rewrote query to: {search_query}")
    else:
        search_query = request.question

    # 3. Retrieve Context from Qdrant
    # Pull 10 candidates using Hybrid Search instead of just 2!
    results = vector_store.similarity_search(search_query, k=10)

    # 3.5 Re-ranking
    # Score all 10 candidates against the search_query using the CrossEncoder
    candidates = [doc.page_content for doc in results]
    pairs = [[search_query, candidate] for candidate in candidates]
    scores = reranker.predict(pairs)

    # Sort them by score (highest first) and take the top 2 absolute best contexts
    scored_results = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    best_contexts = [doc for score, doc in scored_results[:2]]

    context = "\n\n".join(best_contexts)

    # 4. Generate the Answer with Gemma
    prompt = prompt_template.format(
        history=history_text, context=context, question=request.question
    )
    answer = llm.invoke(prompt)

    # 5. Save Gemma's answer to the database
    db_ai_msg = models.ChatHistory(
        session_id=request.session_id, role="assistant", content=answer
    )
    db.add(db_ai_msg)
    db.commit()  # Save both messages to Postgres!

    return {"answer": answer, "context_used": context}


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, db: Session = Depends(get_db)):
    print(f"Received STREAMING question: {request.question}")
    
    # 1. Fetch History
    history_records = db.query(models.ChatHistory).filter(models.ChatHistory.session_id == request.session_id).order_by(models.ChatHistory.timestamp.asc()).limit(10).all()
    history_text = "\n".join([f"{r.role.capitalize()}: {r.content}" for r in history_records])
    if not history_text:
        history_text = "No prior history."
        
    # 2. Rewrite Query
    if history_text != "No prior history.":
        rewrite_prompt = PromptTemplate.from_template("Given the chat history, rewrite the user's question into a standalone question. Do not answer it, just rewrite it.\n\nHistory:\n{history}\n\nQuestion: {question}\n\nStandalone Question:")
        search_query = llm.invoke(rewrite_prompt.format(history=history_text, question=request.question)).strip()
        print(f"Rewrote query to: {search_query}")
    else:
        search_query = request.question
        
    # 3. Hybrid Search + Re-ranking
    results = vector_store.similarity_search(search_query, k=10)
    candidates = [doc.page_content for doc in results]
    scores = reranker.predict([[search_query, candidate] for candidate in candidates])
    best_contexts = [doc for score, doc in sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)[:2]]
    context = "\n\n".join(best_contexts)
    
    # 4. Generate the Prompt
    prompt = prompt_template.format(history=history_text, context=context, question=request.question)
    
    # 5. Define the asynchronous generator for Server-Sent Events
    async def event_generator():
        yield f"data: {json.dumps({'context_used': context})}\n\n"
        
        full_answer = ""
        # Use astream instead of stream so we don't block the FastAPI event loop!
        async for chunk in llm.astream(prompt):
            full_answer += chunk
            yield f"data: {json.dumps({'token': chunk})}\n\n"
            
        # Open a completely new Database Session to save, because the original
        # FastAPI request session closes while this generator is still streaming!
        from database import SessionLocal
        with SessionLocal() as local_db:
            local_db.add(models.ChatHistory(session_id=request.session_id, role="user", content=request.question))
            local_db.add(models.ChatHistory(session_id=request.session_id, role="assistant", content=full_answer))
            local_db.commit()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    print("Starting API on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
