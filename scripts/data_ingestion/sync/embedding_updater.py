#!/usr/bin/env python3
"""
embedding_updater.py

Incremental ChromaDB vector synchronization for the knowledge sync pipeline.
Handles targeted updates to embeddings when markdown files change,
without rebuilding the entire database.

For each change type:
  NEW     → Chunk markdown → Embed → Upsert new vectors
  MODIFIED → Delete old chunk IDs → Re-chunk → Embed → Upsert new vectors
  DELETED  → Delete all chunk IDs associated with that URL
  UNCHANGED → Skip entirely
"""

import hashlib
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import chromadb
    from chromadb.utils import embedding_functions
except ImportError:
    print("Error: chromadb is not installed. Please install it using 'pip install chromadb'")
    sys.exit(1)

from scripts.data_ingestion.sync.manifest import SyncManifest, ManifestEntry
from scripts.data_ingestion.sync.change_detector import ChangeType
from scripts.data_ingestion.sync import SYNC_SYSTEM_VERSION

logger = logging.getLogger("sync.embedding_updater")

# Import chunking utilities from existing ingestion pipeline
from ingest_markdown import (
    parse_markdown_file,
    clean_markdown_content,
    split_into_logical_blocks,
    chunk_logical_blocks,
    validate_chunk,
    get_legacy_collection,
    LEGACY_MAPPING,
    VALID_COLLECTIONS,
)


