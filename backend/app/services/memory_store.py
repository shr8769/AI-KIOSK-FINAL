from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database.models.models import Memory
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

embedding_model = None

def get_embedding_model():
    global embedding_model
    if embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Loaded SentenceTransformer model 'all-MiniLM-L6-v2' successfully.")
        except Exception as e:
            logger.error(f"Failed to load SentenceTransformer: {e}")
            embedding_model = None
    return embedding_model


class MemoryStore:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def store_memory(self, user_id: str, content: str, topic: str = "general") -> Memory:
        """
        Generates embedding for the memory content and inserts it into the database.
        """
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"

        embedding = None
        model = get_embedding_model()
        if model:
            try:
                emb_list = model.encode(content).tolist()
                embedding = emb_list
            except Exception as e:
                logger.error(f"Error encoding embedding: {e}")

        db_memory = Memory(
            memory_id=memory_id,
            user_id=user_id,
            content=content,
            topic=topic,
            embedding=embedding
        )

        self.db.add(db_memory)
        await self.db.commit()
        await self.db.refresh(db_memory)

        logger.info(f"Memory stored: id={memory_id} | user={user_id} | topic='{topic}'")
        return db_memory
