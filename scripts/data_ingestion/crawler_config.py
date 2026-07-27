"""
crawler_config.py

Centralized configuration for the PES University recursive website crawler.
All tuneable constants live here so the crawler modules stay clean.
"""

from pathlib import Path

# ──────────────────────────────────────────────
# Project root (two levels up from this file)
# ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ──────────────────────────────────────────────
# Seed URL & Domain Rules
# ──────────────────────────────────────────────
SEED_URL = "https://pes.edu/"

# Only crawl pages whose hostname ends with one of these.
ALLOWED_DOMAINS = ["pes.edu"]

# If True, subdomains like admissions.pes.edu are also crawled.
ALLOW_SUBDOMAINS = True

# ──────────────────────────────────────────────
# Crawl Limits
# ──────────────────────────────────────────────
MAX_DEPTH = 10          # Maximum link-follow depth from the seed
MAX_PAGES = 2000        # Hard cap on pages to visit
POLITENESS_DELAY = 2.0  # Seconds between successive requests
REQUEST_TIMEOUT = 30000 # Playwright timeout per page (ms)
MAX_RETRIES = 3         # Retries per page on transient failure

# ──────────────────────────────────────────────
# Output Directories
# ──────────────────────────────────────────────
OUTPUT_DIR = PROJECT_ROOT / "knowledge_new"
DOWNLOADS_DIR = OUTPUT_DIR / "downloads"
CHECKPOINT_FILE = PROJECT_ROOT / "crawl_checkpoint.json"
CRAWL_REPORT_FILE = PROJECT_ROOT / "crawl_report.md"

# ──────────────────────────────────────────────
# URL Filtering
# ──────────────────────────────────────────────
# File extensions that are NOT HTML pages (skip crawling these as pages).
BLOCKED_EXTENSIONS = frozenset([
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".webp", ".bmp",
    ".css", ".js", ".map",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
    ".zip", ".rar", ".tar", ".gz", ".7z",
])

# Extensions that are downloadable documents (will be fetched & text-extracted).
DOCUMENT_EXTENSIONS = frozenset([
    ".pdf", ".doc", ".docx",
    ".xls", ".xlsx",
    ".ppt", ".pptx",
])

# URL path segments to skip entirely.
BLOCKED_PATHS = [
    "/wp-admin",
    "/wp-login",
    "/wp-json",
    "/xmlrpc",
    "/feed/",
    "/comments/feed/",
    "/wp-content/uploads",   # direct media files
    "/wp-includes",
    "/wp-cron",
    "/trackback",
    "/embed/",
    "?replytocom=",
    "?share=",
    "/tag/",            # WP tag archives (usually low-value)
    "/author/",         # WP author archives
]

# Query parameters to strip during URL canonicalization.
STRIP_PARAMS = frozenset([
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "share",
    "replytocom", "unapproved", "moderation-hash",
    "_ga", "_gl",
])

# ──────────────────────────────────────────────
# Playwright Selectors for Interactive Elements
# ──────────────────────────────────────────────
# CSS selectors for elements to click/expand before scraping content.
ACCORDION_SELECTORS = [
    ".gdlr-core-accordion-item-title",
    ".accordion-header",
    ".accordion-toggle",
    '[data-toggle="collapse"]',
    ".elementor-accordion-title",
    ".wp-block-details summary",
    ".toggle-title",
    ".gdlr-core-toggle-box-title",
]

TAB_SELECTORS = [
    ".gdlr-core-tab-item-title",
    ".nav-tabs .nav-link",
    ".elementor-tab-title",
    '[role="tab"]',
]

LOAD_MORE_SELECTORS = [
    ".load-more",
    ".read-more",
    "a:has-text('Read More')",
    "a:has-text('Load More')",
    "button:has-text('Read More')",
    "button:has-text('Load More')",
    "a:has-text('View More')",
    "button:has-text('Show More')",
]

FAQ_SELECTORS = [
    ".faq-question",
    ".gdlr-core-accordion-item-title",
    ".faq-title",
]

# ──────────────────────────────────────────────
# Category Routing
# ──────────────────────────────────────────────
# Maps URL path keywords to output folder names.
CATEGORY_MAP = {
    "admissions": "admissions",
    "admission": "admissions",
    "fee": "admissions",
    "fees": "admissions",
    "intake": "admissions",
    "loyalty": "admissions",
    "docs": "admissions",
    "documents-required": "admissions",
    "exams": "admissions",
    "qualifying": "admissions",
    "important-dates": "important_dates",
    "scholarships": "scholarships",
    "scholarship": "scholarships",
    "programs": "programs",
    "programme": "programs",
    "undergraduate": "programs",
    "postgraduate": "programs",
    "btech": "programs",
    "b-tech": "programs",
    "mtech": "programs",
    "m-tech": "programs",
    "mba": "programs",
    "mca": "programs",
    "phd": "programs",
    "bca": "programs",
    "bba": "programs",
    "bcom": "programs",
    "barch": "programs",
    "mbbs": "programs",
    "departments": "departments",
    "department": "departments",
    "faculty": "departments",
    "institute": "departments",
    "placements": "placements",
    "placement": "placements",
    "careers": "placements",
    "recruiters": "placements",
    "research": "research",
    "innovation": "research",
    "hostel": "hostels",
    "hostels": "hostels",
    "accommodation": "hostels",
    "transportation": "transportation",
    "transport": "transportation",
    "bus": "transportation",
    "routes": "transportation",
    "campus-life": "campus_life",
    "campus_life": "campus_life",
    "clubs": "campus_life",
    "events": "campus_life",
    "student-life": "campus_life",
    "sports": "campus_facilities",
    "infrastructure": "campus_facilities",
    "facilities": "campus_facilities",
    "library": "campus_facilities",
    "faqs": "faqs",
    "faq": "faqs",
    "contact": "contact",
    "grievance": "student_support",
    "anti-ragging": "student_support",
    "calendar": "academic_calendar",
    "academic-calendar": "academic_calendar",
    "about": "about",
    "history": "about",
    "leadership": "about",
    "governance": "about",
    "accreditation": "about",
    "rankings": "about",
    "naac": "about",
    "nirf": "about",
    "news": "news",
    "announcements": "news",
    "notifications": "news",
}

# Default category when no URL keyword matches.
DEFAULT_CATEGORY = "general"

# ──────────────────────────────────────────────
# Quality Checks
# ──────────────────────────────────────────────
MIN_WORD_COUNT = 30          # Pages with fewer words are flagged
MIN_CONTENT_LENGTH = 100     # Minimum character length for valid content
CHECKPOINT_INTERVAL = 25     # Save checkpoint every N pages

# ──────────────────────────────────────────────
# OCR Settings
# ──────────────────────────────────────────────
OCR_MIN_IMAGE_WIDTH = 200
OCR_MIN_IMAGE_HEIGHT = 200
OCR_ENABLED = True  # Set False to skip OCR entirely
