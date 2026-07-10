"""
RAG Route — POST /rag (Retrieval-Augmented Generation)
Owner: Harsha
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database.postgres.connection import get_db
from database.models.models import Session
from backend.app.services.session_history_manager import SessionHistoryManager
from backend.app.services.memory_manager import MemoryManager

logger = logging.getLogger(__name__)
router = APIRouter()


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
    answer = f"[MOCK] Info matching '{request.query}' in domain '{request.domain}'."
    
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
        source_documents=[],
        confidence=0.85
    )
