import logging

from database.models.models import Memory
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# We access the cached embedding model from memory_store
from app.services.memory_store import get_embedding_model

logger = logging.getLogger(__name__)


class MemoryRetriever:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def retrieve_memories(self, user_id: str, query_text: str, limit: int = 3) -> list:
        """
        Retrieves relevant memories using vector similarity search (cosine distance).
        Falls back to keyword matching if pgvector/embeddings are unavailable.
        """
        model = get_embedding_model()
        if not model:
            logger.warning("Embedding model unavailable. Performing keyword-fallback retrieval.")
            return await self._fallback_retrieve(user_id, query_text, limit)

        try:
            query_emb = model.encode(query_text).tolist()

            # Use pgvector cosine_distance sorting
            result = await self.db.execute(
                select(Memory)
                .filter(Memory.user_id == user_id)
                .order_by(Memory.embedding.cosine_distance(query_emb))
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error performing vector similarity search: {e}. Falling back to keyword search.")
            return await self._fallback_retrieve(user_id, query_text, limit)

    async def _fallback_retrieve(self, user_id: str, query_text: str, limit: int) -> list:
        """
        Keyword search fallback using SQL LIKE constraints.
        """
        try:
            words = [w.strip() for w in query_text.lower().split() if w.strip()]
            stmt = select(Memory).filter(Memory.user_id == user_id)

            if words:
                conditions = [Memory.content.ilike(f"%{w}%") for w in words]
                stmt = stmt.filter(or_(*conditions))

            stmt = stmt.order_by(Memory.created_at.desc()).limit(limit)
            res = await self.db.execute(stmt)
            return res.scalars().all()
        except Exception as e:
            logger.error(f"Fallback retrieval failed: {e}")
            return []
