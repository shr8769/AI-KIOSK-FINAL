import uuid
import logging
from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession
from database.models.models import Memory

logger = logging.getLogger(__name__)

# Cache SentenceTransformer model in memory globally to prevent reloading on each request
try:
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    logger.info("Loaded SentenceTransformer model 'all-MiniLM-L6-v2' successfully.")
except Exception as e:
    logger.error(f"Failed to load SentenceTransformer: {e}")
    embedding_model = None


class MemoryStore:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def store_memory(self, user_id: str, content: str, topic: str = "general") -> Memory:
        """
        Generates embedding for the memory content and inserts it into the database.
        """
        memory_id = f"mem_{uuid.uuid4().hex[:12]}"
        
        embedding = None
        if embedding_model:
            try:
                emb_list = embedding_model.encode(content).tolist()
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
