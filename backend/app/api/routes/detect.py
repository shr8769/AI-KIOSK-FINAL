"""
Detection Route — POST /detect & DELETE /detect/{session_id}
Owner: Harsha (Engineering Lead) — endpoint
       Haseeb (Project Lead) — fires events from detection module
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from database.models.models import Session, User
from database.postgres.connection import get_db
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.services.memory_manager import MemoryManager

logger = logging.getLogger(__name__)
router = APIRouter()


class DetectRequest(BaseModel):
    camera_id: str = "cam_front_01"
    confidence: float
    bounding_box: dict
    detected_at: Optional[datetime] = None
    frame_width: int = 1920
    frame_height: int = 1080
    user_id: Optional[str] = None
    name: Optional[str] = None


class DetectResponse(BaseModel):
    session_id: str
    action: str
    greeting_text: str
    greeting_audio_url: str
    language_prompt: str
    user_id: str


@router.post("/detect", response_model=DetectResponse)
async def create_session_on_detection(request: DetectRequest, db: AsyncSession = Depends(get_db)):
    """
    Called by detection module when a person is detected.
    Creates/resolves user and new session in the database, loading profiles and past memories.
    """
    logger.info(f"Person detected | camera={request.camera_id} | confidence={request.confidence:.2f}")

    # Resolve user
    user_id = request.user_id
    if not user_id:
        user_id = f"usr_auto_{uuid.uuid4().hex[:8]}"

    name = request.name
    if not name:
        name = f"New User {user_id[-8:]}"

    # Auto-register user if not present
    result = await db.execute(select(User).filter(User.user_id == user_id))
    db_user = result.scalars().first()

    if not db_user:
        db_user = User(
            user_id=user_id,
            name=name,
            role_id="user",
            preferences={}
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        logger.info(f"Automatically created user row: {user_id} ({name})")

    # Auto-create session
    session_id = f"ses_{uuid.uuid4().hex[:12]}"
    db_session = Session(
        session_id=session_id,
        user_id=user_id
    )
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)
    logger.info(f"Automatically created session row: {session_id} -> {user_id}")

    # Retrieve past memories for greeting prompt injection
    memory_manager = MemoryManager(db)
    memories_context = ""
    try:
        memories_context = await memory_manager.get_context_injection(user_id=user_id, query_text="general info", limit=3)
    except Exception as e:
        logger.error(f"Error fetching past memories: {e}")

    # Build personalized greeting text
    greeting_text = f"Hello {db_user.name}! Welcome back to PES University."
    if memories_context:
        # Simulate injecting retrieved memories into LLM prompt / greeting display
        greeting_text += f" [Loaded Context: {len(memories_context.strip().splitlines()) - 1} memories injected]"
    else:
        greeting_text += " How can I help you today?"

    return DetectResponse(
        session_id=session_id,
        action="session_created",
        greeting_text=greeting_text,
        greeting_audio_url="/static/audio/greeting_en.mp3",
        language_prompt="Please speak in English, Kannada, or Hindi.",
        user_id=user_id
    )


@router.delete("/detect/{session_id}")
async def close_session_on_exit(session_id: str):
    """
    Called when person leaves the frame. Closes the session.
    """
    logger.info(f"Person left | session={session_id}")

    return {
        "session_id": session_id,
        "action": "session_closed",
        "duration_seconds": 0,
        "turns_completed": 0
    }
