"""
backend/app/core/dependencies.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Central registry for ALL heavy singletons in the application.

RULES (enforced by code review + test_startup_performance.py):
  1. Every heavy library import (chromadb, sentence_transformers,
     torch, tensorflow, langchain) lives INSIDE a function body here
     — never at module top-level anywhere in backend/app/.
  2. @lru_cache(maxsize=1) makes each getter idempotent — FastAPI may
     call Depends(get_X) on every request but the object is only
     constructed once.
  3. No other file may instantiate CoordinatorAgent, RIARPipeline,
     ChromaDB, or the embedding model directly. Receive via Depends().
"""

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)


# ── Connection Manager ────────────────────────────────────────────────
# Defined here (not in session_ws.py) so that BOTH the WebSocket handler
# AND the HTTP events route share the exact same object via Depends().


class ConnectionManager:
    """
    Tracks active WebSocket connections per session_id.
    Queues events for sessions whose frontend hasn't connected yet —
    flushed on WebSocket connect. This permanently fixes the
    detection-before-frontend race condition.
    """

    def __init__(self):
        self.active: dict[str, object] = {}  # session_id → WebSocket
        self.pending: dict[str, list[dict]] = {}  # session_id → queued events

    async def connect(self, session_id: str, websocket) -> None:
        await websocket.accept()
        self.active[session_id] = websocket
        logger.info(f"WS connected: {session_id}  (total={len(self.active)})")
        # Flush any events queued before the frontend connected
        if session_id in self.pending:
            queued_events = self.pending.pop(session_id)
            for event in queued_events:
                try:
                    await websocket.send_json(event)
                except Exception as exc:
                    logger.warning(f"WS flush failed for {session_id}: {exc}")
                    self.disconnect(session_id)
                    break

    def disconnect(self, session_id: str) -> None:
        self.active.pop(session_id, None)
        logger.info(f"WS disconnected: {session_id}  (total={len(self.active)})")

    async def send(self, session_id: str, message: dict) -> None:
        ws = self.active.get(session_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning(f"WS send failed for {session_id}: {exc}")
                self.disconnect(session_id)
        else:
            self.pending.setdefault(session_id, []).append(message)

    async def broadcast(self, message: dict) -> None:
        """Broadcast to all connected sessions. Also queues for disconnected ones."""
        # For kiosk: greeting should reach anyone who connects within next ~30s
        # We store it in a global-broadcast queue keyed to a sentinel
        for ws in self.active.values():
            try:
                await ws.send_json(message)
            except Exception:
                pass
        # Store for any session_id that connects shortly after
        self._last_broadcast = message

    _last_broadcast: dict = {}

    async def send_pending_broadcast(self, session_id: str, websocket) -> None:
        """Called on WS connect — delivers any pending broadcast the session missed."""
        if self._last_broadcast:
            try:
                await websocket.send_json(self._last_broadcast)
            except Exception as exc:
                logger.warning(f"WS pending broadcast failed for {session_id}: {exc}")


@lru_cache(maxsize=1)
def get_connection_manager() -> ConnectionManager:
    """Single ConnectionManager instance shared across HTTP routes and WS handlers."""
    logger.info("Instantiating ConnectionManager singleton")
    return ConnectionManager()


# ── Coordinator Agent ─────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_coordinator_agent():
    """
    Lazy-loads CoordinatorAgent (pulls in chromadb + sentence-transformers).
    Only executed on first audio_chunk — not at server startup.
    """
    logger.info("Lazy-loading CoordinatorAgent...")
    # Heavy imports inside the function body
    import sys

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from agents.coordinator.coordinator_agent import CoordinatorAgent  # noqa

    agent = CoordinatorAgent()
    logger.info("CoordinatorAgent ready.")
    return agent


# ── RIAR Pipeline ─────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_riar_pipeline():
    """
    Lazy-loads RIARPipeline with Gemini LLM or local Ollama (Qwen) + mocked ChromaDB/embeddings.
    Only executed when first audio_chunk arrives.
    """
    logger.info("Lazy-loading RIAR Pipeline...")
    import sys

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    if root not in sys.path:
        sys.path.insert(0, root)

    from riar.pipeline import RIARPipeline  # noqa

    google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if google_key:
        logger.info("Initializing RIAR LLM with Gemini (ChatGoogleGenerativeAI)")
        from langchain_google_genai import ChatGoogleGenerativeAI  # noqa

        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    else:
        logger.info(
            "GOOGLE_API_KEY missing. Initializing RIAR LLM with local Ollama (qwen3:latest)"
        )
        from langchain_ollama import ChatOllama  # noqa

        llm = ChatOllama(model="qwen3:latest")

    import chromadb
    db_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../..", "knowledge", "vectorstore")
    )
    chroma_client = chromadb.PersistentClient(path=db_path)

    pipeline = RIARPipeline(
        vector_store=chroma_client,
        llm_client=llm,
        embedding_model=None,
    )
    logger.info("RIAR Pipeline ready.")
    return pipeline


