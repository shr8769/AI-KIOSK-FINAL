#!/usr/bin/env python3
"""
sync_report.py

Generates detailed Markdown reports after every knowledge sync run.
Includes change summary, per-URL changes, validation results, and statistics.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.data_ingestion.sync.change_detector import ChangeSet
from scripts.data_ingestion.sync.validator import ValidationResult

logger = logging.getLogger("sync.report")

IST = timezone(timedelta(hours=5, minutes=30))


class SyncReportGenerator:
    """Generates comprehensive sync reports in Markdown format."""

    def __init__(self, config: Dict[str, Any], sync_run_id: str = ""):
        self.config = config
        self.sync_run_id = sync_run_id

        logging_cfg = config.get("logging", {})
        self.report_dir = Path(logging_cfg.get("report_dir", "reports/sync"))
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        change_set: ChangeSet,
        crawl_stats: Dict[str, Any],
        markdown_stats: Dict[str, int],
        embedding_stats: Dict[str, int],
        validation_results: Optional[List[ValidationResult]] = None,
        collection_counts: Optional[Dict[str, int]] = None,
        manifest_stats: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Generate a comprehensive sync report and save to disk.

        Returns the path to the generated report.
        """
        now = datetime.now(IST)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        report_filename = f"sync_{timestamp}.md"
        report_path = self.report_dir / report_filename

        lines = []
        summary = change_set.get_summary()

        # Header
        lines.append("# Knowledge Sync Report")
        lines.append("")
        lines.append(f"**Generated:** {now.strftime('%Y-%m-%d %H:%M:%S IST')}")
        lines.append(f"**Run ID:** {self.sync_run_id}")
        lines.append(f"**Duration:** {crawl_stats.get('crawl_duration_human', 'N/A')}")
        lines.append("")

        # Overall Status
        validation_passed = True
        if validation_results:
            validation_passed = all(r.passed for r in validation_results)

        status_emoji = "✅" if validation_passed else "⚠️"
        lines.append(f"## Status: {status_emoji} {'PASSED' if validation_passed else 'ISSUES DETECTED'}")
        lines.append("")

        # Change Summary
        lines.append("## Change Summary")
        lines.append("")
        lines.append("| Metric | Count |")
        lines.append("| --- | --- |")
        lines.append(f"| Pages Scanned | {summary['total_scanned']} |")
        lines.append(f"| **New Pages** | **{summary['new']}** |")
        lines.append(f"| **Updated Pages** | **{summary['modified']}** |")
        lines.append(f"| **Deleted Pages** | **{summary['deleted']}** |")
        lines.append(f"| Skipped (Unchanged) | {summary['unchanged']} |")
        lines.append(f"| Errors | {summary['errors']} |")
        lines.append(f"| **Total Changes** | **{summary['total_changes']}** |")
        lines.append("")

        # Markdown Operations
        lines.append("## Markdown Operations")
        lines.append("")
        lines.append("| Operation | Count |")
        lines.append("| --- | --- |")
        lines.append(f"| Created | {markdown_stats.get('created', 0)} |")
        lines.append(f"| Updated | {markdown_stats.get('updated', 0)} |")
        lines.append(f"| Archived | {markdown_stats.get('archived', 0)} |")
        lines.append(f"| Deleted | {markdown_stats.get('deleted', 0)} |")
        lines.append(f"| Errors | {markdown_stats.get('errors', 0)} |")
        lines.append("")

        # Embedding Operations
        lines.append("## Embedding Operations")
        lines.append("")
        lines.append("| Operation | Count |")
        lines.append("| --- | --- |")
        lines.append(f"| Chunks Created | {embedding_stats.get('chunks_created', 0)} |")
        lines.append(f"| Chunks Deleted | {embedding_stats.get('chunks_deleted', 0)} |")
        lines.append(f"| Embeddings Generated | {embedding_stats.get('embeddings_generated', 0)} |")
        lines.append(f"| URLs Processed | {embedding_stats.get('urls_processed', 0)} |")
        lines.append(f"| Errors | {embedding_stats.get('errors', 0)} |")
        lines.append("")

        # Collection Counts
        if collection_counts:
            lines.append("## ChromaDB Collection Counts")
            lines.append("")
            lines.append("| Collection | Vectors |")
            lines.append("| --- | --- |")
            total_vectors = 0
            for col_name, count in collection_counts.items():
                lines.append(f"| {col_name} | {count} |")
                total_vectors += count
            lines.append(f"| **Total** | **{total_vectors}** |")
            lines.append("")

        # Manifest Statistics
        if manifest_stats:
            lines.append("## Manifest Statistics")
            lines.append("")
            lines.append("| Metric | Value |")
            lines.append("| --- | --- |")
            lines.append(f"| Total Entries | {manifest_stats.get('total_entries', 0)} |")
            lines.append(f"| Active | {manifest_stats.get('active', 0)} |")
            lines.append(f"| Archived | {manifest_stats.get('archived', 0)} |")
            lines.append(f"| Error | {manifest_stats.get('error', 0)} |")
            lines.append(f"| Total Chunks Tracked | {manifest_stats.get('total_chunks_tracked', 0)} |")
            lines.append(f"| Total Syncs | {manifest_stats.get('total_syncs', 0)} |")
            lines.append("")

        # Detailed Changes
        if change_set.new or change_set.modified or change_set.deleted:
            lines.append("## Detailed Changes")
            lines.append("")

            if change_set.new:
                lines.append("### New Pages")
                lines.append("")
                for record in change_set.new:
                    lines.append(f"- `{record.canonical_url}` — {record.title or 'Untitled'}")
                lines.append("")

            if change_set.modified:
                lines.append("### Modified Pages")
                lines.append("")
                for record in change_set.modified:
                    lines.append(f"- `{record.canonical_url}` — {record.title or 'Untitled'}")
                lines.append("")

            if change_set.deleted:
                lines.append("### Deleted Pages")
                lines.append("")
                for record in change_set.deleted:
                    lines.append(f"- `{record.canonical_url}` — {record.title or 'Untitled'}")
                lines.append("")

        # Errors
        if change_set.errors:
            lines.append("## Errors")
            lines.append("")
            for record in change_set.errors:
                lines.append(
                    f"- `{record.canonical_url}` — {record.error_message}"
                )
            lines.append("")

        # Validation Results
        if validation_results:
            lines.append("## Validation Results")
            lines.append("")
            lines.append("| Check | Status | Message |")
            lines.append("| --- | --- | --- |")
            for result in validation_results:
                status = "✅ PASS" if result.passed else "❌ FAIL"
                lines.append(f"| {result.check_name} | {status} | {result.message} |")
            lines.append("")

            # Show details for failed checks
            failed_checks = [r for r in validation_results if not r.passed]
            if failed_checks:
                lines.append("### Validation Failures")
                lines.append("")
                for result in failed_checks:
                    lines.append(f"**{result.check_name}:** {result.message}")
                    if result.details:
                        for detail in result.details[:10]:
                            lines.append(f"  - {detail}")
                    lines.append("")

        # Crawl Statistics
        lines.append("## Crawl Statistics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        for key, value in crawl_stats.items():
            if key not in ("errors", "failed_urls", "skipped_urls", "files_created"):
                display_key = key.replace("_", " ").title()
                lines.append(f"| {display_key} | {value} |")
        lines.append("")

        # Write report
        report_content = "\n".join(lines)
        report_path.write_text(report_content, encoding="utf-8")

        logger.info(f"Sync report saved: {report_path}")
        return report_path
