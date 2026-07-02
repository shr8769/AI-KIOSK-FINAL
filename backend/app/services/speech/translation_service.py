"""
Translation Service — Multi-tier translation for EN ↔ HI ↔ KN.

Tier 1 (Primary):   deep_translator (Google Translate) — excellent quality, needs internet
Tier 2 (Offline):   MarianMT via MarianMTModel directly — bypasses pipeline(), works offline
Tier 3 (Fallback):  Return original text

Why not pipeline("translation", ...)?
  The `pipeline("translation", ...)` task was removed in transformers ≥ v5.x.
  We call MarianMTModel + MarianTokenizer directly instead.

Degenerate output detection prevents garbage like "ಅಡ್ನ್ನ್ನ..." from propagating.

Owner: Antigravity
"""

import logging
import re
from collections import Counter
from typing import Optional

logger = logging.getLogger(__name__)

# ── Degenerate output detection ───────────────────────────────────────────────

# Indic scripts (Kannada, Hindi) naturally have low char uniqueness because combining
# characters (virama ್/् , vowel signs) appear in almost every syllable.
# These thresholds must be loose enough to never reject valid Indic text.
_DEGENERATE_UNIQUE_RATIO = 0.15  # flag only if < 15% unique chars
_DEGENERATE_REPEAT_THRESHOLD = 0.40  # flag only if a single ngram is > 40% of all ngrams


def _is_degenerate(text: str) -> bool:
    """
    Return True if the translated text is a repetition loop artifact.
    Detects patterns like "ಅಡ್ನ್ನ್ನ..." where a short ngram dominates the output.

    Calibrated on real Kannada data:
      - Garbage: unique_ratio < 0.15  AND  max_ngram_dominance > 0.40
      - Valid Kannada: unique_ratio > 0.30  AND  max_ngram_dominance < 0.10
    Both conditions must hold (AND) to avoid false positives on legitimate Indic text.
    """
    if not text or len(text) < 15:
        return False

    stripped = text.replace(" ", "")
    if not stripped:
        return False

    unique_ratio = len(set(stripped)) / len(stripped)

    # If unique ratio is healthy, definitely not degenerate — fast exit
    if unique_ratio >= _DEGENERATE_UNIQUE_RATIO:
        return False

    # Only check ngram dominance when unique ratio is already suspicious
    max_ngram_dom = 0.0
    for n in (2, 3, 4):
        ngrams = [stripped[i : i + n] for i in range(len(stripped) - n + 1)]
        if ngrams:
            top_count = Counter(ngrams).most_common(1)[0][1]
            max_ngram_dom = max(max_ngram_dom, top_count / len(ngrams))

    # Both conditions must hold: low uniqueness AND high ngram repetition
    if max_ngram_dom > _DEGENERATE_REPEAT_THRESHOLD:
        logger.warning(
            f"Degenerate translation (unique={unique_ratio:.2f}, ngram_dom={max_ngram_dom:.2f}): "
            f"'{text[:60]}'"
        )
        return True

    return False


