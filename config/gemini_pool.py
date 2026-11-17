# gemini_pool.py — Multi-key pool and rotation manager for Gemini API
import os
import time
import logging
from typing import List, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Supported Gemini models in Google GenAI SDK v1beta
VALID_GEMINI_MODELS = ["gemini-3.8-flash"]


class GeminiPool:
    """
    Manages a pool of Gemini API keys with automatic failover and rotation.
    If one key hits a 429 quota exhaustion (e.g. 20 requests/day limit on free tier)
    or 503 high demand/timeout, it automatically rotates to the next available key
    or degrades to local Ollama.
    """

    def __init__(self):
        self._keys: List[str] = []
        self._exhausted_until: dict = {}  # key -> timestamp until when key is exhausted
        self._degraded_until: float = 0.0
        self._current_idx: int = 0
        self._load_keys()

    def _load_keys(self):
        load_dotenv()
        backend_env = Path(__file__).resolve().parents[1] / "backend" / ".env"
        if backend_env.exists():
            load_dotenv(backend_env)

        raw = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        extra = os.getenv("GEMINI_API_KEYS", "")
        combined = f"{raw},{extra}"

        keys = []
        for part in combined.replace("\n", ",").split(","):
            cleaned = part.strip().strip('"').strip("'")
            if cleaned and cleaned not in keys:
                keys.append(cleaned)

        self._keys = keys
        if self._keys:
            logger.info(f"[GeminiPool] Loaded {len(self._keys)} Gemini API key(s).")
        else:
            logger.warning("[GeminiPool] No Gemini API keys found in environment.")

    def get_keys(self) -> List[str]:
        if not self._keys:
            self._load_keys()
        return list(self._keys)

    def is_degraded(self) -> bool:
        return time.time() < self._degraded_until

    def mark_degraded(self, duration_seconds: float = 60.0):
        self._degraded_until = time.time() + duration_seconds
        logger.warning(f"[GeminiPool] Marked Gemini degraded for {duration_seconds}s (503 High Demand / Timeout).")

    def mark_exhausted(self, key: str, retry_delay_seconds: float = 7200.0):
        """Mark a specific key as rate-limited/exhausted for a cooldown duration."""
        self._exhausted_until[key] = time.time() + retry_delay_seconds
        logger.warning(
            f"[GeminiPool] Key ending in ...{key[-6:] if len(key) >= 6 else key} "
            f"marked exhausted for {int(retry_delay_seconds)}s (429 RESOURCE_EXHAUSTED)."
        )

    def get_active_client(self) -> Tuple[Optional[object], Optional[str]]:
        """
        Returns (genai.Client, active_key) for an available non-exhausted key.
        Returns (None, None) if all keys are exhausted, missing, or degraded.
        """
        if self.is_degraded():
            return None, None

        if not self._keys:
            self._load_keys()

        if not self._keys:
            return None, None

        now = time.time()
        # Find first non-exhausted key starting from current index
        total = len(self._keys)
        for offset in range(total):
            idx = (self._current_idx + offset) % total
            candidate = self._keys[idx]
            exhausted_time = self._exhausted_until.get(candidate, 0)
            if now >= exhausted_time:
                self._current_idx = idx
                try:
                    from google import genai
                    from google.genai import types
                    client = genai.Client(
                        api_key=candidate,
                        http_options=types.HttpOptions(timeout=10000)
                    )
                    return client, candidate
                except Exception as e:
                    logger.error(f"[GeminiPool] Failed to initialize client for key: {e}")
                    continue

        logger.warning("[GeminiPool] All Gemini API keys in pool are currently exhausted (429).")
        return None, None

    def get_models(self) -> List[str]:
        configured_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        models = [configured_model] + [m for m in VALID_GEMINI_MODELS if m != configured_model]
        return list(dict.fromkeys(models))


# Global singleton instance
gemini_pool = GeminiPool()
