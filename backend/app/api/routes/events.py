"""
Event Ingestion Route — POST /api/v1/events
Owner: Harsha (Engineering Lead)
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import ConnectionManager, get_connection_manager
from app.core.session_store import create_session, update_session_metadata

logger = logging.getLogger(__name__)
router = APIRouter()


class EventRequest(BaseModel):
    event_type: str
    camera_id: str
    timestamp: Optional[datetime] = None
    payload: Dict[str, Any] = {}


class EventResponse(BaseModel):
    status: str
    action_taken: str
    session_id: Optional[str] = None
    message: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    is_returning_user: bool = False


async def background_greeting_task(session_id: str, greeting_text: str, mgr: ConnectionManager):
    audio_url = None
    try:
        from app.models.schemas import TTSRequest
        from app.services.speech.tts_service import tts_service
        tts_resp = await tts_service.synthesize(
            TTSRequest(session_id=session_id, text=greeting_text, language="en")
        )
        audio_url = tts_resp.audio_url
    except Exception as e:
        logger.warning(f"Background TTS generic greeting failed: {e}")

    try:
        await mgr.send(session_id, {
            "type": "greeting",
            "payload": {"message": greeting_text, "audio_url": audio_url}
        })
    except Exception as e:
        logger.warning(f"Background WS send for greeting failed: {e}")


@router.post("/events", response_model=EventResponse)
async def ingest_event(
    request: EventRequest,
    background_tasks: BackgroundTasks,
    mgr: ConnectionManager = Depends(get_connection_manager),
):
    """
    Unified ingestion endpoint for all edge sensor events.
    The backend remains the Single Source of Truth for session management.
    """
    logger.info(f"Received Event: {request.event_type} | Camera: {request.camera_id}")

    if request.event_type == "PERSON_DETECTED":
        session_id = f"ses_{uuid.uuid4().hex[:12]}"
        logger.info(f"Creating new session {session_id} for camera {request.camera_id}")

        # SQLite/Redis session store fallback
        await create_session(
            session_id=session_id,
            metadata={
                "camera_id": request.camera_id,
                "user_id": None,
                "role": "guest",
                "is_returning": False,
            }
        )

        # Store guest session in PostgreSQL
        try:
            from database.models.models import Session as PGSession
            from database.postgres.connection import AsyncSessionLocal
            async with AsyncSessionLocal() as db_session:
                pg_sess = PGSession(session_id=session_id, user_id="usr_guest")
                await db_session.merge(pg_sess)
                await db_session.commit()
        except Exception as db_e:
            logger.warning(f"Failed to save guest session to PostgreSQL: {db_e}")

        # Personalised greeting instructions
        greeting_text = "Welcome to PES University. Please tell me which language you would like to interact with: English, Kannada, or Hindi?"

        try:
            await mgr.broadcast({
                "type": "detection",
                "payload": {"person_detected": True, "session_id": session_id}
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast detection to WebSocket: {e}")

        # Defer TTS and greeting to background task to prevent edge API gateway timeout
        background_tasks.add_task(background_greeting_task, session_id, greeting_text, mgr)

        return EventResponse(
            status="success",
            action_taken="session_created",
            session_id=session_id,
            message=greeting_text,
            user_role="guest",
        )

    elif request.event_type == "FACE_DETECTED":
        embedding: List[float] = request.payload.get("embedding", [])
        session_id: str = request.payload.get("session_id", "")

        if not embedding:
            logger.warning("FACE_DETECTED received with empty embedding — ignored.")
            return EventResponse(status="error", action_taken="missing_embedding")

        if not session_id:
            logger.warning("FACE_DETECTED received with no session_id — ignored.")
            return EventResponse(status="error", action_taken="missing_session_id")

        # Query via Firebase to find matched face
        matched_user = None
        try:
            from app.services.firebase_client import match_face
            matched_user = match_face(embedding)
        except Exception as e:
            logger.error(f"[FR-8] Face matching via Firebase failed: {e}")

        if matched_user:
            user_id = matched_user["user_id"]
            user_name = matched_user["name"]
            user_role = matched_user.get("role", "guest")
            is_returning = True
            first_name = user_name.split()[0] if user_name.strip() else "there"
            greeting_text = f"Welcome back, {first_name}! Great to see you again."
            logger.info(f"[FR-8] Identified: {user_name} | role={user_role} | session={session_id}")
        else:
            user_id = None
            user_name = None
            user_role = "guest"
            is_returning = False
            greeting_text = "Welcome to PES University! How can I help you today?"
            logger.info(f"[FR-8] Unknown face — treating as guest (session={session_id})")

        # Persist identity into SQLite/Redis session store
        await update_session_metadata(
            session_id=session_id,
            updates={
                "user_id": user_id,
                "user_name": user_name,
                "role": user_role,
                "is_returning": is_returning,
            },
        )

        # Update user mapping in PostgreSQL sessions table
        try:
            from database.models.models import Session as PGSession
            from database.postgres.connection import AsyncSessionLocal
            async with AsyncSessionLocal() as db_session:
                pg_sess = PGSession(session_id=session_id, user_id=user_id if user_id else "usr_guest")
                await db_session.merge(pg_sess)
                await db_session.commit()
        except Exception as db_e:
            logger.error(f"Failed to update session user_id in PostgreSQL: {db_e}")

        # Personalised Recommendations (best-effort)
        recommendations = []
        # In the future, recommendations can be fetched from opportunities database in PG.
        # Currently, retrieve from opportunities.json if matched_user is active
        if user_id:
            try:
                import json
                import os
                opp_path = "knowledge/sources/opportunities.json"
                if os.path.exists(opp_path):
                    with open(opp_path, "r", encoding="utf-8") as f:
                        opps = json.load(f)

                    # Match user interests
                    user_interests = matched_user.get("preferences", {}).get("interests", [])
                    if user_interests:
                        # Simple tag matcher
                        for opp in opps:
                            opp_tags = [t.lower() for t in opp.get("tags", [])]
                            if any(ui.lower() in opp_tags for ui in user_interests):
                                recommendations.append(opp)

                    if not recommendations and opps:
                        recommendations = opps[:3]

                if recommendations:
                    rec = recommendations[0]
                    greeting_text += (
                        f" Based on your interest in {rec.get('tags', ['your field'])[0]}, "
                        f"you might want to check out: {rec.get('title', 'a new opportunity')}."
                    )
            except Exception as e:
                logger.warning(f"[FR-10] Recommendations fetch failed: {e}")

        # Push identity immediately to the frontend
        try:
            await mgr.send(session_id, {
                "type": "user_identified",
                "payload": {
                    "user_id": user_id,
                    "name": user_name,
                    "role": user_role,
                    "is_returning": is_returning,
                    "recommendations": recommendations[:3],
                },
            })
        except Exception as e:
            logger.warning(f"WS send for user_identified failed: {e}")

        # Defer personalized greeting TTS
        background_tasks.add_task(background_greeting_task, session_id, greeting_text, mgr)

        return EventResponse(
            status="success",
            action_taken="face_matched" if matched_user else "guest_session",
            session_id=session_id,
            message=greeting_text,
            user_id=user_id,
            user_name=user_name,
            user_role=user_role,
            is_returning_user=is_returning,
        )

    elif request.event_type == "PERSON_LEFT":
        logger.info(f"Closing session for camera {request.camera_id}")
        try:
            await mgr.broadcast({"type": "detection", "payload": {"person_detected": False}})
        except Exception as e:
            logger.warning(f"Failed to broadcast departure to WebSocket: {e}")

        return EventResponse(status="success", action_taken="session_closed", session_id="dummy_id")

    elif request.event_type == "HEARTBEAT":
        logger.debug(f"Heartbeat from {request.camera_id}: {request.payload}")
        return EventResponse(status="success", action_taken="heartbeat_logged")

    else:
        logger.warning(f"Unknown event type: {request.event_type}")
        raise HTTPException(status_code=400, detail="Unknown event type")
