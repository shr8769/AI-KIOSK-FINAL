"""
Event Ingestion Route — POST /api/v1/events
Owner: Harsha (Engineering Lead)
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.dependencies import ConnectionManager, get_connection_manager

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


@router.post("/events", response_model=EventResponse)
async def ingest_event(
    request: EventRequest,
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

        # Generate TTS for the greeting
        from app.models.schemas import TTSRequest
        from app.services.speech.tts_service import tts_service
        
        greeting_text = "Welcome to PES University. Please tell me which language you would like to interact with: English, Kannada, or Hindi?"
        audio_url = None
        try:
            tts_req = TTSRequest(
                session_id=session_id,
                text=greeting_text,
                language="en"
            )
            tts_resp = await tts_service.synthesize(tts_req)
            audio_url = tts_resp.audio_url
            logger.info(f"Generated greeting TTS: {audio_url}")
        except Exception as e:
            logger.warning(f"Failed to generate TTS for greeting: {e}")

        # Trigger avatar greeting state change via WebSocket using mgr dependency
        try:
            await mgr.broadcast({
                "type": "detection",
                "payload": {"person_detected": True, "session_id": session_id}
            })
            await mgr.broadcast({
                "type": "greeting",
                "payload": {
                    "message": greeting_text,
                    "audio_url": audio_url
                }
            })

        except Exception as e:
            logger.warning(f"Failed to broadcast detection to WebSocket: {e}")

        return EventResponse(
            status="success",
            action_taken="session_created",
            session_id=session_id,
            message=greeting_text,
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
