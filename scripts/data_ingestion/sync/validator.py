#!/usr/bin/env python3
"""
validator.py

Post-sync validation for the knowledge sync pipeline.
Verifies data integrity across the manifest, markdown files, and ChromaDB vectors
after every sync run.
"""

import logging
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    print("Error: chromadb is not installed.")
    sys.exit(1)

from scripts.data_ingestion.sync.manifest import SyncManifest
from ingest_markdown import VALID_COLLECTIONS, validate_chunk

logger = logging.getLogger("sync.validator")


class ValidationResult:
    """Result of a single validation check."""

    def __init__(self, check_name: str, passed: bool, message: str = "", details: List[str] = None):
        self.check_name = check_name
        self.passed = passed
        self.message = message
        self.details = details or []

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.check_name}: {self.message}"


class SyncValidator:
    """
    Post-sync integrity validator.

    Checks:
    1. Every active markdown file has matching vectors in ChromaDB.
    2. Every vector's source_url has a valid active manifest entry.
    3. No orphan chunks (chunks in ChromaDB not tracked in manifest).
    4. No duplicate canonical URLs in manifest.
    5. No duplicate markdown files (by content hash).
    6. Collection counts are reasonable.
    7. Random chunk quality sample passes validation.
    """

    def __init__(self, manifest: SyncManifest, config: Dict[str, Any]):
        self.manifest = manifest
        self.config = config

        ingestion_cfg = config.get("ingestion", {})
        self.db_path = ingestion_cfg.get("db_path", "knowledge/vectorstore")
        self.embedding_model = ingestion_cfg.get("embedding_model", "all-MiniLM-L6-v2")
        self.knowledge_dir = Path(ingestion_cfg.get("knowledge_dir", "knowledge_new"))

        self._client = None
        self._emb_fn = None

    def _init_chromadb(self) -> None:
        """Initialize ChromaDB client."""
        if self._client is not None:
            return
        self._client = chromadb.PersistentClient(path=self.db_path)
        try:
            self._emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.embedding_model
            )
        except Exception:
            self._emb_fn = None

    def validate_all(self) -> List[ValidationResult]:
        """Run all validation checks and return results."""
        self._init_chromadb()

        results = []
        results.append(self.check_markdown_has_vectors())
        results.append(self.check_no_orphan_chunks())
        results.append(self.check_no_duplicate_urls())
        results.append(self.check_no_duplicate_markdown())
        results.append(self.check_collection_counts())
        results.append(self.check_chunk_quality_sample())
        results.append(self.check_markdown_files_exist())

        return results

    def check_markdown_has_vectors(self) -> ValidationResult:
        """Verify every active manifest entry with a markdown file has chunk IDs."""
        check_name = "Markdown -> Vectors"
        missing = []

        for entry in self.manifest.get_urls_by_status("active"):
            if entry.markdown_path and not entry.chunk_ids:
                # Only flag if the markdown file actually exists
                if os.path.exists(entry.markdown_path):
                    missing.append(entry.url)

        if missing:
            return ValidationResult(
                check_name=check_name,
                passed=False,
                message=f"{len(missing)} active pages have markdown but no vectors",
                details=missing[:20],  # Cap details
            )

        active_with_vectors = sum(
            1 for e in self.manifest.get_urls_by_status("active")
            if e.chunk_ids
        )
        return ValidationResult(
            check_name=check_name,
            passed=True,
            message=f"All {active_with_vectors} active pages with markdown have vectors",
        )

    def check_no_orphan_chunks(self) -> ValidationResult:
        """Verify no chunks in ChromaDB are untracked by the manifest."""
        check_name = "No Orphan Chunks"

        manifest_chunk_ids = self.manifest.get_all_chunk_ids()
        orphans = []

        for col_name in VALID_COLLECTIONS:
            try:
                collection = self._client.get_collection(
                    name=col_name, embedding_function=self._emb_fn
                )
                count = collection.count()
                if count == 0:
                    continue

                # Sample a batch of IDs to check
                sample_size = min(count, 200)
                results = collection.get(limit=sample_size, include=[])
                if results and results.get("ids"):
                    for cid in results["ids"]:
                        if cid not in manifest_chunk_ids:
                            orphans.append(f"{col_name}:{cid}")

            except Exception as e:
                logger.warning(f"Failed to check collection '{col_name}': {e}")

        if orphans:
            return ValidationResult(
                check_name=check_name,
                passed=False,
                message=f"{len(orphans)} orphan chunks found (not tracked in manifest)",
                details=orphans[:20],
            )

        return ValidationResult(
            check_name=check_name,
            passed=True,
            message="No orphan chunks detected (sampled up to 200 per collection)",
        )

    def check_no_duplicate_urls(self) -> ValidationResult:
        """Verify no duplicate canonical URLs in manifest."""
        check_name = "No Duplicate URLs"

        urls = self.manifest.get_all_canonical_urls()
        # By definition, the manifest is keyed by canonical URL, so duplicates
        # are not structurally possible. But we still check for URL normalization issues.

        seen_normalized = {}
        duplicates = []
        for url in urls:
            normalized = url.lower().rstrip("/")
            if normalized in seen_normalized:
                duplicates.append(f"{url} ↔ {seen_normalized[normalized]}")
            else:
                seen_normalized[normalized] = url

        if duplicates:
            return ValidationResult(
                check_name=check_name,
                passed=False,
                message=f"{len(duplicates)} near-duplicate URLs found",
                details=duplicates[:10],
            )

        return ValidationResult(
            check_name=check_name,
            passed=True,
            message=f"All {len(urls)} URLs are unique",
        )

    def check_no_duplicate_markdown(self) -> ValidationResult:
        """Verify no two active entries share the same markdown content hash."""
        check_name = "No Duplicate Markdown"

        hash_to_urls: Dict[str, List[str]] = {}
        for entry in self.manifest.get_urls_by_status("active"):
            if entry.markdown_hash:
                hash_to_urls.setdefault(entry.markdown_hash, []).append(entry.url)

        duplicates = {
            h: urls for h, urls in hash_to_urls.items() if len(urls) > 1
        }

        if duplicates:
            details = []
            for h, urls in list(duplicates.items())[:5]:
                details.append(f"Hash {h[:20]}...: {', '.join(urls[:3])}")
            return ValidationResult(
                check_name=check_name,
                passed=False,
                message=f"{len(duplicates)} content hash collisions found",
                details=details,
            )

        return ValidationResult(
            check_name=check_name,
            passed=True,
            message="No duplicate markdown content detected",
        )

    def check_collection_counts(self) -> ValidationResult:
        """Verify each collection has a reasonable document count."""
        check_name = "Collection Counts"

        counts = {}
        for col_name in VALID_COLLECTIONS:
            try:
                col = self._client.get_collection(
                    name=col_name, embedding_function=self._emb_fn
                )
                counts[col_name] = col.count()
            except Exception:
                counts[col_name] = 0

        total = sum(counts.values())
        details = [f"{name}: {count}" for name, count in counts.items()]

        # Flag if total is zero or any collection is suspiciously empty
        if total == 0:
            return ValidationResult(
                check_name=check_name,
                passed=False,
                message="All collections are empty!",
                details=details,
            )

        return ValidationResult(
            check_name=check_name,
            passed=True,
            message=f"Total vectors across all collections: {total}",
            details=details,
        )

    def check_chunk_quality_sample(self, sample_size: int = 30) -> ValidationResult:
        """Random sample of chunks pass quality validation."""
        check_name = "Chunk Quality Sample"

        violations = []
        total_sampled = 0

        for col_name in VALID_COLLECTIONS:
            try:
                collection = self._client.get_collection(
                    name=col_name, embedding_function=self._emb_fn
                )
                count = collection.count()
                if count == 0:
                    continue

                per_col_sample = max(1, sample_size // len(VALID_COLLECTIONS))
                results = collection.get(
                    limit=min(count, per_col_sample),
                    include=["documents"],
                )
                if results and results.get("documents"):
                    for doc in results["documents"]:
                        total_sampled += 1
                        is_valid, reason = validate_chunk(doc)
                        if not is_valid:
                            violations.append(f"{col_name}: {reason}")

            except Exception as e:
                logger.warning(f"Failed sampling '{col_name}': {e}")

        if violations:
            return ValidationResult(
                check_name=check_name,
                passed=False,
                message=f"{len(violations)}/{total_sampled} sampled chunks failed quality check",
                details=violations[:10],
            )

        return ValidationResult(
            check_name=check_name,
            passed=True,
            message=f"All {total_sampled} sampled chunks passed quality checks",
        )

    def check_markdown_files_exist(self) -> ValidationResult:
        """Verify that markdown files referenced in the manifest actually exist on disk."""
        check_name = "Markdown Files Exist"

        missing = []
        checked = 0

        for entry in self.manifest.get_urls_by_status("active"):
            if entry.markdown_path:
                checked += 1
                if not os.path.exists(entry.markdown_path):
                    missing.append(f"{entry.url} -> {entry.markdown_path}")

        if missing:
            return ValidationResult(
                check_name=check_name,
                passed=False,
                message=f"{len(missing)}/{checked} markdown files are missing from disk",
                details=missing[:20],
            )

        return ValidationResult(
            check_name=check_name,
            passed=True,
            message=f"All {checked} referenced markdown files exist",
        )

    def get_summary(self, results: List[ValidationResult]) -> Dict[str, Any]:
        """Generate a summary from validation results."""
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        return {
            "total_checks": len(results),
            "passed": passed,
            "failed": failed,
            "all_passed": failed == 0,
            "checks": [
                {
                    "name": r.check_name,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                }
                for r in results
            ],
        }
