import os
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://admin:password123@localhost:5432/ragdb"

    # Storage (MinIO / S3)
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "admin"
    s3_secret_key: str = "password123"
    s3_bucket_name: str = "rag-documents"

    # Vector DB (Qdrant)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "knowledge_base"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_llm_model: str = "gemma2:2b"

    # Re-ranker
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Security & Server
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    max_upload_size_mb: int = 25

    @property
    def allowed_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