def _split_sentences(text: str) -> list[str]:
    """Split text on sentence boundaries for chunk-level translation."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    result = []
    for part in parts:
        sub = re.split(r"\n(?=\d+\.)", part)
        result.extend(sub)
    return [s.strip() for s in result if s.strip()]


# ── MarianMT cache ────────────────────────────────────────────────────────────

_marian_models: dict = {}
_marian_tokenizers: dict = {}

_MARIAN_MAP = {
    "hi_to_en": "Helsinki-NLP/opus-mt-hi-en",
    "en_to_hi": "Helsinki-NLP/opus-mt-en-hi",
    "kn_to_en": "Helsinki-NLP/opus-mt-dra-en",
    "en_to_kn": "Helsinki-NLP/opus-mt-en-dra",
}

# Language prefix tokens for the multilingual Dravidian model
_MARIAN_PREFIX = {
    "en_to_kn": ">>kan<< ",
    "kn_to_en": ">>eng<< ",
}


def _get_marian(direction: str):
    """Lazy-load and cache MarianMT model + tokenizer (bypasses pipeline())."""
    if direction in _marian_models:
        return _marian_models[direction], _marian_tokenizers[direction]

    model_name = _MARIAN_MAP.get(direction)
    if not model_name:
        return None, None

    try:
        from transformers import MarianMTModel, MarianTokenizer

        logger.info(f"Loading MarianMT model '{model_name}'...")
        tok = MarianTokenizer.from_pretrained(model_name)
        mdl = MarianMTModel.from_pretrained(model_name)
        mdl.eval()
        _marian_tokenizers[direction] = tok
        _marian_models[direction] = mdl
        logger.info(f"MarianMT model '{model_name}' loaded.")
        return mdl, tok
    except Exception as e:
        logger.error(f"Failed to load MarianMT '{model_name}': {e}")
        return None, None


def _marian_translate_chunk(text: str, direction: str) -> Optional[str]:
    """Translate a single text chunk with MarianMT. Returns None on failure."""
    model, tokenizer = _get_marian(direction)
    if model is None:
        return None

    prefix = _MARIAN_PREFIX.get(direction, "")
    src_text = prefix + text

    try:
        import torch

        inputs = tokenizer(
            [src_text], return_tensors="pt", padding=True, truncation=True, max_length=512
        )
        with torch.no_grad():
            translated_ids = model.generate(
                **inputs,
                max_new_tokens=512,
                num_beams=4,
                early_stopping=True,
                no_repeat_ngram_size=3,
            )
        result = tokenizer.decode(translated_ids[0], skip_special_tokens=True).strip()

        # Strip language tokens if model echoed them
        for tok_prefix in [">>kan<<", ">>eng<<", ">>hin<<"]:
            if result.startswith(tok_prefix):
                result = result[len(tok_prefix) :].strip()

        if _is_degenerate(result):
            return None
        return result
    except Exception as e:
        logger.error(f"MarianMT inference failed ({direction}): {e}")
        return None


# ── Main service class ────────────────────────────────────────────────────────


class OfflineTranslationService:
    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Translate text between English, Hindi, and Kannada.

        Tier order:
          1. Google Translate (deep_translator) — best quality, internet needed
          2. MarianMT sentence-chunked — offline
          3. Original text — guaranteed non-garbage fallback

        Args:
            text: Input text.
            source_lang: 'en', 'hi', or 'kn'.
            target_lang: 'en', 'hi', or 'kn'.

        Returns:
            Translated string, or original if all methods fail.
        """
        if not text or not text.strip():
            return text

        # Normalize language codes
        lang_map = {"kannada": "kn", "hindi": "hi", "english": "en"}
        source = lang_map.get(source_lang.lower().split("-")[0], source_lang.lower().split("-")[0])
        target = lang_map.get(target_lang.lower().split("-")[0], target_lang.lower().split("-")[0])

        if source == target:
            return text

        direction = f"{source}_to_{target}"

        # ── Tier 1: Google Translate ──────────────────────────────────────────
        try:
            from deep_translator import GoogleTranslator

            # Use 'auto' source only when source is unknown; explicit codes are faster & more reliable
            gt_source = "auto" if source not in ("en", "hi", "kn") else source
            translated = GoogleTranslator(source=gt_source, target=target).translate(text)
            if translated and not _is_degenerate(translated):
                logger.info(
                    f"Google Translate succeeded ({source}→{target}): '{text[:40]}' → '{translated[:40]}'"
                )
                return translated
            logger.warning("Google Translate returned degenerate output. Falling back to MarianMT.")
        except Exception as e:
            logger.warning(f"Google Translate unavailable ({e}). Falling back to MarianMT.")

        # ── Tier 2: MarianMT (offline, sentence-chunked) ──────────────────────
        if direction in _MARIAN_MAP:
            sentences = _split_sentences(text)
            translated_parts = []
            all_ok = True

            for sentence in sentences:
                part = _marian_translate_chunk(sentence, direction)
                if part is None:
                    all_ok = False
                    break
                translated_parts.append(part)

            if all_ok and translated_parts:
                result = " ".join(translated_parts)
                logger.info(f"MarianMT translation succeeded ({source}→{target}).")
                return result

            # Try the full text as one chunk (for very short inputs)
            if len(sentences) == 1 or not all_ok:
                result = _marian_translate_chunk(text, direction)
                if result:
                    return result

        # ── Tier 3: Return original text (non-garbage guarantee) ──────────────
        logger.warning(
            f"All translation methods failed ({source}→{target}). Returning original text."
        )
        return text


# Singleton instance
offline_translation_service = OfflineTranslationService()
