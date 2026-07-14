"""
detection/face_extractor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FR-8: Facial Recognition — Face Embedding Extractor
Owner: Harsha

Wraps InsightFace (buffalo_sc lightweight model) to extract
512D L2-normalised face embeddings from raw OpenCV frames.

Design decisions:
- Model is loaded in a daemon thread at startup so it never
  blocks YOLO's camera loop.
- extract() is thread-safe (guarded by _lock).
- If InsightFace is not installed or fails to load, the class
  degrades silently — detect() returns None and FR-8 is
  effectively disabled. The rest of the pipeline is unaffected.
"""

import logging
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class FaceExtractor:
    """
    Thread-safe InsightFace wrapper for 512D face embedding extraction.

    Usage:
        extractor = FaceExtractor()
        embedding = extractor.extract(frame)   # list[float] | None
    """

    def __init__(self):
        self._app = None
        self._lock = threading.Lock()
        self._ready = False
        # Load heavyweight ONNX model in background — never blocks startup.
        threading.Thread(
            target=self._load_model, daemon=True, name="insightface-loader"
        ).start()

    # ── Private ───────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Blocking model load — runs once in a background thread."""
        try:
            from insightface.app import FaceAnalysis  # type: ignore

            # buffalo_sc = lightweight single-model variant (detection + recognition).
            # ctx_id=-1 forces CPU inference, avoiding GPU/CUDA driver issues on kiosk.
            app = FaceAnalysis(name="buffalo_sc", providers=["CPUExecutionProvider"])
            app.prepare(
                ctx_id=-1, det_size=(320, 320)
            )  # 320×320 is fast enough for kiosk

            with self._lock:
                self._app = app
                self._ready = True

            logger.info("[FR-8] InsightFace 'buffalo_sc' model loaded on CPU.")
        except ImportError:
            logger.warning(
                "[FR-8] InsightFace not installed. "
                "Run: pip install insightface onnxruntime. "
                "FR-8 (facial recognition) will be disabled."
            )
        except Exception as e:
            logger.error(
                f"[FR-8] InsightFace failed to initialise: {e}. FR-8 disabled."
            )

    # ── Public ────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        """True once the model has finished loading."""
        with self._lock:
            return self._ready

    def extract(self, frame) -> Optional[list]:
        """
        Extract a 512D L2-normalised face embedding from an OpenCV BGR frame.

        Args:
            frame: numpy ndarray in BGR format (as returned by cv2.VideoCapture.read()).

        Returns:
            list[float] of length 512, or None if no face detected / model not ready.
        """
        with self._lock:
            if not self._ready or self._app is None:
                return None
            app = self._app  # local ref so we can release the lock

        try:
            faces = app.get(frame)
        except Exception as e:
            logger.warning(f"[FR-8] InsightFace inference error: {e}")
            return None

        if not faces:
            return None

        # Use the largest detected face (assumed to be the user closest to camera).
        best_face = max(
            faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        )

        embedding: np.ndarray = best_face.embedding  # shape (512,)

        # L2-normalise so cosine similarity reduces to a dot product.
        norm = np.linalg.norm(embedding)
        if norm == 0:
            logger.warning("[FR-8] Zero-norm embedding — skipping.")
            return None

        normalised = (embedding / norm).astype(np.float32).tolist()
        logger.debug(f"[FR-8] Embedding extracted (dim={len(normalised)}).")
        return normalised


# ── Module-level singleton ─────────────────────────────────────────────────
# Shared by detection/main.py — import and use directly.
face_extractor = FaceExtractor()
