#!/usr/bin/env python3
"""
ocr_processor.py

Detects images that may contain text (fee tables, notices, schedules)
and runs Tesseract OCR to extract the text. Appends extracted text
to the parent page's Markdown file or creates standalone documents.

Gracefully skips if Tesseract is not installed.
"""

import io
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests

from scripts.data_ingestion.crawler_config import (
    OCR_MIN_IMAGE_WIDTH, OCR_MIN_IMAGE_HEIGHT, OCR_ENABLED, OUTPUT_DIR,
)

logger = logging.getLogger("ocr_processor")

# Check Tesseract availability at import time
TESSERACT_AVAILABLE = False
try:
    import pytesseract
    from PIL import Image
    # Quick test
    pytesseract.get_tesseract_version()
    TESSERACT_AVAILABLE = True
except Exception:
    pass


def is_ocr_available() -> bool:
    """Check if OCR dependencies are available."""
    return TESSERACT_AVAILABLE and OCR_ENABLED


def should_ocr_image(url: str, alt_text: str = "", width: int = 0, height: int = 0) -> bool:
    """
    Heuristic to decide if an image likely contains useful text.
    Skips logos, icons, decorative images.
    """
    if not is_ocr_available():
        return False

    url_lower = url.lower()

    # Skip known non-text images
    skip_patterns = [
        "logo", "icon", "favicon", "avatar", "thumbnail",
        "banner", "slider", "bg-", "background",
        "social", "facebook", "twitter", "instagram", "linkedin",
        "arrow", "button", "decoration", "ornament",
        "wp-content/themes",  # Theme assets
    ]
    for pattern in skip_patterns:
        if pattern in url_lower:
            return False

    # Skip small images (likely icons/decorations)
    if width > 0 and height > 0:
        if width < OCR_MIN_IMAGE_WIDTH or height < OCR_MIN_IMAGE_HEIGHT:
            return False

    # Skip alt text that suggests decorative image
    if alt_text:
        alt_lower = alt_text.lower()
        skip_alts = ["logo", "icon", "decoration", "separator", "divider"]
        for skip in skip_alts:
            if skip in alt_lower:
                return False

    # Positive indicators (images that likely contain text)
    positive_patterns = [
        "fee", "table", "schedule", "notice", "circular",
        "announcement", "cutoff", "rank", "result",
        "brochure", "poster", "flyer", "chart",
    ]
    for pattern in positive_patterns:
        if pattern in url_lower or (alt_text and pattern in alt_text.lower()):
            return True

    # Default: OCR if large enough
    if width >= OCR_MIN_IMAGE_WIDTH and height >= OCR_MIN_IMAGE_HEIGHT:
        return True

    # If no size info available, try it
    return True


def ocr_image_from_url(url: str) -> Optional[str]:
    """Download an image and run OCR on it."""
    if not is_ocr_available():
        return None

    try:
        response = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 PESUKioskBot/1.0"
        })
        response.raise_for_status()

        image = Image.open(io.BytesIO(response.content))

        # Check dimensions
        width, height = image.size
        if width < OCR_MIN_IMAGE_WIDTH or height < OCR_MIN_IMAGE_HEIGHT:
            return None

        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")

        # Run OCR
        text = pytesseract.image_to_string(image, lang="eng")
        text = text.strip()

        # Filter out garbage (very short or mostly non-alphanumeric)
        if len(text) < 10:
            return None

        alpha_ratio = sum(1 for c in text if c.isalpha()) / max(len(text), 1)
        if alpha_ratio < 0.3:
            return None

        return text

    except Exception as e:
        logger.debug(f"OCR failed for {url}: {e}")
        return None


def ocr_image_from_file(filepath: Path) -> Optional[str]:
    """Run OCR on a local image file."""
    if not is_ocr_available():
        return None

    try:
        image = Image.open(filepath)

        width, height = image.size
        if width < OCR_MIN_IMAGE_WIDTH or height < OCR_MIN_IMAGE_HEIGHT:
            return None

        if image.mode != "RGB":
            image = image.convert("RGB")

        text = pytesseract.image_to_string(image, lang="eng")
        text = text.strip()

        if len(text) < 10:
            return None

        return text

    except Exception as e:
        logger.debug(f"OCR failed for {filepath}: {e}")
        return None


def process_images_for_ocr(image_urls: List[Dict]) -> Dict:
    """
    Process a list of images for OCR.
    Each item: {"url": str, "alt": str, "page_url": str, "page_file": str}
    Returns processing statistics.
    """
    stats = {
        "total": len(image_urls),
        "processed": 0,
        "text_found": 0,
        "skipped": 0,
        "failed": 0,
    }

    if not is_ocr_available():
        logger.warning("Tesseract OCR is not available. Install tesseract-ocr to enable OCR.")
        logger.warning("Skipping all image OCR processing.")
        stats["skipped"] = stats["total"]
        return stats

    logger.info(f"Processing {len(image_urls)} images for OCR...")

    for item in image_urls:
        url = item.get("url", "")
        alt = item.get("alt", "")
        page_file = item.get("page_file", "")

        if not should_ocr_image(url, alt):
            stats["skipped"] += 1
            continue

        text = ocr_image_from_url(url)
        stats["processed"] += 1

        if text:
            stats["text_found"] += 1
            logger.info(f"  OCR extracted {len(text)} chars from image: {url[:80]}")

            # Append to the parent page's markdown file if available
            if page_file and os.path.exists(page_file):
                try:
                    with open(page_file, "a", encoding="utf-8") as f:
                        f.write(f"\n\n---\n\n## OCR Extracted Text\n\n")
                        f.write(f"*Extracted from image: {url}*\n\n")
                        f.write(text)
                        f.write("\n")
                except Exception as e:
                    logger.error(f"Failed to append OCR text to {page_file}: {e}")
        else:
            stats["failed"] += 1

    logger.info(f"OCR complete: {stats['processed']} processed, "
                f"{stats['text_found']} with text, {stats['skipped']} skipped")

    return stats
