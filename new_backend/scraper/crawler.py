import re
import time
import urllib.parse
from typing import Dict, List, Set, Tuple, Any, Optional
from collections import deque
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.edge.options import Options

from new_backend.scraper.config import (
    START_URL, ALLOWED_DOMAINS, CATEGORY_MAPPING, IGNORED_PATTERNS,
    NEWS_PATTERN, RATE_LIMIT_DELAY, MAX_DEPTH, MAX_PAGES
)
from new_backend.scraper.utils import setup_logging
from new_backend.scraper.cleaner import HTMLCleaner

logger = setup_logging()

class PESCrawler:
    """
    Website crawler for PES University kiosk knowledge base.
    Uses BFS, respects rate limiting, discovers and filters URLs,
    and runs the HTMLCleaner to save pages.
    Uses headless Selenium Edge to fully render Javascript and expand accordions/tabs.
    """
    def __init__(self, start_url: str = START_URL, max_depth: int = MAX_DEPTH, max_pages: int = MAX_PAGES):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages
        
        # State tracking
        self.visited_urls: Set[str] = set()
        self.crawled_urls: List[str] = []
        self.skipped_urls: List[Tuple[str, str]] = []  # List of (url, reason)
        self.failed_urls: List[Tuple[str, str]] = []   # List of (url, error_message)
        
        # Queue for BFS: stores tuples of (url, current_depth)
        self.queue: deque = deque([(self.start_url, 0)])
        
        # Quality/extraction stats
        self.extracted_pages: List[Dict[str, Any]] = []
        self.total_characters = 0
        self.total_duplicates_removed = 0
        self.crawl_start_time = 0.0
        
        # Initialize helper classes
        self.cleaner = HTMLCleaner(base_url=self.start_url)
        self.last_request_time = 0.0
        self.driver = None
        self.page_reports = {}

    def _init_driver(self):
        """
        Initializes the headless Edge Webdriver instance if not already active.
        """
        if not self.driver:
            logger.info("Initializing Headless Edge Driver...")
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--log-level=3")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--no-sandbox")
            self.driver = webdriver.Edge(options=options)
        return self.driver

    def close(self):
        """
        Gracefully terminates the Selenium Edge browser.
        """
        if self.driver:
            logger.info("Closing Headless Edge Driver...")
            try:
                self.driver.quit()
            except Exception as e:
                logger.warning(f"Error quitting Edge driver: {e}")
            self.driver = None

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL by removing fragments and stripping trailing slashes.
        """
        parsed = urllib.parse.urlparse(url)
        cleaned_url = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            parsed.params,
            parsed.query,
            ""
        ))
        return cleaned_url

    def _is_same_domain(self, url: str) -> bool:
        """
        Check if URL belongs to the allowed domains.
        """
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        for domain in ALLOWED_DOMAINS:
            if netloc == domain or netloc.endswith("." + domain):
                return True
        return False

    def _check_ignored_patterns(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Checks if the URL matches any ignored patterns or is an old news page.
        Returns (is_ignored, reason_if_ignored).
        """
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        
        for pattern in IGNORED_PATTERNS:
            if re.search(pattern, path, re.IGNORECASE) or re.search(pattern, url, re.IGNORECASE):
                return True, f"Matches ignored pattern: {pattern}"
                
        news_match = re.search(NEWS_PATTERN, path)
        if news_match:
            try:
                year = int(news_match.group(1))
                if year < 2025:
                    return True, f"Old news article from year {year} (older than 1 year)"
            except ValueError:
                pass
                
        return False, None

    def get_url_category(self, url: str) -> Optional[str]:
        """
        Identify which category this URL belongs to based on CATEGORY_MAPPING.
        """
        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            return "general"
            
        path_lower = path.lower()
        for category, keywords in CATEGORY_MAPPING.items():
            for keyword in keywords:
                pattern = r"(^|/|-|_)" + re.escape(keyword) + r"($|/|-|_)"
                if re.search(pattern, path_lower):
                    return category
        return None

    def _should_crawl(self, url: str) -> Tuple[bool, Optional[str]]:
        """
        Evaluates if the crawler should visit this URL.
        """
        norm_url = self._normalize_url(url)
        
        if norm_url in self.visited_urls:
            return False, "Already visited"
            
        if not self._is_same_domain(norm_url):
            return False, "External domain"
            
        is_ignored, reason = self._check_ignored_patterns(norm_url)
        if is_ignored:
            return False, reason or "Ignored pattern match"
            
        category = self.get_url_category(norm_url)
        if not category:
            return False, "Does not map to any target category"
            
        return True, None

    def _sleep_rate_limit(self):
        """
        Respect rate limiting by sleeping if the delay hasn't passed.
        """
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            sleep_time = RATE_LIMIT_DELAY - elapsed
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def discover_links(self, soup: BeautifulSoup, current_url: str) -> List[str]:
        """
        Finds and extracts links on a page.
        """
        found_links = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            absolute_url = urllib.parse.urljoin(current_url, href)
            found_links.append(absolute_url)
        return found_links

    def _expand_interactive_elements(self, url: str, attempt: int):
        """
        Locates and expands all interactive sections: accordions, tabs, collapsibles,
        read-more, load-more, quota sections, etc.
        """
        if not self.driver:
            return
            
        logger.info(f"Expanding interactive elements for {url} (Attempt {attempt})...")
        
        # Base delays scale with attempt number
        delay_multiplier = attempt
        
        # 1. Scroll through page to trigger lazy loading of content/images/scripts
        try:
            total_height = self.driver.execute_script("return document.body.scrollHeight")
            current_position = 0
            scroll_step = 400
            while current_position < total_height:
                current_position += scroll_step
                self.driver.execute_script(f"window.scrollTo(0, {current_position});")
                time.sleep(0.15 * delay_multiplier)
                total_height = self.driver.execute_script("return document.body.scrollHeight")
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5 * delay_multiplier)
        except Exception as e:
            logger.warning(f"Error during lazy-load scrolling: {e}")
            
        accordion_selectors = [
            ".gdlr-core-accordion-item-title",
            ".accordion-title",
            ".accordion-header",
            ".faq-title",
            "[data-toggle='collapse']",
            ".panel-title",
            "a[href^='#collapse']"
        ]
        
        tab_selectors = [
            "[role='tab']",
            "[data-toggle='tab']",
            ".gdlr-core-tab-item-title",
            ".tab-link",
            ".tab-title",
            "ul.nav-tabs li a",
            ".nav-pills a"
        ]
        
        read_load_more_selectors = [
            "a.read-more", "button.read-more", "[class*='read-more']", "[class*='readmore']",
            "a.load-more", "button.load-more", "[class*='load-more']", "[class*='loadmore']"
        ]
        
        accordions_detected = 0
        accordions_expanded = 0
        tabs_visited = 0
        hidden_sections_extracted = 0
        
        # 2. Click and switch every tab to ensure all dynamic panels render
        clicked_tabs = set()
        for selector in tab_selectors:
            try:
                elements = self.driver.find_elements("css selector", selector)
                for idx in range(len(elements)):
                    try:
                        els = self.driver.find_elements("css selector", selector)
                        if idx >= len(els):
                            break
                        el = els[idx]
                        text = el.text.strip()
                        if el.is_displayed() and text and text not in clicked_tabs:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                            time.sleep(0.15 * delay_multiplier)
                            el.click()
                            time.sleep(0.4 * delay_multiplier)
                            clicked_tabs.add(text)
                            tabs_visited += 1
                    except Exception:
                        pass
            except Exception:
                pass
                
        # 3. Recursively click collapsed accordions and dynamic panels (up to 4 levels)
        clicked_accordions = set()
        max_iterations = 4
        for iteration in range(max_iterations):
            clicked_any = False
            for selector in accordion_selectors:
                try:
                    elements = self.driver.find_elements("css selector", selector)
                    accordions_detected = max(accordions_detected, len(elements))
                    for idx in range(len(elements)):
                        try:
                            els = self.driver.find_elements("css selector", selector)
                            if idx >= len(els):
                                break
                            el = els[idx]
                            
                            # Determine if collapsed
                            aria_exp = el.get_attribute("aria-expanded")
                            parent_class = ""
                            try:
                                parent = el.find_element("xpath", "..")
                                parent_class = parent.get_attribute("class") or ""
                            except Exception:
                                pass
                                
                            is_collapsed = True
                            if aria_exp == "true":
                                is_collapsed = False
                            if any(term in parent_class.lower() for term in ["active", "gdlr-active", "show", "open"]):
                                is_collapsed = False
                                
                            if is_collapsed and el.is_displayed() and el not in clicked_accordions:
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                                time.sleep(0.15 * delay_multiplier)
                                el.click()
                                time.sleep(0.4 * delay_multiplier)
                                clicked_any = True
                                clicked_accordions.add(el)
                                accordions_expanded += 1
                        except Exception:
                            pass
                except Exception:
                    pass
            if not clicked_any:
                break
                
        # 4. Expand Read More / Load More elements
        clicked_more = set()
        for selector in read_load_more_selectors:
            try:
                elements = self.driver.find_elements("css selector", selector)
                for idx in range(len(elements)):
                    try:
                        els = self.driver.find_elements("css selector", selector)
                        if idx >= len(els):
                            break
                        el = els[idx]
                        if el.is_displayed() and el not in clicked_more:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                            time.sleep(0.15 * delay_multiplier)
                            el.click()
                            time.sleep(0.5 * delay_multiplier)
                            clicked_more.add(el)
                            hidden_sections_extracted += 1
                    except Exception:
                        pass
            except Exception:
                pass
                
        # 5. Expand general buttons containing text like "load more", "read more", "quota"
        try:
            buttons = self.driver.find_elements("css selector", "button, a, div[role='button']")
            for el in buttons:
                try:
                    text = el.text.lower()
                    if any(kw in text for kw in ["read more", "load more", "quota-specific", "department-specific"]):
                        if el.is_displayed() and el not in clicked_more and el not in clicked_accordions and el not in clicked_tabs:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                            time.sleep(0.15 * delay_multiplier)
                            el.click()
                            time.sleep(0.5 * delay_multiplier)
                            clicked_more.add(el)
                            hidden_sections_extracted += 1
                except Exception:
                    pass
        except Exception:
            pass

        # Write reports
        if url in self.page_reports:
            self.page_reports[url]["accordions_detected"] = accordions_detected
            self.page_reports[url]["accordions_expanded"] = accordions_expanded
            self.page_reports[url]["tabs_visited"] = tabs_visited
            self.page_reports[url]["hidden_sections_extracted"] = hidden_sections_extracted

    def _validate_markdown(self, markdown_content: str, html_content: str) -> Tuple[bool, str]:
        """
        Validates the quality and completeness of extracted markdown.
        Checks for:
        - Empty page
        - Heading-only content
        - Too short content
        - Missing nested/accordion details
        """
        stripped = markdown_content.strip()
        if not stripped:
            return False, "Empty page content"
            
        lines = [line.strip() for line in stripped.split("\n") if line.strip()]
        heading_lines = [line for line in lines if line.startswith("#")]
        if len(heading_lines) == len(lines):
            return False, "Page contains only headings, no body content"
            
        word_count = len(stripped.split())
        if word_count < 30:
            return False, f"Very short content ({word_count} words)"
            
        # Check if accordions are present in DOM but missing in extracted markdown body
        soup = BeautifulSoup(html_content, "lxml")
        accordion_headers = soup.select(".gdlr-core-accordion-item-title, .accordion-title, [data-toggle='collapse']")
        if accordion_headers:
            body_elements = [line for line in lines if line.startswith("-") or line.startswith("*") or (not line.startswith("#") and len(line) > 20)]
            if len(body_elements) < 3:
                return False, f"Missing nested section details (page has {len(accordion_headers)} accordions but only {len(body_elements)} content body lines)"
                
        return True, ""

    def crawl_page(self, url: str, depth: int) -> Optional[Tuple[str, Dict[str, Any], List[str]]]:
        """
        Crawls a single URL: fetches, expands interactive elements recursively,
        validates content quality, retries if invalid, and returns processed markdown.
        """
        logger.info(f"Crawling: {url} (Depth: {depth})")
        self._sleep_rate_limit()
        
        self.page_reports[url] = {
            "url": url,
            "title": "",
            "accordions_detected": 0,
            "accordions_expanded": 0,
            "tabs_visited": 0,
            "hidden_sections_extracted": 0,
            "retries": 0,
            "internal_links_count": 0,
            "word_count": 0,
            "status": "FAILED",
            "failure_reason": "",
            "manual_inspection": False
        }
        
        driver = self._init_driver()
        try:
            driver.get(url)
            time.sleep(2.0)
        except Exception as e:
            err_msg = f"Edge fetch failure: {str(e)}"
            logger.error(f"Failed to fetch {url} via Edge: {e}")
            self.failed_urls.append((url, err_msg))
            self.page_reports[url]["failure_reason"] = err_msg
            self.page_reports[url]["manual_inspection"] = True
            return None
            
        title = driver.title
        self.page_reports[url]["title"] = title
        if "404" in title or "Page Not Found" in title:
            err_msg = f"HTTP 404 (title: {title})"
            logger.warning(f"404 / Page Not Found for {url}: {title}")
            self.failed_urls.append((url, err_msg))
            self.page_reports[url]["failure_reason"] = err_msg
            self.page_reports[url]["manual_inspection"] = True
            return None

        # 3-Attempt Extraction & Expansion Loop
        best_markdown = ""
        best_stats = {}
        best_word_count = -1
        validation_reason = ""
        success = False
        
        for attempt in range(1, 4):
            if attempt > 1:
                self.page_reports[url]["retries"] += 1
                logger.info(f"Retrying element expansion for {url} (Attempt {attempt}/3)...")
                
            try:
                self._expand_interactive_elements(url, attempt)
            except Exception as e:
                logger.warning(f"Interactive element expansion failed on attempt {attempt}: {e}")
                
            # Grab source HTML
            html_content = driver.page_source
            
            try:
                markdown_content, stats = self.cleaner.clean(html_content, url)
                word_count = len(markdown_content.split())
                if word_count > best_word_count:
                    best_markdown = markdown_content
                    best_stats = stats
                    best_word_count = word_count
                    
                # Run quality validation check
                is_valid, reason = self._validate_markdown(markdown_content, html_content)
                if is_valid:
                    success = True
                    break
                else:
                    validation_reason = reason
            except Exception as e:
                validation_reason = f"Cleaning exception: {str(e)}"
                
        # If extraction could not validate successfully across 3 retries
        if not success:
            logger.warning(f"Validation failed for {url} after 3 attempts: {validation_reason}")
            # Fall back to the best attempt if it has some content, otherwise mark as failed
            if best_word_count >= 30:
                logger.info(f"Using best fallback attempt with {best_word_count} words.")
                markdown_content = best_markdown
                stats = best_stats
            else:
                err_msg = f"Quality validation failed: {validation_reason}"
                self.failed_urls.append((url, err_msg))
                self.page_reports[url]["failure_reason"] = err_msg
                self.page_reports[url]["manual_inspection"] = True
                return None

        # 1. Discover links
        try:
            html_content = driver.page_source
            soup = BeautifulSoup(html_content, "lxml")
            links = self.discover_links(soup, url)
            internal_links = [link for link in links if self._is_same_domain(self._normalize_url(link))]
            self.page_reports[url]["internal_links_count"] = len(internal_links)
        except Exception as e:
            logger.error(f"Error parsing links from {url}: {e}")
            links = []

        # 2. Finalize success report
        self.page_reports[url]["word_count"] = len(markdown_content.split())
        self.page_reports[url]["status"] = "SUCCESS"
        self.page_reports[url]["manual_inspection"] = False
        
        return markdown_content, stats, links

    def run(self) -> List[Dict[str, Any]]:
        """
        Starts the BFS crawling loop.
        """
        logger.info(f"Starting BFS crawl. Seed: {self.start_url}")
        
        seed_normalized = self._normalize_url(self.start_url)
        self.visited_urls.add(seed_normalized)
        
        pages_processed = 0
        
        try:
            while self.queue and pages_processed < self.max_pages:
                current_url, depth = self.queue.popleft()
                
                crawl_res = self.crawl_page(current_url, depth)
                if not crawl_res:
                    continue
                    
                markdown_content, stats, discovered_links = crawl_res
                category = self.get_url_category(current_url) or "general"
                
                self.crawled_urls.append(current_url)
                pages_processed += 1
                
                page_data = {
                    "url": current_url,
                    "category": category,
                    "markdown": markdown_content,
                    "stats": stats,
                    "title": self._extract_title(markdown_content) or "PES University Page"
                }
                self.extracted_pages.append(page_data)
                self.total_characters += stats["clean_char_count"]
                self.total_duplicates_removed += stats["duplicates_removed"]
                
                if depth < self.max_depth:
                    for link in discovered_links:
                        norm_link = self._normalize_url(link)
                        if norm_link not in self.visited_urls:
                            should_crawl, reason = self._should_crawl(norm_link)
                            if should_crawl:
                                self.visited_urls.add(norm_link)
                                self.queue.append((norm_link, depth + 1))
                            else:
                                self.skipped_urls.append((norm_link, reason))
        finally:
            self.close()

        logger.info(f"Crawl completed. Crawled: {len(self.crawled_urls)}, Failed: {len(self.failed_urls)}, Skipped: {len(self.skipped_urls)}")
        return self.extracted_pages

    def _extract_title(self, markdown_content: str) -> Optional[str]:
        """
        Attempts to extract a title from the first heading in the markdown content.
        """
        for line in markdown_content.split("\n"):
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return None

    def get_summary_report(self) -> Dict[str, Any]:
        """
        Returns a formatted dictionary summarizing the crawling metrics.
        """
        return {
            "pages_crawled_count": len(self.crawled_urls),
            "pages_skipped_count": len(self.skipped_urls),
            "failed_pages_count": len(self.failed_urls),
            "characters_extracted": self.total_characters,
            "duplicate_lines_removed": self.total_duplicates_removed,
            "crawled_urls": self.crawled_urls,
            "failed_urls": self.failed_urls,
            "skipped_summary": self._summarize_skipped_reasons()
        }

    def _summarize_skipped_reasons(self) -> Dict[str, int]:
        """
        Helper to count skipped reasons.
        """
        summary = {}
        for _, reason in self.skipped_urls:
            summary[reason] = summary.get(reason, 0) + 1
        return summary

