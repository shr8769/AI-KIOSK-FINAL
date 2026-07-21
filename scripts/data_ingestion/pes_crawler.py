#!/usr/bin/env python3
"""
pes_crawler.py

Production-grade recursive website crawler for PES University.
Uses Playwright for JavaScript rendering and BeautifulSoup for content extraction.
Implements BFS crawling with URL canonicalization, checkpoint/resume, auto-expansion
of accordions/tabs/FAQs, and clean Markdown output.
"""

import asyncio
import json
import logging
import os
import re
import time
import hashlib
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

from bs4 import BeautifulSoup, NavigableString, Tag

try:
    from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeout
except ImportError:
    raise ImportError("Playwright is required. Install with: pip install playwright && playwright install chromium")

from scripts.data_ingestion.crawler_config import (
    SEED_URL, ALLOWED_DOMAINS, ALLOW_SUBDOMAINS,
    MAX_DEPTH, MAX_PAGES, POLITENESS_DELAY, REQUEST_TIMEOUT, MAX_RETRIES,
    OUTPUT_DIR, DOWNLOADS_DIR, CHECKPOINT_FILE,
    BLOCKED_EXTENSIONS, DOCUMENT_EXTENSIONS, BLOCKED_PATHS, STRIP_PARAMS,
    ACCORDION_SELECTORS, TAB_SELECTORS, LOAD_MORE_SELECTORS, FAQ_SELECTORS,
    CATEGORY_MAP, DEFAULT_CATEGORY,
    MIN_WORD_COUNT, MIN_CONTENT_LENGTH, CHECKPOINT_INTERVAL,
)

logger = logging.getLogger("pes_crawler")

# IST timezone
IST = timezone(timedelta(hours=5, minutes=30))


# ═══════════════════════════════════════════════
# URL Utilities
# ═══════════════════════════════════════════════

def canonicalize_url(url: str) -> Optional[str]:
    """
    Normalize a URL for deduplication:
    - Lowercase scheme and host
    - Strip fragment
    - Strip tracking query params
    - Remove trailing slash (except root)
    - Normalize path
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    # Only HTTP(S)
    if parsed.scheme not in ("http", "https"):
        return None

    scheme = "https"  # Normalize to https
    host = parsed.hostname
    if not host:
        return None
    host = host.lower().rstrip(".")

    path = parsed.path or "/"
    # Remove trailing slash except for root
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Strip tracking params
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in params.items() if k.lower() not in STRIP_PARAMS}
        query = urlencode(filtered, doseq=True) if filtered else ""
    else:
        query = ""

    # Rebuild without fragment
    canonical = urlunparse((scheme, host, path, "", query, ""))
    return canonical


def is_allowed_domain(url: str) -> bool:
    """Check if URL belongs to an allowed PES domain."""
    try:
        host = urlparse(url).hostname
        if not host:
            return False
        host = host.lower()
        for domain in ALLOWED_DOMAINS:
            if host == domain or (ALLOW_SUBDOMAINS and host.endswith("." + domain)):
                return True
        return False
    except Exception:
        return False


def is_blocked_path(url: str) -> bool:
    """Check if URL matches any blocked path pattern."""
    url_lower = url.lower()
    for blocked in BLOCKED_PATHS:
        if blocked.lower() in url_lower:
            return True
    return False


def is_document_url(url: str) -> bool:
    """Check if URL points to a downloadable document."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    return any(path_lower.endswith(ext) for ext in DOCUMENT_EXTENSIONS)


def is_blocked_extension(url: str) -> bool:
    """Check if URL points to a non-HTML resource (image, CSS, etc.)."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    return any(path_lower.endswith(ext) for ext in BLOCKED_EXTENSIONS)


def url_to_filename(url: str) -> str:
    """Convert a URL to a safe filename slug."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return "index"
    # Replace slashes with underscores, remove special chars
    slug = re.sub(r'[^\w\-]', '_', path.replace("/", "_"))
    # Collapse multiple underscores
    slug = re.sub(r'_+', '_', slug).strip("_")
    if not slug:
        slug = hashlib.md5(url.encode()).hexdigest()[:12]
    return slug[:80]  # Cap length


