#!/usr/bin/env python3
"""
document_processor.py

Downloads and extracts text from documents (PDF, DOCX, XLSX, PPTX) found
during the PES University website crawl. Generates companion Markdown files
for each document.
"""

import logging
import os
import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from scripts.data_ingestion.crawler_config import (
    OUTPUT_DIR, DOWNLOADS_DIR, CATEGORY_MAP, DEFAULT_CATEGORY,
)

logger = logging.getLogger("document_processor")

IST = timezone(timedelta(hours=5, minutes=30))


def download_file(url: str, output_dir: Path) -> Optional[Path]:
    """Download a file from URL to output_dir. Returns filepath or None."""
    try:
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate a safe filename
        parsed = urlparse(url)
        original_name = os.path.basename(parsed.path)
        if not original_name:
            original_name = hashlib.md5(url.encode()).hexdigest()[:12]

        filepath = output_dir / original_name

        # Don't re-download if already exists
        if filepath.exists():
            logger.info(f"  Already downloaded: {filepath.name}")
            return filepath

        logger.info(f"  Downloading: {url}")
        response = requests.get(url, timeout=60, stream=True, headers={
            "User-Agent": "Mozilla/5.0 PESUKioskBot/1.0"
        })
        response.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = filepath.stat().st_size / 1024
        logger.info(f"  Downloaded: {filepath.name} ({size_kb:.1f} KB)")
        return filepath

    except Exception as e:
        logger.error(f"  Failed to download {url}: {e}")
        return None


def extract_pdf_text(filepath: Path) -> Tuple[str, List[str]]:
    """Extract text and tables from a PDF file."""
    text_parts = []
    tables = []

    try:
        import pdfplumber

        with pdfplumber.open(filepath) as pdf:
            for i, page_obj in enumerate(pdf.pages, 1):
                # Extract text
                page_text = page_obj.extract_text()
                if page_text:
                    text_parts.append(f"### Page {i}\n\n{page_text}")

                # Extract tables
                page_tables = page_obj.extract_tables()
                for table in page_tables:
                    if table and len(table) > 1:
                        # Convert to markdown table
                        md_table = _table_to_markdown(table)
                        if md_table:
                            tables.append(md_table)
                            text_parts.append(f"\n{md_table}\n")

    except ImportError:
        logger.warning("pdfplumber not installed, skipping PDF text extraction")
    except Exception as e:
        logger.error(f"Error extracting text from PDF {filepath.name}: {e}")

    return "\n\n".join(text_parts), tables


def extract_docx_text(filepath: Path) -> str:
    """Extract text from a DOCX file."""
    try:
        from docx import Document

        doc = Document(str(filepath))
        parts = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                # Try to preserve heading styles
                if para.style and para.style.name and "Heading" in para.style.name:
                    try:
                        level = int(para.style.name.split()[-1])
                        parts.append(f"{'#' * level} {text}")
                    except (ValueError, IndexError):
                        parts.append(f"## {text}")
                else:
                    parts.append(text)

        # Extract tables
        for table in doc.tables:
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(cells)
            if rows:
                md_table = _table_to_markdown(rows)
                if md_table:
                    parts.append(f"\n{md_table}\n")

        return "\n\n".join(parts)

    except ImportError:
        logger.warning("python-docx not installed, skipping DOCX extraction")
        return ""
    except Exception as e:
        logger.error(f"Error extracting text from DOCX {filepath.name}: {e}")
        return ""


def extract_xlsx_text(filepath: Path) -> str:
    """Extract text/data from an XLSX file."""
    try:
        from openpyxl import load_workbook

        wb = load_workbook(str(filepath), read_only=True, data_only=True)
        parts = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            parts.append(f"## Sheet: {sheet_name}\n")

            rows = []
            for row in ws.iter_rows(values_only=True):
                cells = [str(cell) if cell is not None else "" for cell in row]
                if any(c.strip() for c in cells):
                    rows.append(cells)

            if rows:
                md_table = _table_to_markdown(rows)
                if md_table:
                    parts.append(md_table)

        wb.close()
        return "\n\n".join(parts)

    except ImportError:
        logger.warning("openpyxl not installed, skipping XLSX extraction")
        return ""
    except Exception as e:
        logger.error(f"Error extracting text from XLSX {filepath.name}: {e}")
        return ""


