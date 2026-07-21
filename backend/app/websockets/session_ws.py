"""
backend/app/websockets/session_ws.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thin WebSocket handler. Zero heavy imports.

ALL singletons (ConnectionManager, CoordinatorAgent, RIARPipeline)
come from app.core.dependencies — never instantiated here.
"""

import asyncio
import json
import uuid
from typing import Optional

from fastapi import Depends, WebSocket, WebSocketDisconnect

from app.core.dependencies import (
    ConnectionManager,
    get_connection_manager,
)
from app.core.logging import logger
from app.core.session_store import (
    get_session,
    log_barge_in,
    mark_turn_interrupted,
)
from app.services.speech.asr_service import asr_service
from app.models.schemas import ASRRequest, TTSRequest
from app.services.speech.tts_service import tts_service

# Re-export manager for events.py
manager = get_connection_manager()

# Store active turn tokens to prevent stale turn execution
active_turn_tokens = {}

def _is_language_command(text: str):
    if not text:
        return None
    text_lower = text.strip().lower().rstrip(".").rstrip("?")
    if (
        text_lower in ["english", "eng", "ಇಂಗ್ಲಿಷ್", "ಇಂಗ್ಲೀಷ್", "इंग्लिश", "अंग्रेजी"]
        or "select english" in text_lower
        or "ಇಂಗ್ಲಿಷ್ ಆಯ್ಕೆ" in text_lower
    ):
        return "en"
    if (
        text_lower in ["kannada", "kn", "ಕನ್ನಡ", "ಕನ್ನಡ್", "कन्नड़"]
        or "ಕನ್ನಡ ಭಾಷೆ" in text_lower
        or "select kannada" in text_lower
    ):
        return "kn"
    if (
        text_lower in ["hindi", "hi", "हिंदी", "hind", "हिन्दी"]
        or "हिंदी भाषा" in text_lower
        or "select hindi" in text_lower
    ):
        return "hi"
    return None

async def websocket_session_handler(
    websocket: WebSocket,
    session_id: str,
    mgr: ConnectionManager = Depends(get_connection_manager),
):
    session = await get_session(session_id)
    if not session:
        await websocket.accept()
        await websocket.send_json({"type": "error", "payload": {"message": "Session not found", "code": "session_not_found"}})
        await websocket.close(code=4004)
        return

    await mgr.connect(session_id, websocket)
    await mgr.send_pending_broadcast(session_id, websocket)

    active_task: Optional[asyncio.Task] = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await mgr.send(session_id, {"type": "error", "payload": {"message": "Invalid JSON", "code": "invalid_json"}})
                continue

            msg_type = msg.get("type", "unknown")
            payload = msg.get("payload", {})
            logger.debug(f"WS [{session_id}] type={msg_type}")

            if msg_type == "ping":
                await mgr.send(session_id, {"type": "pong", "payload": {}})

            elif msg_type == "audio_chunk":
                if active_task and not active_task.done():
                    active_task.cancel()
                    logger.info(f"WS [{session_id}] Cancelled active task due to new audio_chunk")
                
                turn_token = str(uuid.uuid4())
                active_turn_tokens[session_id] = turn_token
                
                active_task = asyncio.create_task(
                    _handle_audio_chunk(mgr, session_id, payload, turn_token)
                )

            elif msg_type == "interrupt":
                if active_task and not active_task.done():
                    active_task.cancel()
                    logger.info(f"WS [{session_id}] Cancelled active task due to interrupt")

                turn_id = payload.get("turn_id", "unknown")
                reason = payload.get("reason", "unknown")
                position_ms = payload.get("position_ms", 0)
                logger.info(f"WS [{session_id}] Barge-in interrupt received for turn {turn_id} (Reason: {reason}, Pos: {position_ms}ms).")
                
                active_turn_tokens[session_id] = str(uuid.uuid4()) # Invalidate previous token

                await mark_turn_interrupted(session_id)
                await log_barge_in(session_id, reason, position_ms)
                await mgr.send(
                    session_id,
                    {"type": "info", "payload": {"message": "Interrupt acknowledged and logged"}},
                )

            elif msg_type == "frame":
                await mgr.send(session_id, {"type": "detection", "payload": {"person_detected": True, "confidence": 0.91}})

            elif msg_type == "text_query":
                if active_task and not active_task.done():
                    active_task.cancel()
                    logger.info(f"WS [{session_id}] Cancelled active task due to new text_query")
                
                turn_token = str(uuid.uuid4())
                active_turn_tokens[session_id] = turn_token
                
                active_task = asyncio.create_task(
                    _handle_text_query(mgr, session_id, payload, turn_token)
                )

            else:
                await mgr.send(session_id, {"type": "error", "payload": {"message": f"Unknown type: {msg_type}", "code": "unknown_type"}})

    except WebSocketDisconnect:
        mgr.disconnect(session_id)
    except Exception as e:
        logger.exception(f"WS error [{session_id}]: {e}")
        mgr.disconnect(session_id)
    finally:
        if active_task and not active_task.done():
            active_task.cancel()
            logger.info(f"WS [{session_id}] Cleaned up active task on disconnect.")


