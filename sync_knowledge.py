#!/usr/bin/env python3
"""
sync_knowledge.py

Top-level entry point for the automated knowledge synchronization system.
Orchestrates the full pipeline: crawl → detect changes → update markdown →
update embeddings → validate → generate report.

Usage:
    python sync_knowledge.py                       # Full incremental sync
    python sync_knowledge.py --full                # Force full recrawl
    python sync_knowledge.py --dry-run             # Preview changes without modifying anything
    python sync_knowledge.py --validate-only       # Run post-sync validation only
    python sync_knowledge.py --config custom.yaml  # Use custom config file
    python sync_knowledge.py --schedule            # Run as a scheduled daemon
    python sync_knowledge.py --max-pages 20        # Limit pages for testing
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.data_ingestion.sync import SYNC_SYSTEM_VERSION
from scripts.data_ingestion.sync.manifest import SyncManifest
from scripts.data_ingestion.sync.change_detector import ChangeSet, ChangeType
from scripts.data_ingestion.sync.incremental_crawler import IncrementalCrawler
from scripts.data_ingestion.sync.markdown_sync import MarkdownSyncManager
from scripts.data_ingestion.sync.embedding_updater import EmbeddingUpdater
from scripts.data_ingestion.sync.validator import SyncValidator
from scripts.data_ingestion.sync.sync_report import SyncReportGenerator
from scripts.data_ingestion.sync.scheduler import SyncScheduler

IST = timezone(timedelta(hours=5, minutes=30))

# ── Logging Setup ────────────────────────────────────


def setup_logging(config: Dict[str, Any]) -> None:
    """Configure logging for the sync pipeline."""
    logging_cfg = config.get("logging", {})
    log_dir = Path(logging_cfg.get("log_dir", "logs/sync"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_level = getattr(logging, logging_cfg.get("log_level", "INFO").upper(), logging.INFO)

    timestamp = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"sync_{timestamp}.log"

    formatter = logging.Formatter(
        "%(asctime)s [%(name)-24s] %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(str(log_file), mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Apply to all sync loggers
    for logger_name in [
        "sync.manifest", "sync.change_detector", "sync.incremental_crawler",
        "sync.markdown_sync", "sync.embedding_updater", "sync.validator",
        "sync.report", "sync.scheduler", "sync.orchestrator",
    ]:
        lg = logging.getLogger(logger_name)
        lg.setLevel(logging.DEBUG)
        lg.addHandler(console)
        lg.addHandler(file_handler)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.addHandler(console)

    return log_file


def load_config(config_path: str = "sync_config.yaml") -> Dict[str, Any]:
    """Load sync configuration from YAML file."""
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Error: Config file not found: {config_file.resolve()}")
        print("Run the sync setup or create sync_config.yaml from the template.")
        sys.exit(1)

    with open(config_file, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


# ── Main Sync Pipeline ──────────────────────────────


async def run_sync(config: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    """
    Execute the full knowledge synchronization pipeline.

    Returns a summary dict with results from each stage.
    """
    logger = logging.getLogger("sync.orchestrator")

    # Generate a unique run ID
    sync_run_id = f"sync_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}"

    # Override max_pages if specified
    if args.max_pages:
        config.setdefault("crawler", {})["max_pages"] = args.max_pages

    print()
    print("=" * 70)
    print("   PES University Knowledge Base - Automated Sync")
    print("=" * 70)
    print(f"   Run ID         : {sync_run_id}")
    print(f"   Sync Version   : {SYNC_SYSTEM_VERSION}")
    print(f"   Mode           : {'DRY RUN' if args.dry_run else 'FULL RECRAWL' if args.full else 'INCREMENTAL'}")
    print(f"   Max Pages      : {config.get('crawler', {}).get('max_pages', 2000)}")
    print("=" * 70)
    print()

    start_time = time.time()
    summary = {"run_id": sync_run_id, "mode": "dry_run" if args.dry_run else "full" if args.full else "incremental"}

    # -- Stage 1: Load Manifest --------------------

    print("[STAGE 1/7] Loading Sync Manifest")
    print("-" * 40)

    sync_cfg = config.get("sync", {})
    manifest = SyncManifest(manifest_path=sync_cfg.get("manifest_path", "sync_manifest.json"))

    if args.full:
        # Force full recrawl — start with empty manifest
        logger.info("Full recrawl requested. Starting with empty manifest.")
        print("   Full recrawl mode: manifest reset.")
    else:
        manifest.load()

    manifest_stats_before = manifest.get_stats()
    print(f"   Entries in manifest: {manifest_stats_before['total_entries']}")
    print(f"   Active: {manifest_stats_before['active']}, "
          f"Archived: {manifest_stats_before['archived']}, "
          f"Error: {manifest_stats_before['error']}")
    print()

    # -- Stage 2: Incremental Crawl ----------------

    print("[STAGE 2/7] Incremental Crawl & Change Detection")
    print("-" * 40)

    crawler = IncrementalCrawler(manifest=manifest, config=config)
    change_set, crawl_results = await crawler.crawl(dry_run=args.dry_run)
    crawl_stats = crawler.get_stats()

    change_summary = change_set.get_summary()
    print(f"   Pages scanned    : {change_summary['total_scanned']}")
    print(f"   New pages        : {change_summary['new']}")
    print(f"   Modified pages   : {change_summary['modified']}")
    print(f"   Unchanged pages  : {change_summary['unchanged']}")
    print(f"   Deleted pages    : {change_summary['deleted']}")
    print(f"   Errors           : {change_summary['errors']}")
    print()

    if args.dry_run:
        print("   *** DRY RUN - No files or vectors modified ***")
        print()
        # Skip stages 3-5 in dry run
        summary["change_summary"] = change_summary
        summary["crawl_stats"] = crawl_stats
        duration = time.time() - start_time
        summary["duration_seconds"] = round(duration, 2)

        # Still generate report
        report_gen = SyncReportGenerator(config=config, sync_run_id=sync_run_id)
        report_path = report_gen.generate(
            change_set=change_set,
            crawl_stats=crawl_stats,
            markdown_stats={"created": 0, "updated": 0, "archived": 0, "deleted": 0, "errors": 0},
            embedding_stats={"chunks_created": 0, "chunks_deleted": 0, "embeddings_generated": 0, "urls_processed": 0, "errors": 0},
        )
        print(f"   Dry-run report: {report_path}")
        return summary

    # -- Stage 3: Markdown Sync --------------------

    print("[STAGE 3/7] Markdown Synchronization")
    print("-" * 40)

    md_manager = MarkdownSyncManager(
        manifest=manifest, config=config, sync_run_id=sync_run_id
    )

    # Process NEW pages
    for result in crawl_results:
        if result.change_type == ChangeType.NEW and result.success and result.markdown_path:
            md_manager.process_new_page(
                canonical_url=result.canonical_url,
                title=result.title,
                category=result.category,
                content_hash=result.content_hash,
                markdown_path=result.markdown_path,
            )

    # Process MODIFIED pages
    for result in crawl_results:
        if result.change_type == ChangeType.MODIFIED and result.success and result.markdown_path:
            md_manager.process_modified_page(
                canonical_url=result.canonical_url,
                title=result.title,
                category=result.category,
                content_hash=result.content_hash,
                markdown_path=result.markdown_path,
            )

    # Process UNCHANGED pages (update last_crawl_time)
    for record in change_set.unchanged:
        md_manager.process_unchanged_page(record.canonical_url)

    # Process DELETED pages
    for record in change_set.deleted:
        md_manager.process_deleted_page(record.canonical_url)

    # Process ERROR pages
    for record in change_set.errors:
        md_manager.process_error_page(record.canonical_url, record.error_message)

    markdown_stats = md_manager.get_stats()
    print(f"   Created  : {markdown_stats['created']}")
    print(f"   Updated  : {markdown_stats['updated']}")
    print(f"   Archived : {markdown_stats['archived']}")
    print(f"   Deleted  : {markdown_stats['deleted']}")
    print(f"   Errors   : {markdown_stats['errors']}")
    print()

    # -- Stage 4: Embedding Update -----------------

    print("[STAGE 4/7] Incremental ChromaDB Update")
    print("-" * 40)

    emb_updater = EmbeddingUpdater(manifest=manifest, config=config)

    # Process NEW pages
    new_urls = [r.canonical_url for r in crawl_results
                if r.change_type == ChangeType.NEW and r.success and r.markdown_path]
    for url in new_urls:
        emb_updater.process_new_page(url)

    # Process MODIFIED pages
    mod_urls = [r.canonical_url for r in crawl_results
                if r.change_type == ChangeType.MODIFIED and r.success and r.markdown_path]
    for url in mod_urls:
        emb_updater.process_modified_page(url)

    # Process DELETED pages
    for record in change_set.deleted:
        emb_updater.process_deleted_page(record.canonical_url)

    embedding_stats = emb_updater.get_stats()
    collection_counts = emb_updater.get_collection_counts()

    print(f"   Chunks created    : {embedding_stats['chunks_created']}")
    print(f"   Chunks deleted    : {embedding_stats['chunks_deleted']}")
    print(f"   Embeddings gen    : {embedding_stats['embeddings_generated']}")
    print(f"   URLs processed    : {embedding_stats['urls_processed']}")
    print(f"   Errors            : {embedding_stats['errors']}")
    print()

    # -- Stage 5: Save Manifest --------------------

    print("[STAGE 5/7] Saving Manifest")
    print("-" * 40)

    manifest.update_sync_metadata(sync_run_id)
    manifest.save()
    manifest_stats_after = manifest.get_stats()

    print(f"   Entries: {manifest_stats_after['total_entries']} "
          f"(active: {manifest_stats_after['active']}, "
          f"archived: {manifest_stats_after['archived']})")
    print(f"   Total syncs: {manifest_stats_after['total_syncs']}")
    print()

    # -- Stage 6: Validation -----------------------

    print("[STAGE 6/7] Post-Sync Validation")
    print("-" * 40)

    validator = SyncValidator(manifest=manifest, config=config)
    validation_results = validator.validate_all()
    validation_summary = validator.get_summary(validation_results)

    for result in validation_results:
        status = "PASS" if result.passed else "FAIL"
        print(f"   [{status}] {result.check_name}: {result.message}")

    print()
    if validation_summary["all_passed"]:
        print("   [OK] All validation checks PASSED")
    else:
        print(f"   [WARN] {validation_summary['failed']} check(s) FAILED")
    print()

    # -- Stage 7: Report ---------------------------

    print("[STAGE 7/7] Generating Sync Report")
    print("-" * 40)

    report_gen = SyncReportGenerator(config=config, sync_run_id=sync_run_id)
    report_path = report_gen.generate(
        change_set=change_set,
        crawl_stats=crawl_stats,
        markdown_stats=markdown_stats,
        embedding_stats=embedding_stats,
        validation_results=validation_results,
        collection_counts=collection_counts,
        manifest_stats=manifest_stats_after,
    )

    print(f"   Report saved: {report_path}")
    print()

    # -- Final Summary -----------------------------

    duration = time.time() - start_time

    print("=" * 70)
    print("   SYNC COMPLETE")
    print("=" * 70)
    print(f"   Duration          : {int(duration // 60)}m {int(duration % 60)}s")
    print(f"   New Pages         : {change_summary['new']}")
    print(f"   Updated Pages     : {change_summary['modified']}")
    print(f"   Deleted Pages     : {change_summary['deleted']}")
    print(f"   Unchanged         : {change_summary['unchanged']}")
    print(f"   Chunks Created    : {embedding_stats['chunks_created']}")
    print(f"   Chunks Deleted    : {embedding_stats['chunks_deleted']}")
    print(f"   Validation        : {'PASSED' if validation_summary['all_passed'] else 'ISSUES DETECTED'}")
    print(f"   Report            : {report_path}")
    print("=" * 70)
    print()

    summary.update({
        "change_summary": change_summary,
        "crawl_stats": crawl_stats,
        "markdown_stats": markdown_stats,
        "embedding_stats": embedding_stats,
        "validation": validation_summary,
        "collection_counts": collection_counts,
        "manifest_stats": manifest_stats_after,
        "duration_seconds": round(duration, 2),
        "report_path": str(report_path),
    })

    return summary


# -- Validate-Only Mode -------------------------------


def run_validate_only(config: Dict[str, Any]) -> None:
    """Run only the post-sync validation checks."""
    sync_cfg = config.get("sync", {})
    manifest = SyncManifest(manifest_path=sync_cfg.get("manifest_path", "sync_manifest.json"))
    manifest.load()

    print()
    print("=" * 70)
    print("   Knowledge Base Validation")
    print("=" * 70)
    print()

    validator = SyncValidator(manifest=manifest, config=config)
    results = validator.validate_all()
    summary = validator.get_summary(results)

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"   [{status}] {result.check_name}")
        print(f"           {result.message}")
        if result.details and not result.passed:
            for detail in result.details[:5]:
                print(f"           - {detail}")
        print()

    print("=" * 70)
    if summary["all_passed"]:
        print("   [OK] All validation checks PASSED")
    else:
        print(f"   [WARN] {summary['failed']}/{summary['total_checks']} check(s) FAILED")
    print("=" * 70)


# -- CLI ──────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="PES University Knowledge Base — Automated Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Incremental sync (default)
  python sync_knowledge.py

  # Force full recrawl
  python sync_knowledge.py --full

  # Preview changes without modifying anything
  python sync_knowledge.py --dry-run

  # Quick test with 20 pages
  python sync_knowledge.py --max-pages 20

  # Run validation only
  python sync_knowledge.py --validate-only

  # Run as scheduled daemon (cron from config)
  python sync_knowledge.py --schedule

  # Use custom config
  python sync_knowledge.py --config custom_sync.yaml
        """,
    )

    parser.add_argument(
        "--config", type=str, default="sync_config.yaml",
        help="Path to sync config YAML file (default: sync_config.yaml)",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Force a full recrawl (ignore manifest)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without modifying files or vectors",
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Run post-sync validation checks only",
    )
    parser.add_argument(
        "--schedule", action="store_true",
        help="Run as a scheduled daemon using cron from config",
    )
    parser.add_argument(
        "--max-pages", type=int, default=None,
        help="Override max pages to crawl (useful for testing)",
    )

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Setup logging
    log_file = setup_logging(config)

    # Validate-only mode
    if args.validate_only:
        run_validate_only(config)
        return

    # Schedule mode
    if args.schedule:
        schedule_cfg = config.get("schedule", {})
        cron_expr = schedule_cfg.get("cron", "0 2 * * *")

        def sync_job():
            asyncio.run(run_sync(config, args))

        scheduler = SyncScheduler(
            cron_expression=cron_expr,
            sync_function=sync_job,
        )
        try:
            scheduler.run()
        except KeyboardInterrupt:
            print("\nScheduler stopped.")
        return

    # One-shot sync
    try:
        asyncio.run(run_sync(config, args))
    except KeyboardInterrupt:
        print("\n\nSync interrupted. Manifest may be partially updated.")
        print("Run again to resume from last state.")
        sys.exit(1)
    except Exception as e:
        logging.getLogger("sync.orchestrator").critical(f"Fatal error: {e}", exc_info=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
