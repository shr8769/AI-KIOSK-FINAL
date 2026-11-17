"""
TTS Service — Text-To-Speech wrapper.

Priority order:
  1. MMS-TTS (facebook/mms-tts-*) — fully offline HuggingFace model (Hindi, Kannada)
  2. gTTS — high-quality online synthesis (fallback when internet is available)
  3. pyttsx3 SAPI5 — local Windows TTS (English only, last resort)

Owner: Harsha
"""

import asyncio
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lock to ensure only one thread uses SAPI5 engine at a time
_tts_lock = threading.Lock()

# Cache for MMS-TTS models to avoid reloading on every call
_mms_models: Dict[str, Any] = {}
_mms_processors: Dict[str, Any] = {}
_mms_lock = threading.Lock()

# MMS-TTS model IDs for supported languages
_MMS_MODEL_MAP = {
    "hi": "facebook/mms-tts-hin",
    "kn": "facebook/mms-tts-kan",
}

# Default Microsoft Edge-TTS neural voices (Female high-quality online TTS)
_EDGE_VOICE_MAP = {
    "kn": "kn-IN-SapnaNeural",    # Female Kannada
    "hi": "hi-IN-SwaraNeural",    # Female Hindi
    "en": "en-IN-NeerjaNeural",   # Female Indian English
}

# Shorthand mapping for custom voice selection (All mapped to natural female voices by default)
_SHORT_VOICE_MAP = {
    "sapna": "kn-IN-SapnaNeural",
    "swara": "hi-IN-SwaraNeural",
    "neerja": "en-IN-NeerjaNeural",
    "female": "en-IN-NeerjaNeural",
}


def normalize_for_speech(text: str, lang: str = "en") -> str:
    """
    Normalizes text for speech synthesis so that numbers, percentages,
    English loanwords (e.g. 'exams', 'F grade'), and symbols are clearly articulated.
    """
    import re

    if not text:
        return ""

    # Remove markdown links and raw URLs
    clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    clean = re.sub(r'http[s]?://\S+', 'the link provided', clean)
    # Remove markdown formatting characters
    clean = re.sub(r'[*_#`~]', '', clean)

    # Normalize quotes around single letters or grades: 'F' -> F, "A" -> A
    clean = re.sub(r'[\'\"‘“]([A-Za-z0-9])[\'\"’”]', r' \1 ', clean)
    clean = clean.replace("'", " ").replace('"', " ")

    req_lang = (lang or "en").lower().split("-")[0]

    if req_lang in ("hi", "hindi"):
        # Convert percent symbol: 75% -> 75 प्रतिशत
        clean = re.sub(r'(\d+)\s*%', r'\1 प्रतिशत', clean)
        clean = clean.replace('%', ' प्रतिशत')
        # Standardize 'एग्ज़ाम्स' / 'एग्ज़ाम' (remove nuqta collision that breaks phonemizers)
        clean = clean.replace('एग्ज़ाम्स', 'एग्जाम्स').replace('एग्ज़ाम', 'एग्जाम')
        # Common English grades and single letters in Hindi context
        clean = re.sub(r'\bF\b', 'एफ', clean)
        clean = re.sub(r'\bA\b', 'ए', clean)
        clean = re.sub(r'\bB\b', 'बी', clean)
        clean = re.sub(r'\bC\b', 'सी', clean)
        clean = re.sub(r'\bD\b', 'डी', clean)
        clean = re.sub(r'\bS\b', 'एस', clean)
    elif req_lang in ("kn", "kannada"):
        # Convert percent symbol: 75% -> 75 ಪ್ರತಿಶತ
        clean = re.sub(r'(\d+)\s*%', r'\1 ಪ್ರತಿಶತ', clean)
        clean = clean.replace('%', ' ಪ್ರತಿಶತ')
        clean = re.sub(r'\bF\b', 'ಎಫ್', clean)
        clean = re.sub(r'\bA\b', 'ಎ', clean)
        clean = re.sub(r'\bB\b', 'ಬಿ', clean)
        clean = re.sub(r'\bS\b', 'ಎಸ್', clean)
    else:
        # English: 75% -> 75 percent
        clean = re.sub(r'(\d+)\s*%', r'\1 percent', clean)
        clean = clean.replace('%', ' percent')

    # Collapse multiple spaces
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def _get_edge_voice(lang: str, voice_id: str) -> str:
    voice_id_lower = (voice_id or "").lower()
    if voice_id_lower in _SHORT_VOICE_MAP:
        return _SHORT_VOICE_MAP[voice_id_lower]
    if voice_id and voice_id != "default" and "-" in voice_id:
        return voice_id
    # Fallback to defaults
    return _EDGE_VOICE_MAP.get(lang, "en-IN-NeerjaNeural")