def extract_pptx_text(filepath: Path) -> str:
    """Extract text from a PPTX file."""
    try:
        from pptx import Presentation

        prs = Presentation(str(filepath))
        parts = []

        for i, slide in enumerate(prs.slides, 1):
            slide_text = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        text = paragraph.text.strip()
                        if text:
                            slide_text.append(text)
                if shape.has_table:
                    rows = []
                    for row in shape.table.rows:
                        cells = [cell.text.strip() for cell in row.cells]
                        rows.append(cells)
                    if rows:
                        md_table = _table_to_markdown(rows)
                        if md_table:
                            slide_text.append(md_table)

            if slide_text:
                parts.append(f"### Slide {i}\n\n" + "\n\n".join(slide_text))

        return "\n\n".join(parts)

    except ImportError:
        logger.warning("python-pptx not installed, skipping PPTX extraction")
        return ""
    except Exception as e:
        logger.error(f"Error extracting text from PPTX {filepath.name}: {e}")
        return ""


def _table_to_markdown(rows: List[List]) -> str:
    """Convert a list of rows (list of cells) to Markdown table."""
    if not rows or len(rows) < 1:
        return ""

    # Clean cells
    clean_rows = []
    for row in rows:
        clean_cells = [str(cell).replace("|", "\\|").replace("\n", " ").strip() for cell in row]
        if any(c for c in clean_cells):
            clean_rows.append(clean_cells)

    if not clean_rows:
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in clean_rows)
    for row in clean_rows:
        while len(row) < max_cols:
            row.append("")

    lines = []
    lines.append("| " + " | ".join(clean_rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for row in clean_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def categorize_document(url: str, filename: str) -> str:
    """Determine category folder for a downloaded document."""
    url_lower = url.lower()
    filename_lower = filename.lower()

    combined = url_lower + " " + filename_lower

    for keyword, category in CATEGORY_MAP.items():
        if keyword in combined:
            return category

    return DEFAULT_CATEGORY


def process_documents(document_urls: List[str]) -> Dict:
    """
    Download and extract text from all discovered documents.
    Returns processing statistics.
    """
    stats = {
        "total": len(document_urls),
        "downloaded": 0,
        "extracted": 0,
        "failed": 0,
        "files": [],
    }

    if not document_urls:
        logger.info("No documents to process")
        return stats

    logger.info(f"Processing {len(document_urls)} documents...")

    # Deduplicate
    unique_urls = list(set(document_urls))
    stats["total"] = len(unique_urls)

    for url in unique_urls:
        parsed = urlparse(url)
        ext = os.path.splitext(parsed.path)[1].lower()

        # Download
        filepath = download_file(url, DOWNLOADS_DIR)
        if not filepath:
            stats["failed"] += 1
            continue
        stats["downloaded"] += 1

        # Extract text based on file type
        extracted_text = ""
        if ext == ".pdf":
            extracted_text, _ = extract_pdf_text(filepath)
        elif ext == ".docx":
            extracted_text = extract_docx_text(filepath)
        elif ext in (".xlsx", ".xls"):
            extracted_text = extract_xlsx_text(filepath)
        elif ext == ".pptx":
            extracted_text = extract_pptx_text(filepath)
        else:
            logger.warning(f"  Unsupported format: {ext} - {filepath.name}")
            continue

        if not extracted_text or len(extracted_text.strip()) < 20:
            logger.warning(f"  No meaningful text extracted from {filepath.name}")
            continue

        stats["extracted"] += 1

        # Write companion Markdown
        category = categorize_document(url, filepath.name)
        category_dir = OUTPUT_DIR / category
        category_dir.mkdir(parents=True, exist_ok=True)

        md_filename = filepath.stem + "_document.md"
        md_path = category_dir / md_filename

        now = datetime.now(IST).isoformat()
        frontmatter = f"""---
title: "{filepath.name}"
url: {url}
category: {category}
source_type: document
file_type: {ext.lstrip('.')}
file_size_kb: {filepath.stat().st_size / 1024:.1f}
last_crawled: "{now}"
---

# {filepath.stem}

*Source: [{filepath.name}]({url})*

"""
        md_path.write_text(frontmatter + extracted_text, encoding="utf-8")
        stats["files"].append({"url": url, "file": str(md_path), "type": ext})
        logger.info(f"  Extracted text from {filepath.name} -> {md_path.name}")

    logger.info(f"Document processing complete: {stats['downloaded']} downloaded, "
                f"{stats['extracted']} extracted, {stats['failed']} failed")

    return stats