def categorize_url(url: str) -> str:
    """Determine output category folder from URL path."""
    parsed = urlparse(url)
    path_lower = parsed.path.lower().strip("/")

    # Check each segment of the path
    segments = path_lower.split("/")
    for segment in segments:
        # Direct match
        if segment in CATEGORY_MAP:
            return CATEGORY_MAP[segment]
        # Partial match (e.g., "b-tech-cse" matches "btech")
        for keyword, category in CATEGORY_MAP.items():
            if keyword in segment:
                return category

    # Check hostname for subdomains
    host = parsed.hostname or ""
    host_prefix = host.replace(".pes.edu", "").replace(".edu", "")
    if host_prefix in CATEGORY_MAP:
        return CATEGORY_MAP[host_prefix]

    return DEFAULT_CATEGORY


# ═══════════════════════════════════════════════
# Content Extraction
# ═══════════════════════════════════════════════

def extract_breadcrumb(soup: BeautifulSoup) -> str:
    """Extract breadcrumb navigation text."""
    breadcrumb_selectors = [
        ".gdlr-core-breadcrumb",
        ".breadcrumb",
        '[class*="breadcrumb"]',
        "nav[aria-label='breadcrumb']",
    ]
    for selector in breadcrumb_selectors:
        bc = soup.select_one(selector)
        if bc:
            text = bc.get_text(separator=" > ", strip=True)
            if text:
                return text
    return ""


