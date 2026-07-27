#!/usr/bin/env python3
"""
autonomous_sync.py

Autonomous website change monitoring and incremental RAG ingestion scheduler.
Periodically checks target URL headers/hash, crawls only changed pages using Selenium Edge,
and performs incremental vector DB updates.
"""

import os
import sys
import time
import argparse
import logging
import hashlib
import requests
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Ensure the repository root is in python path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from new_backend.scraper.config import (  # noqa: E402
    KNOWLEDGE_NEW_DIR, TARGET_URLS,
    SYNC_INTERVAL_HOURS, TRACKER_FILE_PATH, AUTONOMOUS_LOG_FILE,
    HEADERS, REQUEST_TIMEOUT
)
from new_backend.scraper.utils import slugify, format_frontmatter  # noqa: E402
from new_backend.scraper.crawler import PESCrawler  # noqa: E402
from new_backend.scraper.incremental_ingester import ingest_single_file, delete_single_file_chunks  # noqa: E402

# Setup logging specific to autonomous sync
logger = logging.getLogger("autonomous_sync")
logger.setLevel(logging.INFO)

if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    # File handler
    os.makedirs(os.path.dirname(AUTONOMOUS_LOG_FILE), exist_ok=True)
    file_handler = logging.FileHandler(AUTONOMOUS_LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

DEFAULT_DB_PATH = os.path.join(root_dir, "knowledge", "vectorstore")

def calculate_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def load_tracker() -> Dict[str, Any]:
    if not os.path.exists(TRACKER_FILE_PATH):
        logger.info("No crawler tracker file found. Starting fresh.")
        return {}
    try:
        with open(TRACKER_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read tracker file: {e}. Starting fresh.")
        return {}

def save_tracker(tracker: Dict[str, Any]):
    try:
        os.makedirs(os.path.dirname(TRACKER_FILE_PATH), exist_ok=True)
        with open(TRACKER_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(tracker, f, indent=4, ensure_ascii=False)
        logger.debug("Successfully saved crawler tracker.")
    except Exception as e:
        logger.error(f"Failed to save tracker file: {e}")

def check_url_headers(url: str, retries: int = 3, backoff: float = 2.0) -> Tuple[bool, Optional[str], Optional[str], Optional[requests.Response]]:
    """
    Tries to retrieve HTTP response headers for change detection.
    Performs retries with exponential backoff on transient errors.
    Returns (success, last_modified, etag, response)
    """
    attempt_err = None
    for attempt in range(retries):
        try:
            # We do a standard GET but with a short timeout and streams to grab headers first
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
            if response.status_code == 404:
                logger.warning(f"URL {url} returned 404. Page may be deleted.")
                return False, None, None, response
            if response.status_code >= 400:
                raise requests.RequestException(f"HTTP error status code {response.status_code}")
                
            last_modified = response.headers.get("Last-Modified")
            etag = response.headers.get("ETag")
            return True, last_modified, etag, response
        except Exception as e:
            attempt_err = e
            if attempt < retries - 1:
                sleep_time = backoff ** (attempt + 1)
                logger.warning(f"Request failed for {url}: {e}. Retrying in {sleep_time}s...")
                time.sleep(sleep_time)
            
    logger.error(f"Failed to fetch headers for {url} after {retries} attempts: {attempt_err}")
    return False, None, None, None

def run_sync_cycle(db_path: str = DEFAULT_DB_PATH, dry_run: bool = False) -> Dict[str, Any]:
    """
    Executes a single check, crawl, and vector DB update cycle.
    """
    logger.info("=" * 60)
    logger.info(f"Starting Autonomous Sync Cycle: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    tracker = load_tracker()
    active_urls = set(TARGET_URLS)
    
    stats = {
        "checked": 0,
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "failed": 0,
        "chunks_added": 0,
        "chunks_removed": 0
    }
    
    crawler = PESCrawler()
    driver = None
    crawler_initialized = False
    
    try:
        # Check target URLs
        for url in TARGET_URLS:
            stats["checked"] += 1
            logger.info(f"[{stats['checked']}/{len(TARGET_URLS)}] Checking: {url}")
            
            # Fetch headers
            success, last_modified, etag, response = check_url_headers(url)
            
            # Handle deleted / 404 URLs directly
            if response is not None and response.status_code == 404:
                logger.warning(f"Page deleted (404): {url}")
                # We let the deletion cleanup section below handle it since it is no longer in TARGET_URLS or we flag it
                continue
                
            if not success:
                logger.warning(f"Skipping check for {url} due to header request failure.")
                stats["failed"] += 1
                continue
                
            # Check tracker matching
            slug = slugify(url)
            category = crawler.get_url_category(url) or "general"
            
            tracked_info = tracker.get(url)
            is_new = tracked_info is None
            
            # Change flags
            headers_indicate_change = False
            if not is_new:
                # Compare headers if available
                tracked_lm = tracked_info.get("last_modified")
                tracked_etag = tracked_info.get("etag")
                
                if (last_modified and tracked_lm and last_modified != tracked_lm) or \
                   (etag and tracked_etag and etag != tracked_etag):
                    logger.info(f"Headers indicate changes for {url}. Last-Modified: '{last_modified}' vs '{tracked_lm}'")
                    headers_indicate_change = True
                    
            # Skip if headers match and it's not new
            if not is_new and not headers_indicate_change and last_modified and etag:
                logger.info(f"Unchanged via headers for {url}. Skipping fetch.")
                continue
                
            # Content changed or headers not available or new: fetch full body
            try:
                if not crawler_initialized:
                    driver = crawler._init_driver()
                    crawler_initialized = True
                    
                logger.info(f"Fetching full page content via headless Edge: {url}")
                # clean_url handles expanding accordions, tabs, etc.
                markdown_content, discovered_links = crawler.cleaner.clean_url(url, driver=driver)
                
                if not markdown_content or len(markdown_content.strip()) == 0:
                    logger.warning(f"No content extracted for {url}. Skipping.")
                    stats["failed"] += 1
                    continue
                    
                curr_hash = calculate_hash(markdown_content)
                
                # Check text content hash to double check if something changed
                if not is_new and tracked_info.get("content_hash") == curr_hash:
                    logger.info(f"Content hash unchanged for {url}. Skipping DB update.")
                    # Update tracker headers to prevent future redundant fetches
                    tracker[url]["last_modified"] = last_modified or ""
                    tracker[url]["etag"] = etag or ""
                    save_tracker(tracker)
                    continue
                    
                # Clean or create directory
                category_dir = os.path.join(KNOWLEDGE_NEW_DIR, category)
                os.makedirs(category_dir, exist_ok=True)
                md_file_path = os.path.join(category_dir, f"{slug}.md")
                
                # Extract title
                title = "PES University Page"
                for line in markdown_content.split("\n"):
                    if line.strip().startswith("# "):
                        title = line.strip()[2:].strip()
                        break
                        
                # Construct updated metadata
                meta = {
                    "title": title,
                    "url": url,
                    "category": category,
                    "last_crawled": datetime.now().isoformat(),
                    "last_modified": last_modified or "",
                    "content_hash": curr_hash,
                    "version": "1.0.0",
                    "source": "PES University Official Portal"
                }
                
                md_with_meta = format_frontmatter(meta) + markdown_content
                
                if dry_run:
                    logger.info(f"[DRY-RUN] Would write markdown file and ingest to DB: {md_file_path}")
                    stats["added" if is_new else "updated"] += 1
                    continue
                    
                # Write to disk
                with open(md_file_path, "w", encoding="utf-8") as f:
                    f.write(md_with_meta)
                    
                # Trigger incremental database update
                logger.info(f"Triggering incremental DB upsert for file: {md_file_path}")
                ingest_res = ingest_single_file(Path(md_file_path), db_path=db_path)
                
                if ingest_res["status"] == "success":
                    tracker[url] = {
                        "url": url,
                        "last_crawled": meta["last_crawled"],
                        "last_modified": meta["last_modified"],
                        "etag": etag or "",
                        "content_hash": curr_hash,
                        "chunk_ids": ingest_res["chunk_ids"],
                        "category": category,
                        "version": "1.0.0"
                    }
                    save_tracker(tracker)
                    
                    stats["added" if is_new else "updated"] += 1
                    stats["chunks_added"] += ingest_res["chunks_upserted"]
                    stats["chunks_removed"] += ingest_res["chunks_purged"]
                    logger.info(f"Incrementally updated {url} successfully. Upserted {ingest_res['chunks_upserted']} chunks.")
                elif ingest_res["status"] == "skipped":
                    logger.warning(f"Document ingestion skipped (e.g. invalid content): {ingest_res['reason_detail']}")
                else:
                    logger.error(f"Incremental DB ingestion failed: {ingest_res.get('reason_detail')}")
                    stats["failed"] += 1
                    
            except Exception as e:
                logger.error(f"Error processing URL {url}: {e}")
                stats["failed"] += 1
                
        # 6. Cleanup Deleted URLs (Tracker contains URL that is not in TARGET_URLS, or returns 404)
        for url in list(tracker.keys()):
            if url not in active_urls:
                stats["deleted"] += 1
                logger.info(f"Detecting deletion/removal of target URL: {url}")
                
                tracked_info = tracker[url]
                category = tracked_info.get("category", "general")
                slug = slugify(url)
                
                # Delete chunks from ChromaDB
                relative_path = f"knowledge_new/{category}/{slug}.md"
                if not dry_run:
                    del_res = delete_single_file_chunks(relative_path, category, db_path=db_path)
                    stats["chunks_removed"] += del_res.get("chunks_deleted", 0)
                    
                    # Delete file from filesystem
                    md_file_path = os.path.join(KNOWLEDGE_NEW_DIR, category, f"{slug}.md")
                    if os.path.exists(md_file_path):
                        try:
                            os.remove(md_file_path)
                            logger.info(f"Deleted file from filesystem: {md_file_path}")
                        except Exception as e:
                            logger.error(f"Failed to delete file {md_file_path}: {e}")
                            
                logger.info(f"Cleaned up metadata and database records for deleted page: {url}")
                del tracker[url]
                save_tracker(tracker)
                
    finally:
        crawler.close()
        
    logger.info("=" * 60)
    logger.info("Autonomous Sync Cycle Completed.")
    logger.info(f"Checked      : {stats['checked']}")
    logger.info(f"Added        : {stats['added']}")
    logger.info(f"Updated      : {stats['updated']}")
    logger.info(f"Deleted      : {stats['deleted']}")
    logger.info(f"Failed       : {stats['failed']}")
    logger.info(f"Chunks Added : {stats['chunks_added']}")
    logger.info(f"Chunks Purged: {stats['chunks_removed']}")
    logger.info("=" * 60)
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="Autonomous web scraper and RAG incremental ingestion agent.")
    parser.add_argument("--daemon", action="store_true", help="Run persistently in daemon scheduling mode.")
    parser.add_argument("--run-once", action="store_true", default=False, help="Run a single sync cycle immediately and exit.")
    parser.add_argument("--interval-seconds", type=int, default=None, help="Scheduling interval override in seconds.")
    parser.add_argument("--db-path", type=str, default=DEFAULT_DB_PATH, help="ChromaDB persistent database path.")
    parser.add_argument("--dry-run", action="store_true", help="Perform change detection and crawl without writing to disk or database.")
    args = parser.parse_args()
    
    if args.run_once or not args.daemon:
        logger.info("Executing single one-off sync run...")
        run_sync_cycle(db_path=args.db_path, dry_run=args.dry_run)
        sys.exit(0)
        
    interval_sec = args.interval_seconds if args.interval_seconds is not None else (SYNC_INTERVAL_HOURS * 3600)
    logger.info(f"Starting persistent daemon scheduling mode. Loop interval: {interval_sec} seconds ({interval_sec/3600:.2f} hours).")
    
    try:
        while True:
            try:
                run_sync_cycle(db_path=args.db_path, dry_run=args.dry_run)
            except Exception as e:
                logger.error(f"Uncaught exception during execution cycle: {e}")
            logger.info(f"Sleeping for {interval_sec} seconds...")
            time.sleep(interval_sec)
    except KeyboardInterrupt:
        logger.info("Scheduler daemon shut down by user request.")

if __name__ == "__main__":
    main()
