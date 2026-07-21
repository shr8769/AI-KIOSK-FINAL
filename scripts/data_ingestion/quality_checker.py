#!/usr/bin/env python3
"""
quality_checker.py

Post-crawl validation for generated Markdown files.
Checks content quality, completeness, and flags pages for manual review.
"""

import logging
import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Tuple

from scripts.data_ingestion.crawler_config import (
    OUTPUT_DIR, MIN_WORD_COUNT, MIN_CONTENT_LENGTH,
)

logger = logging.getLogger("quality_checker")


def check_frontmatter(content: str) -> Tuple[bool, str]:
    """Verify YAML frontmatter is present and valid."""
    if not content.startswith("---"):
        return False, "Missing YAML frontmatter"

    parts = content.split("---", 2)
    if len(parts) < 3:
        return False, "Malformed YAML frontmatter (no closing ---)"

    try:
        fm = yaml.safe_load(parts[1])
        if not isinstance(fm, dict):
            return False, "Frontmatter is not a valid YAML mapping"
    except Exception as e:
        return False, f"Invalid YAML: {e}"

    required_fields = ["title", "url", "category", "last_crawled"]
    missing = [f for f in required_fields if f not in fm or not fm[f]]
    if missing:
        return False, f"Missing frontmatter fields: {', '.join(missing)}"

    return True, "OK"


def check_content_quality(content: str) -> Tuple[bool, str, Dict]:
    """
    Check that content has sufficient substance.
    Returns (is_valid, message, stats).
    """
    # Strip frontmatter
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            body = parts[2]

    body = body.strip()

    stats = {
        "word_count": 0,
        "char_count": len(body),
        "heading_count": 0,
        "table_count": 0,
        "list_count": 0,
        "link_count": 0,
    }

    if not body:
        return False, "Empty content body", stats

    words = body.split()
    stats["word_count"] = len(words)

    if len(words) < MIN_WORD_COUNT:
        return False, f"Too few words ({len(words)} < {MIN_WORD_COUNT})", stats

    if len(body) < MIN_CONTENT_LENGTH:
        return False, f"Content too short ({len(body)} chars)", stats

    # Count structural elements
    stats["heading_count"] = len(re.findall(r'^#{1,6}\s', body, re.MULTILINE))
    stats["table_count"] = len(re.findall(r'^\|.*\|$', body, re.MULTILINE)) // 3  # rough estimate
    stats["list_count"] = len(re.findall(r'^[-*]\s|^\d+\.\s', body, re.MULTILINE))
    stats["link_count"] = len(re.findall(r'\[.*?\]\(.*?\)', body))

    return True, "OK", stats


def check_file(filepath: Path) -> Dict:
    """
    Run all quality checks on a single Markdown file.
    Returns a result dict with check outcomes.
    """
    result = {
        "file": str(filepath),
        "filename": filepath.name,
        "category": filepath.parent.name,
        "valid": True,
        "issues": [],
        "stats": {},
    }

    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        result["valid"] = False
        result["issues"].append(f"Cannot read file: {e}")
        return result

    # Check frontmatter
    fm_valid, fm_msg = check_frontmatter(content)
    if not fm_valid:
        result["valid"] = False
        result["issues"].append(fm_msg)

    # Check content quality
    cq_valid, cq_msg, cq_stats = check_content_quality(content)
    result["stats"] = cq_stats
    if not cq_valid:
        result["valid"] = False
        result["issues"].append(cq_msg)

    return result


def run_quality_checks() -> Dict:
    """
    Run quality checks on all Markdown files in the output directory.
    Returns a summary with pass/fail counts and details.
    """
    logger.info(f"Running quality checks on files in {OUTPUT_DIR}...")

    summary = {
        "total_files": 0,
        "passed": 0,
        "failed": 0,
        "total_words": 0,
        "total_tables": 0,
        "total_headings": 0,
        "failed_files": [],
        "passed_files": [],
        "categories": {},
    }

    if not OUTPUT_DIR.exists():
        logger.error(f"Output directory does not exist: {OUTPUT_DIR}")
        return summary

    for md_file in OUTPUT_DIR.rglob("*.md"):
        # Skip the downloads directory
        if "downloads" in str(md_file):
            continue

        summary["total_files"] += 1
        result = check_file(md_file)

        # Update category counts
        cat = result["category"]
        if cat not in summary["categories"]:
            summary["categories"][cat] = {"files": 0, "words": 0, "passed": 0, "failed": 0}
        summary["categories"][cat]["files"] += 1

        if result["valid"]:
            summary["passed"] += 1
            summary["categories"][cat]["passed"] += 1
            summary["passed_files"].append(result)
        else:
            summary["failed"] += 1
            summary["categories"][cat]["failed"] += 1
            summary["failed_files"].append(result)
            logger.warning(f"  FAIL: {md_file.name} - {', '.join(result['issues'])}")

        # Accumulate stats
        stats = result.get("stats", {})
        summary["total_words"] += stats.get("word_count", 0)
        summary["total_tables"] += stats.get("table_count", 0)
        summary["total_headings"] += stats.get("heading_count", 0)
        summary["categories"][cat]["words"] += stats.get("word_count", 0)

    pass_rate = (summary["passed"] / max(summary["total_files"], 1)) * 100

    logger.info(f"Quality check complete:")
    logger.info(f"  Total files: {summary['total_files']}")
    logger.info(f"  Passed: {summary['passed']} ({pass_rate:.1f}%)")
    logger.info(f"  Failed: {summary['failed']}")
    logger.info(f"  Total words: {summary['total_words']}")

    return summary


def get_urls_needing_retry(quality_summary: Dict) -> List[str]:
    """
    Extract URLs from failed quality checks that should be re-crawled.
    """
    retry_urls = []

    for result in quality_summary.get("failed_files", []):
        filepath = Path(result["file"])
        try:
            content = filepath.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1])
                    if fm and "url" in fm:
                        retry_urls.append(fm["url"])
        except Exception:
            pass

    return retry_urls
