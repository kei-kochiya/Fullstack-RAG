from pyspark.sql import SparkSession
from langchain_text_splitters import CharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
from langchain_core.documents import Document

# 1. Initialize PySpark Session
print("Starting Spark Session...")
spark = SparkSession.builder \
    .appName("RAG_Ingestion") \
    .master("local[*]") \
    .getOrCreate()

# 2. Read raw data using PySpark
print("Reading data.txt...")
df = spark.read.text("data.txt")
rows = df.collect()
raw_text = "\n".join([row.value for row in rows])

# 3. Chunk the text
print("Chunking text...")
text_splitter = CharacterTextSplitter(chunk_size=50, chunk_overlap=0, separator="\n")
chunks = text_splitter.split_text(raw_text)

# Convert strings to LangChain Document objects
documents = [Document(page_content=chunk) for chunk in chunks]

# 4. Set up Ollama Embeddings (using the Gemma model we downloaded)
print("Initializing Ollama Embeddings...")
embeddings = OllamaEmbeddings(
    model="nomic-embed-text", # or gemma2:9b depending on what you downloaded
    base_url="http://localhost:11434"
)

# 5. Connect to Qdrant and insert the vectors
print("Connecting to Qdrant and saving vectors...")
client = QdrantClient("http://localhost:6333")
collection_name = "knowledge_base"

# Ensure collection exists
if not client.collection_exists(collection_name):
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE), # Gemma 2b/9b embedding size
    )

# Save documents to Qdrant
QdrantVectorStore.from_documents(
    documents,
    embeddings,
    url="http://localhost:6333",
    collection_name=collection_name,
)

print("Ingestion Complete!")
spark.stop()
