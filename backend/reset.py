from qdrant_client import QdrantClient
from sqlalchemy import create_engine, text

# 1. Delete Qdrant Collection
client = QdrantClient("http://localhost:6333")
if client.collection_exists("knowledge_base"):
    client.delete_collection("knowledge_base")

# 2. Reset Postgres Document Status
engine = create_engine("postgresql://admin:password123@localhost:5432/ragdb")
with engine.connect() as conn:
    conn.execute(text("UPDATE documents SET status = 'uploaded'"))
    conn.commit()
print("Reset successful!")
