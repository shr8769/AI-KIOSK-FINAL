"""
sync_state_manager.py

Centralised state manager for the knowledge sync pipeline.
Provides progress tracking, admin actions (approve / reject / delete),
manifest reading, analytics computation, schedule management,
and callback hooks for WebSocket broadcasting.
"""

import hashlib
import json
import logging
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("admin.sync_state")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

IST = timezone(timedelta(hours=5, minutes=30))

VALID_INTERVALS = {
    "5min": 5 * 60,
    "15min": 15 * 60,
    "1hour": 60 * 60,
    "daily": 24 * 60 * 60,
}


def _url_hash(url: str) -> str:
    """Deterministic short hash used as a URL identifier in the admin API."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class SyncProgress:
    """Mutable snapshot of a running sync's progress."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.stage: str = ""
        self.stage_number: int = 0
        self.total_stages: int = 7
        self.current_url: str = ""
        self.pages_total: int = 0
        self.pages_done: int = 0
        self.pages_failed: int = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.started_at: str = ""
        self.updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        pct = 0
        if self.pages_total > 0:
            pct = round(self.pages_done / self.pages_total * 100, 1)
        elif self.stage_number > 0:
            pct = round(self.stage_number / self.total_stages * 100, 1)

        return {
            "stage": self.stage,
            "stage_number": self.stage_number,
            "total_stages": self.total_stages,
            "current_url": self.current_url,
            "pages_total": self.pages_total,
            "pages_done": self.pages_done,
            "pages_remaining": max(0, self.pages_total - self.pages_done),
            "pages_failed": self.pages_failed,
            "progress_pct": pct,
            "errors": self.errors[-20:],
            "warnings": self.warnings[-20:],
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


class SyncStateManager:
    """
    Singleton that owns all admin-facing state for the knowledge sync system.

    Responsibilities:
    - Current sync progress tracking (for live monitor)
    - Admin actions: approve / reject / re-extract / delete / rebuild
    - Schedule management (persist chosen interval)
    - Analytics computation from manifest
    - Callback hooks for WebSocket broadcasting
    """

    _instance: Optional["SyncStateManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._admin_state_path = PROJECT_ROOT / "data" / "admin_state.json"
        self._manifest_path = PROJECT_ROOT / "sync_manifest.json"
        self._sync_config_path = PROJECT_ROOT / "sync_config.yaml"
        self._knowledge_dir = PROJECT_ROOT / "knowledge_new"

        # Live progress
        self.progress = SyncProgress()
        self.is_syncing = False
        self.last_sync_status: str = "idle"  # idle | running | success | error

        # Event callbacks (set by WebSocket handler)
        self._event_callbacks: List[Callable] = []

        # Admin state (persisted)
        self._admin_state: Dict[str, Any] = {
            "schedule_interval": "daily",
            "auto_sync_enabled": True,
            "require_approval": False,
            "page_statuses": {},  # url_hash -> "approved" | "rejected" | "pending"
        }
        self._load_admin_state()

    # ── Persistence ──────────────────────────────────────────

    def _load_admin_state(self) -> None:
        if self._admin_state_path.exists():
            try:
                with open(self._admin_state_path, "r", encoding="utf-8") as f:
                    self._admin_state.update(json.load(f))
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Could not load admin state: {e}")

    def _save_admin_state(self) -> None:
        try:
            self._admin_state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._admin_state_path, "w", encoding="utf-8") as f:
                json.dump(self._admin_state, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Failed to save admin state: {e}")

    # ── Manifest Access ──────────────────────────────────────

    def _load_manifest_raw(self) -> Dict[str, Any]:
        """Load the raw manifest JSON (read-only)."""
        if not self._manifest_path.exists():
            return {"metadata": {}, "entries": {}}
        try:
            with open(self._manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"metadata": {}, "entries": {}}

    def get_manifest_metadata(self) -> Dict[str, Any]:
        data = self._load_manifest_raw()
        return data.get("metadata", {})

    def get_all_pages(self, page: int = 1, per_page: int = 50,
                      status_filter: str = "", search: str = "") -> Dict[str, Any]:
        """Return paginated page list with admin status overlay."""
        data = self._load_manifest_raw()
        entries = data.get("entries", {})

        items = []
        for canonical_url, entry in entries.items():
            uh = _url_hash(canonical_url)
            admin_status = self._admin_state.get("page_statuses", {}).get(uh, "auto")

            if status_filter and entry.get("status") != status_filter:
                continue
            if search:
                search_lower = search.lower()
                searchable = f"{canonical_url} {entry.get('title', '')} {entry.get('category', '')}".lower()
                if search_lower not in searchable:
                    continue

            items.append({
                "url_hash": uh,
                "url": canonical_url,
                "title": entry.get("title", ""),
                "category": entry.get("category", ""),
                "collection": entry.get("collection", ""),
                "status": entry.get("status", ""),
                "admin_status": admin_status,
                "chunk_count": len(entry.get("chunk_ids", [])),
                "content_hash": entry.get("content_hash", "")[:12],
                "last_crawl_time": entry.get("last_crawl_time", ""),
                "first_seen": entry.get("first_seen", ""),
                "error_message": entry.get("error_message", ""),
                "markdown_path": entry.get("markdown_path", ""),
            })

        # Sort by last_crawl_time descending
        items.sort(key=lambda x: x.get("last_crawl_time", ""), reverse=True)

        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page

        return {
            "pages": items[start:end],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
        }

    def get_page_detail(self, url_hash: str) -> Optional[Dict[str, Any]]:
        """Return full detail for a single page by url_hash."""
        data = self._load_manifest_raw()
        entries = data.get("entries", {})

        for canonical_url, entry in entries.items():
            if _url_hash(canonical_url) == url_hash:
                admin_status = self._admin_state.get("page_statuses", {}).get(url_hash, "auto")

                # Try to read the markdown content
                markdown_content = ""
                md_path = entry.get("markdown_path", "")
                if md_path:
                    md_full = Path(md_path)
                    if not md_full.is_absolute():
                        md_full = PROJECT_ROOT / md_path
                    if md_full.exists():
                        try:
                            markdown_content = md_full.read_text(encoding="utf-8")
                        except IOError:
                            markdown_content = "[Error reading file]"

                return {
                    "url_hash": url_hash,
                    "url": canonical_url,
                    "title": entry.get("title", ""),
                    "category": entry.get("category", ""),
                    "collection": entry.get("collection", ""),
                    "status": entry.get("status", ""),
                    "admin_status": admin_status,
                    "content_hash": entry.get("content_hash", ""),
                    "markdown_hash": entry.get("markdown_hash", ""),
                    "markdown_path": md_path,
                    "markdown_content": markdown_content,
                    "chunk_ids": entry.get("chunk_ids", []),
                    "chunk_count": len(entry.get("chunk_ids", [])),
                    "http_status": entry.get("http_status", 0),
                    "last_crawl_time": entry.get("last_crawl_time", ""),
                    "last_modified": entry.get("last_modified", ""),
                    "first_seen": entry.get("first_seen", ""),
                    "crawl_count": entry.get("crawl_count", 0),
                    "error_message": entry.get("error_message", ""),
                    "scraper_version": entry.get("scraper_version", ""),
                    "ingestion_version": entry.get("ingestion_version", ""),
                }

        return None

    # ── Admin Actions ────────────────────────────────────────

    def approve_page(self, url_hash: str) -> bool:
        page_statuses = self._admin_state.setdefault("page_statuses", {})
        page_statuses[url_hash] = "approved"
        self._save_admin_state()
        return True

    def reject_page(self, url_hash: str) -> bool:
        page_statuses = self._admin_state.setdefault("page_statuses", {})
        page_statuses[url_hash] = "rejected"
        self._save_admin_state()
        return True

    def delete_page(self, url_hash: str) -> Dict[str, Any]:
        """Delete a page from manifest and its embeddings from ChromaDB."""
        data = self._load_manifest_raw()
        entries = data.get("entries", {})
        target_url = None
        target_entry = None

        for canonical_url, entry in entries.items():
            if _url_hash(canonical_url) == url_hash:
                target_url = canonical_url
                target_entry = entry
                break

        if not target_url:
            return {"success": False, "message": "Page not found"}

        # Delete from ChromaDB
        chunks_deleted = 0
        chunk_ids = target_entry.get("chunk_ids", [])
        collection_name = target_entry.get("collection", "")
        if chunk_ids and collection_name:
            try:
                import chromadb
                ingestion_cfg = self._load_ingestion_config()
                db_path = ingestion_cfg.get("db_path", "knowledge/vectorstore")
                client = chromadb.PersistentClient(path=str(PROJECT_ROOT / db_path))
                try:
                    col = client.get_collection(name=collection_name)
                    col.delete(ids=chunk_ids)
                    chunks_deleted = len(chunk_ids)
                except Exception as e:
                    logger.warning(f"Could not delete chunks: {e}")
            except ImportError:
                logger.warning("chromadb not available for chunk deletion")

        # Remove from manifest
        del entries[target_url]
        try:
            with open(self._manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            return {"success": False, "message": f"Failed to update manifest: {e}"}

        # Remove admin status
        self._admin_state.get("page_statuses", {}).pop(url_hash, None)
        self._save_admin_state()

        return {
            "success": True,
            "message": f"Deleted page and {chunks_deleted} chunks",
            "chunks_deleted": chunks_deleted,
        }

    def rebuild_embeddings(self, url_hash: str) -> Dict[str, Any]:
        """Rebuild embeddings for a single page."""
        data = self._load_manifest_raw()
        entries = data.get("entries", {})
        target_url = None

        for canonical_url, entry in entries.items():
            if _url_hash(canonical_url) == url_hash:
                target_url = canonical_url
                break

        if not target_url:
            return {"success": False, "message": "Page not found"}

        try:
            import yaml
            from scripts.data_ingestion.sync.embedding_updater import EmbeddingUpdater
            from scripts.data_ingestion.sync.manifest import SyncManifest
            sync_config = {}
            if self._sync_config_path.exists():
                with open(self._sync_config_path, "r", encoding="utf-8") as f:
                    sync_config = yaml.safe_load(f) or {}

            manifest = SyncManifest(manifest_path=str(self._manifest_path))
            manifest.load()

            updater = EmbeddingUpdater(manifest=manifest, config=sync_config)
            success = updater.process_modified_page(target_url)
            stats = updater.get_stats()

            if success:
                manifest.save()

            return {
                "success": success,
                "message": "Embeddings rebuilt" if success else "Rebuild failed",
                "chunks_created": stats.get("chunks_created", 0),
                "chunks_deleted": stats.get("chunks_deleted", 0),
            }
        except Exception as e:
            logger.error(f"Rebuild embeddings failed: {e}", exc_info=True)
            return {"success": False, "message": str(e)}

    # ── Search ───────────────────────────────────────────────

    def search_knowledge(self, query: str, field: str = "all",
                         limit: int = 50) -> List[Dict[str, Any]]:
        """Search manifest entries by field."""
        data = self._load_manifest_raw()
        entries = data.get("entries", {})
        query_lower = query.lower()
        results = []

        for canonical_url, entry in entries.items():
            matched = False
            match_field = ""

            if field in ("all", "url"):
                if query_lower in canonical_url.lower():
                    matched = True
                    match_field = "url"

            if not matched and field in ("all", "title"):
                if query_lower in entry.get("title", "").lower():
                    matched = True
                    match_field = "title"

            if not matched and field in ("all", "collection"):
                if query_lower in entry.get("collection", "").lower():
                    matched = True
                    match_field = "collection"

            if not matched and field in ("all", "chunk"):
                # Search in chunk IDs
                for cid in entry.get("chunk_ids", []):
                    if query_lower in cid.lower():
                        matched = True
                        match_field = "chunk"
                        break

            if not matched and field in ("all", "markdown"):
                md_path = entry.get("markdown_path", "")
                if md_path:
                    md_full = Path(md_path)
                    if not md_full.is_absolute():
                        md_full = PROJECT_ROOT / md_path
                    if md_full.exists():
                        try:
                            content = md_full.read_text(encoding="utf-8").lower()
                            if query_lower in content:
                                matched = True
                                match_field = "markdown"
                        except IOError:
                            pass

            if matched:
                results.append({
                    "url_hash": _url_hash(canonical_url),
                    "url": canonical_url,
                    "title": entry.get("title", ""),
                    "collection": entry.get("collection", ""),
                    "status": entry.get("status", ""),
                    "chunk_count": len(entry.get("chunk_ids", [])),
                    "match_field": match_field,
                })

            if len(results) >= limit:
                break

        return results

    # ── Chatbot Verification ─────────────────────────────────

    def verify_page_with_chatbot(self, url_hash: str, question: str) -> Dict[str, Any]:
        """Query ChromaDB restricted to chunks from a specific page."""
        detail = self.get_page_detail(url_hash)
        if not detail:
            return {"answer": "Page not found", "sources": [], "chunks_used": 0}

        chunk_ids = detail.get("chunk_ids", [])
        collection_name = detail.get("collection", "")

        if not chunk_ids or not collection_name:
            return {"answer": "No chunks available for this page", "sources": [], "chunks_used": 0}

        try:
            import chromadb
            from chromadb.utils import embedding_functions

            ingestion_cfg = self._load_ingestion_config()
            db_path = ingestion_cfg.get("db_path", "knowledge/vectorstore")
            model = ingestion_cfg.get("embedding_model", "all-MiniLM-L6-v2")

            client = chromadb.PersistentClient(path=str(PROJECT_ROOT / db_path))
            emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=model)
            col = client.get_collection(name=collection_name, embedding_function=emb_fn)

            # Query only within this page's chunks
            results = col.query(
                query_texts=[question],
                n_results=min(5, len(chunk_ids)),
                where={"source_url": detail["url"]},
            )

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            if not documents:
                return {
                    "answer": "No relevant chunks found for this question on this page.",
                    "sources": [],
                    "chunks_used": 0,
                }

            # Build context and generate answer using LLM
            context = "\n\n---\n\n".join(documents)
            answer = self._generate_verification_answer(question, context, detail.get("title", ""))

            sources = []
            for meta in metadatas:
                sources.append({
                    "heading": meta.get("heading", ""),
                    "chunk_number": meta.get("chunk_number", 0),
                    "word_count": meta.get("word_count", 0),
                })

            return {
                "answer": answer,
                "sources": sources,
                "chunks_used": len(documents),
            }

        except Exception as e:
            logger.error(f"Chatbot verification failed: {e}", exc_info=True)
            return {"answer": f"Verification error: {str(e)}", "sources": [], "chunks_used": 0}

    def _generate_verification_answer(self, question: str, context: str, title: str) -> str:
        """Generate an answer using the available LLM, restricted to provided context."""
        try:
            google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
            if google_key:
                from langchain_google_genai import ChatGoogleGenerativeAI
                llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
            else:
                from langchain_ollama import ChatOllama
                llm = ChatOllama(model="qwen3:latest")

            prompt = (
                f"You are verifying the extraction quality of the page: '{title}'.\n"
                f"Answer the following question using ONLY the provided context. "
                f"If the context does not contain the answer, say so.\n\n"
                f"Context:\n{context}\n\n"
                f"Question: {question}\n\n"
                f"Answer:"
            )
            response = llm.invoke(prompt)
            return response.content.strip()
        except Exception:
            # Fallback: return the raw context snippets
            return f"[LLM unavailable — raw context]\n\n{context[:1500]}"

    # ── Analytics ────────────────────────────────────────────

    def get_analytics(self) -> Dict[str, Any]:
        """Compute analytics from manifest data."""
        data = self._load_manifest_raw()
        metadata = data.get("metadata", {})
        entries = data.get("entries", {})

        total_pages = len(entries)
        total_chunks = 0
        total_embeddings = 0
        failed_pages = 0
        duplicate_hashes: Dict[str, int] = {}
        crawl_counts: Dict[str, int] = {}
        collections: Dict[str, int] = {}
        categories: Dict[str, int] = {}
        statuses: Dict[str, int] = {}

        for canonical_url, entry in entries.items():
            chunk_ids = entry.get("chunk_ids", [])
            total_chunks += len(chunk_ids)
            total_embeddings += len(chunk_ids)

            status = entry.get("status", "")
            statuses[status] = statuses.get(status, 0) + 1

            if status == "error":
                failed_pages += 1

            # Track duplicates by content hash
            ch = entry.get("content_hash", "")
            if ch:
                duplicate_hashes[ch] = duplicate_hashes.get(ch, 0) + 1

            # Track most frequently updated pages
            cc = entry.get("crawl_count", 0)
            if cc > 1:
                crawl_counts[canonical_url] = cc

            col = entry.get("collection", "")
            if col:
                collections[col] = collections.get(col, 0) + 1

            cat = entry.get("category", "")
            if cat:
                categories[cat] = categories.get(cat, 0) + 1

        duplicate_pages = sum(1 for v in duplicate_hashes.values() if v > 1)

        # Most frequently updated (top 10)
        most_updated = sorted(crawl_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_pages": total_pages,
            "total_chunks": total_chunks,
            "total_embeddings": total_embeddings,
            "duplicate_pages": duplicate_pages,
            "failed_pages": failed_pages,
            "statuses": statuses,
            "collections": collections,
            "categories": categories,
            "total_syncs": metadata.get("total_syncs", 0),
            "last_sync_time": metadata.get("last_sync_time", ""),
            "last_sync_run_id": metadata.get("last_sync_run_id", ""),
            "most_frequently_updated": [
                {"url": url, "crawl_count": count} for url, count in most_updated
            ],
        }

    # ── Dashboard ────────────────────────────────────────────

    def get_dashboard(self) -> Dict[str, Any]:
        """Combined dashboard data."""
        analytics = self.get_analytics()
        metadata = self.get_manifest_metadata()

        return {
            "last_sync_time": metadata.get("last_sync_time", "Never"),
            "sync_status": self.last_sync_status,
            "is_syncing": self.is_syncing,
            "total_pages": analytics["total_pages"],
            "total_chunks": analytics["total_chunks"],
            "total_embeddings": analytics["total_embeddings"],
            "failed_pages": analytics["failed_pages"],
            "duplicate_pages": analytics["duplicate_pages"],
            "total_syncs": analytics["total_syncs"],
            "statuses": analytics["statuses"],
            "collections": analytics["collections"],
            "categories": analytics["categories"],
            "schedule": {
                "interval": self._admin_state.get("schedule_interval", "daily"),
                "auto_sync_enabled": self._admin_state.get("auto_sync_enabled", True),
            },
        }

    # ── Schedule Management ──────────────────────────────────

    def get_schedule(self) -> Dict[str, Any]:
        return {
            "interval": self._admin_state.get("schedule_interval", "daily"),
            "interval_seconds": VALID_INTERVALS.get(
                self._admin_state.get("schedule_interval", "daily"), 86400
            ),
            "auto_sync_enabled": self._admin_state.get("auto_sync_enabled", True),
            "valid_intervals": list(VALID_INTERVALS.keys()),
        }

    def set_schedule(self, interval: str, auto_sync_enabled: Optional[bool] = None) -> Dict[str, Any]:
        if interval not in VALID_INTERVALS:
            return {"success": False, "message": f"Invalid interval. Choose from: {list(VALID_INTERVALS.keys())}"}

        self._admin_state["schedule_interval"] = interval
        if auto_sync_enabled is not None:
            self._admin_state["auto_sync_enabled"] = auto_sync_enabled
        self._save_admin_state()

        return {
            "success": True,
            "interval": interval,
            "interval_seconds": VALID_INTERVALS[interval],
            "auto_sync_enabled": self._admin_state.get("auto_sync_enabled", True),
        }

    def get_interval_seconds(self) -> int:
        interval = self._admin_state.get("schedule_interval", "daily")
        return VALID_INTERVALS.get(interval, 86400)

    # ── Progress Tracking ────────────────────────────────────

    def start_sync_progress(self) -> None:
        self.progress.reset()
        self.progress.started_at = datetime.now(IST).isoformat()
        self.is_syncing = True
        self.last_sync_status = "running"
        self._emit_event("sync_started", self.progress.to_dict())

    def update_progress(self, **kwargs) -> None:
        for key, val in kwargs.items():
            if hasattr(self.progress, key):
                setattr(self.progress, key, val)
        self.progress.updated_at = datetime.now(IST).isoformat()
        self._emit_event("sync_progress", self.progress.to_dict())

    def add_progress_error(self, error: str) -> None:
        self.progress.errors.append(error)
        self.progress.pages_failed += 1
        self._emit_event("sync_error", {"error": error})

    def add_progress_warning(self, warning: str) -> None:
        self.progress.warnings.append(warning)
        self._emit_event("sync_warning", {"warning": warning})

    def finish_sync_progress(self, success: bool) -> None:
        self.is_syncing = False
        self.last_sync_status = "success" if success else "error"
        self._emit_event("sync_complete", {
            "success": success,
            "progress": self.progress.to_dict(),
        })

    def get_progress(self) -> Dict[str, Any]:
        return {
            "is_syncing": self.is_syncing,
            "status": self.last_sync_status,
            **self.progress.to_dict(),
        }

    # ── Event Callbacks (for WebSocket) ──────────────────────

    def register_event_callback(self, callback: Callable) -> None:
        self._event_callbacks.append(callback)

    def unregister_event_callback(self, callback: Callable) -> None:
        self._event_callbacks = [cb for cb in self._event_callbacks if cb is not callback]

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        event = {"type": event_type, "data": data, "timestamp": datetime.now(IST).isoformat()}
        for cb in self._event_callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.warning(f"Event callback error: {e}")

    # ── Helpers ──────────────────────────────────────────────

    def _load_ingestion_config(self) -> Dict[str, Any]:
        """Load ingestion config from sync_config.yaml."""
        try:
            import yaml
            if self._sync_config_path.exists():
                with open(self._sync_config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                return config.get("ingestion", {})
        except Exception:
            pass
        return {}
