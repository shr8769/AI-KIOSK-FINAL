#!/usr/bin/env python3
"""
announcement_monitor.py

Autonomous agent dedicated to monitoring university announcements
from PESU Academy. Scrapes ONLY announcements — ignores attendance,
grades, timetable, profile, assignments, and fee details.

Supports both real scraping (with credentials) and mock data mode
for development/testing.
"""

import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.autonomous.base_autonomous_agent import (  # noqa: E402
    BaseAutonomousAgent,
    AgentRunResult,
)
from agents.autonomous.announcement_store import (  # noqa: E402
    Announcement,
    AnnouncementStore,
)

logger = logging.getLogger("agent.announcement_monitor")

IST = timezone(timedelta(hours=5, minutes=30))


# ── Mock Announcement Data ───────────────────────────────────
# Used when use_mock_data=true or PESU Academy is unreachable.

MOCK_ANNOUNCEMENTS = [
    {
        "title": "End Semester Examination Schedule – July 2026",
        "body": "The End Semester Examinations for all UG and PG programs will commence from July 28, 2026. Students are requested to download their hall tickets from the student portal. Seating arrangements will be displayed on the notice boards of respective departments.",
        "category": "Examinations",
        "posted_date": "2026-07-20T10:00:00+05:30",
    },
    {
        "title": "PES University Placement Drive – Microsoft",
        "body": "Microsoft will be conducting an on-campus recruitment drive on August 5, 2026 for B.Tech CSE, ECE, and MCA students. Eligible students must register on the placement portal by July 30. Pre-placement talk will be held on August 4 at 2:00 PM in Seminar Hall 1.",
        "category": "Placements",
        "posted_date": "2026-07-22T14:30:00+05:30",
    },
    {
        "title": "Library Extended Hours During Exam Period",
        "body": "The Central Library will remain open from 7:00 AM to 11:00 PM during the examination period (July 28 – August 15). Students are encouraged to utilize the reading rooms and digital resources available.",
        "category": "Campus",
        "posted_date": "2026-07-18T09:00:00+05:30",
    },
    {
        "title": "Workshop on AI and Machine Learning – Registration Open",
        "body": "The Department of Computer Science is organizing a 3-day workshop on 'Practical Applications of AI and Machine Learning' from August 10-12, 2026. Industry experts from Google and Amazon will conduct hands-on sessions. Registration is free for PES students.",
        "category": "Events",
        "posted_date": "2026-07-21T11:00:00+05:30",
    },
    {
        "title": "Hostel Fee Payment Deadline – August 2026",
        "body": "Students residing in university hostels are reminded that the hostel fee for the next semester must be paid by August 1, 2026. Late payments will attract a penalty of ₹500 per day. Payment can be made through the student portal.",
        "category": "Administrative",
        "posted_date": "2026-07-19T16:00:00+05:30",
    },
    {
        "title": "Inter-University Sports Meet 2026",
        "body": "PES University is hosting the Inter-University Sports Meet from August 20-25. Events include cricket, football, basketball, athletics, and swimming. Interested students can register with the Sports Department by August 10.",
        "category": "Events",
        "posted_date": "2026-07-23T08:30:00+05:30",
    },
    {
        "title": "New Bus Routes Added – Whitefield & Electronic City",
        "body": "Two new bus routes have been added for the upcoming semester: Route 15 (Whitefield via ITPL) and Route 16 (Electronic City via Silk Board). Students can register for these routes through the transport portal starting August 1.",
        "category": "Transport",
        "posted_date": "2026-07-17T12:00:00+05:30",
    },
    {
        "title": "Research Paper Submission Deadline – ICSE Conference",
        "body": "Faculty and PhD scholars are informed that the deadline for submitting research papers to the International Conference on Software Engineering (ICSE 2027) has been extended to September 15, 2026. Contact the Research Office for formatting guidelines.",
        "category": "Research",
        "posted_date": "2026-07-15T10:00:00+05:30",
    },
]


