#!/usr/bin/env python3
"""
crawl_report.py

Generates a comprehensive Markdown crawl report after the PES University
website crawl is complete.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict

from scripts.data_ingestion.crawler_config import CRAWL_REPORT_FILE

logger = logging.getLogger("crawl_report")

IST = timezone(timedelta(hours=5, minutes=30))


def generate_report(
    crawl_stats: Dict,
    doc_stats: Dict = None,
    ocr_stats: Dict = None,
    quality_stats: Dict = None,
) -> Path:
    """
    Generate a comprehensive crawl report and write it to disk.
    Returns the path to the report file.
    """
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

    lines = []
    lines.append("# PES University Website Crawl Report")
    lines.append("")
    lines.append(f"**Generated:** {now}")
    lines.append("")
    lines.append(f"**Crawl Duration:** {crawl_stats.get('crawl_duration_human', 'N/A')}")
    lines.append("")

    # ── Overview ──────────────────────────────
    lines.append("## Overview")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("| --- | --- |")
    lines.append(f"| URLs Discovered | {crawl_stats.get('urls_discovered', 0)} |")
    lines.append(f"| URLs Visited | {crawl_stats.get('urls_visited', 0)} |")
    lines.append(f"| Successful Pages | {crawl_stats.get('pages_successful', 0)} |")
    lines.append(f"| Failed Pages | {crawl_stats.get('pages_failed', 0)} |")
    lines.append(f"| Skipped Pages | {crawl_stats.get('pages_skipped', 0)} |")
    lines.append(f"| Duplicate Pages | {crawl_stats.get('pages_duplicate', 0)} |")
    lines.append(f"| Documents Found | {crawl_stats.get('documents_found', 0)} |")
    lines.append(f"| Tables Extracted | {crawl_stats.get('tables_extracted', 0)} |")
    lines.append(f"| Accordions Expanded | {crawl_stats.get('accordions_expanded', 0)} |")
    lines.append(f"| FAQs Expanded | {crawl_stats.get('faqs_expanded', 0)} |")
    lines.append(f"| Tabs Expanded | {crawl_stats.get('tabs_expanded', 0)} |")
    lines.append(f"| Markdown Files Created | {crawl_stats.get('markdown_files_created', 0)} |")
    lines.append(f"| Total Words | {crawl_stats.get('total_words', 0):,} |")
    lines.append("")

    # Coverage estimate
    visited = crawl_stats.get('urls_visited', 0)
    discovered = crawl_stats.get('urls_discovered', 0)
    if discovered > 0:
        coverage = (visited / discovered) * 100
        lines.append(f"**Coverage:** {coverage:.1f}% ({visited} / {discovered} discovered URLs)")
    else:
        lines.append("**Coverage:** N/A")
    lines.append("")

    # ── Document Processing ──────────────────
    if doc_stats:
        lines.append("## Document Processing")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("| --- | --- |")
        lines.append(f"| Total Documents | {doc_stats.get('total', 0)} |")
        lines.append(f"| Downloaded | {doc_stats.get('downloaded', 0)} |")
        lines.append(f"| Text Extracted | {doc_stats.get('extracted', 0)} |")
        lines.append(f"| Failed | {doc_stats.get('failed', 0)} |")
        lines.append("")

        if doc_stats.get("files"):
            lines.append("### Downloaded Documents")
            lines.append("")
            lines.append("| File | Type | URL |")
            lines.append("| --- | --- | --- |")
            for f in doc_stats["files"][:50]:
                name = Path(f["file"]).name
                lines.append(f"| {name} | {f['type']} | {f['url'][:80]} |")
            lines.append("")

    # ── OCR Processing ───────────────────────
    if ocr_stats:
        lines.append("## OCR Processing")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("| --- | --- |")
        lines.append(f"| Total Images | {ocr_stats.get('total', 0)} |")
        lines.append(f"| Processed | {ocr_stats.get('processed', 0)} |")
        lines.append(f"| Text Found | {ocr_stats.get('text_found', 0)} |")
        lines.append(f"| Skipped | {ocr_stats.get('skipped', 0)} |")
        lines.append(f"| Failed | {ocr_stats.get('failed', 0)} |")
        lines.append("")

    # ── Quality Check Results ────────────────
    if quality_stats:
        lines.append("## Quality Check Results")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("| --- | --- |")
        lines.append(f"| Total Files Checked | {quality_stats.get('total_files', 0)} |")
        lines.append(f"| Passed | {quality_stats.get('passed', 0)} |")
        lines.append(f"| Failed | {quality_stats.get('failed', 0)} |")
        lines.append(f"| Total Words | {quality_stats.get('total_words', 0):,} |")
        lines.append(f"| Total Tables | {quality_stats.get('total_tables', 0)} |")
        lines.append(f"| Total Headings | {quality_stats.get('total_headings', 0)} |")
        lines.append("")

        # Category breakdown
        if quality_stats.get("categories"):
            lines.append("### By Category")
            lines.append("")
            lines.append("| Category | Files | Words | Passed | Failed |")
            lines.append("| --- | --- | --- | --- | --- |")
            for cat, data in sorted(quality_stats["categories"].items()):
                lines.append(f"| {cat} | {data['files']} | {data['words']:,} | {data['passed']} | {data['failed']} |")
            lines.append("")

        # Failed files
        if quality_stats.get("failed_files"):
            lines.append("### Files Requiring Manual Inspection")
            lines.append("")
            lines.append("| File | Category | Issues |")
            lines.append("| --- | --- | --- |")
            for f in quality_stats["failed_files"][:30]:
                issues = "; ".join(f.get("issues", []))
                lines.append(f"| {f['filename']} | {f['category']} | {issues} |")
            lines.append("")

    # ── Failed URLs ──────────────────────────
    failed_urls = crawl_stats.get("failed_urls", [])
    if failed_urls:
        lines.append("## Failed URLs")
        lines.append("")
        lines.append("These pages could not be crawled and may need manual inspection:")
        lines.append("")
        for url in failed_urls[:50]:
            lines.append(f"- {url}")
        lines.append("")

    # ── Created Files ────────────────────────
    files_created = crawl_stats.get("files_created", [])
    if files_created:
        lines.append("## Created Markdown Files")
        lines.append("")
        lines.append(f"Total: {len(files_created)} files")
        lines.append("")
        lines.append("| File | Category | Words | Tables |")
        lines.append("| --- | --- | --- | --- |")
        for f in sorted(files_created, key=lambda x: x.get("category", "")):
            name = Path(f["file"]).name
            lines.append(f"| {name} | {f['category']} | {f.get('words', 0)} | {f.get('tables', 0)} |")
        lines.append("")

    # ── Errors ───────────────────────────────
    errors = crawl_stats.get("errors", [])
    if errors:
        lines.append("## Errors Log")
        lines.append("")
        for err in errors[:30]:
            lines.append(f"- **{err.get('url', 'unknown')}**: {err.get('error', 'unknown error')}")
        lines.append("")

    # Write report
    report_content = "\n".join(lines)
    CRAWL_REPORT_FILE.write_text(report_content, encoding="utf-8")

    logger.info(f"Crawl report generated: {CRAWL_REPORT_FILE}")
    return CRAWL_REPORT_FILE
