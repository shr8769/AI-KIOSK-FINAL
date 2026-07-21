import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.memory_summary import MemorySummary
from app.services.memory_store import MemoryStore
from app.services.memory_retriever import MemoryRetriever

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.summary_service = MemorySummary()
        self.store_service = MemoryStore(db_session)
        self.retriever_service = MemoryRetriever(db_session)

    async def store_conversation_segment(self, user_id: str, conversation_text: str) -> dict:
        """
        Executes workflow: Conversation -> Summary & Topic -> Embedding -> Store
        """
        logger.info(f"Running store memory workflow for user {user_id}")
        
        # 1. Summary & Topic extraction
        summary_data = self.summary_service.generate_summary(conversation_text)
        summary = summary_data.get("summary")
        topic = summary_data.get("topic", "general")
        
        # 2. Store with vector embedding
        db_memory = await self.store_service.store_memory(
            user_id=user_id,
            content=summary,
            topic=topic
        )
        
        return {
            "memory_id": db_memory.memory_id,
            "summary": summary,
            "topic": topic
        }

    async def get_context_injection(self, user_id: str, query_text: str, limit: int = 3) -> str:
        """
        Retrieves top relevant past memories and formats them for context injection at session start/RAG.
        """
        logger.info(f"Retrieving past memories injection context for user {user_id} with query '{query_text}'")
        memories = await self.retriever_service.retrieve_memories(user_id, query_text, limit=limit)
        
        if not memories:
            return ""
            
        formatted_memories = []
        for mem in memories:
            formatted_memories.append(f"- {mem.content} (Topic: {mem.topic})")
            
        context_string = "\nUser's Relevant Past Memories:\n" + "\n".join(formatted_memories) + "\n"
        return context_string
