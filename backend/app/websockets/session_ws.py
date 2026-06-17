"""
WebSocket handler for /ws/session/{session_id}

Message protocol (JSON):
  Client → Server:  { "type": "ping" | "audio_chunk" | "frame", "payload": <any> }
  Server → Client:  { "type": "pong" | "transcript" | "answer" | "tts_chunk" | "error", "payload": <any> }
"""

import json
import os
import sys
from typing import Dict

# Add project root to sys.path to allow importing from agents
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from fastapi import WebSocket, WebSocketDisconnect

from app.core.logging import logger
from app.core.session_store import get_session
from app.models.schemas import ASRRequest, RAGRequest, RIARRequest, RouteRequest, TTSRequest
from app.services.mock_services import rag_service, riar_service, route_service
from app.services.speech.asr_service import asr_service
from app.services.speech.tts_service import tts_service

from agents.coordinator.coordinator_agent import CoordinatorAgent
from deep_translator import GoogleTranslator

# Initialize the coordinator agent singleton
coordinator_agent = CoordinatorAgent()


def translate_to_english(text: str, source_lang: str = "auto") -> str:
    if not text or not text.strip() or source_lang == "en":
        return text
    try:
        translated = GoogleTranslator(source=source_lang, target="en").translate(text)
        logger.info(f"Translated query '{text}' ({source_lang}) -> '{translated}' (en)")
        return translated
    except Exception as e:
        logger.error(f"Translation to English failed: {e}")
        return text


def translate_from_english(text: str, target_lang: str) -> str:
    if not text or not text.strip() or target_lang == "en":
        return text
    try:
        translated = GoogleTranslator(source="en", target=target_lang).translate(text)
        logger.info(f"Translated response '{text}' (en) -> '{translated}' ({target_lang})")
        return translated
    except Exception as e:
        logger.error(f"Translation from English failed: {e}")
        return text


# ── Connection Manager ────────────────────────


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}  # session_id → WebSocket

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self.active[session_id] = ws
        logger.info(f"WS connected: {session_id}  (total={len(self.active)})")

    def disconnect(self, session_id: str):
        self.active.pop(session_id, None)
        logger.info(f"WS disconnected: {session_id}  (total={len(self.active)})")

    async def send(self, session_id: str, message: dict):
        ws = self.active.get(session_id)
        if ws:
            await ws.send_json(message)

    async def broadcast(self, message: dict):
        for ws in self.active.values():
            await ws.send_json(message)


manager = ConnectionManager()


# ── Handler ───────────────────────────────────