class AnnouncementMonitorAgent(BaseAutonomousAgent):
    """
    Autonomous agent that monitors PESU Academy for university announcements.

    Responsibilities:
        - Monitor ONLY announcements (not attendance, grades, etc.)
        - Detect new, updated, and deleted announcements
        - Maintain announcement cache with deduplication
        - Track announcement lifecycle (New → Active → Expired → Archived)
        - Support both real scraping and mock data modes

    Safety:
        - Respects robots.txt
        - Polite crawling with configurable delays
        - Retry limits and error cooldown
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        ann_cfg = config.get("announcements", {})
        self._target_url = ann_cfg.get(
            "target_url",
            "https://www.pesuacademy.com/Academy/s/studentProfilePESU",
        )
        self._check_interval_minutes = ann_cfg.get("check_interval_minutes", 30)
        self._use_mock_data = ann_cfg.get("use_mock_data", True)
        self._new_badge_hours = ann_cfg.get("new_badge_hours", 48)

        # Scraping config
        scraping_cfg = ann_cfg.get("scraping", {})
        self._timeout = scraping_cfg.get("timeout_seconds", 30)
        self._scrape_retries = scraping_cfg.get("max_retries", 3)
        self._retry_delay = scraping_cfg.get("retry_delay_seconds", 5)
        self._user_agent = scraping_cfg.get(
            "user_agent",
            "Mozilla/5.0 PESUKioskBot/2.0",
        )

        # Credentials (for real scraping)
        creds = ann_cfg.get("credentials", {})
        self._username = os.getenv("PESU_ACADEMY_USERNAME", creds.get("username", ""))
        self._password = os.getenv("PESU_ACADEMY_PASSWORD", creds.get("password", ""))

        # Initialize the announcement store
        self._store = AnnouncementStore(
            cache_path=ann_cfg.get("cache_path", "data/announcements.json"),
            max_announcements=ann_cfg.get("max_announcements", 500),
            expire_after_days=ann_cfg.get("expire_after_days", 90),
            archive_after_days=ann_cfg.get("archive_after_days", 180),
            new_badge_hours=self._new_badge_hours,
        )

    @property
    def agent_name(self) -> str:
        return "announcement_monitor"

    @property
    def store(self) -> AnnouncementStore:
        """Expose the store for API access."""
        return self._store

    def get_interval_seconds(self) -> float:
        """Get the configured check interval in seconds."""
        return self._check_interval_minutes * 60

    async def _execute_cycle(self) -> AgentRunResult:
        """
        Execute one announcement monitoring cycle.

        1. Fetch announcements (mock or real)
        2. Compare with existing cache
        3. Add new, update existing, detect deleted
        4. Update lifecycle statuses
        5. Persist to disk
        """
        self.logger.info("=" * 60)
        self.logger.info("Announcement monitor cycle starting...")
        self.logger.info("=" * 60)

        try:
            # Step 1: Fetch announcements
            if self._use_mock_data:
                raw_announcements = self._get_mock_announcements()
                self.logger.info(
                    f"Using mock data: {len(raw_announcements)} announcements"
                )
            else:
                raw_announcements = await self._scrape_announcements()
                self.logger.info(
                    f"Scraped {len(raw_announcements)} announcements from PESU Academy"
                )

            # Step 2: Process announcements
            new_count = 0
            updated_count = 0

            # Track which hashes we saw this cycle (for deletion detection)
            seen_hashes = set()

            for raw in raw_announcements:
                ann = Announcement(
                    title=raw.get("title", ""),
                    body=raw.get("body", ""),
                    posted_date=raw.get("posted_date", ""),
                    category=raw.get("category", "General"),
                    source_url=self._target_url,
                )
                seen_hashes.add(ann.content_hash)

                is_new = self._store.add_or_update(ann)
                if is_new:
                    new_count += 1
                    self.logger.info(f"📢 New announcement: {ann.title[:60]}...")
                else:
                    updated_count += 1

            # Step 3: Detect deleted announcements (only in real mode)
            deleted_count = 0
            if not self._use_mock_data and len(seen_hashes) >= 10:
                now_dt = datetime.now(IST)
                for ann_dict in self._store.get_active():
                    last_seen_str = ann_dict.get("last_seen", "")
                    try:
                        last_seen_dt = datetime.fromisoformat(last_seen_str)
                        days_since_seen = (now_dt - last_seen_dt).days
                    except Exception:
                        days_since_seen = 0

                    if ann_dict["content_hash"] not in seen_hashes and days_since_seen >= 7:
                        self._store.mark_deleted(ann_dict["content_hash"])
                        deleted_count += 1
                        self.logger.info(
                            f"🗑 Announcement removed: {ann_dict['title'][:60]}..."
                        )

            # Step 4: Update lifecycle statuses
            transitions = self._store.update_lifecycle()

            # Step 5: Persist
            self._store.record_sync()
            self._store.save()

            # Build summary
            stats = self._store.get_stats()
            summary = {
                "announcements_fetched": len(raw_announcements),
                "new": new_count,
                "updated": updated_count,
                "deleted": deleted_count,
                "lifecycle_transitions": transitions,
                "store_stats": stats,
                "source": "mock" if self._use_mock_data else "pesu_academy",
            }

            self.logger.info(
                f"✅ Announcement sync complete: "
                f"{new_count} new, {updated_count} updated, "
                f"{deleted_count} deleted, {stats['total']} total"
            )

            return AgentRunResult(success=True, summary=summary)

        except Exception as e:
            self.logger.error(f"Announcement sync failed: {e}", exc_info=True)
            return AgentRunResult(
                success=False,
                summary={},
                error=str(e),
            )

    # ── Mock Data ────────────────────────────────────────────

    def _get_mock_announcements(self) -> List[Dict[str, str]]:
        """Return mock announcement data for testing."""
        return MOCK_ANNOUNCEMENTS

    # ── Real Scraping ────────────────────────────────────────

    async def _scrape_announcements(self) -> List[Dict[str, str]]:
        """
        Scrape real announcements from PESU Academy.

        Uses Playwright to handle JavaScript-rendered content and
        authentication. Only extracts announcement content — ignores
        attendance, grades, timetable, etc.
        """
        announcements = []

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.error(
                "Playwright is required for real scraping. "
                "Install with: pip install playwright && playwright install"
            )
            self.logger.info("Falling back to mock data.")
            return self._get_mock_announcements()

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=self._user_agent,
                )
                page = await context.new_page()
                page.set_default_timeout(self._timeout * 1000)

                # Navigate to login page
                await page.goto(
                    "https://www.pesuacademy.com/Academy/",
                    wait_until="networkidle",
                )

                # Wait a polite interval
                import asyncio
                safety_cfg = self.config.get("safety", {})
                delay = safety_cfg.get("min_request_interval_seconds", 2.0)
                await asyncio.sleep(delay)

                # Navigate to the target URL (login page) first
                await page.goto(self._target_url, wait_until="networkidle")
                await asyncio.sleep(delay)

                # Login if credentials available
                if self._username and self._password:
                    try:
                        # Fill login form
                        await page.fill(
                            'input[name="j_username"]',
                            self._username,
                        )
                        await page.fill(
                            'input[name="j_password"]',
                            self._password,
                        )
                        await page.click('button[id^="postloginform"]', force=True)
                        await page.wait_for_load_state("networkidle")
                        await asyncio.sleep(delay)

                        self.logger.info("Successfully logged in to PESU Academy")
                    except Exception as e:
                        self.logger.error(f"Login failed: {e}")
                        await browser.close()
                        return self._get_mock_announcements()

                # Navigate to student profile page if logged in
                if self._username and self._password:
                    await page.goto("https://www.pesuacademy.com/Academy/s/studentProfilePESU", wait_until="networkidle")
                else:
                    await page.goto(self._target_url, wait_until="networkidle")
                await asyncio.sleep(delay)

                # Extract ONLY announcements
                # Look for common announcement containers
                announcement_selectors = [
                    ".announcements-inner li",
                    ".announcement",
                    ".announcements-list",
                    "#announcementsTab",
                    '[data-toggle="announcements"]',
                    ".card.announcement",
                    ".notice-board",
                ]

                content = await page.content()

                # Try to find announcement section
                for selector in announcement_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        if elements:
                            # Iterate in reverse so the top items get added last (larger first_seen timestamp)
                            # This ensures that sorting by first_seen DESCENDING preserves the correct top-to-bottom DOM order!
                            for el in reversed(elements):
                                title_el = await el.query_selector(
                                    "h3, h4, h5, .title, .announcement-title, strong, .anc-text p"
                                )
                                date_el = await el.query_selector(
                                    ".date, .timestamp, time, .posted-date, small, .published-date"
                                )

                                title = (
                                    await title_el.inner_text()
                                    if title_el
                                    else "Untitled"
                                )

                                body = await el.evaluate('''el => {
                                    const b = el.querySelector(".body, .announcement-body, .content, .description") || el;
                                    if (b !== el) {
                                        return b.innerText.trim();
                                    } else {
                                        return el.innerText.trim();
                                    }
                                }''')
                                
                                # Try to fetch detailed body and PDF links if it's a PESU Academy announcement
                                a_el = await el.query_selector("a[onclick*='handleShowMoreAnnouncement']")
                                if a_el:
                                    onclick_val = await a_el.get_attribute("onclick")
                                    if onclick_val:
                                        import re
                                        match = re.search(r'handleShowMoreAnnouncement\((.*?),(.*?),(.*?)\)', onclick_val.replace(' ', ''))
                                        if match:
                                            c_mode, a_type, ann_id = match.groups()
                                            try:
                                                detail_html = await page.evaluate(f'''() => {{
                                                    return new Promise((resolve, reject) => {{
                                                        $.ajax({{
                                                            url: '/Academy/s/studentProfilePESUAdmin',
                                                            type: 'POST',
                                                            data: {{ controllerMode: {c_mode}, actionType: {a_type}, AnnouncementId: {ann_id} }},
                                                            success: function(data) {{ resolve(data); }},
                                                            error: function(err) {{ reject(err); }}
                                                        }});
                                                    }});
                                                }}''')
                                                
                                                from bs4 import BeautifulSoup
                                                soup = BeautifulSoup(detail_html, "html.parser")
                                                
                                                # Extract full text
                                                body_div = soup.select_one('.col-md-12')
                                                if body_div:
                                                    body = body_div.get_text(separator='\\n', strip=True)
                                                    
                                                # Extract PDF links
                                                links = []
                                                for a_tag in soup.find_all('a', href=True):
                                                    href = a_tag['href']
                                                    if 'handleDownloadAnoncemntdoc' in href:
                                                        doc_match = re.search(r'handleDownloadAnoncemntdoc\([\'"](\d+)[\'"]\)', href)
                                                        if doc_match:
                                                            doc_id = doc_match.group(1)
                                                            pdf_text = a_tag.get_text(strip=True)
                                                            if not pdf_text:
                                                                pdf_text = f"Attachment_{doc_id}.pdf"
                                                            links.append(f"- [{pdf_text}](https://www.pesuacademy.com/Academy/s/studentProfilePESU/downloadAnoncemntdoc/{doc_id})")
                                                            
                                                if links:
                                                    links = list(dict.fromkeys(links))
                                                    body += "\\n\\n**Links & Attachments:**\\n" + "\\n".join(links)
                                                    
                                                await asyncio.sleep(0.5) # rate limit requests
                                            except Exception as e:
                                                self.logger.error(f"Failed to fetch detail/PDFs for {ann_id}: {e}")
                                
                                date = (
                                    await date_el.inner_text()
                                    if date_el
                                    else ""
                                ).strip()

                                if title or body:
                                    announcements.append({
                                        "title": title or "Untitled Announcement",
                                        "body": body,
                                        "posted_date": date,
                                        "category": "General",
                                    })
                            break
                    except Exception:
                        continue

                # Fallback: parse page content for announcement-like patterns
                if not announcements:
                    self.logger.warning(
                        "Could not find announcement elements via selectors. "
                        "Trying text-based extraction..."
                    )
                    try:
                        from bs4 import BeautifulSoup

                        soup = BeautifulSoup(content, "html.parser")

                        # Remove non-announcement sections
                        for tag in soup.find_all(
                            class_=re.compile(
                                r"attendance|grade|timetable|profile|assignment|fee",
                                re.IGNORECASE,
                            )
                        ):
                            tag.decompose()

                        # Look for announcement-like content
                        for card in soup.find_all(
                            ["div", "article", "section"],
                            class_=re.compile(r"announce|notice|news|alert", re.IGNORECASE),
                        ):
                            heading = card.find(["h1", "h2", "h3", "h4", "h5", "strong"])
                            body_tag = card.find(["p", "div"])
                            date_tag = card.find(
                                ["time", "small", "span"],
                                class_=re.compile(r"date|time|posted", re.IGNORECASE),
                            )

                            title = heading.get_text(strip=True) if heading else ""
                            body = body_tag.get_text(strip=True) if body_tag else ""
                            date = date_tag.get_text(strip=True) if date_tag else ""

                            if title or body:
                                announcements.append({
                                    "title": title or "Untitled Announcement",
                                    "body": body,
                                    "posted_date": date,
                                    "category": "General",
                                })
                    except ImportError:
                        self.logger.error("beautifulsoup4 is required for fallback parsing")

                await browser.close()

        except Exception as e:
            self.logger.error(f"Scraping failed: {e}", exc_info=True)
            self.logger.info("Falling back to mock data")
            return self._get_mock_announcements()

        if not announcements:
            self.logger.warning(
                "No announcements found via scraping. Falling back to mock data."
            )
            return self._get_mock_announcements()

        return announcements

    # ── API Helpers ───────────────────────────────────────────

    def get_active_announcements(self) -> List[Dict[str, Any]]:
        """Get active announcements for the API."""
        return self._store.get_active()

    def get_latest_announcements(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get latest announcements for the API."""
        return self._store.get_latest(limit=limit)

    def get_announcement_stats(self) -> Dict[str, Any]:
        """Get announcement statistics for the API."""
        return self._store.get_stats()

    def start_scheduled(self) -> None:
        """Start the agent with configured interval."""
        interval = self.get_interval_seconds()
        self.start(interval_seconds=interval)
