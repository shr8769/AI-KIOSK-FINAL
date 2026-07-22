#!/usr/bin/env python3
"""
change_detector.py

Content fingerprinting and change classification for the knowledge sync pipeline.
Compares fresh crawl results against the manifest to determine what action to take
for each URL: NEW, MODIFIED, UNCHANGED, DELETED, or ERROR.
"""

import hashlib
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Set

from scripts.data_ingestion.sync.manifest import SyncManifest

logger = logging.getLogger("sync.change_detector")


class ChangeType(Enum):
    """Classification of a URL's sync status."""
    NEW = "new"                 # URL not in manifest → full crawl + ingest
    MODIFIED = "modified"       # Content hash differs → recrawl + reingest
    UNCHANGED = "unchanged"     # Content hash matches → skip
    DELETED = "deleted"         # URL in manifest but gone from site → archive + remove vectors
    ERROR = "error"             # Network/parse error → log, retry next cycle


@dataclass
class ChangeRecord:
    """Describes what changed for a single URL."""
    url: str
    canonical_url: str
    change_type: ChangeType
    old_content_hash: str = ""
    new_content_hash: str = ""
    old_http_status: int = 0
    new_http_status: int = 0
    title: str = ""
    category: str = ""
    error_message: str = ""

    def __repr__(self) -> str:
        return f"ChangeRecord({self.change_type.value}: {self.canonical_url})"


@dataclass
class ChangeSet:
    """Aggregated results of change detection across all URLs."""
    new: List[ChangeRecord] = field(default_factory=list)
    modified: List[ChangeRecord] = field(default_factory=list)
    unchanged: List[ChangeRecord] = field(default_factory=list)
    deleted: List[ChangeRecord] = field(default_factory=list)
    errors: List[ChangeRecord] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        """Count of URLs that need action (new + modified + deleted)."""
        return len(self.new) + len(self.modified) + len(self.deleted)

    @property
    def total_scanned(self) -> int:
        """Total URLs evaluated."""
        return (
            len(self.new) + len(self.modified) +
            len(self.unchanged) + len(self.deleted) + len(self.errors)
        )

    def get_actionable_urls(self) -> List[ChangeRecord]:
        """Return URLs that require crawl action (NEW or MODIFIED)."""
        return self.new + self.modified

    def get_summary(self) -> Dict[str, int]:
        """Return summary counts."""
        return {
            "new": len(self.new),
            "modified": len(self.modified),
            "unchanged": len(self.unchanged),
            "deleted": len(self.deleted),
            "errors": len(self.errors),
            "total_scanned": self.total_scanned,
            "total_changes": self.total_changes,
        }

    def __repr__(self) -> str:
        s = self.get_summary()
        return (
            f"ChangeSet(new={s['new']}, modified={s['modified']}, "
            f"unchanged={s['unchanged']}, deleted={s['deleted']}, errors={s['errors']})"
        )


def compute_content_hash(content: str, algorithm: str = "sha256") -> str:
    """
    Compute a content fingerprint from cleaned text content.

    Uses the cleaned/extracted text rather than raw HTML to avoid false
    positives from template/CSS changes that don't affect actual content.
    """
    if not content:
        return ""

    # Normalize whitespace for consistent hashing
    normalized = " ".join(content.split())
    hash_func = hashlib.new(algorithm)
    hash_func.update(normalized.encode("utf-8"))
    return f"{algorithm}:{hash_func.hexdigest()}"


