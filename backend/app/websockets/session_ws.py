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
import logging
from typing import TYPE_CHECKING

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
from app.core.session_store import add_agent_turn, add_user_turn, get_session
from app.models.schemas import ASRRequest, RIARRequest, TTSRequest, TurnModel
from app.services.riar_service import riar_service
from app.services.speech.asr_service import asr_service
from app.services.speech.tts_service import tts_service

# Re-export manager for events.py (backwards-compat shim — will be removed once
# events.py is fully migrated to Depends(get_connection_manager))
manager = get_connection_manager()


# ── WebSocket endpoint ────────────────────────────────────────────────


async def websocket_session_handler(
    websocket: WebSocket,
    session_id: str,
    mgr: ConnectionManager = Depends(get_connection_manager),
):
    session = await get_session(session_id)
    if not session:
        await websocket.accept()
        await websocket.send_json({"type": "error", "payload": {"message": "Session not found"}})
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
                await mgr.send(session_id, {"type": "error", "payload": {"message": "Invalid JSON"}})
                continue

            msg_type = msg.get("type", "unknown")
            payload = msg.get("payload", {})
            logger.debug(f"WS [{session_id}] type={msg_type}")

            # ── Ping ──────────────────────────────────────────────────
            if msg_type == "ping":
                await mgr.send(session_id, {"type": "pong", "payload": {}})

            # ── Audio chunk (main pipeline) ───────────────────────────
            elif msg_type == "audio_chunk":
                await _handle_audio_chunk(mgr, session_id, payload)

            # ── Camera frame (stub) ───────────────────────────────────
            elif msg_type == "frame":
                await mgr.send(session_id, {"type": "detection", "payload": {"person_detected": True, "confidence": 0.91}})

            # ── Dev text shortcut ─────────────────────────────────────
            elif msg_type == "text_query":
                text = payload.get("text", "")
                await mgr.send(session_id, {"type": "answer", "payload": {"text": f"[dev] {text}", "sources": []}})

            else:
                await mgr.send(session_id, {"type": "error", "payload": {"message": f"Unknown type: {msg_type}"}})

    except WebSocketDisconnect:
        mgr.disconnect(session_id)
    except Exception as e:
        logger.exception(f"WS error [{session_id}]: {e}")
        mgr.disconnect(session_id)


# ── Pipeline handler (extracted for readability) ──────────────────────


async def _handle_audio_chunk(mgr: ConnectionManager, session_id: str, payload: dict) -> None:
    audio_base64 = payload.get("audio_base64")
    if not audio_base64:
        await mgr.send(session_id, {"type": "error", "payload": {"message": "Missing audio_base64"}})
        return

    turn_id = payload.get("turn_id", 1)
    language_hint = payload.get("language_hint") or None

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

        await mgr.send(session_id, {
            "type": "transcript",
            "payload": {"text": asr_resp.transcript, "confidence": asr_resp.confidence, "final": True},
        })

        # ── 2. Normalize language + translate to English ───────────────
        detected_lang = (asr_resp.detected_language or "en").lower().split("-")[0]
        query_en = (
            translate_to_english(asr_resp.transcript, source_lang=detected_lang)
            if detected_lang in ("kn", "hi")
            else asr_resp.transcript
        )

        # ── 3. Persist user turn ──────────────────────────────────────
        await add_user_turn(session_id, asr_resp.transcript)

        updated_session = await get_session(session_id)
        raw_history = updated_session.metadata.get("history", []) if updated_session else []
        # Use TurnModel (Pydantic) — the ONLY schema for turn data crossing API boundaries
        history_turns = [
            TurnModel(turn_id=i + 1, role=t["role"], text=t["content"])
            for i, t in enumerate(raw_history)
        ]

        # ── 4. RIAR ambiguity gate (skipped when no API key) ──────────
        ambiguous = False
        riar_resp = None
        if RIAR_ENABLED:
            riar_resp = await riar_service.classify(
                RIARRequest(
                    session_id=session_id,
                    turn_id=turn_id,
                    query=query_en,
                    language="en",
                    session_history=history_turns,
                )
            )
            ambiguous = getattr(riar_resp, "requires_clarification",
                                getattr(riar_resp, "ambiguity_detected", False))
        else:
            logger.debug("RIAR skipped — no GOOGLE_API_KEY")

        if ambiguous:
            # ── 4a. Clarification ──────────────────────────────────
            question_en = riar_resp.clarification_question or "Could you clarify your question?"
            question_native = translate_from_english(question_en, target_lang=detected_lang)
            await add_agent_turn(session_id, question_native)

            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=question_native, language=detected_lang)
            )
            await mgr.send(session_id, {
                "type": "clarifying",
                "payload": {
                    "text": question_native,
                    "audio_url": tts_resp.audio_url,
                    "ambiguity_type": riar_resp.ambiguity_type,
                },
            })
        else:
            # ── 4b. FAQ retrieval ──────────────────────────────────
            refined_query = (
                getattr(riar_resp, "refined_query", None) or query_en
                if riar_resp else query_en
            )
            await mgr.send(session_id, {"type": "retrieving", "payload": {}})

            coordinator = get_coordinator_agent()  # lazy — loads on first call
            domain, confidence, _reason, _all = coordinator.route(refined_query)

            if domain is None or confidence <= 0.0:
                answer_en = (
                    "I'm sorry, I couldn't identify the right department for your query. "
                    "Please try asking about: Admissions, Academics, Placements, Research, "
                    "Student Services, or Navigation."
                )
                citations = []
            else:
                agent = coordinator.agents.get(domain)
                docs = agent.retrieve(refined_query) if agent else []
                if docs:
                    best = docs[0]
                    answer_en = best["answer"]
                    citations = [f"{domain.title().replace('_', ' ')} | Ref: {best['id']}"]
                else:
                    answer_en = f"I couldn't find information about that in the {domain} section."
                    citations = []

            # ── 5. Back-translate ──────────────────────────────────
            answer_native = (
                translate_from_english(answer_en, target_lang=detected_lang)
                if detected_lang in ("kn", "hi")
                else answer_en
            )
            await add_agent_turn(session_id, answer_native)

            # ── 6. TTS ────────────────────────────────────────────
            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=answer_native, language=detected_lang)
            )
            await mgr.send(session_id, {
                "type": "answer",
                "payload": {"text": answer_native, "audio_url": tts_resp.audio_url, "sources": citations},
            })

    except Exception as e:
        logger.exception(f"Pipeline error [{session_id}]: {e}")
        await mgr.send(session_id, {"type": "error", "payload": {"message": f"Pipeline failed: {e}"}})
