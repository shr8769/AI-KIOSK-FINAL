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

            # ── Dev text shortcut ─────────────────────────────────────
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
    domain = None
    ambiguity_type = "CLEAR"

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
        raw_transcript = asr_resp.transcript
        from app.services.speech.translation_service import preprocess_and_detect_language
        clean_transcript, detected_lang = preprocess_and_detect_language(
            raw_transcript,
            language_hint or (asr_resp.detected_language or "en").lower().split("-")[0]
        )

        # Check if this is a language selection command
        lang_cmd = _is_language_command(clean_transcript)
        if lang_cmd:
            confirmation_texts = {
                "en": "You selected English. How can I help you today?",
                "kn": "ಕನ್ನಡ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆ ಮಾಡಿದ್ದೀರಿ. ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಲಿ?",
                "hi": "आपने हिंदी भाषा चुनी है। मैं आज आपकी क्या सहायता कर सकता हूँ?"
            }
            text_response = confirmation_texts[lang_cmd]
            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=text_response, language=lang_cmd)
            )
            await mgr.send(session_id, {
                "type": "answer",
                "payload": {
                    "text": text_response,
                    "audio_url": tts_resp.audio_url,
                    "sources": []
                }
            })
            return

        if detected_lang in ["kn", "hi"]:
            try:
                query_en = translate_to_english(clean_transcript, source_lang=detected_lang)
                # Translate back to clean native script to display nicely on screen
                clean_transcript = translate_from_english(query_en, target_lang=detected_lang)
                logger.info(f"Corrected ASR script: '{raw_transcript}' -> '{clean_transcript}' ({detected_lang})")
            except Exception as e:
                logger.error(f"ASR script correction/translation failed: {e}")
                query_en = translate_to_english(clean_transcript, source_lang=detected_lang)
        else:
            query_en = clean_transcript

        await mgr.send(session_id, {
            "type": "transcript",
            "payload": {"text": clean_transcript, "confidence": asr_resp.confidence, "final": True},
        })


        # ── 3. Persist user turn ──────────────────────────────────────
        await add_user_turn(session_id, clean_transcript)


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

            response_text = question_native
            ambiguity_type = riar_resp.ambiguity_type if riar_resp else "CLEAR"
            domain = None

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

            target_domain = getattr(riar_resp, "selected_domain", None) if riar_resp else None
            if not target_domain or target_domain == "general":
                query_lower = refined_query.lower()
                if "admission" in query_lower:
                    target_domain = "admissions"
                elif "academic" in query_lower or "course" in query_lower or "grade" in query_lower:
                    target_domain = "academics"
                elif "placement" in query_lower or "salary" in query_lower or "job" in query_lower or "company" in query_lower or "recruit" in query_lower:
                    target_domain = "placements"
                elif "research" in query_lower or "paper" in query_lower or "publication" in query_lower or "project" in query_lower:
                    target_domain = "research"
                elif "student" in query_lower or "hostel" in query_lower or "fee" in query_lower or "scholarship" in query_lower:
                    target_domain = "student_services"
                elif "where" in query_lower or "locate" in query_lower or "direction" in query_lower or "floor" in query_lower or "room" in query_lower or "building" in query_lower or "map" in query_lower:
                    target_domain = "navigation"
                else:
                    target_domain = "general"
            coordinator = get_coordinator_agent()  # lazy — loads on first call
            # Use the explicit routing decision from RIAR. Run in thread to prevent event loop blocking.
            import asyncio
            full_answer = await asyncio.to_thread(coordinator.answer, refined_query, target_domain=target_domain)

            nav_payload = None
            citations = []

            if target_domain == "navigation":
                try:
                    metadata = json.loads(full_answer)
                    if "error" not in metadata:
                        from app.services.navigation_service import navigation_service
                        nav_id = await navigation_service.create_session(metadata)

                        from app.core.config import get_local_ip
                        answer_en = f"The {metadata.get('destination_name')} is located in {metadata.get('building')}, Floor {metadata.get('floor')}. Please scan the QR code for detailed directions."
                        nav_payload = {
                            "navigation_id": nav_id,
                            "destination_name": metadata.get("destination_name"),
                            "building": metadata.get("building"),
                            "floor": metadata.get("floor"),
                            "room": metadata.get("room"),
                            "kiosk_ip": get_local_ip()
                        }
                    else:
                        answer_en = metadata["error"]
                except Exception as e:
                    logger.error(f"Failed to parse navigation JSON: {e}")
                    answer_en = "I'm sorry, I couldn't retrieve the location details."
            else:
                if "\n\n[Source: " in full_answer:
                    parts = full_answer.split("\n\n[Source: ", 1)
                    answer_en = parts[0]
                    citations = [parts[1].rstrip("]")]
                else:
                    answer_en = full_answer

            # ── 5. Back-translate ──────────────────────────────────
            answer_native = (
                translate_from_english(answer_en, target_lang=detected_lang)
                if detected_lang in ("kn", "hi")
                else answer_en
            )
            await add_agent_turn(session_id, answer_native)

            response_text = answer_native
            ambiguity_type = getattr(riar_resp, "ambiguity_type", "CLEAR") if riar_resp else "CLEAR"
            domain = target_domain

            import re
            # Strip markdown for TTS so it doesn't speak "asterisk"
            tts_text = re.sub(r'[*_#]', '', answer_native)

            # ── 6. TTS ────────────────────────────────────────────
            tts_resp = await tts_service.synthesize(
                TTSRequest(session_id=session_id, text=tts_text, language=detected_lang)
            )

            payload = {"text": answer_native, "audio_url": tts_resp.audio_url, "sources": citations}
            if nav_payload:
                payload["navigation"] = nav_payload

            await mgr.send(session_id, {
                "type": "answer",
                "payload": payload,
            })

        # ── PostgreSQL Turn Logging ───────────────────────────────────────────
        try:
            from database.models.models import Session as PGSession
            from database.postgres.connection import AsyncSessionLocal
            from sqlalchemy.future import select

            from app.services.query_store import QueryStore

            user_id = None
            async with AsyncSessionLocal() as db_session:
                sess_res = await db_session.execute(
                    select(PGSession).filter(PGSession.session_id == session_id)
                )
                db_sess = sess_res.scalars().first()
                if db_sess:
                    user_id = db_sess.user_id

            latency_ms = int((time.perf_counter() - start_time) * 1000)
            async with AsyncSessionLocal() as db_session:
                store = QueryStore(db_session)
                await store.store_query(
                    session_id=session_id,
                    user_id=user_id,
                    query_text=clean_transcript,
                    refined_query=refined_query,
                    response_text=response_text,
                    domain=domain,
                    language=detected_lang,
                    ambiguity_type=ambiguity_type,
                    latency_ms=latency_ms
                )
        except Exception as db_e:
            logger.error(f"Failed to log user query to PostgreSQL: {db_e}")

    except Exception as e:
        logger.exception(f"Pipeline error [{session_id}]: {e}")
        fallback_msg = "I'm sorry, I encountered a temporary issue while processing your request. Please try again."

        # Send error state to UI
        await mgr.send(session_id, {"type": "error", "payload": {"message": fallback_msg, "code": "pipeline_error"}})

        # Synthesize the error message so the avatar speaks the fallback instead of silently freezing
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

