#!/usr/bin/env python3
"""
incremental_crawler.py

Incremental crawler that wraps the existing PES crawler with change-detection
awareness. Implements a two-pass approach:

1. Discovery Pass — Crawl the full site link graph, fetch content, compute hashes,
   and classify each URL against the manifest.
2. Content Pass — Only process URLs that are NEW or MODIFIED (already done inline
   during discovery since Playwright renders full pages anyway).

Does NOT modify the existing pes_crawler.py — builds on top of its utilities.
"""

import asyncio
import hashlib
import logging
import re
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup

try:
    from playwright.async_api import (
        async_playwright,
        Page,
        TimeoutError as PlaywrightTimeout,
    )
except ImportError:
    raise ImportError(
        "Playwright is required. Install with: pip install playwright && playwright install chromium"
    )

# Reuse existing crawler utilities
from scripts.data_ingestion.pes_crawler import (
    canonicalize_url,
    is_allowed_domain,
    is_blocked_path,
    is_blocked_extension,
    is_document_url,
    url_to_filename,
    categorize_url,
    extract_content_to_markdown,
    extract_all_links,
    expand_interactive_elements,
    render_page,
    write_markdown_file,
)
from scripts.data_ingestion.crawler_config import (
    BLOCKED_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    MIN_CONTENT_LENGTH,
    MIN_WORD_COUNT,
)
from scripts.data_ingestion.sync.manifest import SyncManifest, ManifestEntry
from scripts.data_ingestion.sync.change_detector import (
    ChangeDetector,
    ChangeSet,
    ChangeType,
    ChangeRecord,
    compute_content_hash,
)
from scripts.data_ingestion.sync import SYNC_SYSTEM_VERSION

logger = logging.getLogger("sync.incremental_crawler")

IST = timezone(timedelta(hours=5, minutes=30))


import dataclasses


@dataclasses.dataclass
class CrawlResult:
    """Result of crawling a single URL."""
    url: str
    canonical_url: str
    change_type: ChangeType
    title: str = ""
    category: str = ""
    breadcrumb: str = ""
    markdown_content: str = ""
    markdown_path: str = ""
    content_hash: str = ""
    http_status: int = 200
    word_count: int = 0
    extraction_stats: Optional[Dict] = dataclasses.field(default_factory=dict)
    error_message: str = ""
    success: bool = True