async def _handle_audio_chunk(mgr: ConnectionManager, session_id: str, payload: dict, turn_token: str) -> None:
    audio_base64 = payload.get("audio_base64")
    if not audio_base64:
        await mgr.send(
            session_id,
            {
                "type": "error",
                "payload": {"message": "Missing audio_base64", "code": "missing_audio"},
            },
        )
        return

    turn_id = payload.get("turn_id", 1)
    language_hint = payload.get("language_hint") or None

    await mgr.send(session_id, {"type": "thinking", "payload": {}})

    try:
        asr_resp = await asr_service.transcribe(
            ASRRequest(
                session_id=session_id,
                audio_base64=audio_base64,
                language_hint=language_hint,
                turn_id=turn_id,
            )
        )
        logger.info(f"ASR: '{asr_resp.transcript}' lang={asr_resp.detected_language}")

        if active_turn_tokens.get(session_id) != turn_token:
            logger.info(f"Stale turn detected in _handle_audio_chunk for session {session_id}")
            return

        await mgr.send(
            session_id,
            {
                "type": "transcript",
                "payload": {
                    "text": asr_resp.transcript,
                    "confidence": getattr(asr_resp, "confidence", 1.0),
                    "final": True,
                },
            },
        )

        raw_transcript = asr_resp.transcript
        detected_lang = language_hint or (asr_resp.detected_language or "en").lower().split("-")[0]

        from app.services.query_pipeline import run_query_pipeline

        result = await run_query_pipeline(session_id, raw_transcript, detected_lang)

        if active_turn_tokens.get(session_id) != turn_token:
            logger.info(f"Stale turn detected after pipeline for session {session_id}")
            return

        if result["type"] == "clarifying":
            await mgr.send(
                session_id,
                {
                    "type": "clarifying",
                    "payload": {
                        "text": result["text"],
                        "audio_url": result["audio_url"],
                        "ambiguity_type": result["ambiguity_type"],
                    },
                },
            )
        else:
            ans_payload = {
                "text": result["text"],
                "audio_url": result["audio_url"],
                "sources": result["sources"],
            }
            if result.get("navigation"):
                ans_payload["navigation"] = result["navigation"]

            await mgr.send(session_id, {"type": "answer", "payload": ans_payload})
    except asyncio.CancelledError:
        logger.info(f"WS [{session_id}] Audio chunk processing task cancelled.")
        raise
    except Exception as e:
        logger.exception(f"Pipeline error [{session_id}]: {e}")
        fallback_msg = "I'm sorry, I encountered a temporary issue while processing your request. Please try again."
        await mgr.send(
            session_id,
            {"type": "error", "payload": {"message": fallback_msg, "code": "pipeline_error"}},
        )
        try:
            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=fallback_msg, language="en")
            )
            await mgr.send(
                session_id,
                {
                    "type": "answer",
                    "payload": {
                        "text": fallback_msg,
                        "audio_url": tts_resp.audio_url,
                        "sources": [],
                    },
                },
            )
        except Exception as tts_e:
            logger.error(f"Failed to synthesize error fallback: {tts_e}")


async def _handle_text_query(mgr: ConnectionManager, session_id: str, payload: dict, turn_token: str) -> None:
    text = payload.get("text")
    if not text:
        await mgr.send(session_id, {"type": "error", "payload": {"message": "Missing text query", "code": "missing_text"}})
        return

    language_hint = payload.get("language_hint") or None

    await mgr.send(session_id, {"type": "thinking", "payload": {}})
    await mgr.send(session_id, {
        "type": "transcript",
        "payload": {"text": text, "confidence": 1.0, "final": True},
    })

    try:
        from app.services.query_pipeline import run_query_pipeline
        result = await run_query_pipeline(session_id, text, language_hint)

        if active_turn_tokens.get(session_id) != turn_token:
            logger.info(f"Stale turn detected after pipeline for session {session_id}")
            return

        if result["type"] == "clarifying":
            await mgr.send(session_id, {
                "type": "clarifying",
                "payload": {
                    "text": result["text"],
                    "audio_url": result["audio_url"],
                    "ambiguity_type": result["ambiguity_type"]
                }
            })
        else:
            ans_payload = {
                "text": result["text"],
                "audio_url": result["audio_url"],
                "sources": result["sources"]
            }
            if result.get("navigation"):
                ans_payload["navigation"] = result["navigation"]

            await mgr.send(session_id, {"type": "answer", "payload": ans_payload})
    except asyncio.CancelledError:
        logger.info(f"WS [{session_id}] Text query processing task cancelled.")
        raise
    except Exception as e:
        import traceback
        with open("crash.txt", "w") as f:
            f.write(traceback.format_exc())
        logger.exception(f"Pipeline error for text query [{session_id}]: {e}")
        fallback_msg = "I'm sorry, I encountered a temporary issue while processing your request. Please try again."
        await mgr.send(session_id, {"type": "error", "payload": {"message": fallback_msg, "code": "pipeline_error"}})
