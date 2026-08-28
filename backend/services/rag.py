import asyncio
import logging
from typing import AsyncGenerator, List, Tuple
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore
from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder
from config import Settings

logger = logging.getLogger(__name__)

ANSWER_PROMPT = PromptTemplate.from_template("""
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

REWRITE_PROMPT = PromptTemplate.from_template("""
Given the chat history, rewrite the user's question into a standalone question. Do not answer it, only rewrite it.

History:
{history}

Question: {question}

Standalone Question:
""")


class RAGService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.qdrant_client = QdrantClient(url=settings.qdrant_url)
        
        self.embeddings = OllamaEmbeddings(
            model=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
        )
        self.sparse_embeddings = FastEmbedSparse(model_name="Qdrant/bm25")
        
        self.vector_store = QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=settings.qdrant_collection,
            embedding=self.embeddings,
            sparse_embedding=self.sparse_embeddings,
            retrieval_mode="hybrid",
        )
        
        self.reranker = CrossEncoder(settings.reranker_model)
        self.llm = OllamaLLM(
            model=settings.ollama_llm_model,
            base_url=settings.ollama_base_url,
        )

    async def rewrite_query(self, question: str, history_text: str) -> str:
        if not history_text or history_text == "No prior history.":
            return question

        prompt = REWRITE_PROMPT.format(history=history_text, question=question)
        try:
            rewritten = await asyncio.to_thread(self.llm.invoke, prompt)
            cleaned = rewritten.strip()
            return cleaned if cleaned else question
        except Exception as exc:
            logger.warning(f"Query rewrite failed, falling back to original: {exc}")
            return question

    async def retrieve_contexts(
        self, query: str, candidate_k: int = 10, final_k: int = 2
    ) -> Tuple[List[str], str]:
        def _search_and_rerank():
            try:
                results = self.vector_store.similarity_search(query, k=candidate_k)
            except Exception as exc:
                logger.warning(f"Vector search failed or collection empty: {exc}")
                return []

            if not results:
                return []

            candidates = [doc.page_content for doc in results if doc.page_content.strip()]
            if not candidates:
                return []

            pairs = [[query, candidate] for candidate in candidates]
            scores = self.reranker.predict(pairs)

            ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
            return [doc for _, doc in ranked[:final_k]]

        best_contexts = await asyncio.to_thread(_search_and_rerank)
        context_str = "\n\n".join(best_contexts)
        return best_contexts, context_str

    def format_prompt(self, question: str, history_text: str, context: str) -> str:
        return ANSWER_PROMPT.format(
            history=history_text if history_text else "No prior history.",
            context=context if context else "No context available.",
            question=question,
        )

    async def generate_answer(self, prompt: str) -> str:
        return await asyncio.to_thread(self.llm.invoke, prompt)

    async def stream_answer(self, prompt: str) -> AsyncGenerator[str, None]:
        async for chunk in self.llm.astream(prompt):
            yield chunk