# ── Translation helpers ───────────────────────────────────────────────


def _get_translation_llm():
    """Lazily load the LLM client for high-quality conversational translations."""
    google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if google_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    else:
        from langchain_ollama import ChatOllama
        return ChatOllama(model="qwen3:latest")


def translate_to_english_llm(text: str, source_lang: str) -> str:
    """Translates conversational or mixed native query to clear English using LLM."""
    try:
        llm = _get_translation_llm()
        lang_name = "Kannada" if source_lang == "kn" else "Hindi"
        prompt = f"""Translate this conversational, mixed {lang_name} user query into standard, clear English.
User query: "{text}"
English translation:"""
        response = llm.invoke(prompt)
        translated = response.content.strip().strip('"').strip("'")
        if translated:
            return translated
    except Exception as e:
        logger.warning(f"LLM translation to English failed: {e}")
    return text


def translate_from_english_llm(text: str, target_lang: str) -> str:
    """Translates English to conversational, mixed target language using LLM with loanword preservation."""
    try:
        llm = _get_translation_llm()
        lang_name = "Kannada" if target_lang == "kn" else "Hindi"
        prompt = f"""You are a professional, human-like translator for the PES University AI Kiosk.
Translate the following English text into conversational, natural {lang_name} as spoken by students and faculty in daily life.

Rules:
1. Avoid pure, textbook, or archaic {lang_name} vocabulary that sounds robotic or formal.
2. Naturally integrate common English loanwords (e.g. "office", "placement", "internship", "admissions", "fees", "exams", "canteen", "library", "labs", "classes", "grades", "results", "attendance", "scholarship") by TRANSLITERATING them into the {lang_name} script (e.g., for Kannada, write "ಪ್ಲೇಸ್‌ಮೆಂಟ್" for placement, "ಆಫೀಸ್" for office, "ಅಡ್ಮಿಷನ್" for admission).
3. Keep the tone friendly, conversational, helpful, and natural.
4. Strictly return ONLY the translated text. Do not include any explanations, English subtitles, or markdown formatting.

English text: "{text}"
Conversational {lang_name} translation:"""
        response = llm.invoke(prompt)
        translated = response.content.strip().strip('"').strip("'")
        if translated:
            return translated
    except Exception as e:
        logger.warning(f"LLM translation from English failed: {e}")
    return text


def translate_to_english(text: str, source_lang: str = "auto") -> str:
    if not text or not text.strip() or source_lang == "en":
        return text

    # Try LLM-based translation first
    if source_lang in ("kn", "hi"):
        translated_llm = translate_to_english_llm(text, source_lang)
        if translated_llm and translated_llm != text:
            logger.info(f"LLM conversational translation succeeded ({source_lang} -> en)")
            return translated_llm

    try:
        from app.services.speech.translation_service import offline_translation_service
        translated = offline_translation_service.translate(text, source_lang, "en")
        logger.info(f"Translated '{text[:40]}' ({source_lang}) -> en")
        return translated
    except Exception as e:
        logger.error(f"Translation to English failed: {e}")
        return text


def translate_from_english(text: str, target_lang: str) -> str:
    if not text or not text.strip() or target_lang == "en":
        return text

    # Try LLM-based conversational translation first
    if target_lang in ("kn", "hi"):
        translated_llm = translate_from_english_llm(text, target_lang)
        if translated_llm and translated_llm != text:
            logger.info(f"LLM conversational translation succeeded (en -> {target_lang})")
            return translated_llm

    try:
        from app.services.speech.translation_service import offline_translation_service
        translated = offline_translation_service.translate(text, "en", target_lang)
        logger.info(f"Translated response (en) -> {target_lang}")
        return translated
    except Exception as e:
        logger.error(f"Translation from English failed: {e}")
        return text


# ── RIAR enabled flag ─────────────────────────────────────────────────
def _check_ollama_running() -> bool:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("localhost", 11434))
        return True
    except Exception:
        return False


def _is_riar_enabled() -> bool:
    google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if google_key:
        return True
    if _check_ollama_running():
        return True
    return False


RIAR_ENABLED: bool = _is_riar_enabled()
logger.info(f"RIAR Pipeline activation status: {RIAR_ENABLED}")
