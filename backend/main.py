from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_core.prompts import PromptTemplate

# 1. Initialize FastAPI
app = FastAPI(title="RAG Backend API")

# Add CORS so our React frontend will be allowed to talk to it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Connect to our Qdrant Vector Database
qdrant_client = QdrantClient("http://localhost:6333")
embeddings = OllamaEmbeddings(
    model="nomic-embed-text",  # Must match what we ingested with!
    base_url="http://localhost:11434"
)
vector_store = QdrantVectorStore(
    client=qdrant_client, 
    collection_name="knowledge_base", 
    embedding=embeddings
)

# 3. Initialize the Generative LLM (Gemma)
llm = OllamaLLM(model="gemma2:2b", base_url="http://localhost:11434")

# 4. Define our strict Prompt Template
prompt_template = PromptTemplate.from_template("""
You are a highly intelligent assistant. Use the following context to answer the user's question. 
If you cannot answer using the context provided, politely say that you don't have enough information.

Context:
{context}

Question:
{question}

Answer:
""")

# Define what the incoming request body looks like
class ChatRequest(BaseModel):
    question: str

# 5. Create the Chat Endpoint
@app.post("/chat")
def chat(request: ChatRequest):
    print(f"Received question: {request.question}")
    
    # A. Search the vector database for similar chunks
    results = vector_store.similarity_search(request.question, k=2)
    
    # B. Combine the chunks into a single context string
    context = "\n\n".join([doc.page_content for doc in results])
    print(f"Retrieved context:\n{context}")
    
    # C. Build the prompt
    prompt = prompt_template.format(context=context, question=request.question)
    
    # D. Ask Gemma to answer!
    answer = llm.invoke(prompt)
    
    return {
        "answer": answer, 
        "context_used": context
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting API on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