def html_table_to_markdown(table: Tag) -> str:
    """Convert an HTML table to Markdown table format."""
    rows = []
    for tr in table.find_all("tr"):
        cells = []
        for td in tr.find_all(["th", "td"]):
            cell_text = td.get_text(separator=" ", strip=True)
            # Escape pipe characters in cell content
            cell_text = cell_text.replace("|", "\\|")
            cells.append(cell_text)
        if cells:
            rows.append(cells)

    if not rows:
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in rows)
    for row in rows:
        while len(row) < max_cols:
            row.append("")

    lines = []
    # Header row
    lines.append("| " + " | ".join(rows[0]) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    # Data rows
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def extract_content_to_markdown(soup: BeautifulSoup, url: str) -> Tuple[str, Dict]:
    """
    Extract main content from a rendered page and convert to clean Markdown.
    Returns (markdown_text, extraction_stats).
    """
    stats = {
        "headings": 0,
        "paragraphs": 0,
        "tables": 0,
        "lists": 0,
        "links_found": 0,
        "images": 0,
        "emails": [],
        "phones": [],
        "download_links": [],
    }

    # Try to find the main content area (skip nav/header/footer for content extraction)
    main_content = None
    content_selectors = [
        ".gdlr-core-page-builder-body",
        "main",
        "#content",
        ".entry-content",
        ".page-content",
        "article",
        '[role="main"]',
        ".kingster-content-area",
        ".gdlr-core-container",
    ]
    for selector in content_selectors:
        main_content = soup.select_one(selector)
        if main_content:
            break

    if not main_content:
        # Fallback: use body but remove nav/header/footer
        main_content = soup.find("body")
        if main_content:
            for tag in main_content.find_all(["nav", "header", "footer", "script", "style", "noscript"]):
                tag.decompose()

    if not main_content:
        return "", stats

    # Remove script, style, noscript tags
    for tag in main_content.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    # Remove hidden elements
    for tag in main_content.find_all(attrs={"style": re.compile(r"display\s*:\s*none", re.I)}):
        tag.decompose()

    md_parts = []

    def process_element(element, depth=0):
        """Recursively process HTML elements into Markdown."""
        if isinstance(element, NavigableString):
            text = str(element).strip()
            if text:
                md_parts.append(text)
            return

        if not isinstance(element, Tag):
            return

        tag_name = element.name

        # Headings
        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            text = element.get_text(strip=True)
            if text:
                prefix = "#" * level
                md_parts.append(f"\n{prefix} {text}\n")
                stats["headings"] += 1
            return

        # Tables
        if tag_name == "table":
            table_md = html_table_to_markdown(element)
            if table_md:
                md_parts.append(f"\n{table_md}\n")
                stats["tables"] += 1
            return

        # Lists
        if tag_name in ("ul", "ol"):
            stats["lists"] += 1
            for i, li in enumerate(element.find_all("li", recursive=False)):
                li_text = li.get_text(strip=True)
                if li_text:
                    if tag_name == "ol":
                        md_parts.append(f"{i+1}. {li_text}")
                    else:
                        md_parts.append(f"- {li_text}")
            md_parts.append("")
            return

        # Paragraphs
        if tag_name == "p":
            text = element.get_text(strip=True)
            if text:
                md_parts.append(f"\n{text}\n")
                stats["paragraphs"] += 1
            return

        # Links
        if tag_name == "a":
            href = element.get("href", "")
            text = element.get_text(strip=True)
            if href and text:
                full_url = urljoin(url, href)
                # Check for document downloads
                if is_document_url(full_url):
                    stats["download_links"].append(full_url)
                    md_parts.append(f"[{text}]({full_url})")
                else:
                    md_parts.append(f"[{text}]({full_url})")
                stats["links_found"] += 1

                # Extract emails
                if href.startswith("mailto:"):
                    email = href.replace("mailto:", "").strip()
                    stats["emails"].append(email)
                # Extract phone numbers
                if href.startswith("tel:"):
                    phone = href.replace("tel:", "").strip()
                    stats["phones"].append(phone)
            elif text:
                md_parts.append(text)
            return

        # Images
        if tag_name == "img":
            alt = element.get("alt", "")
            src = element.get("src", "") or element.get("data-src", "")
            if src and alt:
                md_parts.append(f"![{alt}]({urljoin(url, src)})")
                stats["images"] += 1
            return

        # Blockquotes
        if tag_name == "blockquote":
            text = element.get_text(strip=True)
            if text:
                md_parts.append(f"\n> {text}\n")
            return

        # Strong / Bold
        if tag_name in ("strong", "b"):
            text = element.get_text(strip=True)
            if text:
                md_parts.append(f"**{text}**")
            return

        # Emphasis / Italic
        if tag_name in ("em", "i"):
            text = element.get_text(strip=True)
            if text:
                md_parts.append(f"*{text}*")
            return

        # Line breaks
        if tag_name == "br":
            md_parts.append("\n")
            return

        # Horizontal rules
        if tag_name == "hr":
            md_parts.append("\n---\n")
            return

        # Div, section, article - recurse into children
        if tag_name in ("div", "section", "article", "span", "main", "aside", "figure", "figcaption", "details", "summary"):
            for child in element.children:
                process_element(child, depth + 1)
            return

        # For anything else, try to get text
        text = element.get_text(strip=True)
        if text and len(text) > 2:
            md_parts.append(text)

    process_element(main_content)

    # Also extract emails/phones from full page text
    full_text = main_content.get_text()
    email_pattern = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
    phone_pattern = re.compile(r'(?:\+91[\s\-]?)?(?:\d[\s\-]?){10}')

    for email in email_pattern.findall(full_text):
        if email not in stats["emails"] and not email.endswith((".png", ".jpg", ".css", ".js")):
            stats["emails"].append(email)

    for phone in phone_pattern.findall(full_text):
        phone_clean = re.sub(r'[\s\-]', '', phone)
        if len(phone_clean) >= 10 and phone_clean not in stats["phones"]:
            stats["phones"].append(phone_clean)

    # Join and clean up
    markdown = "\n".join(md_parts)
    # Clean up excessive newlines
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    markdown = markdown.strip()

    return markdown, stats


def extract_all_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    Extract all internal links from the full page (including nav, footer, sidebar).
    Returns a list of canonicalized URLs.
    """
    links = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        full_url = urljoin(base_url, href)
        canonical = canonicalize_url(full_url)

        if canonical and is_allowed_domain(canonical) and not is_blocked_path(canonical) and not is_blocked_extension(canonical):
            links.add(canonical)

    return list(links)


# ═══════════════════════════════════════════════
# Page Rendering & Interactive Element Expansion
# ═══════════════════════════════════════════════

async def expand_interactive_elements(page: Page) -> Dict[str, int]:
    """
    Click all accordions, tabs, FAQ elements, and 'Load More' buttons
    to reveal hidden content before extraction.
    Returns counts of expanded elements.
    """
    expansion_stats = {"accordions": 0, "tabs": 0, "load_more": 0, "faqs": 0}

    # Scroll to bottom to trigger lazy loading
    try:
        await page.evaluate("""
            async () => {
                const delay = ms => new Promise(r => setTimeout(r, ms));
                const height = document.body.scrollHeight;
                for (let i = 0; i < height; i += 400) {
                    window.scrollTo(0, i);
                    await delay(100);
                }
                window.scrollTo(0, 0);
            }
        """)
        await page.wait_for_timeout(500)
    except Exception:
        pass

    # Expand accordions
    for selector in ACCORDION_SELECTORS:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                try:
                    await el.click(timeout=2000)
                    await page.wait_for_timeout(300)
                    expansion_stats["accordions"] += 1
                except Exception:
                    pass
        except Exception:
            pass

    # Click tabs
    for selector in TAB_SELECTORS:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                try:
                    await el.click(timeout=2000)
                    await page.wait_for_timeout(300)
                    expansion_stats["tabs"] += 1
                except Exception:
                    pass
        except Exception:
            pass

    # Click Load More / Read More buttons
    for selector in LOAD_MORE_SELECTORS:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                try:
                    if await el.is_visible():
                        await el.click(timeout=2000)
                        await page.wait_for_timeout(500)
                        expansion_stats["load_more"] += 1
                except Exception:
                    pass
        except Exception:
            pass

    # Expand FAQ items
    for selector in FAQ_SELECTORS:
        try:
            elements = await page.query_selector_all(selector)
            for el in elements:
                try:
                    await el.click(timeout=2000)
                    await page.wait_for_timeout(300)
                    expansion_stats["faqs"] += 1
                except Exception:
                    pass
        except Exception:
            pass

    # Wait a moment for all content to render
    await page.wait_for_timeout(500)

    return expansion_stats


async def render_page(page: Page, url: str) -> Optional[str]:
    """
    Navigate to a URL, wait for rendering, expand interactive elements,
    and return the fully-rendered HTML.
    """
    try:
        response = await page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT)
        if response is None or response.status >= 400:
            status = response.status if response else "None"
            logger.warning(f"HTTP {status} for {url}")
            return None

        # Additional wait for JS rendering
        await page.wait_for_timeout(1000)

        # Expand interactive elements
        await expand_interactive_elements(page)

        # Get final rendered HTML
        html = await page.content()
        return html

    except PlaywrightTimeout:
        logger.warning(f"Timeout loading {url}")
        return None
    except Exception as e:
        logger.error(f"Error rendering {url}: {e}")
        return None


# ═══════════════════════════════════════════════
# Markdown File Writer
# ═══════════════════════════════════════════════

def write_markdown_file(url: str, title: str, breadcrumb: str, markdown_content: str,
                        category: str, stats: Dict) -> Optional[Path]:
    """Write extracted content as a Markdown file with YAML frontmatter."""
    if not markdown_content or len(markdown_content.strip()) < MIN_CONTENT_LENGTH:
        return None

    filename = url_to_filename(url) + ".md"
    category_dir = OUTPUT_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)
    filepath = category_dir / filename

    now = datetime.now(IST).isoformat()

    frontmatter = f"""---
title: "{title}"
url: {url}
category: {category}
breadcrumb: "{breadcrumb}"
last_crawled: "{now}"
---

"""
    # Add contact info section if found
    contact_section = ""
    if stats.get("emails") or stats.get("phones"):
        contact_parts = []
        if stats["emails"]:
            contact_parts.append("**Emails:** " + ", ".join(set(stats["emails"])))
        if stats["phones"]:
            contact_parts.append("**Phone:** " + ", ".join(set(stats["phones"])))
        contact_section = "\n\n---\n\n## Contact Information\n\n" + "\n\n".join(contact_parts) + "\n"

    full_content = frontmatter + markdown_content + contact_section

    filepath.write_text(full_content, encoding="utf-8")
    return filepath


# ═══════════════════════════════════════════════
# Checkpoint / Resume
# ═══════════════════════════════════════════════

def save_checkpoint(visited: Set[str], queue: deque, document_urls: List[str],
                    crawl_stats: Dict) -> None:
    """Save crawl state to JSON for resume capability."""
    data = {
        "visited": list(visited),
        "queue": list(queue),
        "document_urls": document_urls,
        "stats": crawl_stats,
        "timestamp": datetime.now(IST).isoformat(),
    }
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info(f"Checkpoint saved: {len(visited)} visited, {len(queue)} in queue")


def load_checkpoint() -> Optional[Dict]:
    """Load crawl state from checkpoint file."""
    if not CHECKPOINT_FILE.exists():
        return None
    try:
        data = json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
        logger.info(f"Checkpoint loaded: {len(data.get('visited', []))} visited, "
                     f"{len(data.get('queue', []))} in queue")
        return data
    except Exception as e:
        logger.error(f"Failed to load checkpoint: {e}")
        return None


# ═══════════════════════════════════════════════
# Main Crawler
# ═══════════════════════════════════════════════

class PESCrawler:
    """
    Recursive BFS crawler for PES University website.
    Uses Playwright for rendering and BeautifulSoup for extraction.
    """

    def __init__(self, max_pages: int = MAX_PAGES, max_depth: int = MAX_DEPTH,
                 delay: float = POLITENESS_DELAY, resume: bool = False):
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.delay = delay
        self.resume = resume

        # Crawl state
        self.visited: Set[str] = set()
        self.queue: deque = deque()  # (url, depth)
        self.document_urls: List[str] = []

        # Statistics
        self.stats = {
            "urls_discovered": 0,
            "urls_visited": 0,
            "pages_successful": 0,
            "pages_failed": 0,
            "pages_skipped": 0,
            "pages_duplicate": 0,
            "documents_found": 0,
            "tables_extracted": 0,
            "accordions_expanded": 0,
            "faqs_expanded": 0,
            "tabs_expanded": 0,
            "markdown_files_created": 0,
            "total_words": 0,
            "errors": [],
            "failed_urls": [],
            "skipped_urls": [],
            "files_created": [],
        }

    async def crawl(self) -> Dict:
        """Run the full crawl pipeline."""
        logger.info("=" * 60)
        logger.info("PES University Recursive Crawler - Starting")
        logger.info("=" * 60)

        # Resume from checkpoint if requested
        if self.resume:
            checkpoint = load_checkpoint()
            if checkpoint:
                self.visited = set(checkpoint.get("visited", []))
                queue_items = checkpoint.get("queue", [])
                self.queue = deque()
                for item in queue_items:
                    if isinstance(item, list) and len(item) == 2:
                        self.queue.append(tuple(item))
                    elif isinstance(item, str):
                        self.queue.append((item, 0))
                self.document_urls = checkpoint.get("document_urls", [])
                prev_stats = checkpoint.get("stats", {})
                self.stats.update(prev_stats)
                logger.info(f"Resumed from checkpoint: {len(self.visited)} already visited")
            else:
                logger.info("No checkpoint found, starting fresh")
                self._seed_queue()
        else:
            self._seed_queue()

        # Ensure output directory exists
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

        start_time = time.time()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
                           "PESUKioskBot/1.0",
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            # Block unnecessary resources for speed
            await page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot,mp4,webm}",
                             lambda route: route.abort())

            pages_crawled = 0

            while self.queue and pages_crawled < self.max_pages:
                url, depth = self.queue.popleft()

                # Skip if already visited
                canonical = canonicalize_url(url)
                if not canonical or canonical in self.visited:
                    self.stats["pages_duplicate"] += 1
                    continue

                # Skip if too deep
                if depth > self.max_depth:
                    self.stats["pages_skipped"] += 1
                    self.stats["skipped_urls"].append({"url": url, "reason": "max_depth"})
                    continue

                # Mark as visited
                self.visited.add(canonical)
                self.stats["urls_visited"] += 1

                logger.info(f"[{pages_crawled + 1}/{self.max_pages}] Depth={depth} Crawling: {url}")

                # Render the page
                success = False
                for attempt in range(1, MAX_RETRIES + 1):
                    html = await render_page(page, url)
                    if html:
                        success = True
                        break
                    if attempt < MAX_RETRIES:
                        wait = attempt * 2
                        logger.info(f"  Retry {attempt}/{MAX_RETRIES} in {wait}s...")
                        await asyncio.sleep(wait)

                if not success:
                    self.stats["pages_failed"] += 1
                    self.stats["failed_urls"].append(url)
                    self.stats["errors"].append({"url": url, "error": "Failed after retries"})
                    continue

                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, "lxml")

                # Extract page title
                title_tag = soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else ""
                # Clean up WP title suffixes
                title = re.sub(r'\s*[\-–|]\s*PES University\s*$', '', title, flags=re.I).strip()
                if not title:
                    h1 = soup.find("h1")
                    title = h1.get_text(strip=True) if h1 else url_to_filename(url)

                # Extract breadcrumb
                breadcrumb = extract_breadcrumb(soup)

                # Discover links (from full page including nav/footer)
                new_links = extract_all_links(soup, url)
                for link in new_links:
                    if link not in self.visited:
                        if is_document_url(link):
                            if link not in self.document_urls:
                                self.document_urls.append(link)
                                self.stats["documents_found"] += 1
                        else:
                            self.queue.append((link, depth + 1))
                            self.stats["urls_discovered"] += 1

                # Extract content and convert to Markdown
                markdown_content, extraction_stats = extract_content_to_markdown(soup, url)

                # Update stats
                self.stats["tables_extracted"] += extraction_stats.get("tables", 0)
                self.document_urls.extend(extraction_stats.get("download_links", []))

                # Categorize and write
                category = categorize_url(url)
                filepath = write_markdown_file(url, title, breadcrumb, markdown_content, category, extraction_stats)

                if filepath:
                    word_count = len(markdown_content.split())
                    self.stats["markdown_files_created"] += 1
                    self.stats["total_words"] += word_count
                    self.stats["files_created"].append({
                        "url": url,
                        "file": str(filepath),
                        "category": category,
                        "words": word_count,
                        "tables": extraction_stats.get("tables", 0),
                    })
                    logger.info(f"  -> Saved: {filepath.name} ({word_count} words, {extraction_stats.get('tables', 0)} tables)")
                else:
                    self.stats["pages_skipped"] += 1
                    self.stats["skipped_urls"].append({"url": url, "reason": "insufficient_content"})
                    logger.info(f"  -> Skipped (insufficient content)")

                self.stats["pages_successful"] += 1
                pages_crawled += 1

                # Checkpoint
                if pages_crawled % CHECKPOINT_INTERVAL == 0:
                    save_checkpoint(
                        self.visited,
                        self.queue,
                        self.document_urls,
                        self.stats,
                    )

                # Politeness delay
                await asyncio.sleep(self.delay)

            await browser.close()

        # Final checkpoint
        save_checkpoint(self.visited, self.queue, self.document_urls, self.stats)

        duration = time.time() - start_time
        self.stats["crawl_duration_seconds"] = round(duration, 2)
        self.stats["crawl_duration_human"] = f"{int(duration // 60)}m {int(duration % 60)}s"

        logger.info("=" * 60)
        logger.info(f"Crawl complete in {self.stats['crawl_duration_human']}")
        logger.info(f"Pages visited: {self.stats['urls_visited']}")
        logger.info(f"Markdown files: {self.stats['markdown_files_created']}")
        logger.info(f"Documents found: {self.stats['documents_found']}")
        logger.info(f"Total words: {self.stats['total_words']}")
        logger.info("=" * 60)

        return self.stats

    def _seed_queue(self):
        """Initialize the crawl queue with the seed URL."""
        canonical = canonicalize_url(SEED_URL)
        if canonical:
            self.queue.append((canonical, 0))
            self.stats["urls_discovered"] += 1
