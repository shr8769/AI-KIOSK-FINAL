"""
Session Management Route — GET/POST /session
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


class SessionInfo(BaseModel):
    session_id: str
    status: str = "active"
    duration_seconds: int = 0
    turns_completed: int = 0
    language: str = "en"
    user_id: Optional[str] = None


@router.get("/session/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve session information and resolve session_id -> user_id -> profile.
    """
    logger.info(f"Retrieving session: {session_id}")
    result = await db.execute(
        select(Session).filter(Session.session_id == session_id)
    )
    db_session = result.scalars().first()
    
    if not db_session:
        # Fallback for compatibility or if the DB has not been seeded yet
        if session_id == "demo_session_id":
            return SessionInfo(
                session_id=session_id,
                status="active",
                duration_seconds=120,
                turns_completed=3,
                language="en",
                user_id="usr_demo_123"
            )
        raise HTTPException(status_code=404, detail="Session not found")
        
    return SessionInfo(
        session_id=db_session.session_id,
        status="active",
        duration_seconds=0,
        turns_completed=0,
        language="en",
        user_id=db_session.user_id
    )


@router.post("/session/{session_id}/close")
async def close_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Close a session, summarize any remaining dialog turns, store them, and clear session logs.
    """
    logger.info(f"Closing session: {session_id}")
    
    # 1. Retrieve dialog history
    history = SessionHistoryManager.get_history(session_id)
    turns_count = len(history)
    
    # 2. Archive remaining history if present
    if turns_count > 0:
        result = await db.execute(select(Session).filter(Session.session_id == session_id))
        db_session = result.scalars().first()
        if db_session:
            user_id = db_session.user_id
            history_text = SessionHistoryManager.get_history_text(session_id)
            logger.info(f"Session {session_id} is closing. Archiving final {turns_count} turns into memories for user {user_id}.")
            try:
                manager = MemoryManager(db)
                await manager.store_conversation_segment(user_id=user_id, conversation_text=history_text)
            except Exception as e:
                logger.error(f"Error storing final memories during session close: {e}")
        else:
            logger.warning(f"Session {session_id} not found in database; cannot archive final memories.")
            
        # 3. Clear session history log
        SessionHistoryManager.clear_history(session_id)
        
    return {
        "session_id": session_id,
        "action": "session_closed",
        "duration_seconds": 0,
        "turns_completed": turns_count
    }