def _get_mms_model(lang: str):
    """Load and cache an MMS-TTS model for the given language code."""
    if lang in _mms_models:
        return _mms_models[lang], _mms_processors[lang]

    model_id = _MMS_MODEL_MAP.get(lang)
    if not model_id:
        return None, None

    with _mms_lock:
        # Double-checked locking
        if lang in _mms_models:
            return _mms_models[lang], _mms_processors[lang]
        try:
            from transformers import AutoTokenizer, VitsModel

            logger.info(f"Loading MMS-TTS model '{model_id}' on CPU...")
            processor = AutoTokenizer.from_pretrained(model_id)
            model = VitsModel.from_pretrained(model_id)
            model.eval()

            _mms_processors[lang] = processor
            _mms_models[lang] = model
            logger.info(f"MMS-TTS model '{model_id}' loaded successfully.")
            return model, processor
        except Exception as e:
            logger.error(f"Failed to load MMS-TTS model '{model_id}': {e}")
            return None, None


def _synthesize_mms(text: str, lang: str, filepath: str) -> float:
    """Synthesize speech using facebook/mms-tts and save to filepath. Returns duration."""
    model, processor = _get_mms_model(lang)
    if model is None or processor is None:
        raise RuntimeError(f"MMS-TTS model not available for language: {lang}")

    import scipy.io.wavfile as wavfile
    import torch

    inputs = processor(text, return_tensors="pt")
    with torch.no_grad():
        output = model(**inputs)

    waveform = output.waveform[0].numpy()
    sample_rate = model.config.sampling_rate

    wavfile.write(filepath, sample_rate, waveform)
    duration = len(waveform) / sample_rate
    return round(duration, 2)


def _run_pyttsx3_synthesis(
    text: str, filepath: str, voice_id: str, speed_multiplier: float
) -> float:
    """Synchronous pyttsx3 helper to run in a background thread."""
    with _tts_lock:
        import pyttsx3

        logger.debug(f"Initializing pyttsx3 for: {filepath}")
        engine = pyttsx3.init()

        # Configure speech rate (default is ~200 words per minute)
        rate = engine.getProperty("rate")
        engine.setProperty("rate", int(rate * speed_multiplier))

        # Select voice if requested
        if voice_id and voice_id != "default":
            voices = engine.getProperty("voices")
            for voice in voices:
                if voice_id.lower() in voice.name.lower() or voice_id == voice.id:
                    engine.setProperty("voice", voice.id)
                    logger.debug(f"Selected voice: {voice.name}")
                    break

        engine.save_to_file(text, filepath)
        engine.runAndWait()

        # Estimate duration based on word count (~150 WPM default)
        words = len(text.split())
        duration = round(words * (60.0 / int(rate * speed_multiplier)), 2)

        # Explicit clean-up of SAPI COM reference
        del engine
        return duration


