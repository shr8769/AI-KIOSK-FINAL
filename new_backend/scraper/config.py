import os
import re
from typing import Dict, List

# Target URL configuration
START_URL = "https://pes.edu/"
ALLOWED_DOMAINS = ["pes.edu", "www.pes.edu"]

# Category Definitions mapping to URL path fragments / page keywords
CATEGORY_MAPPING: Dict[str, List[str]] = {
    "admissions": ["admission", "admissions", "eligibility", "fee-structure", "fees", "fee", "apply", "intake", "seat-matrix", "docs", "documents", "document", "exams", "loyalty"],
    "programs": ["programs", "courses", "undergraduate", "postgraduate", "phd", "btech", "mtech", "mba", "mca"],
    "departments": ["departments", "department", "cse", "ece", "eee", "mech", "civil", "biotech", "design", "law", "pharmacy"],
    "placements": ["placements", "placement", "recruiters", "placement-statistics", "career-guidance", "placement-cell"],
    "scholarships": ["scholarships", "scholarship", "financial-aid", "mrd-scholarship"],
    "hostels": ["hostels", "hostel", "accommodation", "residential", "housing", "boys"],
    "transportation": ["transportation", "bus-routes", "transport", "bus", "rr", "ec"],
    "student_services": ["student-services", "registrar", "office", "services", "administrative-services"],
    "campus_facilities": ["facilities", "campus", "sports", "gym", "canteen", "infrastructure", "food-court", "amenities"],
    "library": ["library", "libraries", "central-library", "e-resources"],
    "academic_calendar": ["academic-calendar", "calendar", "almanac"],
    "events": ["events", "event", "seminars", "workshops", "conferences"],
    "faqs": ["faq", "faqs", "frequently-asked-questions"],
    "campus_life": ["campus-life", "clubs", "activities", "sports", "fests", "aatmatrisha", "student-life"],
    "student_support": ["support", "counseling", "student-support", "mentoring", "grievance", "complaint"],
    "orientation": ["orientation", "induction", "first-year-orientation", "bridge-course"],
    "campus_maps": ["maps", "map", "directions", "how-to-reach", "location", "contact-us", "contact"],
    "important_dates": ["important-dates", "dates", "deadlines"]
}

# Strict IGNORE patterns (regex format)
IGNORED_PATTERNS: List[str] = [
    # Faculty and staff
    r"/faculty\b", r"/staff\b", r"/people/faculty", r"/people/staff",
    # Research and publications
    r"/research\b", r"/publications\b", r"/patents\b", r"/labs\b", r"/journals\b",
    # Recruitment/Careers for staff
    r"/recruit\b", r"/careers?\b", r"/jobs?\b", r"/work-with-us\b",
    # Internal Administration
    r"/admin(?:istration)?\b", r"/senate\b", r"/governing-body\b", r"/management\b", r"/trust\b",
    # Media & galleries
    r"/gallery\b", r"/galleries\b", r"/media\b", r"/photos\b", r"/videos\b",
    # Non-HTML files
    r"\.(pdf|jpg|jpeg|png|gif|zip|tar\.gz|docx|xlsx|pptx|mp4|avi)$"
]

# Pattern to identify news and check dates
# Older than 1 year means if current year is 2026, news before 2025 should be ignored.
NEWS_PATTERN = r"/news/(\d{4})/"

# Request Settings
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5"
}
RATE_LIMIT_DELAY = 1.0  # seconds between requests
REQUEST_TIMEOUT = 10    # seconds
MAX_DEPTH = 3           # crawling BFS depth
MAX_PAGES = 150         # safety limit for crawling in dry-run/testing

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "output", "raw")
CLEAN_DIR = os.path.join(BASE_DIR, "output", "clean")
KNOWLEDGE_NEW_DIR = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "knowledge_new")
LOG_FILE = os.path.join(BASE_DIR, "scraper.log")

# Autonomous scheduler settings
SYNC_INTERVAL_HOURS = 24
TRACKER_FILE_PATH = os.path.join(KNOWLEDGE_NEW_DIR, "crawler_tracker.json")
AUTONOMOUS_LOG_FILE = os.path.join(BASE_DIR, "autonomous_sync.log")

# Content selectors to target the page's main content wrapper in order of priority
CONTENT_SELECTORS = [
    ".gdlr-core-page-builder-body",
    ".kingster-page-builder-body",
    ".kingster-content-container",
    "#content",
    "main",
    "article",
    ".entry-content",
]

# Direct Target URLs list to scrape (student-facing pages)
TARGET_URLS = [
    # Admissions hub & sub-pages
    "https://pes.edu/admissions/",
    "https://pes.edu/docs/",
    "https://pes.edu/exams/",
    "https://pes.edu/fee/",
    "https://pes.edu/important-dates/",
    "https://pes.edu/loyalty/",
    # Programs & Departments
    "https://pes.edu/programs/",
    "https://pes.edu/departments/",
    # Placements
    "https://pes.edu/placements/",
    # Hostel hub & sub-pages
    "https://pes.edu/hostel/",
    "https://pes.edu/hostel/boys",
    # Transportation hub & sub-pages
    "https://pes.edu/transportation/",
    "https://pes.edu/transportation/rr/",
    "https://pes.edu/transportation/ec/",
    # Scholarships
    "https://pes.edu/scholarships/",
    # Academic calendar & FAQs
    "https://pes.edu/calendar/",
    "https://pes.edu/faqs/",
    # Campus Life
    "https://pes.edu/campus-life/",
    # Research
    "https://pes.edu/phd/",
]