async def websocket_session_handler(websocket: WebSocket, session_id: str):
    # Validate session exists
    session = await get_session(session_id)
    if not session:
        await websocket.accept()
        await websocket.send_json({"type": "error", "payload": {"message": "Session not found"}})
        await websocket.close(code=4004)
        return

    await manager.connect(session_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send(
                    session_id, {"type": "error", "payload": {"message": "Invalid JSON"}}
                )
                continue

            msg_type = msg.get("type", "unknown")
            payload = msg.get("payload", {})

            logger.debug(f"WS [{session_id}] received type={msg_type}")

            # ── Message dispatch ──────────────
            if msg_type == "ping":
                await manager.send(session_id, {"type": "pong", "payload": {}})

            elif msg_type == "audio_chunk":
                audio_base64 = payload.get("audio_base64")
                if not audio_base64:
                    await manager.send(
                        session_id,
                        {"type": "error", "payload": {"message": "Missing audio_base64 payload"}},
                    )
                    continue

                turn_id = payload.get("turn_id", 1)
                language_hint = payload.get("language_hint", "en")

                # Send processing state update (thinking)
                await manager.send(session_id, {"type": "thinking", "payload": {}})

                try:
                    # 1. ASR Transcription
                    asr_req = ASRRequest(
                        session_id=session_id,
                        audio_base64=audio_base64,
                        language_hint=language_hint,
                        turn_id=turn_id,
                    )
                    asr_resp = await asr_service.transcribe(asr_req)

                    # Debug logging to file
                    with open("pipeline_debug.log", "a", encoding="utf-8") as f:
                        f.write(f"\n--- NEW TURN ({session_id}) ---\n")
                        f.write(f"Language Hint: {language_hint}\n")
                        f.write(f"ASR Transcript: '{asr_resp.transcript}'\n")
                        f.write(f"Detected Language: {asr_resp.detected_language}\n")

                    # Send transcription transcript back to client
                    await manager.send(
                        session_id,
                        {
                            "type": "transcript",
                            "payload": {
                                "text": asr_resp.transcript,
                                "confidence": asr_resp.confidence,
                                "final": True,
                            },
                        },
                    )

                    # 2. Translation to English if query is in other languages
                    detected_lang = (asr_resp.detected_language or "en").lower().split("-")[0]
                    
                    if detected_lang in ["kn", "hi"]:
                        query_en = translate_to_english(asr_resp.transcript, source_lang=detected_lang)
                    else:
                        query_en = asr_resp.transcript
                        detected_lang = "en"

                    # 3. Route query and retrieve answer using CoordinatorAgent
                    await manager.send(session_id, {"type": "retrieving", "payload": {}})

                    selected_domain, confidence, reason, all_matches = coordinator_agent.route(query_en)
                    
                    if selected_domain is None or confidence <= 0.0:
                        answer_en = (
                            "I'm sorry, I couldn't identify the right department for your query.\n"
                            "Please try asking about one of the following topics:\n"
                            "- Admissions (requirements, application, fees, scholarships)\n"
                            "- Academics (attendance, exams, SGPA/CGPA, transcripts)\n"
                            "- Placements (internships, company eligibility, recruitment process)\n"
                            "- Research (labs, publications, faculty projects, UROP)\n"
                            "- Student Services (hostel, library, ID cards, certificate requests)\n"
                            "- Navigation (campus directions, building/office locations)"
                        )
                        citations = []
                    else:
                        agent = coordinator_agent.agents.get(selected_domain)
                        if not agent:
                            answer_en = f"I'm sorry, I couldn't find any information regarding that query in the {selected_domain} section."
                            citations = []
                        else:
                            docs = agent.retrieve(query_en)
                            if not docs:
                                answer_en = f"I'm sorry, I couldn't find any information regarding that query in the {selected_domain} section."
                                citations = []
                            else:
                                best_doc = docs[0]
                                answer_en = best_doc["answer"]
                                citations = [f"{selected_domain.title().replace('_', ' ')} | Ref: {best_doc['id']}"]

                    # 4. Translate English answer back to native language if needed
                    if detected_lang in ["kn", "hi"]:
                        answer_native = translate_from_english(answer_en, target_lang=detected_lang)
                    else:
                        answer_native = answer_en

                    # Debug logging to file
                    with open("pipeline_debug.log", "a", encoding="utf-8") as f:
                        f.write(f"Query EN: '{query_en}'\n")
                        f.write(f"Selected Domain: {selected_domain} (confidence: {confidence:.2f})\n")
                        f.write(f"Answer EN: '{answer_en}'\n")
                        f.write(f"Answer Native: '{answer_native}'\n")

                    # 5. TTS Response audio generation in the correct language
                    tts_req = TTSRequest(
                        session_id=session_id,
                        text=answer_native,
                        language=detected_lang,
                    )
                    tts_resp = await tts_service.synthesize(tts_req)

                    # Send final answer payload to client (speaking state)
                    await manager.send(
                        session_id,
                        {
                            "type": "answer",
                            "payload": {
                                "text": answer_native,
                                "audio_url": tts_resp.audio_url,
                                "sources": citations,
                            },
                        },
                    )

                except Exception as e:
                    logger.exception(f"Pipeline error processing audio: {e}")
                    await manager.send(
                        session_id,
                        {"type": "error", "payload": {"message": f"Pipeline processing failed: {str(e)}"}},
                    )

            elif msg_type == "frame":
                # TODO: pipe to DetectionService
                await manager.send(
                    session_id,
                    {"type": "detection", "payload": {"person_detected": True, "confidence": 0.91}},
                )

            elif msg_type == "text_query":
                # Direct text query shortcut (useful during dev)
                await manager.send(
                    session_id,
                    {
                        "type": "answer",
                        "payload": {
                            "text": f"[mock] You asked: {payload.get('text', '')}",
                            "sources": [],
                        },
                    },
                )

            else:
                await manager.send(
                    session_id,
                    {"type": "error", "payload": {"message": f"Unknown message type: {msg_type}"}},
                )

    except WebSocketDisconnect:
        manager.disconnect(session_id)
    except Exception as e:
        logger.exception(f"WS error [{session_id}]: {e}")
        manager.disconnect(session_id)
