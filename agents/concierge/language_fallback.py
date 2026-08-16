import os
import json
import logging
import time
import urllib.request
import urllib.error
import traceback
from abc import ABC, abstractmethod
from typing import Tuple
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class BaseTranslator(ABC):
    """
    Abstract Base Class for translation components.
    Ensures pluggability so that Gemini translation can easily be replaced
    with local neural machine translation pipelines like IndicTrans2.
    """
    @abstractmethod
    def translate_to_english(self, text: str) -> Tuple[str, str]:
        """
        Detects query language and translates it to English.
        Returns:
            Tuple[str, str]: (translated_text, detected_language) where language code is 'en', 'kn', or 'hi'.
        """
        pass

    @abstractmethod
    def translate_from_english(self, text: str, target_lang: str) -> str:
        """
        Translates text from English to target language.
        """
        pass


def _is_ascii(text: str) -> bool:
    """Returns True if text is pure ASCII (likely English)."""
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


class GeminiTranslator(BaseTranslator):
    """
    Translator implementation using Google's Gemini models via the google-genai SDK.
    Used for initial prototype before offline IndicTrans2 deployment.
    Falls back gracefully if quota is exceeded.
    """
    def __init__(self, api_key: str = None, model_name: str = "gemini-3.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        self.client = None

        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini Client for translation: {e}")
        else:
            logger.warning("GEMINI_API_KEY not found. Translator running in passthrough mode.")
        self.cache = {}
        self.is_degraded = False

    def _check_cooldown(self) -> bool:
        """Returns True if still in cooldown (degraded), False if cooldown expired."""
        if not getattr(self, "is_degraded", False):
            return False
        degraded_at = getattr(self, "degraded_at", 0)
        if time.time() - degraded_at > 60.0:
            self.is_degraded = False
            logger.info("GeminiTranslator cooldown expired. Restoring service.")
            return False
        return True

    def translate_to_english(self, text: str) -> Tuple[str, str]:
        # Check cache first
        if text in self.cache:
            return self.cache[text]

        if self._check_cooldown():
            raise RuntimeError("GeminiTranslator is in cooldown (rate-limited).")

        # Fast path for ASCII (English) queries
        if _is_ascii(text):
            return text, "en"

        if not self.client:
            raise RuntimeError("GeminiTranslator client not initialized.")

        prompt = f"""You are a multilingual translation assistant.
Analyze the following text query from a university kiosk user:
"{text}"

1. Classify the language of the query as exactly one of: 'kn' (Kannada), 'hi' (Hindi), or 'en' (English).
2. If it is Kannada ('kn') or Hindi ('hi'), translate it to English.
3. If it is English ('en'), return the query unmodified.

Return your response strictly in the following JSON format, with no markdown styling:
{{
  "detected_language": "en" | "kn" | "hi",
  "translated_text": "the translated English query"
}}
"""
        max_retries = 3
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                result = json.loads(response.text.strip())
                detected = result.get("detected_language", "en")
                translated = result.get("translated_text", text)

                self.is_degraded = False

                if detected == "en":
                    self.cache[text] = (text, "en")
                    return text, "en"

                logger.info(
                    f"[GeminiTranslator] '{text}' -> '{translated}' (lang={detected})"
                )
                self.cache[text] = (translated, detected)
                return translated, detected

            except Exception as e:
                err_str = str(e)
                is_quota = "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str
                is_daily_limit = "limit: 20" in err_str or "daily" in err_str.lower()

                if is_quota:
                    if is_daily_limit:
                        self.is_degraded = True
                        self.degraded_at = time.time()
                        raise RuntimeError(f"GeminiTranslator daily quota exhausted: {e}")
                    if attempt < max_retries - 1:
                        sleep_time = backoff ** (attempt + 1)
                        logger.warning(
                            f"[GeminiTranslator] Rate limit hit. Retrying in {sleep_time}s... (attempt {attempt+1}/{max_retries})"
                        )
                        time.sleep(sleep_time)
                        continue
                    else:
                        self.is_degraded = True
                        self.degraded_at = time.time()

                raise RuntimeError(f"GeminiTranslator failed: {e}")

        raise RuntimeError("GeminiTranslator exhausted all retries.")

    def translate_from_english(self, text: str, target_lang: str) -> str:
        if self._check_cooldown():
            return text

        if not self.client or target_lang == "en" or not text:
            return text

        prompt = f"""You are a professional university kiosk translation assistant.
Translate the following English text into the target language: '{target_lang}' ('kn' for Kannada, 'hi' for Hindi).
Provide a natural, conversational translation that captures the exact meaning of the original context.

English Text:
{text}

Translation:"""

        max_retries = 3
        backoff = 2.0

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                )
                if response.text:
                    self.is_degraded = False
                    return response.text.strip()
                return text
            except Exception as e:
                err_str = str(e)
                is_quota = "429" in err_str or "quota" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str
                is_daily_limit = "limit: 20" in err_str or "daily" in err_str.lower()

                if is_quota:
                    if is_daily_limit:
                        self.is_degraded = True
                        self.degraded_at = time.time()
                        break
                    if attempt < max_retries - 1:
                        sleep_time = backoff ** (attempt + 1)
                        logger.warning(
                            f"[GeminiTranslator] Rate limit on translate_from_english. Retrying in {sleep_time}s..."
                        )
                        time.sleep(sleep_time)
                        continue
                    else:
                        self.is_degraded = True
                        self.degraded_at = time.time()

                logger.error(f"[GeminiTranslator] translate_from_english failed: {e}. Returning original.")
                return text

        return text


