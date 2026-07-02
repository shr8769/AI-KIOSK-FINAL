"""
backend/app/websockets/session_ws.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thin WebSocket handler. Zero heavy imports.

ALL singletons (ConnectionManager, CoordinatorAgent, RIARPipeline)
come from app.core.dependencies — never instantiated here.

Pipeline:
  1. ASR  (faster-whisper)
  2. Translate → EN  (deep_translator — lazy in dependencies.py)
  3. RIAR ambiguity gate  (only when GOOGLE_API_KEY set)
  4. FAQ retrieval  (CoordinatorAgent, lazy-loaded on first call)
  5. Translate → native language
  6. TTS  (gTTS)

Message protocol:
  Client → Server: { "type": "ping"|"audio_chunk"|"frame", "payload": <any> }
  Server → Client: { "type": "pong"|"transcript"|"answer"|"clarifying"|"error", ... }
"""

import json

from fastapi import Depends, WebSocket, WebSocketDisconnect

from app.core.dependencies import (
    RIAR_ENABLED,
    ConnectionManager,
    get_connection_manager,
    get_coordinator_agent,
    translate_from_english,
    translate_to_english,
)
from app.core.logging import logger
from app.core.session_store import (
    add_agent_turn,
    add_user_turn,
    get_session,
    log_barge_in,
    mark_turn_interrupted,
)
from app.models.schemas import ASRRequest, RIARRequest, TTSRequest, TurnModel
from app.services.riar_service import riar_service
from app.services.speech.asr_service import asr_service
from app.services.speech.tts_service import tts_service

# Re-export manager for events.py (backwards-compat shim — will be removed once
# events.py is fully migrated to Depends(get_connection_manager))
manager = get_connection_manager()


def _is_language_command(text: str):
    if not text:
        return None
    text_lower = text.strip().lower().rstrip(".").rstrip("?")
    if text_lower in ["english", "eng"] or "select english" in text_lower:
        return "en"
    if text_lower in ["kannada", "kn", "ಕನ್ನಡ"] or "ಕನ್ನಡ ಭಾಷೆ" in text_lower or "select kannada" in text_lower:
        return "kn"
    if text_lower in ["hindi", "hi", "हिंदी", "hind"] or "हिंदी भाषा" in text_lower or "select hindi" in text_lower:
        return "hi"
    return None


# ── WebSocket endpoint ────────────────────────────────────────────────


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
    # Deliver any detection/greeting events that arrived before frontend connected
    await mgr.send_pending_broadcast(session_id, websocket)

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

            # ── Ping ──────────────────────────────────────────────────
            if msg_type == "ping":
                await mgr.send(session_id, {"type": "pong", "payload": {}})

            elif msg_type == "audio_chunk":
                await _handle_audio_chunk(mgr, session_id, payload)

            elif msg_type == "interrupt":
                turn_id = payload.get("turn_id", "unknown")
                reason = payload.get("reason", "unknown")
                position_ms = payload.get("position_ms", 0)
                logger.info(f"WS [{session_id}] Barge-in interrupt received for turn {turn_id} (Reason: {reason}, Pos: {position_ms}ms).")

                # Mark current turn as interrupted
                await mark_turn_interrupted(session_id)

                # Log the metric to the database
                await log_barge_in(session_id, reason, position_ms)

                # In Phase 2 (streaming), we would cancel the active generation task here.
                # For Phase 1, the frontend has already halted playback and reset to listening.
                await mgr.send(session_id, {"type": "info", "payload": {"message": "Interrupt acknowledged and logged"}})            # ── Camera frame (stub) ───────────────────────────────────
            elif msg_type == "frame":
                await mgr.send(session_id, {"type": "detection", "payload": {"person_detected": True, "confidence": 0.91}})

            # ── Text query ────────────────────────────────────────────
            elif msg_type == "text_query":
                await _handle_text_query(mgr, session_id, payload)

            else:
                await mgr.send(session_id, {"type": "error", "payload": {"message": f"Unknown type: {msg_type}", "code": "unknown_type"}})

    except WebSocketDisconnect:
        mgr.disconnect(session_id)
    except Exception as e:
        logger.exception(f"WS error [{session_id}]: {e}")
        mgr.disconnect(session_id)


# ── Pipeline handler (extracted for readability) ──────────────────────


async def _handle_audio_chunk(mgr: ConnectionManager, session_id: str, payload: dict) -> None:
    audio_base64 = payload.get("audio_base64")
    if not audio_base64:
        await mgr.send(session_id, {"type": "error", "payload": {"message": "Missing audio_base64", "code": "missing_audio"}})
        return

    turn_id = payload.get("turn_id", 1)
    language_hint = payload.get("language_hint") or None

    import time
    start_time = time.perf_counter()
    refined_query = None
    response_text = None

    await mgr.send(session_id, {"type": "thinking", "payload": {}})

    try:
        # ── 1. ASR ────────────────────────────────────────────────────
        asr_resp = await asr_service.transcribe(
            ASRRequest(
                session_id=session_id,
                audio_base64=audio_base64,
                language_hint=language_hint,
                turn_id=turn_id,
            )
        )
        logger.info(f"ASR: '{asr_resp.transcript}' lang={asr_resp.detected_language}")

        # Prioritize explicitly selected session language (language_hint) over ASR auto-detection
        detected_lang = language_hint or (asr_resp.detected_language or "en").lower().split("-")[0]
        raw_transcript = asr_resp.transcript
        
        from app.services.query_pipeline import run_query_pipeline
        result = await run_query_pipeline(session_id, raw_transcript, detected_lang)

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

            await mgr.send(session_id, {
                "type": "answer",
                "payload": ans_payload
            })
    except Exception as e:
        logger.exception(f"Pipeline error [{session_id}]: {e}")
        fallback_msg = "I'm sorry, I encountered a temporary issue while processing your request. Please try again."
        await mgr.send(session_id, {"type": "error", "payload": {"message": fallback_msg, "code": "pipeline_error"}})
        try:
            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=fallback_msg, language="en")
            )
            await mgr.send(session_id, {
                "type": "answer",
                "payload": {"text": fallback_msg, "audio_url": tts_resp.audio_url, "sources": []},
            })
        except Exception as tts_e:
            logger.error(f"Failed to synthesize error fallback: {tts_e}")


async def _handle_text_query(mgr: ConnectionManager, session_id: str, payload: dict) -> None:
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

            await mgr.send(session_id, {
                "type": "answer",
                "payload": ans_payload
            })
    except Exception as e:
        logger.exception(f"Pipeline error for text query [{session_id}]: {e}")
        fallback_msg = "I'm sorry, I encountered a temporary issue while processing your request. Please try again."
        await mgr.send(session_id, {"type": "error", "payload": {"message": fallback_msg, "code": "pipeline_error"}})
