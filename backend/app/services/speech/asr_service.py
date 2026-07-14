"""
ASR Service — Speech-To-Text with 3-tier pipeline:
  Tier 1: Bhashini API     (best Indian language quality, needs credentials)
  Tier 2: Google Speech    (free, no key, excellent kn-IN/hi-IN, needs internet)
  Tier 3: faster-whisper   (fully offline fallback)
Owner: Harsha
"""

import base64
import io
import logging
import re
import time
import wave
from collections import Counter
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)


def _clean_whisper_transcript(text: str) -> str:
    """
    Remove Whisper hallucination artifacts from the transcript.

    Whisper (especially base/small models) can loop and generate repetitive
    characters at the end of a transcript, e.g.:
      "ಪ್ರವೇಶ ಪ್ರಕ್ರಿಯೆ ಹೆಗಿದ ನನನನನನನನನನನನ..."
      "admission process hai nnnnnnnn..."

    Strategy:
    1. Detect 3+ consecutive identical characters → truncate at that point.
    2. Sliding window: if the last 40% of text has ngram dominance > 60%,
       keep only the clean prefix.
    3. Cap transcript at 250 characters (a spoken query is never longer).
    """
    if not text:
        return text

    # Step 1: cut at first occurrence of 3+ consecutive identical characters
    match = re.search(r"(.)\1{2,}", text)
    if match:
        text = text[: match.start()].rstrip()

    # Step 2: sliding-window ngram check on the tail
    if len(text) > 30:
        tail_start = len(text) * 6 // 10  # last 40%
        tail = text[tail_start:].replace(" ", "")
        if len(tail) > 8:
            for n in (2, 3):
                ngrams = [tail[i : i + n] for i in range(len(tail) - n + 1)]
                if ngrams:
                    top = Counter(ngrams).most_common(1)[0][1]
                    if top / len(ngrams) > 0.60:
                        # Find the last clean word boundary before the tail
                        clean_end = text[:tail_start].rstrip()
                        if clean_end:
                            text = clean_end
                        break

    # Step 3: cap length
    if len(text) > 250:
        # Prefer to cut at last sentence break within 250 chars
        for punct in ["।", ".", "?", "!", ",", " "]:
            idx = text.rfind(punct, 0, 250)
            if idx > 20:
                text = text[: idx + 1]
                break
        else:
            text = text[:250]

    return text.strip()