class IncrementalCrawler:
    """
    Incremental website crawler with change detection.

    Crawls the PES University website, compares content against the sync manifest,
    and only processes pages that have changed. Produces CrawlResults for each
    NEW or MODIFIED URL.
    """

    def __init__(
        self,
        manifest: SyncManifest,
        config: Dict[str, Any],
    ):
        self.manifest = manifest
        self.config = config

        # Crawler settings from config
        crawler_cfg = config.get("crawler", {})
        self.seed_urls = crawler_cfg.get("seed_urls", ["https://pes.edu/"])
        self.allowed_domains = crawler_cfg.get("allowed_domains", ["pes.edu"])
        self.allow_subdomains = crawler_cfg.get("allow_subdomains", True)
        self.max_depth = crawler_cfg.get("max_depth", 10)
        self.max_pages = crawler_cfg.get("max_pages", 2000)
        self.politeness_delay = crawler_cfg.get("politeness_delay", 2.0)
        self.request_timeout = crawler_cfg.get("request_timeout", 30000)
        self.max_retries = crawler_cfg.get("max_retries", 3)
        self.user_agent = crawler_cfg.get(
            "user_agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 PESUKioskBot/2.0",
        )

        # Sync settings
        sync_cfg = config.get("sync", {})
        self.hash_algorithm = sync_cfg.get("content_hash_algorithm", "sha256")

        # Output settings
        ingestion_cfg = config.get("ingestion", {})
        self.output_dir = Path(ingestion_cfg.get("knowledge_dir", "knowledge_new"))

        # Versioning
        versioning_cfg = config.get("versioning", {})
        self.scraper_version = versioning_cfg.get("scraper_version", SYNC_SYSTEM_VERSION)

        # Change detector
        self.change_detector = ChangeDetector(
            manifest=manifest,
            hash_algorithm=self.hash_algorithm,
            max_consecutive_errors=sync_cfg.get("max_consecutive_errors", 3),
        )

        # Crawl state
        self.visited: Set[str] = set()
        self.discovered_urls: Set[str] = set()
        self.crawl_results: List[CrawlResult] = []
        self.document_urls: List[str] = []

        # Statistics
        self.stats = {
            "urls_discovered": 0,
            "urls_visited": 0,
            "pages_successful": 0,
            "pages_failed": 0,
            "pages_skipped_unchanged": 0,
            "pages_new": 0,
            "pages_modified": 0,
            "pages_errors": 0,
            "markdown_files_created": 0,
            "markdown_files_updated": 0,
            "total_words": 0,
            "tables_extracted": 0,
            "documents_found": 0,
            "crawl_duration_seconds": 0,
            "crawl_duration_human": "",
        }

    async def crawl(self, dry_run: bool = False) -> Tuple[ChangeSet, List[CrawlResult]]:
        """
        Run the incremental crawl pipeline.

        Args:
            dry_run: If True, discover and classify URLs but don't write markdown.

        Returns:
            Tuple of (ChangeSet, list of CrawlResults for actionable URLs).
        """
        logger.info("=" * 60)
        logger.info("Incremental Knowledge Sync Crawler — Starting")
        logger.info(f"Manifest has {self.manifest.entry_count} existing entries")
        logger.info("=" * 60)

        start_time = time.time()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=self.user_agent,
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            # Block unnecessary resources for speed
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot,mp4,webm}",
                lambda route: route.abort(),
            )

            # Seed the BFS queue
            queue = deque()
            for seed_url in self.seed_urls:
                canonical = canonicalize_url(seed_url)
                if canonical:
                    queue.append((canonical, 0))
                    self.stats["urls_discovered"] += 1

            pages_crawled = 0

            while queue and pages_crawled < self.max_pages:
                url, depth = queue.popleft()

                # Canonicalize
                canonical = canonicalize_url(url)
                if not canonical or canonical in self.visited:
                    continue

                # Depth check
                if depth > self.max_depth:
                    continue

                # Mark as visited
                self.visited.add(canonical)
                self.discovered_urls.add(canonical)
                self.stats["urls_visited"] += 1

                logger.info(
                    f"[{pages_crawled + 1}/{self.max_pages}] "
                    f"Depth={depth} Crawling: {canonical}"
                )

                # Render the page with retries
                html = None
                for attempt in range(1, self.max_retries + 1):
                    html = await render_page(page, canonical)
                    if html:
                        break
                    if attempt < self.max_retries:
                        wait = attempt * 2
                        logger.info(f"  Retry {attempt}/{self.max_retries} in {wait}s...")
                        await asyncio.sleep(wait)

                if not html:
                    self.stats["pages_failed"] += 1
                    self.stats["pages_errors"] += 1
                    self.change_detector.classify_url(
                        canonical_url=canonical,
                        content_hash="",
                        http_status=0,
                        error_message="Failed after retries",
                    )
                    self.crawl_results.append(CrawlResult(
                        url=canonical,
                        canonical_url=canonical,
                        change_type=ChangeType.ERROR,
                        error_message="Failed after retries",
                        success=False,
                    ))
                    continue

                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, "lxml")

                # Extract page title
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else ""
                title = re.sub(
                    r'\s*[\-–|]\s*PES University\s*$', '', title, flags=re.I
                ).strip()
                if not title:
                    h1 = soup.find("h1")
                    title = h1.get_text(strip=True) if h1 else url_to_filename(canonical)

                # Discover links (BFS expansion)
                new_links = extract_all_links(soup, canonical)
                for link in new_links:
                    if link not in self.visited:
                        if is_document_url(link):
                            if link not in self.document_urls:
                                self.document_urls.append(link)
                                self.stats["documents_found"] += 1
                        else:
                            queue.append((link, depth + 1))
                            self.discovered_urls.add(link)
                            self.stats["urls_discovered"] += 1

                # Extract content
                from scripts.data_ingestion.pes_crawler import extract_breadcrumb
                breadcrumb = extract_breadcrumb(soup)
                markdown_content, extraction_stats = extract_content_to_markdown(
                    soup, canonical
                )

                # Compute content hash from extracted content
                content_hash = compute_content_hash(
                    markdown_content, self.hash_algorithm
                )

                # Classify this URL
                category = categorize_url(canonical)
                change_type = self.change_detector.classify_url(
                    canonical_url=canonical,
                    content_hash=content_hash,
                    http_status=200,
                    title=title,
                    category=category,
                )

                # Track stats
                self.stats["tables_extracted"] += extraction_stats.get("tables", 0)
                self.stats["pages_successful"] += 1
                pages_crawled += 1

                if change_type == ChangeType.UNCHANGED:
                    self.stats["pages_skipped_unchanged"] += 1
                    logger.info(f"  -> Skipped (unchanged): {canonical}")
                    await asyncio.sleep(self.politeness_delay)
                    continue

                if change_type == ChangeType.NEW:
                    self.stats["pages_new"] += 1
                elif change_type == ChangeType.MODIFIED:
                    self.stats["pages_modified"] += 1

                # Write markdown (unless dry-run)
                markdown_path = ""
                if not dry_run and markdown_content and len(markdown_content.strip()) >= MIN_CONTENT_LENGTH:
                    filepath = write_markdown_file(
                        canonical, title, breadcrumb, markdown_content,
                        category, extraction_stats,
                    )
                    if filepath:
                        markdown_path = str(filepath)
                        word_count = len(markdown_content.split())
                        self.stats["total_words"] += word_count

                        if change_type == ChangeType.NEW:
                            self.stats["markdown_files_created"] += 1
                        else:
                            self.stats["markdown_files_updated"] += 1

                        logger.info(
                            f"  -> {change_type.value.upper()}: {filepath.name} "
                            f"({word_count} words)"
                        )

                # Record result
                result = CrawlResult(
                    url=canonical,
                    canonical_url=canonical,
                    change_type=change_type,
                    title=title,
                    category=category,
                    breadcrumb=breadcrumb,
                    markdown_content=markdown_content,
                    markdown_path=markdown_path,
                    content_hash=content_hash,
                    http_status=200,
                    word_count=len(markdown_content.split()) if markdown_content else 0,
                    extraction_stats=extraction_stats,
                    success=True,
                )
                self.crawl_results.append(result)

                # Politeness delay
                await asyncio.sleep(self.politeness_delay)

            await browser.close()

        # Detect deletions — URLs in manifest but not discovered
        self.change_detector.detect_deletions(self.discovered_urls)

        # Finalize stats
        duration = time.time() - start_time
        self.stats["crawl_duration_seconds"] = round(duration, 2)
        self.stats["crawl_duration_human"] = (
            f"{int(duration // 60)}m {int(duration % 60)}s"
        )

        change_set = self.change_detector.get_change_set()

        logger.info("=" * 60)
        logger.info(f"Crawl complete in {self.stats['crawl_duration_human']}")
        logger.info(f"Pages visited: {self.stats['urls_visited']}")
        logger.info(f"New: {self.stats['pages_new']}, "
                     f"Modified: {self.stats['pages_modified']}, "
                     f"Unchanged: {self.stats['pages_skipped_unchanged']}")
        logger.info(f"Deletions detected: {len(change_set.deleted)}")
        logger.info("=" * 60)

        return change_set, self.crawl_results

    def get_stats(self) -> Dict[str, Any]:
        """Return crawl statistics."""
        return dict(self.stats)