class ChangeDetector:
    """
    Detects changes between fresh crawl data and the sync manifest.

    Usage:
        detector = ChangeDetector(manifest)

        # During discovery pass, classify each URL found
        detector.classify_url(url, content_hash, http_status, title, category)

        # After discovery, detect deletions
        detector.detect_deletions(discovered_urls)

        # Get the full change set
        change_set = detector.get_change_set()
    """

    def __init__(
        self,
        manifest: SyncManifest,
        hash_algorithm: str = "sha256",
        max_consecutive_errors: int = 3,
    ):
        self.manifest = manifest
        self.hash_algorithm = hash_algorithm
        self.max_consecutive_errors = max_consecutive_errors
        self._change_set = ChangeSet()
        self._classified_urls: Set[str] = set()

    def classify_url(
        self,
        canonical_url: str,
        content_hash: str,
        http_status: int = 200,
        title: str = "",
        category: str = "",
        error_message: str = "",
    ) -> ChangeType:
        """
        Classify a single URL based on its content hash vs the manifest.

        Args:
            canonical_url: The normalized URL.
            content_hash: Hash of the extracted content (use compute_content_hash()).
            http_status: HTTP response status code.
            title: Page title.
            category: Content category.
            error_message: Error message if crawl failed.

        Returns:
            The ChangeType classification.
        """
        self._classified_urls.add(canonical_url)

        # Handle error cases
        if error_message or http_status >= 400:
            record = ChangeRecord(
                url=canonical_url,
                canonical_url=canonical_url,
                change_type=ChangeType.ERROR,
                new_http_status=http_status,
                title=title,
                category=category,
                error_message=error_message or f"HTTP {http_status}",
            )
            existing = self.manifest.get_entry(canonical_url)
            if existing:
                record.old_content_hash = existing.content_hash
                record.old_http_status = existing.http_status
            self._change_set.errors.append(record)
            return ChangeType.ERROR

        existing = self.manifest.get_entry(canonical_url)

        if existing is None:
            # New URL — not in manifest at all
            record = ChangeRecord(
                url=canonical_url,
                canonical_url=canonical_url,
                change_type=ChangeType.NEW,
                new_content_hash=content_hash,
                new_http_status=http_status,
                title=title,
                category=category,
            )
            self._change_set.new.append(record)
            logger.debug(f"NEW: {canonical_url}")
            return ChangeType.NEW

        if existing.status == "archived":
            # Previously archived URL has reappeared
            record = ChangeRecord(
                url=canonical_url,
                canonical_url=canonical_url,
                change_type=ChangeType.NEW,
                old_content_hash=existing.content_hash,
                new_content_hash=content_hash,
                new_http_status=http_status,
                title=title,
                category=category,
            )
            self._change_set.new.append(record)
            logger.info(f"REAPPEARED (was archived): {canonical_url}")
            return ChangeType.NEW

        # Compare content hash
        if existing.content_hash and content_hash == existing.content_hash:
            record = ChangeRecord(
                url=canonical_url,
                canonical_url=canonical_url,
                change_type=ChangeType.UNCHANGED,
                old_content_hash=existing.content_hash,
                new_content_hash=content_hash,
                old_http_status=existing.http_status,
                new_http_status=http_status,
                title=title or existing.title,
                category=category or existing.category,
            )
            self._change_set.unchanged.append(record)
            logger.debug(f"UNCHANGED: {canonical_url}")
            return ChangeType.UNCHANGED

        # Content has changed
        record = ChangeRecord(
            url=canonical_url,
            canonical_url=canonical_url,
            change_type=ChangeType.MODIFIED,
            old_content_hash=existing.content_hash,
            new_content_hash=content_hash,
            old_http_status=existing.http_status,
            new_http_status=http_status,
            title=title,
            category=category,
        )
        self._change_set.modified.append(record)
        logger.debug(f"MODIFIED: {canonical_url}")
        return ChangeType.MODIFIED

    def detect_deletions(self, discovered_urls: Set[str]) -> List[ChangeRecord]:
        """
        Detect URLs that are in the manifest but were NOT discovered during
        the current crawl. These are candidates for deletion/archiving.

        Args:
            discovered_urls: Set of all canonical URLs found during crawl.

        Returns:
            List of ChangeRecords for deleted URLs.
        """
        deleted_records = []
        active_manifest_urls = self.manifest.get_active_urls()

        for manifest_url in active_manifest_urls:
            if manifest_url not in discovered_urls:
                entry = self.manifest.get_entry(manifest_url)
                if entry is None:
                    continue

                record = ChangeRecord(
                    url=manifest_url,
                    canonical_url=manifest_url,
                    change_type=ChangeType.DELETED,
                    old_content_hash=entry.content_hash,
                    old_http_status=entry.http_status,
                    title=entry.title,
                    category=entry.category,
                )
                self._change_set.deleted.append(record)
                deleted_records.append(record)
                logger.info(f"DELETED (not discovered): {manifest_url}")

        return deleted_records

    def get_change_set(self) -> ChangeSet:
        """Return the accumulated change set."""
        return self._change_set

    def get_classified_urls(self) -> Set[str]:
        """Return set of all URLs that have been classified."""
        return set(self._classified_urls)

    def reset(self) -> None:
        """Reset the detector for a fresh run."""
        self._change_set = ChangeSet()
        self._classified_urls.clear()