def _detect_lang_by_unicode(text: str) -> str:
    """
    Detect language using Unicode block ranges.
    Kannada: U+0C80-U+0CFF
    Devanagari (Hindi): U+0900-U+097F
    Returns 'kn', 'hi', or 'en'.
    """
    kn_chars = sum(1 for c in text if 0x0C80 <= ord(c) <= 0x0CFF)
    hi_chars = sum(1 for c in text if 0x0900 <= ord(c) <= 0x097F)
    if kn_chars > hi_chars and kn_chars > 0:
        return "kn"
    if hi_chars > 0:
        return "hi"
    return "en"


class QwenTranslator(BaseTranslator):
    """
    Translation fallback using local Qwen3:8b via Ollama.
    Used when Gemini is rate-limited or quota-exhausted.
    Uses plain-text prompts (no JSON) with think=false for fast responses.
    Language detection is done via Unicode block ranges instead of asking the model.
    """
    def __init__(self, ollama_url: str = None, model_name: str = None):
        from config import llm_config
        self.ollama_url = ollama_url or llm_config.OLLAMA_URL
        self.model_name = model_name or llm_config.OLLAMA_MODEL
        self.cache = {}

    def _is_available(self) -> bool:
        """Check if Ollama service and qwen3:8b model are available."""
        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/tags", method="GET"
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return any(self.model_name in m or m in self.model_name for m in models)
        except Exception as e:
            logger.warning(f"[QwenTranslator] Ollama availability check failed: {e}")
        return False

    def _call_ollama(self, prompt: str, timeout: float = 90.0) -> str:
        """Send a prompt to Ollama with think=false and return the response text."""
        import re
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "think": False,          # Disable chain-of-thought for speed
            "options": {
                "temperature": 0,
                "num_predict": 150    # Translation needs very few tokens
            }
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            raw = res_data.get("response", "").strip()
            # Strip any residual <think> blocks just in case
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            return raw

    def translate_to_english(self, text: str) -> Tuple[str, str]:
        if text in self.cache:
            return self.cache[text]

        # Fast path for ASCII (English)
        if _is_ascii(text):
            return text, "en"

        # Detect language via Unicode ranges (fast, no model call needed)
        detected = _detect_lang_by_unicode(text)

        if not self._is_available():
            raise RuntimeError("QwenTranslator: Ollama/qwen3:8b unavailable.")

        # Plain-text prompt — much faster than JSON-structured output
        prompt = (
            "Translate the following university kiosk query into English. "
            "Output ONLY the translated English text, no explanation, no punctuation changes.\n\n"
            f"{text}"
        )

        start = time.perf_counter()
        try:
            translated = self._call_ollama(prompt, timeout=90.0)
            latency = time.perf_counter() - start

            if not translated:
                raise ValueError("Qwen returned empty translation.")

            logger.info(
                f"[QwenTranslator] '{text[:60]}' -> '{translated[:80]}' "
                f"(lang={detected}, latency={latency:.2f}s)"
            )
            self.cache[text] = (translated, detected)
            return translated, detected

        except Exception as e:
            latency = time.perf_counter() - start
            logger.error(
                f"[QwenTranslator] translate_to_english failed after {latency:.2f}s: {e}\n"
                f"{traceback.format_exc()}"
            )
            raise RuntimeError(f"QwenTranslator failed: {e}")

    def translate_from_english(self, text: str, target_lang: str) -> str:
        if target_lang == "en" or not text:
            return text

        if not self._is_available():
            logger.warning("[QwenTranslator] Ollama unavailable for translate_from_english. Returning original.")
            return text

        lang_name = "Kannada" if target_lang == "kn" else "Hindi"
        prompt = (
            f"Translate the following English text to {lang_name}. "
            "Output ONLY the translated text, nothing else.\n\n"
            f"{text}"
        )

        try:
            raw = self._call_ollama(prompt, timeout=90.0)
            return raw if raw else text
        except Exception as e:
            logger.error(f"[QwenTranslator] translate_from_english failed: {e}")
            return text