class ASRService:
    def __init__(self):
        self.model = None

    def _get_model(self):
        """Lazy load Whisper model to avoid slow server startup."""
        if self.model is None:
            model_size = settings.WHISPER_MODEL_SIZE
            logger.info(f"Loading faster-whisper model '{model_size}' on CPU...")
            from faster_whisper import WhisperModel

            # Using configured model with int8 quantization for speed on CPU
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info(f"faster-whisper model '{model_size}' loaded.")
        return self.model

    def preload(self):
        """Force load the Whisper model into GPU/CPU memory."""
        self._get_model()

    def warmup_inference(self):
        """Run a dummy transcription of 1 second silence to compile CUDA kernels and optimize graph."""
        logger.info("Warming up Whisper model with dummy audio...")
        import numpy as np

        # 1 second of silence at 16kHz
        dummy_audio = np.zeros(16000, dtype=np.float32)
        model = self._get_model()
        # Discard output, just force inference
        try:
            model.transcribe(dummy_audio, beam_size=1, best_of=1, temperature=0.0, language="en")
        except Exception:
            pass
        logger.info("Whisper model warm-up complete.")

    def _load_wav_to_numpy(self, audio_bytes: bytes) -> "np.ndarray":
        """
        Decodes WAV file bytes directly into a normalized float32 numpy array.
        Bypasses FFmpeg dependency entirely. Falls back to raw 16-bit PCM.
        """
        import numpy as np

        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
                n_channels = wav_file.getnchannels()
                sample_width = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                n_frames = wav_file.getnframes()

                raw_data = wav_file.readframes(n_frames)

                if sample_width == 2:
                    data = np.frombuffer(raw_data, dtype=np.int16)
                elif sample_width == 1:
                    data = np.frombuffer(raw_data, dtype=np.uint8) - 128
                elif sample_width == 4:
                    data = np.frombuffer(raw_data, dtype=np.int32)
                else:
                    raise ValueError(f"Unsupported WAV sample width: {sample_width}")

                # Normalize to [-1.0, 1.0]
                if sample_width == 2:
                    data = data.astype(np.float32) / 32768.0
                elif sample_width == 1:
                    data = data.astype(np.float32) / 128.0
                elif sample_width == 4:
                    data = data.astype(np.float32) / 2147483648.0

                # Convert stereo to mono
                if n_channels > 1:
                    data = data.reshape(-1, n_channels).mean(axis=1)

                # Resample to 16kHz if needed (Whisper expects 16kHz)
                if framerate != 16000:
                    duration = len(data) / framerate
                    target_samples = int(duration * 16000)
                    data = np.interp(
                        np.linspace(0, len(data), target_samples, endpoint=False),
                        np.arange(len(data)),
                        data,
                    ).astype(np.float32)

                return data
        except Exception as e:
            # Fallback to raw PCM 16kHz 16-bit mono
            try:
                data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                return data
            except Exception:
                raise ValueError(f"Failed to decode audio bytes as WAV or raw PCM: {e}")

    async def transcribe(self, request) -> Any:
        """
        Transcribe audio to text.
        Returns ASRResponse with transcript and latency.
        """
        from app.models.schemas import ASRResponse

        start_time = time.time()

        if settings.USE_MOCK_SERVICES:
            # Mock transcription behavior
            latency_ms = int((time.time() - start_time) * 1000)
            return ASRResponse(
                session_id=request.session_id,
                turn_id=request.turn_id,
                transcript="Where is the admissions office?",
                transcript_en="Where is the admissions office?",
                detected_language="en",
                confidence=0.95,
                duration_ms=3000,
                latency_ms=latency_ms,
            )

        try:
            # 1. Attempt Bhashini Speech-To-Text if enabled and credentials exist
            from app.services.speech.bhashini_service import bhashini_service

            if settings.USE_BHASHINI and bhashini_service.has_credentials():
                lang_hint = (
                    request.language_hint if request.language_hint in ["en", "kn", "hi"] else "hi"
                )
                transcript = bhashini_service.transcribe_audio(
                    request.audio_base64, language=lang_hint
                )

                if transcript:
                    duration_ms = 3000  # Placeholder duration
                    latency_ms = int((time.time() - start_time) * 1000)
                    return ASRResponse(
                        session_id=request.session_id,
                        turn_id=request.turn_id,
                        transcript=transcript,
                        transcript_en=transcript,  # Will be translated by session WebSocket handler
                        detected_language=lang_hint,
                        confidence=1.0,
                        duration_ms=duration_ms,
                        latency_ms=latency_ms,
                    )
                else:
                    logger.warning(
                        "Bhashini ASR returned empty transcript. Falling back to Google Speech."
                    )

            # ── Tier 2: Google Speech Recognition (free, no API key needed) ──────
            # Supports kn-IN and hi-IN natively. Falls back to Whisper if offline.
            lang_hint_raw = (
                request.language_hint if request.language_hint in ["en", "kn", "hi"] else None
            )
            google_lang_map = {"kn": "kn-IN", "hi": "hi-IN", "en": "en-US"}
            google_lang = google_lang_map.get(lang_hint_raw, "kn-IN")

            try:
                import speech_recognition as sr

                recognizer = sr.Recognizer()
                audio_bytes_raw = base64.b64decode(request.audio_base64)

                # Convert raw bytes to AudioData (speech_recognition expects WAV)
                with sr.AudioFile(io.BytesIO(audio_bytes_raw)) as source:
                    audio_data_sr = recognizer.record(source)

                google_transcript = recognizer.recognize_google(
                    audio_data_sr, language=google_lang, show_all=False
                )

                if google_transcript and google_transcript.strip():
                    google_transcript = _clean_whisper_transcript(google_transcript)
                    logger.info(f"Google Speech ASR success ({google_lang}): '{google_transcript}'")
                    latency_ms = int((time.time() - start_time) * 1000)
                    return ASRResponse(
                        session_id=request.session_id,
                        turn_id=request.turn_id,
                        transcript=google_transcript,
                        transcript_en=google_transcript,
                        detected_language=lang_hint_raw or "kn",
                        confidence=0.95,
                        duration_ms=3000,
                        latency_ms=latency_ms,
                    )
                else:
                    logger.warning("Google Speech returned empty. Falling back to Whisper.")

            except Exception as google_err:
                logger.warning(
                    f"Google Speech ASR unavailable ({google_err}). Falling back to Whisper."
                )

            # ── Tier 3: faster-whisper (fully offline) ────────────────────────────
            audio_bytes = base64.b64decode(request.audio_base64)
            audio_data = self._load_wav_to_numpy(audio_bytes)

            model = self._get_model()
            lang_hint = (
                request.language_hint if request.language_hint in ["en", "kn", "hi"] else None
            )

            # Define language-specific prompt to guide the script/spelling of Whisper
            initial_prompt = None
            if lang_hint == "kn":
                initial_prompt = "ಕನ್ನಡ"
            elif lang_hint == "hi":
                initial_prompt = "हिंदी"
            elif lang_hint == "en":
                initial_prompt = "English"

            # Transcribe audio array with VAD filtering and script prompt guidance
            # no_repeat_ngram_size and log_prob_threshold reduce hallucination loops
            segments, info = model.transcribe(
                audio_data,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                language=lang_hint,
                initial_prompt=initial_prompt,
                vad_filter=True,
                condition_on_previous_text=False,
                no_repeat_ngram_size=3,
                log_prob_threshold=-1.0,
                compression_ratio_threshold=2.4,
            )
            raw_transcript = "".join([segment.text for segment in segments]).strip()

            # Remove Whisper hallucination loops (e.g. "ನನನನ...", repeated chars)
            transcript = _clean_whisper_transcript(raw_transcript)
            if transcript != raw_transcript:
                logger.warning(
                    f"Whisper hallucination cleaned: '{raw_transcript[:60]}...' → '{transcript}'"
                )

            duration_ms = int(info.duration * 1000)
            latency_ms = int((time.time() - start_time) * 1000)

            # Simple translation skeleton: if English is detected, transcript_en matches transcript
            transcript_en = transcript

            return ASRResponse(
                session_id=request.session_id,
                turn_id=request.turn_id,
                transcript=transcript,
                transcript_en=transcript_en,
                detected_language=info.language,
                confidence=round(info.language_probability, 3),
                duration_ms=duration_ms,
                latency_ms=latency_ms,
            )

        except Exception as e:
            logger.exception(f"ASR Service transcription failed: {e}")
            raise


# Singleton instance
asr_service = ASRService()
