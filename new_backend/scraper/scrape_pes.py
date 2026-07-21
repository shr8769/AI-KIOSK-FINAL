import os
import json
import argparse
import time
import shutil
from typing import Dict, Any, List
from datetime import datetime
import requests

from new_backend.scraper.config import (
    RAW_DIR, CLEAN_DIR, KNOWLEDGE_NEW_DIR, START_URL, MAX_DEPTH, MAX_PAGES, TARGET_URLS
)
from new_backend.scraper.utils import setup_logging, format_frontmatter, slugify
from new_backend.scraper.crawler import PESCrawler

logger = setup_logging()

class ExternalDataIngester:
    """
    Ingests external data sources (KCET, COMEDK, Historical Ranks, Seat Matrix, Admission Statistics)
    and formats them as structured Markdown documents stored separately from PES website scraped files.
    """
    def __init__(self, data_dir: str, output_dir: str, target_dir: str, dry_run: bool = False):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.target_dir = target_dir
        self.dry_run = dry_run
        
    def _create_frontmatter(self, doc_title: str, url: str, source: str) -> str:
        meta = {
            "title": doc_title,
            "url": url,
            "category": "government_sources",
            "scrape_date": datetime.today().strftime("%Y-%m-%d"),
            "source": source
        }
        return format_frontmatter(meta)

    def ingest_kcet(self) -> int:
        file_path = os.path.join(self.data_dir, "kcet.json")
        if not os.path.exists(file_path):
            logger.warning(f"KCET source file not found at {file_path}")
            return 0
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        content = data["content"]
        md = self._create_frontmatter(data["title"], data["url"], data["source"])
        
        md += f"# {data['title']}\n\n"
        md += f"{content['introduction']}\n\n"
        
        md += "## PES University College Codes\n"
        for campus, code in content["pes_college_codes"].items():
            md += f"- **{campus}**: College Code `{code}`\n"
        md += "\n"
        
        md += "## Eligibility Criteria\n"
        for item in content["eligibility_criteria"]:
            md += f"- {item}\n"
        md += "\n"
        
        md += "## KCET Admission & Counseling Process\n"
        for step in content["counseling_process"]:
            md += f"1. {step}\n"
            
        self._write_document("kcet", md)
        return len(md)

    def ingest_comedk(self) -> int:
        file_path = os.path.join(self.data_dir, "comedk.json")
        if not os.path.exists(file_path):
            logger.warning(f"COMEDK source file not found at {file_path}")
            return 0
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        content = data["content"]
        md = self._create_frontmatter(data["title"], data["url"], data["source"])
        
        md += f"# {data['title']}\n\n"
        md += f"{content['introduction']}\n\n"
        md += f"{content['pes_admissions']}\n\n"
        
        md += "## Eligibility Criteria\n"
        for item in content["eligibility_criteria"]:
            md += f"- {item}\n"
        md += "\n"
        
        md += "## Counseling Process\n"
        for step in content["counseling_and_fees"]["process"]:
            md += f"1. {step}\n"
        md += "\n"
        
        md += "## Fees and Tuition Structure\n"
        md += f"{content['counseling_and_fees']['annual_tuition_fee']}\n"
        
        self._write_document("comedk", md)
        return len(md)

    def ingest_historical_ranks(self) -> int:
        file_path = os.path.join(self.data_dir, "historical_ranks.json")
        if not os.path.exists(file_path):
            logger.warning(f"Historical Ranks source file not found at {file_path}")
            return 0
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        content = data["content"]
        md = self._create_frontmatter(data["title"], data["url"], data["source"])
        
        md += f"# {data['title']}\n\n"
        
        md += "## KCET Cutoff Ranks (Ring Road Campus)\n"
        md += "| Branch | Opening Rank | Closing Rank |\n"
        md += "| --- | --- | --- |\n"
        for branch, cutoffs in content["ring_road_campus_kcet_cutoffs"].items():
            name = branch.replace("_", " ").title()
            md += f"| {name} | {cutoffs['opening_rank']} | {cutoffs['closing_rank']} |\n"
        md += "\n"
        
        md += "## KCET Cutoff Ranks (Electronic City Campus)\n"
        md += "| Branch | Opening Rank | Closing Rank |\n"
        md += "| --- | --- | --- |\n"
        for branch, cutoffs in content["electronic_city_campus_kcet_cutoffs"].items():
            name = branch.replace("_", " ").title()
            md += f"| {name} | {cutoffs['opening_rank']} | {cutoffs['closing_rank']} |\n"
        md += "\n"
        
        md += "## COMEDK Cutoff Ranks (Ring Road Campus)\n"
        md += "| Branch | Opening Rank | Closing Rank |\n"
        md += "| --- | --- | --- |\n"
        for branch, cutoffs in content["comedk_cutoffs_ring_road"].items():
            name = branch.replace("_", " ").title()
            md += f"| {name} | {cutoffs['opening_rank']} | {cutoffs['closing_rank']} |\n"
            
        self._write_document("historical_ranks", md)
        return len(md)

    def ingest_seat_matrix(self) -> int:
        file_path = os.path.join(self.data_dir, "seat_matrix.json")
        if not os.path.exists(file_path):
            logger.warning(f"Seat Matrix source file not found at {file_path}")
            return 0
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        content = data["content"]
        md = self._create_frontmatter(data["title"], data["url"], data["source"])
        
        md += f"# {data['title']}\n\n"
        
        md += "## Seat Allocation Quota Distribution\n"
        md += "| Quota Type | Seat Share Percentage |\n"
        md += "| --- | --- |\n"
        for quota, pct in content["total_intake_distribution"].items():
            name = quota.replace("_", " ").title()
            md += f"| {name} | {pct} |\n"
        md += "\n"
        
        md += "## Ring Road Campus Seat Intake\n"
        md += "| Course | Seat Intake Capacity |\n"
        md += "| --- | --- |\n"
        for branch, intake in content["ring_road_campus_engineering_intake"].items():
            name = branch.replace("_", " ").title()
            md += f"| {name} | {intake} |\n"
        md += "\n"
        
        md += "## Electronic City Campus Seat Intake\n"
        md += "| Course | Seat Intake Capacity |\n"
        md += "| --- | --- |\n"
        for branch, intake in content["electronic_city_campus_engineering_intake"].items():
            name = branch.replace("_", " ").title()
            md += f"| {name} | {intake} |\n"
        md += "\n"
        
        md += "## Reservation Policies\n"
        for item in content["reservation_policies"]:
            md += f"- {item}\n"
            
        self._write_document("seat_matrix", md)
        return len(md)

    def ingest_admission_statistics(self) -> int:
        file_path = os.path.join(self.data_dir, "admission_statistics.json")
        if not os.path.exists(file_path):
            logger.warning(f"Admission Statistics source file not found at {file_path}")
            return 0
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        content = data["content"]
        md = self._create_frontmatter(data["title"], data["url"], data["source"])
        
        md += f"# {data['title']}\n\n"
        
        md += f"### Enrollment Overview (Academic Year: {content['recent_enrollment_summary']['academic_year']})\n"
        md += f"- **Undergraduate Enrollment**: {content['recent_enrollment_summary']['total_undergraduate_enrollment']} students\n"
        md += f"- **Postgraduate Enrollment**: {content['recent_enrollment_summary']['total_postgraduate_enrollment']} students\n"
        md += f"- **Gender Ratio**: Male {content['recent_enrollment_summary']['gender_ratio']['male']} / Female {content['recent_enrollment_summary']['gender_ratio']['female']}\n\n"
        
        md += "## Students' Regional Distribution\n"
        for region, pct in content["regional_distribution"].items():
            name = region.replace("_", " ").title()
            md += f"- **{name}**: {pct}\n"
        md += "\n"
        
        md += "## Average Student Academic Profile\n"
        profile = content["average_academic_profile"]
        md += f"- **Average Board percentage (12th Std)**: {profile['average_board_percentage_12th']}\n"
        md += f"- **Average PESSAT Percentile (CSE)**: {profile['average_pessat_percentile_cse']}\n"
        md += f"- **Placement Success Rate**: {profile['placement_success_rate']}\n"
        
        self._write_document("admission_statistics", md)
        return len(md)

    def _write_document(self, name: str, content: str):
        """
        Helper to write the external data document.
        """
        # Save to output/clean/government_sources/name.md
        clean_subdir = os.path.join(self.output_dir, "government_sources")
        os.makedirs(clean_subdir, exist_ok=True)
        clean_file_path = os.path.join(clean_subdir, f"{name}.md")
        
        # Save to final knowledge_new/government_sources/name.md (if not dry run)
        knowledge_subdir = os.path.join(self.target_dir, "government_sources")
        
        if not self.dry_run:
            os.makedirs(knowledge_subdir, exist_ok=True)
            knowledge_file_path = os.path.join(knowledge_subdir, f"{name}.md")
            with open(knowledge_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Ingested and saved: {knowledge_file_path}")
            
        with open(clean_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved local copy: {clean_file_path}")

    def run_all(self) -> Dict[str, int]:
        """
        Runs all external data ingestions and returns character count dictionary.
        """
        results = {}
        logger.info("Starting ingestion of external/government data sources...")
        results["kcet.md"] = self.ingest_kcet()
        results["comedk.md"] = self.ingest_comedk()
        results["historical_ranks.md"] = self.ingest_historical_ranks()
        results["seat_matrix.md"] = self.ingest_seat_matrix()
        results["admission_statistics.md"] = self.ingest_admission_statistics()
        logger.info("External data sources ingestion completed.")
        return results

def main():
    parser = argparse.ArgumentParser(description="Official PES University Web Scraper and Knowledge Base Ingester")
    parser.add_argument(
        "--limit-pages",
        type=int,
        default=MAX_PAGES,
        help=f"Maximum pages to crawl in BFS mode (default: {MAX_PAGES})"
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=MAX_DEPTH,
        help=f"Maximum crawling depth in BFS mode (default: {MAX_DEPTH})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run scraping and cleaning without writing to knowledge_new/"
    )
    parser.add_argument(
        "--start-url",
        type=str,
        default=START_URL,
        help=f"Crawl seed URL in BFS mode (default: {START_URL})"
    )
    parser.add_argument(
        "--crawl-bfs",
        action="store_true",
        help="Run legacy BFS crawler with link discovery instead of target list scraping"
    )
    args = parser.parse_args()

    start_time = time.time()
    logger.info("Initializing Scraper Pipeline...")

    # Initialize Directories
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(CLEAN_DIR, exist_ok=True)
    if not args.dry_run:
        os.makedirs(KNOWLEDGE_NEW_DIR, exist_ok=True)
        logger.info(f"Target directory for new knowledge base initialized: {KNOWLEDGE_NEW_DIR}")
    else:
        logger.info("DRY RUN ACTIVE: No files will be written to knowledge_new/ folder.")

    attempted_urls = []
    successful_urls = []
    failed_urls = []
    output_files = []
    
    total_characters = 0
    total_duplicates_removed = 0
    
    # Instantiate helper elements
    from new_backend.scraper.cleaner import HTMLCleaner
    cleaner = HTMLCleaner()
    dummy_crawler = PESCrawler()  # For slugification and category lookup

    if args.crawl_bfs:
        # 1. Run BFS Crawler (Legacy/Compatibility mode)
        logger.info("Starting BFS crawl (discovery mode)...")
        crawler = PESCrawler(
            start_url=args.start_url,
            max_depth=args.depth,
            max_pages=args.limit_pages
        )
        crawled_results = crawler.run()

        logger.info("Saving crawled documents...")
        for idx, page in enumerate(crawled_results):
            attempted_urls.append(page["url"])
            successful_urls.append(page["url"])
            
            slug = slugify(page["url"])
            category = page["category"]
            markdown_content = page["markdown"]
            
            # We append metadata frontmatter
            meta = {
                "title": page["title"],
                "url": page["url"],
                "category": category,
                "scrape_date": datetime.today().strftime("%Y-%m-%d"),
                "source": "PES University Official Portal"
            }
            
            document_with_meta = format_frontmatter(meta) + markdown_content
            
            # Save flat to output/clean/<slug>.md
            clean_file_path = os.path.join(CLEAN_DIR, f"{slug}.md")
            with open(clean_file_path, "w", encoding="utf-8") as f:
                f.write(document_with_meta)
            output_files.append(clean_file_path)
                
            # If not dry run, copy to knowledge_new/<category>/<slug>.md
            if not args.dry_run:
                knowledge_cat_dir = os.path.join(KNOWLEDGE_NEW_DIR, category)
                os.makedirs(knowledge_cat_dir, exist_ok=True)
                knowledge_file_path = os.path.join(knowledge_cat_dir, f"{slug}.md")
                with open(knowledge_file_path, "w", encoding="utf-8") as f:
                    f.write(document_with_meta)

        summary = crawler.get_summary_report()
        total_characters = summary["characters_extracted"]
        total_duplicates_removed = summary["duplicate_lines_removed"]
        failed_urls = summary["failed_urls"]
        skipped_summary = summary["skipped_summary"]
    else:
        # 2. Run Direct Target list scraping (Default mode) with automatic sub-page discovery
        logger.info("Starting Target-List Scraping (Sequential mode with sub-page discovery)...")
        skipped_summary = {}
        
        # Use a queue instead of a fixed list to allow dynamic sub-page discovery
        scrape_queue = list(TARGET_URLS)
        scraped_urls = set()

        try:
            queue_idx = 0
            while queue_idx < len(scrape_queue):
                url = scrape_queue[queue_idx]
                queue_idx += 1
                
                # Skip if already processed
                norm_url = dummy_crawler._normalize_url(url)
                if norm_url in scraped_urls:
                    continue
                scraped_urls.add(norm_url)
                
                logger.info(f"Scraping target page: {url}")
                attempted_urls.append(url)

                crawl_res = dummy_crawler.crawl_page(url, 0)
                if not crawl_res:
                    continue

                markdown_content, stats, discovered_links = crawl_res
                successful_urls.append(url)
                total_characters += stats["clean_char_count"]
                total_duplicates_removed += stats["duplicates_removed"]

                # Lookup categories and generate metadata
                category = dummy_crawler.get_url_category(url) or "general"
                slug = slugify(url)
                
                # Title extraction from markdown content
                title = "PES University Page"
                for line in markdown_content.split("\n"):
                    if line.strip().startswith("# "):
                        title = line.strip()[2:].strip()
                        break

                meta = {
                    "title": title,
                    "url": url,
                    "category": category,
                    "scrape_date": datetime.today().strftime("%Y-%m-%d"),
                    "source": "PES University Official Portal"
                }
                
                document_with_meta = format_frontmatter(meta) + markdown_content

                # Save flat to output/clean/<slug>.md
                clean_file_path = os.path.join(CLEAN_DIR, f"{slug}.md")
                with open(clean_file_path, "w", encoding="utf-8") as f:
                    f.write(document_with_meta)
                output_files.append(clean_file_path)
                logger.info(f"Saved cleaned output to {clean_file_path}")

                # Save to knowledge_new/<category>/<slug>.md
                if not args.dry_run:
                    knowledge_cat_dir = os.path.join(KNOWLEDGE_NEW_DIR, category)
                    os.makedirs(knowledge_cat_dir, exist_ok=True)
                    knowledge_file_path = os.path.join(knowledge_cat_dir, f"{slug}.md")
                    with open(knowledge_file_path, "w", encoding="utf-8") as f:
                        f.write(document_with_meta)
                    logger.info(f"Ingested to new knowledge base: {knowledge_file_path}")
                
                # Automatic sub-page discovery: inspect discovered links for new pes.edu pages
                # Only discover sub-pages on the main pes.edu domain, NOT sub-domains
                # like cs.pes.edu, clubs.pes.edu, etc. which have their own site structures
                if discovered_links:
                    import urllib.parse as _urlparse
                    for link in discovered_links:
                        link_norm = dummy_crawler._normalize_url(link)
                        # Restrict to main domain only (pes.edu / www.pes.edu)
                        parsed_link = _urlparse.urlparse(link_norm)
                        if parsed_link.netloc not in ("pes.edu", "www.pes.edu"):
                            continue
                        if link_norm in scraped_urls:
                            continue
                        is_ignored, _ = dummy_crawler._check_ignored_patterns(link_norm)
                        if is_ignored:
                            continue
                        link_category = dummy_crawler.get_url_category(link_norm)
                        if link_category and link_norm not in [dummy_crawler._normalize_url(u) for u in scrape_queue]:
                            logger.info(f"Auto-discovered sub-page: {link} (category: {link_category})")
                            scrape_queue.append(link)
        finally:
            dummy_crawler.close()

        failed_urls = dummy_crawler.failed_urls
        skipped_summary = dummy_crawler._summarize_skipped_reasons()

    # 3. Run Ingestion for Extra/Government Data
    external_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "external_data")
    ingester = ExternalDataIngester(
        data_dir=external_data_dir,
        output_dir=CLEAN_DIR,
        target_dir=KNOWLEDGE_NEW_DIR,
        dry_run=args.dry_run
    )
    external_ingest_stats = ingester.run_all()

    duration = time.time() - start_time
    
    # 4. Generate Verification Report
    report_lines = []
    report_lines.append("# Knowledge Base Scraping and Ingestion Verification Report")
    report_lines.append(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Execution Duration: {duration:.2f} seconds")
    report_lines.append(f"Scraper Mode: {'BFS Crawler' if args.crawl_bfs else 'Target List Scraper'}")
    report_lines.append(f"Dry Run Mode: {args.dry_run}")
    
    report_lines.append("\n## Ingestion Summary Statistics")
    active_reports = crawler.page_reports if args.crawl_bfs else dummy_crawler.page_reports
    
    pages_containing_accordions = sum(1 for rep in active_reports.values() if rep.get("accordions_detected", 0) > 0)
    total_accordions_expanded = sum(rep.get("accordions_expanded", 0) for rep in active_reports.values())
    total_tabs_visited = sum(rep.get("tabs_visited", 0) for rep in active_reports.values())
    total_hidden_extracted = sum(rep.get("hidden_sections_extracted", 0) for rep in active_reports.values())
    total_pages_retried = sum(1 for rep in active_reports.values() if rep.get("retries", 0) > 0)
    manual_inspection_urls = [url for url, rep in active_reports.items() if rep.get("manual_inspection", False)]

    report_lines.append(f"- **Total Pages Attempted**: {len(attempted_urls)}")
    report_lines.append(f"- **Successful Pages**: {len(successful_urls)}")
    report_lines.append(f"- **Failed Pages**: {len(failed_urls)}")
    report_lines.append(f"- **Pages Containing Accordions**: {pages_containing_accordions}")
    report_lines.append(f"- **Accordions Successfully Expanded**: {total_accordions_expanded}")
    report_lines.append(f"- **Tabs Visited**: {total_tabs_visited}")
    report_lines.append(f"- **Hidden Sections Extracted (Read/Load More)**: {total_hidden_extracted}")
    report_lines.append(f"- **Pages Retried**: {total_pages_retried}")
    report_lines.append(f"- **Pages Requiring Manual Inspection**: {len(manual_inspection_urls)}")
    report_lines.append(f"- **Web Content Characters Extracted**: {total_characters}")
    report_lines.append(f"- **Duplicate Lines Removed**: {total_duplicates_removed}")
    
    report_lines.append("\n## Detailed Page Extraction Report")
    report_lines.append("| URL | Page Title | Accordions (Det/Exp) | Tabs Visited | Hidden Extracted | Retries | Status | Manual Inspection? |")
    report_lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    
    for url, rep in active_reports.items():
        title_esc = rep['title'].replace('|', '\\|') if rep['title'] else "N/A"
        req_inspect = "YES" if rep.get("manual_inspection", False) else "NO"
        report_lines.append(
            f"| {url} | {title_esc} | {rep.get('accordions_detected', 0)} / {rep.get('accordions_expanded', 0)} | "
            f"{rep.get('tabs_visited', 0)} | {rep.get('hidden_sections_extracted', 0)} | {rep.get('retries', 0)} | "
            f"{rep['status']} | {req_inspect} |"
        )
    
    report_lines.append("\n## Output Files Generated")
    for fpath in output_files:
        report_lines.append(f"- `{os.path.basename(fpath)}` ({os.path.abspath(fpath)})")
        
    report_lines.append("\n## Extra Data Ingestion Statistics")
    total_ext_chars = 0
    for name, chars in external_ingest_stats.items():
        report_lines.append(f"- **{name}**: {chars} characters ingested")
        total_ext_chars += chars
    report_lines.append(f"- **Total Government/External Characters**: {total_ext_chars}")
    
    if skipped_summary:
        report_lines.append("\n## Skipped URLs breakdown (Reasons)")
        for reason, count in skipped_summary.items():
            report_lines.append(f"- `{reason}`: {count} URLs")
            
    if manual_inspection_urls:
        report_lines.append("\n## Pages Requiring Manual Inspection")
        for url in manual_inspection_urls:
            rep = active_reports[url]
            report_lines.append(f"- **URL**: {url}  \n  **Reason**: {rep.get('failure_reason', 'Unknown failure')}")
        
    if failed_urls:
        report_lines.append("\n## Failed URLs detailed log")
        for url, err in failed_urls:
            report_lines.append(f"- **URL**: {url}  \n  **Error**: {err}")
            
    report_lines.append("\n## Successfully Processed pages list")
    for url in successful_urls:
        report_text = "\n".join(report_lines)
    
    report_text = "\n".join(report_lines)
    
    # Save verification report
    report_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "verification_report.md")
    with open(report_file_path, "w", encoding="utf-8") as f:
        f.write(report_text)
        
    # Output to stdout
    print("\n" + "="*80)
    print("                 KNOWLEDGE BASE scraping Verification REPORT")
    print("="*80)
    print(f"Status              : COMPLETED in {duration:.2f} seconds")
    print(f"Total Attempted     : {len(attempted_urls)}")
    print(f"Successful Pages    : {len(successful_urls)}")
    print(f"Failed Pages        : {len(failed_urls)}")
    print(f"Pages w/ Accordions : {pages_containing_accordions}")
    print(f"Accordions Expanded : {total_accordions_expanded}")
    print(f"Tabs Visited        : {total_tabs_visited}")
    print(f"Hidden Extracted    : {total_hidden_extracted}")
    print(f"Pages Retried       : {total_pages_retried}")
    print(f"Requires Inspection : {len(manual_inspection_urls)}")
    print(f"Characters Extracted: {total_characters} (Web) + {total_ext_chars} (Gov)")
    print(f"Duplicates Removed  : {total_duplicates_removed}")
    print("\nOutput Files Generated:")
    for fpath in output_files:
        print(f"  - {os.path.basename(fpath)}")
    print(f"\nReport File Saved   : {os.path.abspath(report_file_path)}")
    print("="*80)

if __name__ == "__main__":
    main()
