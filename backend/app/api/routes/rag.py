"""
RAG Route — POST /rag (Retrieval-Augmented Generation)
Owner: Harsha
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database.postgres.connection import get_db
from database.models.models import Session
from app.services.session_history_manager import SessionHistoryManager
from app.services.memory_manager import MemoryManager
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Instantiate the Coordinator Agent if real agents are enabled
coordinator = None
if settings.USE_REAL_AGENTS:
    try:
        from agents.coordinator.coordinator_agent import CoordinatorAgent
        coordinator = CoordinatorAgent()
        logger.info("Real Coordinator Agent loaded successfully in RAG route.")
    except Exception as e:
        logger.error(f"Failed to load real Coordinator Agent: {e}")

class RAGRequest(BaseModel):
    session_id: str
    query: str
    context: Optional[str] = None
    domain: str = "admissions"
    language: str = "en"


class RAGResponse(BaseModel):
    session_id: str
    answer: str
    source_documents: list = []
    confidence: float = 0.85


@router.post("/rag", response_model=RAGResponse)
async def retrieve_and_generate(request: RAGRequest, db: AsyncSession = Depends(get_db)):
    """
    Retrieve relevant documents and generate answer.
    Maintains session history and automatically summarizes and archives conversation turns into long-term memory.
    """
    sources = []
    confidence = 0.85
    
    if settings.USE_REAL_AGENTS and coordinator:
        try:
            logger.info(f"Querying real Coordinator Agent: '{request.query}' (session: {request.session_id})")
            raw_ans = coordinator.answer(request.query, session_id=request.session_id)
            
            # Parse returned answer to separate answer and source
            if "\n\nSources:\n    " in raw_ans:
                answer, source_part = raw_ans.split("\n\nSources:\n    ", 1)
                if answer.startswith("Answer:\n"):
                    answer = answer[len("Answer:\n"):]
                sources = [source_part.strip()]
            else:
                answer = raw_ans
                sources = []
                
            # Retrieve routing details to estimate confidence
            _, conf, _, _ = coordinator.route(request.query)
            confidence = conf if conf > 0 else 0.85
        except Exception as e:
            logger.error(f"Error querying real Coordinator Agent: {e}")
            answer = f"I encountered an issue retrieving that information. Please contact the Admissions office."
            sources = []
    else:
        answer = f"[MOCK] Info matching '{request.query}' in domain '{request.domain}'."
        sources = []
    
    # Track the turn
    SessionHistoryManager.append_turn(request.session_id, request.query, answer)
    
    # Auto-archive memories if N (5) turns are reached
    history = SessionHistoryManager.get_history(request.session_id)
    if len(history) >= 5:
        # Resolve user
        result = await db.execute(select(Session).filter(Session.session_id == request.session_id))
        db_session = result.scalars().first()
        if db_session:
            user_id = db_session.user_id
            history_text = SessionHistoryManager.get_history_text(request.session_id)
            logger.info(f"Session {request.session_id} reached 5 turns. Archiving to long-term memories for user {user_id}.")
            try:
                manager = MemoryManager(db)
                await manager.store_conversation_segment(user_id=user_id, conversation_text=history_text)
                # Clear history for this session as it has been archived
                SessionHistoryManager.clear_history(request.session_id)
            except Exception as e:
                logger.error(f"Error auto-storing memories: {e}")
        else:
            logger.warning(f"Session {request.session_id} not found in database; cannot auto-archive memories.")

    return RAGResponse(
        session_id=request.session_id,
        answer=answer,
        source_documents=sources,
        confidence=confidence
    )
