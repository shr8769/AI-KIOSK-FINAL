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
        self.active: dict[str, object] = {}          # session_id → WebSocket
        self.pending: dict[str, list[dict]] = {}     # session_id → queued events

    async def connect(self, session_id: str, websocket) -> None:
        await websocket.accept()
        self.active[session_id] = websocket
        logger.info(f"WS connected: {session_id}  (total={len(self.active)})")
        # Flush any events queued before the frontend connected
        if session_id in self.pending:
            for event in self.pending.pop(session_id):
                try:
                    await websocket.send_json(event)
                except Exception:
                    pass

    def disconnect(self, session_id: str) -> None:
        self.active.pop(session_id, None)
        logger.info(f"WS disconnected: {session_id}  (total={len(self.active)})")

    async def send(self, session_id: str, message: dict) -> None:
        ws = self.active.get(session_id)
        if ws:
            await ws.send_json(message)
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
            except Exception:
                pass


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
    from unittest.mock import MagicMock

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    if root not in sys.path:
        sys.path.insert(0, root)

    from riar.pipeline import RIARPipeline  # noqa

    google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if google_key:
        logger.info("Initializing RIAR LLM with Gemini (ChatGoogleGenerativeAI)")
        from langchain_google_genai import ChatGoogleGenerativeAI  # noqa
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")
    else:
        logger.info("GOOGLE_API_KEY missing. Initializing RIAR LLM with local Ollama (qwen3:latest)")
        from langchain_community.chat_models import ChatOllama  # noqa
        llm = ChatOllama(model="qwen3:latest")

    chroma_mock = MagicMock()
    col = MagicMock()
    col.query.return_value = {
        "documents": [["Mock context chunk"]],
        "metadatas": [[{"domain": "admissions", "chunk_id": "m1"}]],
        "distances": [[0.1]],
    }
    chroma_mock.get_collection.return_value = col
    emb_mock = MagicMock()
    emb_mock.encode.return_value = [[0.1] * 384]

    pipeline = RIARPipeline(
        vector_store=chroma_mock,
        llm_client=llm,
        embedding_model=emb_mock,
    )
    logger.info("RIAR Pipeline ready.")
    return pipeline


# ── Translation helpers ───────────────────────────────────────────────

def translate_to_english(text: str, source_lang: str = "auto") -> str:
    if not text or not text.strip() or source_lang == "en":
        return text
    try:
        from deep_translator import GoogleTranslator  # noqa: lazy
        translated = GoogleTranslator(source=source_lang, target="en").translate(text)
        logger.info(f"Translated '{text[:40]}' ({source_lang}) → en")
        return translated
    except Exception as e:
        logger.error(f"Translation to English failed: {e}")
        return text


def translate_from_english(text: str, target_lang: str) -> str:
    if not text or not text.strip() or target_lang == "en":
        return text
    try:
        from deep_translator import GoogleTranslator  # noqa: lazy
        translated = GoogleTranslator(source="en", target=target_lang).translate(text)
        logger.info(f"Translated response (en) → {target_lang}")
        return translated
    except Exception as e:
        logger.error(f"Translation from English failed: {e}")
        return text


# ── RIAR enabled flag ─────────────────────────────────────────────────
RIAR_ENABLED: bool = True
