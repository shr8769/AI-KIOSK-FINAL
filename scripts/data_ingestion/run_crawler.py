#!/usr/bin/env python3
"""
run_crawler.py

CLI entry point for the PES University recursive website crawler.
Orchestrates the full pipeline:
  1. Crawl   — Recursive BFS discovery and scraping
  2. Download — Fetch and extract documents (PDF, DOCX, etc.)
  3. OCR     — Extract text from images (if Tesseract available)
  4. Quality — Validate all generated Markdown files
  5. Report  — Generate comprehensive crawl report
"""

import argparse
import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.data_ingestion.crawler_config import (
    MAX_PAGES, MAX_DEPTH, POLITENESS_DELAY, OUTPUT_DIR, CHECKPOINT_FILE,
)
from scripts.data_ingestion.pes_crawler import PESCrawler
from scripts.data_ingestion.document_processor import process_documents
from scripts.data_ingestion.ocr_processor import is_ocr_available
from scripts.data_ingestion.quality_checker import run_quality_checks, get_urls_needing_retry
from scripts.data_ingestion.crawl_report import generate_report

# ── Logging Setup ────────────────────────────

def setup_logging(verbose: bool = False):
    """Configure logging for all crawler modules."""
    level = logging.DEBUG if verbose else logging.INFO

    formatter = logging.Formatter(
        "%(asctime)s [%(name)-18s] %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)

    # File handler
    log_file = OUTPUT_DIR.parent / "crawler.log" if OUTPUT_DIR.parent.exists() else "crawler.log"
    file_handler = logging.FileHandler(str(log_file), mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Apply to all crawler loggers
    for logger_name in ["pes_crawler", "document_processor", "ocr_processor",
                         "quality_checker", "crawl_report"]:
        lg = logging.getLogger(logger_name)
        lg.setLevel(level)
        lg.addHandler(console)
        lg.addHandler(file_handler)

    # Root logger for uncaught messages
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(console)


# ── Main Pipeline ────────────────────────────

async def run_pipeline(args):
    """Execute the full crawl pipeline."""

    logger = logging.getLogger("pes_crawler")

    print()
    print("=" * 70)
    print("   PES University Knowledge Base Crawler")
    print("=" * 70)
    print(f"   Max Pages  : {args.max_pages}")
    print(f"   Max Depth  : {args.max_depth}")
    print(f"   Delay      : {args.delay}s")
    print(f"   Resume     : {args.resume}")
    print(f"   Output Dir : {args.output_dir}")
    print(f"   OCR        : {'Available' if is_ocr_available() else 'Not available (skipped)'}")
    print("=" * 70)
    print()

    # ── Stage 1: Crawl ──────────────────────
    print("\n[STAGE 1/5] Recursive Website Crawl")
    print("-" * 40)

    crawler = PESCrawler(
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        delay=args.delay,
        resume=args.resume,
    )

    crawl_stats = await crawler.crawl()

    # ── Stage 2: Document Processing ────────
    print("\n[STAGE 2/5] Document Download & Extraction")
    print("-" * 40)

    doc_stats = None
    if crawler.document_urls:
        doc_stats = process_documents(crawler.document_urls)
    else:
        print("No documents to process.")
        doc_stats = {"total": 0, "downloaded": 0, "extracted": 0, "failed": 0, "files": []}

    # ── Stage 3: OCR ────────────────────────
    print("\n[STAGE 3/5] Image OCR Processing")
    print("-" * 40)

    ocr_stats = None
    if is_ocr_available():
        # OCR images are tracked during crawl; for now we log availability
        from scripts.data_ingestion.ocr_processor import process_images_for_ocr
        # Note: In a full implementation, image URLs would be collected during crawl
        # For now, this is a placeholder that checks OCR readiness
        ocr_stats = {"total": 0, "processed": 0, "text_found": 0, "skipped": 0, "failed": 0}
        print("OCR available but no images queued for processing.")
    else:
        print("Tesseract OCR not available. Skipping image text extraction.")
        ocr_stats = {"total": 0, "processed": 0, "text_found": 0, "skipped": 0, "failed": 0}

    # ── Stage 4: Quality Checks ─────────────
    print("\n[STAGE 4/5] Quality Validation")
    print("-" * 40)

    quality_stats = run_quality_checks()

    # Auto-retry failed pages (up to one retry pass)
    retry_urls = get_urls_needing_retry(quality_stats)
    if retry_urls and args.retry_failed:
        print(f"\nRetrying {len(retry_urls)} failed pages...")
        retry_crawler = PESCrawler(
            max_pages=len(retry_urls),
            max_depth=1,
            delay=args.delay,
            resume=False,
        )
        # Add retry URLs directly to queue
        for url in retry_urls:
            retry_crawler.queue.append((url, 0))

        retry_stats = await retry_crawler.crawl()

        # Re-run quality checks
        quality_stats = run_quality_checks()

    # ── Stage 5: Report ─────────────────────
    print("\n[STAGE 5/5] Generating Crawl Report")
    print("-" * 40)

    report_path = generate_report(
        crawl_stats=crawl_stats,
        doc_stats=doc_stats,
        ocr_stats=ocr_stats,
        quality_stats=quality_stats,
    )

    # ── Final Summary ───────────────────────
    print()
    print("=" * 70)
    print("   CRAWL COMPLETE")
    print("=" * 70)
    print(f"   Duration        : {crawl_stats.get('crawl_duration_human', 'N/A')}")
    print(f"   Pages Visited   : {crawl_stats.get('urls_visited', 0)}")
    print(f"   Pages Successful: {crawl_stats.get('pages_successful', 0)}")
    print(f"   Pages Failed    : {crawl_stats.get('pages_failed', 0)}")
    print(f"   Markdown Files  : {crawl_stats.get('markdown_files_created', 0)}")
    print(f"   Total Words     : {crawl_stats.get('total_words', 0):,}")
    print(f"   Documents Found : {crawl_stats.get('documents_found', 0)}")
    print(f"   Quality Pass    : {quality_stats.get('passed', 0)}/{quality_stats.get('total_files', 0)}")
    print(f"   Report          : {report_path}")
    print("=" * 70)
    print()

    # Cleanup checkpoint on full completion
    if not args.keep_checkpoint and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("Checkpoint file cleaned up.")

    return crawl_stats


# ── CLI ──────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PES University Knowledge Base Crawler - Recursive website scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test with 20 pages
  python scripts/data_ingestion/run_crawler.py --max-pages 20 --delay 1

  # Full crawl
  python scripts/data_ingestion/run_crawler.py --max-pages 2000 --delay 2

  # Resume a previous crawl
  python scripts/data_ingestion/run_crawler.py --resume

  # Full crawl with auto-retry of failed pages
  python scripts/data_ingestion/run_crawler.py --max-pages 2000 --retry-failed
        """
    )

    parser.add_argument(
        "--max-pages", type=int, default=MAX_PAGES,
        help=f"Maximum number of pages to crawl (default: {MAX_PAGES})"
    )
    parser.add_argument(
        "--max-depth", type=int, default=MAX_DEPTH,
        help=f"Maximum link-follow depth (default: {MAX_DEPTH})"
    )
    parser.add_argument(
        "--delay", type=float, default=POLITENESS_DELAY,
        help=f"Seconds between requests (default: {POLITENESS_DELAY})"
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last checkpoint"
    )
    parser.add_argument(
        "--output-dir", type=str, default=str(OUTPUT_DIR),
        help=f"Output directory for Markdown files (default: {OUTPUT_DIR})"
    )
    parser.add_argument(
        "--retry-failed", action="store_true", default=True,
        help="Auto-retry pages that failed quality checks (default: True)"
    )
    parser.add_argument(
        "--keep-checkpoint", action="store_true",
        help="Don't delete checkpoint file after successful crawl"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug-level logging"
    )

    args = parser.parse_args()

    # Override output dir if specified
    if args.output_dir != str(OUTPUT_DIR):
        from scripts.data_ingestion import crawler_config
        from pathlib import Path
        crawler_config.OUTPUT_DIR = Path(args.output_dir)
        crawler_config.DOWNLOADS_DIR = Path(args.output_dir) / "downloads"

    setup_logging(verbose=args.verbose)

    # Run the async pipeline
    try:
        asyncio.run(run_pipeline(args))
    except KeyboardInterrupt:
        print("\n\nCrawl interrupted by user. Checkpoint saved for resume.")
        print("Run with --resume to continue from where you left off.")
        sys.exit(1)
    except Exception as e:
        logging.getLogger("pes_crawler").critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