class EmbeddingUpdater:
    """
    Handles incremental ChromaDB updates.

    Only touches vectors for pages that have actually changed.
    Reuses the existing chunking and embedding logic from ingest_markdown.py.
    """

    def __init__(
        self,
        manifest: SyncManifest,
        config: Dict[str, Any],
    ):
        self.manifest = manifest
        self.config = config

        ingestion_cfg = config.get("ingestion", {})
        versioning_cfg = config.get("versioning", {})

        self.db_path = ingestion_cfg.get("db_path", "knowledge/vectorstore")
        self.embedding_model = ingestion_cfg.get("embedding_model", "all-MiniLM-L6-v2")
        self.batch_size = ingestion_cfg.get("batch_size", 100)
        self.knowledge_dir = Path(ingestion_cfg.get("knowledge_dir", "knowledge_new"))
        self.ingestion_version = versioning_cfg.get("ingestion_version", SYNC_SYSTEM_VERSION)

        # ChromaDB client and embedding function (initialized lazily)
        self._client = None
        self._emb_fn = None
        self._collections: Dict[str, Any] = {}

        # Statistics
        self.stats = {
            "chunks_created": 0,
            "chunks_deleted": 0,
            "chunks_updated": 0,
            "chunks_skipped": 0,
            "embeddings_generated": 0,
            "urls_processed": 0,
            "errors": 0,
        }

    def _init_chromadb(self) -> None:
        """Initialize ChromaDB client and embedding function."""
        if self._client is not None:
            return

        logger.info(f"Initializing ChromaDB at: {self.db_path}")
        self._client = chromadb.PersistentClient(path=self.db_path)

        logger.info(f"Loading embedding model: {self.embedding_model}")
        self._emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.embedding_model
        )

        # Pre-load all collections
        for col_name in VALID_COLLECTIONS:
            try:
                self._collections[col_name] = self._client.get_or_create_collection(
                    name=col_name,
                    embedding_function=self._emb_fn,
                )
            except Exception as e:
                logger.error(f"Failed to load collection '{col_name}': {e}")

    def process_new_page(self, canonical_url: str) -> bool:
        """
        Process a NEW page: chunk its markdown, embed, and upsert into ChromaDB.
        Updates the manifest with chunk IDs and collection name.

        Returns True on success.
        """
        self._init_chromadb()

        entry = self.manifest.get_entry(canonical_url)
        if not entry:
            logger.error(f"No manifest entry for NEW page: {canonical_url}")
            return False

        return self._ingest_markdown_for_url(canonical_url, entry)

    def process_modified_page(self, canonical_url: str) -> bool:
        """
        Process a MODIFIED page:
        1. Delete all existing chunk IDs for this URL from ChromaDB.
        2. Re-chunk the updated markdown.
        3. Embed and upsert new vectors.
        4. Update manifest with new chunk IDs.

        Returns True on success.
        """
        self._init_chromadb()

        entry = self.manifest.get_entry(canonical_url)
        if not entry:
            logger.error(f"No manifest entry for MODIFIED page: {canonical_url}")
            return False

        # Step 1: Delete old chunks
        if entry.chunk_ids:
            self._delete_chunks_from_chromadb(entry.chunk_ids, entry.collection)

        # Step 2+3+4: Re-ingest
        return self._ingest_markdown_for_url(canonical_url, entry)

    def process_deleted_page(self, canonical_url: str) -> bool:
        """
        Process a DELETED page: remove all its vectors from ChromaDB.

        Returns True on success.
        """
        self._init_chromadb()

        entry = self.manifest.get_entry(canonical_url)
        if not entry:
            logger.warning(f"No manifest entry for DELETED page: {canonical_url}")
            return True  # Nothing to delete

        if entry.chunk_ids:
            deleted = self._delete_chunks_from_chromadb(entry.chunk_ids, entry.collection)
            self.stats["chunks_deleted"] += deleted

            # Clear chunk IDs in manifest
            self.manifest.update_entry(canonical_url, chunk_ids=[])

        self.stats["urls_processed"] += 1
        logger.info(f"Vectors deleted for: {canonical_url} ({len(entry.chunk_ids)} chunks)")
        return True

    def _ingest_markdown_for_url(
        self, canonical_url: str, entry: ManifestEntry
    ) -> bool:
        """
        Core ingestion logic: read markdown, chunk, validate, embed, upsert.
        Reuses logic from ingest_markdown.py.
        """
        md_path = Path(entry.markdown_path)
        if not md_path.exists():
            logger.error(f"Markdown file not found: {md_path} for {canonical_url}")
            self.stats["errors"] += 1
            return False

        try:
            # Parse markdown
            frontmatter, content = parse_markdown_file(md_path)
            if not content.strip():
                logger.warning(f"Empty content in {md_path}")
                return False

            # Clean content
            cleaned_content = clean_markdown_content(content)
            if not cleaned_content.strip():
                logger.warning(f"No semantic content after cleaning in {md_path}")
                return False

            # Determine target collection
            parent_dir = md_path.parent.name
            category = frontmatter.get("category") or parent_dir
            target_collection = get_legacy_collection(category)

            if target_collection not in self._collections:
                logger.error(f"Collection '{target_collection}' not available")
                self.stats["errors"] += 1
                return False

            collection = self._collections[target_collection]

            # Split into logical blocks and chunk
            doc_title = frontmatter.get("title") or md_path.stem.replace("_", " ").title()
            source_url = frontmatter.get("url") or canonical_url

            ops = {"merged": 0, "split": 0, "removed": 0}
            blocks = split_into_logical_blocks(cleaned_content)
            chunks = chunk_logical_blocks(blocks, doc_title, ops)

            if not chunks:
                logger.warning(f"No valid chunks generated from {md_path}")
                return False

            # Prepare chunk data for upsert
            slug = md_path.stem
            chunk_ids = []
            chunk_docs = []
            chunk_metas = []

            for chunk_number, (heading, subheading, chunk_text) in enumerate(chunks, 1):
                # Validate chunk
                is_valid, reason = validate_chunk(chunk_text)
                if not is_valid:
                    continue

                # Generate chunk ID (same logic as ingest_markdown.py)
                heading_clean = re.sub(r'[^a-zA-Z0-9]', '', heading.lower())[:15]
                if not heading_clean:
                    heading_clean = "intro"
                heading_hash = hashlib.md5(heading.encode("utf-8")).hexdigest()[:8]
                chunk_id = f"{target_collection}_{slug}_{heading_clean}_{heading_hash}_s{chunk_number}"

                content_hash_val = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()

                metadata = {
                    "title": doc_title,
                    "heading": heading,
                    "subheading": subheading,
                    "category": category,
                    "folder": parent_dir,
                    "parent_folder": md_path.parent.parent.name,
                    "relative_path": str(md_path),
                    "slug": slug,
                    "document_name": md_path.name,
                    "source_url": source_url,
                    "chunk_number": chunk_number,
                    "total_chunks": len(chunks),
                    "word_count": len(chunk_text.split()),
                    "character_count": len(chunk_text),
                    "content_hash": content_hash_val,
                    "ingestion_timestamp": str(time.time()),
                    "ingestion_version": self.ingestion_version,
                    "sync_source": "incremental",
                }

                chunk_ids.append(chunk_id)
                chunk_docs.append(chunk_text)
                chunk_metas.append(metadata)

            if not chunk_ids:
                logger.warning(f"All chunks rejected for {md_path}")
                return False

            # Upsert into ChromaDB in batches
            total_upserted = 0
            for i in range(0, len(chunk_ids), self.batch_size):
                batch_ids = chunk_ids[i:i + self.batch_size]
                batch_docs = chunk_docs[i:i + self.batch_size]
                batch_metas = chunk_metas[i:i + self.batch_size]

                try:
                    collection.upsert(
                        ids=batch_ids,
                        documents=batch_docs,
                        metadatas=batch_metas,
                    )
                    total_upserted += len(batch_ids)
                except Exception as e:
                    logger.error(f"Upsert failed for {canonical_url}: {e}")
                    self.stats["errors"] += 1

            # Update manifest with new chunk IDs and collection
            self.manifest.update_entry(
                canonical_url,
                chunk_ids=chunk_ids,
                collection=target_collection,
                ingestion_version=self.ingestion_version,
            )

            self.stats["chunks_created"] += total_upserted
            self.stats["embeddings_generated"] += total_upserted
            self.stats["urls_processed"] += 1

            logger.info(
                f"Ingested {total_upserted} chunks into '{target_collection}' "
                f"for {canonical_url}"
            )
            return True

        except Exception as e:
            logger.error(f"Error ingesting {canonical_url}: {e}", exc_info=True)
            self.stats["errors"] += 1
            return False

    def _delete_chunks_from_chromadb(
        self, chunk_ids: List[str], collection_name: str
    ) -> int:
        """
        Delete specific chunk IDs from a ChromaDB collection.
        Returns the number of chunks deleted.
        """
        if not chunk_ids:
            return 0

        # Group chunks by collection prefix if collection_name is empty
        if not collection_name:
            # Infer collection from chunk ID prefix
            collections_to_delete: Dict[str, List[str]] = {}
            for cid in chunk_ids:
                for col in VALID_COLLECTIONS:
                    if cid.startswith(f"{col}_"):
                        collections_to_delete.setdefault(col, []).append(cid)
                        break

            total_deleted = 0
            for col_name, ids in collections_to_delete.items():
                total_deleted += self._delete_from_collection(col_name, ids)
            return total_deleted

        return self._delete_from_collection(collection_name, chunk_ids)

    def _delete_from_collection(self, collection_name: str, chunk_ids: List[str]) -> int:
        """Delete chunk IDs from a specific collection."""
        collection = self._collections.get(collection_name)
        if not collection:
            logger.warning(f"Collection '{collection_name}' not available for deletion")
            return 0

        deleted = 0
        for i in range(0, len(chunk_ids), self.batch_size):
            batch = chunk_ids[i:i + self.batch_size]
            try:
                collection.delete(ids=batch)
                deleted += len(batch)
            except Exception as e:
                logger.error(f"Delete failed in '{collection_name}': {e}")

        if deleted:
            logger.info(f"Deleted {deleted} chunks from '{collection_name}'")
        return deleted

    def get_collection_counts(self) -> Dict[str, int]:
        """Return current document counts for all collections."""
        self._init_chromadb()
        counts = {}
        for col_name in VALID_COLLECTIONS:
            try:
                col = self._client.get_collection(name=col_name)
                counts[col_name] = col.count()
            except Exception:
                counts[col_name] = 0
        return counts

    def get_stats(self) -> Dict[str, int]:
        """Return embedding update statistics."""
        return dict(self.stats)