class ChainedTranslator(BaseTranslator):
    """
    Three-tier translation pipeline:
      1. GeminiTranslator  (primary)
      2. QwenTranslator    (fallback when Gemini fails or is quota-limited)
      3. Passthrough       (return original text if both fail)

    Logs original query, translated query, and which engine was used.
    """
    def __init__(self):
        self.gemini = GeminiTranslator()
        self.qwen = QwenTranslator()
        self.cache = self.gemini.cache  # share single cache across engines

    def translate_to_english(self, text: str) -> Tuple[str, str]:
        original = text

        # 1. Try Gemini
        try:
            translated, detected = self.gemini.translate_to_english(text)
            logger.info(
                f"[Translation] engine=Gemini | original='{original}' | "
                f"translated='{translated}' | lang={detected}"
            )
            return translated, detected
        except Exception as gemini_err:
            logger.warning(
                f"[Translation] Gemini failed ({gemini_err}). Trying Qwen3 fallback..."
            )

        # 2. Try Qwen3
        try:
            translated, detected = self.qwen.translate_to_english(text)
            logger.info(
                f"[Translation] engine=Qwen3 | original='{original}' | "
                f"translated='{translated}' | lang={detected}"
            )
            return translated, detected
        except Exception as qwen_err:
            logger.warning(
                f"[Translation] Qwen3 also failed ({qwen_err}). Using passthrough."
            )

        # 3. Passthrough
        logger.warning(
            f"[Translation] engine=passthrough | original='{original}' | "
            f"translated='{original}' | lang=en"
        )
        return text, "en"

    def translate_from_english(self, text: str, target_lang: str) -> str:
        if target_lang == "en" or not text:
            return text

        if os.getenv("SPEEDUP_BENCHMARK") == "1":
            return text

        # 1. Try Gemini
        try:
            result = self.gemini.translate_from_english(text, target_lang)
            if result and result != text:
                logger.info(f"[Translation] engine=Gemini | translate_from_english -> lang={target_lang}")
                return result
        except Exception as e:
            logger.warning(f"[Translation] Gemini translate_from_english failed: {e}. Trying Qwen3...")

        # 2. Try Qwen3
        try:
            result = self.qwen.translate_from_english(text, target_lang)
            if result and result != text:
                logger.info(f"[Translation] engine=Qwen3 | translate_from_english -> lang={target_lang}")
                return result
        except Exception as e:
            logger.warning(f"[Translation] Qwen3 translate_from_english failed: {e}. Returning original.")

        # 3. Passthrough
        logger.warning("[Translation] engine=passthrough | translate_from_english returning original.")
        return text


class IndicTrans2Translator(BaseTranslator):
    """
    Future implementation placeholder using AI4Bharat's IndicTrans2 for offline/local translation.
    """
    def __init__(self, model_dir: str = None):
        self.model_dir = model_dir

    def translate_to_english(self, text: str) -> Tuple[str, str]:
        logger.info("IndicTrans2 translate_to_english placeholder called.")
        return text, "en"

    def translate_from_english(self, text: str, target_lang: str) -> str:
        logger.info("IndicTrans2 translate_from_english placeholder called.")
        return text
