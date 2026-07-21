# PES University Web Scraper & Knowledge Base Ingest Module

A production-quality, completely independent scraping and crawler module built to transition the VidyaSahayak AI Avatar Kiosk from synthetic ChatGPT-generated documents to an authentic knowledge base built from official sources.

---

## Architecture

This module is designed to be modular and decoupled from the active backend so that it can be verified safely without affecting the production kiosk.

```
new_backend/
    scraper/
        config.py           # Allowed/ignored path settings, rate limits, directories
        cleaner.py          # HTML cleaner, tag/aside stripper, table and markdown converter
        crawler.py          # BFS crawling with link discovery and rate limit control
        utils.py            # Log configurations, slugification, frontmatter formatting
        scrape_pes.py       # Main entry point orchestrating web crawl and extra source ingestion
        requirements.txt    # Library dependencies (requests, beautifulsoup4, lxml, pyyaml)
        README.md           # This architecture and operations documentation
        external_data/      # Structured JSON files for KCET, COMEDK and rankings
        output/
            raw/            # Stores raw scraped html responses
            clean/          # Local output directory for clean Markdown and metadata
            verification_report.md  # Generated extraction and deduplication metrics
```

---

## Features

1. **Category Filtering**: Only crawls and saves content related to kiosk user concerns (Admissions, Programs, Placements, Hostels, etc.).
2. **Strict Exclusion rules**: Ignores Faculty pages, Staff Recruitment, Internal Administration, and Research directories to align with target audience personas.
3. **Advanced Cleaning**: Strips navigation, headers, footers, scripts, and CSS. Converts HTML tables into clean Markdown tables.
4. **Boilerplate and Duplicate removal**: Detects and strips repeated lines or global header/footer duplicate statements.
5. **Government Ingestion support**: Imports KCET and COMEDK guidelines, historical cutoffs, seat matrices, and admission statistics from official data sheets separately from crawled web pages.
6. **Metadata Frontmatter**: Stores `Title`, `URL`, `Category`, `Scrape Date`, and `Source` within every saved Markdown file.

---

## Quick Start

### 1. Setup Environment
Ensure your Python virtual environment is activated, then install dependencies:
```bash
pip install -r new_backend/scraper/requirements.txt
```

### 2. Run Tests
Validate the cleaner, parser, crawler, and normalization logic:
```bash
python -m unittest discover -s new_backend/scraper/tests
```

### 3. Run Ingestion (Dry Run Mode)
Run a dry run crawl to verify links and categories without writing to the final kiosk folders:
```bash
python new_backend/scraper/scrape_pes.py --limit-pages 20 --dry-run
```

### 4. Run Live Ingestion
Run a full live crawl to build the new knowledge base under `knowledge_new/`:
```bash
python new_backend/scraper/scrape_pes.py --limit-pages 150
```

---

## Verification & Audit Report
After running `scrape_pes.py`, a detailed metrics report is outputted to standard out and saved to:
`new_backend/scraper/output/verification_report.md`

This report displays:
- Number of pages successfully crawled.
- Number of pages skipped (and exact reasons, e.g., external domains, ignored patterns).
- List of any failed requests.
- Duplicate removal stats and characters extracted.