class TTSService:
    async def synthesize(self, request) -> Any:
        """
        Convert text to speech.
        Saves output file to the static/audio directory and returns public audio URL.
        """
        import re

        from app.models.schemas import TTSResponse

        req_lang = (request.language or "en").lower().split("-")[0]

        # Clean and normalize text for natural speech (handles numbers, %, loanwords, and punctuation)
        clean_text = normalize_for_speech(request.text, req_lang)

        start_time = time.time()

        # Ensure static audio directory exists
        static_dir = os.path.join("static", "audio")
        os.makedirs(static_dir, exist_ok=True)

        if settings.USE_MOCK_SERVICES:
            latency_ms = int((time.time() - start_time) * 1000)
            return TTSResponse(
                session_id=request.session_id,
                audio_url="/static/audio/response.mp3",
                duration_seconds=5.0,
                format="mp3",
                latency_ms=latency_ms,
            )

        # ── 1. Edge-TTS (online, Microsoft Neural Female Voices - highest quality) ────
        try:
            import edge_tts

            voice = _get_edge_voice(req_lang, getattr(request, "voice_id", "default"))
            speed = getattr(request, "speed", 1.0)
            rate_pct = int((speed - 1.0) * 100)
            rate_str = f"{'+' if rate_pct >= 0 else ''}{rate_pct}%"

            filename = f"response_{request.session_id}_{uuid.uuid4().hex[:8]}.mp3"
            filepath = os.path.join(static_dir, filename)

            logger.info(f"Synthesizing speech via Edge-TTS (female voice={voice}, rate={rate_str})...")
            communicate = edge_tts.Communicate(
                clean_text, voice, rate=rate_str, boundary="WordBoundary"
            )

            total_duration = 0.0
            with open(filepath, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk.get("type") == "audio":
                        f.write(chunk["data"])
                    elif chunk.get("type") == "WordBoundary":
                        offset = chunk.get("offset", 0)
                        duration = chunk.get("duration", 0)
                        total_duration = (offset + duration) / 10000000.0

            if total_duration == 0.0:
                words = len(clean_text.split())
                total_duration = max(1.0, round(words * 0.45, 2))

            latency_ms = int((time.time() - start_time) * 1000)
            return TTSResponse(
                session_id=request.session_id,
                audio_url=f"/static/audio/{filename}",
                duration_seconds=max(0.5, round(total_duration, 2)),
                format="mp3",
                latency_ms=latency_ms,
            )
        except Exception as e:
            logger.warning(
                f"Edge-TTS synthesis failed: {e}. Falling back to gTTS (Google Female Neural TTS)."
            )

        # ── 2. gTTS (online, Google Natural Female Voice - resilient fallback) ────────
        try:
            from gtts import gTTS

            lang = "en"
            tld = "co.in"
            if req_lang in ("kn", "kannada"):
                lang = "kn"
            elif req_lang in ("hi", "hindi"):
                lang = "hi"

            filename = f"response_{request.session_id}_{uuid.uuid4().hex[:8]}.mp3"
            filepath = os.path.join(static_dir, filename)

            logger.info(f"Synthesizing speech via gTTS female voice (lang={lang})...")
            tts = gTTS(text=clean_text, lang=lang, tld=tld if lang == "en" else "com")
            await asyncio.to_thread(tts.save, filepath)

            words = len(clean_text.split())
            duration = max(1.0, round(words * 0.45, 2))
            latency_ms = int((time.time() - start_time) * 1000)

            return TTSResponse(
                session_id=request.session_id,
                audio_url=f"/static/audio/{filename}",
                duration_seconds=duration,
                format="mp3",
                latency_ms=latency_ms,
            )
        except Exception as e:
            logger.warning(f"gTTS synthesis failed: {e}. Falling back to offline fallback (MMS-TTS).")

        # ── 3. MMS-TTS (offline HuggingFace fallback, Hindi & Kannada) ──────────────
        if req_lang in _MMS_MODEL_MAP:
            try:
                filename = f"response_{request.session_id}_{uuid.uuid4().hex[:8]}.wav"
                filepath = os.path.join(static_dir, filename)

                logger.info(f"Synthesizing speech via offline MMS-TTS (lang={req_lang})...")
                duration = await asyncio.to_thread(
                    _synthesize_mms, clean_text, req_lang, filepath
                )

                latency_ms = int((time.time() - start_time) * 1000)
                return TTSResponse(
                    session_id=request.session_id,
                    audio_url=f"/static/audio/{filename}",
                    duration_seconds=max(0.5, duration),
                    format="wav",
                    latency_ms=latency_ms,
                )
            except Exception as e:
                logger.warning(
                    f"MMS-TTS synthesis failed for lang={req_lang}: {e}. Falling back to pyttsx3."
                )

        # ── 4. pyttsx3 SAPI5 (offline fallback, English only, last resort) ────
        try:
            filename = f"response_{request.session_id}_{uuid.uuid4().hex[:8]}.wav"
            filepath = os.path.join(static_dir, filename)

            duration = await asyncio.to_thread(
                _run_pyttsx3_synthesis,
                clean_text,
                filepath,
                getattr(request, "voice_id", "default"),
                getattr(request, "speed", 1.0),
            )

            latency_ms = int((time.time() - start_time) * 1000)
            audio_url = f"/static/audio/{filename}"

            return TTSResponse(
                session_id=request.session_id,
                audio_url=audio_url,
                duration_seconds=duration,
                format="wav",
                latency_ms=latency_ms,
            )

        except Exception as e:
            logger.exception(f"TTS Service synthesis failed completely: {e}")
            raise


# Singleton instance
tts_service = TTSService()
