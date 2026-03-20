"""
Vector Memory Service using AstraDB + Jina AI Embeddings API
─────────────────────────────────────────────────────────────
Uses Jina AI REST API for embeddings → zero local model RAM (~0 MB).
Fits comfortably inside Render's 512 MB free tier.
Model: jina-embeddings-v3  (1024-dim, SOTA retrieval quality)
Jina free tier: 1 million tokens/month
"""
import time
import hashlib
from typing import Any

import httpx
from loguru import logger
from astrapy import DataAPIClient

from config import get_settings

settings = get_settings()

COLLECTION_NAME = "kg_documents"
JINA_EMBED_URL = "https://api.jina.ai/v1/embeddings"
EMBEDDING_DIM = 1024          # jina-embeddings-v3 output dimension
MAX_INPUT_CHARS = 8192        # Jina's per-text limit (chars, not tokens)


class VectorService:
    """
    AstraDB vector store backed by Jina AI embeddings.
    No local ML model → near-zero RAM usage.
    """

    def __init__(self):
        self.collection = None
        self._http = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {settings.jina_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )
        logger.info("VectorService initialised (Jina AI API, no local model)")

    async def connect(self):
        """Initialise AstraDB collection (1024-dim cosine)."""
        try:
            client = DataAPIClient(settings.astra_db_token)
            db = client.get_database_by_api_endpoint(
                settings.astra_db_api_endpoint
            )
            try:
                self.collection = db.create_collection(
                    COLLECTION_NAME,
                    dimension=EMBEDDING_DIM,
                    metric="cosine",
                )
                logger.success(f"Created AstraDB collection: {COLLECTION_NAME}")
            except Exception:
                self.collection = db.get_collection(COLLECTION_NAME)
                logger.info(f"Using existing AstraDB collection: {COLLECTION_NAME}")

            # Smoke-test Jina
            await self._embed("hello world")
            logger.success("✅ AstraDB + Jina AI embeddings ready")
        except Exception as e:
            logger.error(f"VectorService connect failed: {e}")
            raise

    async def _embed(self, text: str) -> list[float]:
        """Call Jina AI REST API and return a 1024-dim embedding vector."""
        text = text[:MAX_INPUT_CHARS].strip() or "empty"
        try:
            resp = await self._http.post(
                JINA_EMBED_URL,
                json={
                    "model": settings.jina_embedding_model,
                    "task": "retrieval.passage",
                    "dimensions": EMBEDDING_DIM,
                    "input": [text],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            logger.warning(f"Jina embed failed: {e}")
            return [0.0] * EMBEDDING_DIM

    async def _embed_query(self, text: str) -> list[float]:
        """Same as _embed but uses retrieval.query task."""
        text = text[:MAX_INPUT_CHARS].strip() or "empty"
        try:
            resp = await self._http.post(
                JINA_EMBED_URL,
                json={
                    "model": settings.jina_embedding_model,
                    "task": "retrieval.query",
                    "dimensions": EMBEDDING_DIM,
                    "input": [text],
                },
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception as e:
            logger.warning(f"Jina query embed failed: {e}")
            return [0.0] * EMBEDDING_DIM

    async def store_document(
        self,
        user_id: int,
        session_id: str,
        text: str,
        filename: str,
        concepts: list[str],
        domain: str,
        summary: str,
    ) -> str:
        """Embed + store a document in AstraDB."""
        try:
            doc_id = hashlib.md5(
                f"{user_id}:{session_id}:{filename}".encode()
            ).hexdigest()

            embed_text = summary or text[:500]
            vector = await self._embed(embed_text)

            document = {
                "_id": doc_id,
                "$vector": vector,
                "user_id": str(user_id),
                "session_id": session_id,
                "filename": filename,
                "domain": domain,
                "summary": summary[:1000],
                "concepts": concepts[:50],
                "text_preview": text[:2000],
                "timestamp": time.time(),
            }

            # Use find_one_and_replace with upsert=True for document storage
            self.collection.find_one_and_replace(
                filter={"_id": doc_id},
                replacement=document,
                upsert=True
            )
            logger.success(f"Stored document {doc_id[:8]}… in AstraDB")
            return doc_id
        except Exception as e:
            logger.error(f"store_document failed: {e}")
            return ""

    async def semantic_search(
        self, user_id: int, query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Semantic search."""
        try:
            query_vector = await self._embed_query(query)
            results = self.collection.find(
                filter={"user_id": str(user_id)},
                sort={"$vector": query_vector},
                limit=top_k,
                projection={"$vector": False},
            )
            return list(results)
        except Exception as e:
            logger.error(f"semantic_search failed: {e}")
            return []

    async def delete_user_data(self, user_id: int) -> int:
        """Delete all documents for a user."""
        try:
            result = self.collection.delete_many(
                filter={"user_id": str(user_id)}
            )
            return getattr(result, "deleted_count", 0)
        except Exception as e:
            logger.error(f"delete_user_data failed: {e}")
            return 0

    async def close(self):
        await self._http.aclose()
