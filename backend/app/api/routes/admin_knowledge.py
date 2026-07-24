"""
Admin Knowledge API Routes — /api/v1/admin/knowledge/*

Provides REST endpoints for:
- Knowledge Inspector (paginated pages, page details)
- Human Approval (approve / reject / re-extract / delete / rebuild)
- Search (URL, title, chunk, markdown, collection)
- Chatbot Verification (restricted Q&A per page)
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.sync_state_manager import SyncStateManager

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response Models ──────────────────────────────────────────

class PageSummary(BaseModel):
    url_hash: str
    url: str
    title: str
    category: str = ""
    collection: str = ""
    status: str = ""
    admin_status: str = "auto"
    chunk_count: int = 0
    content_hash: str = ""
    last_crawl_time: str = ""
    first_seen: str = ""
    error_message: str = ""
    markdown_path: str = ""


class PagesListResponse(BaseModel):
    pages: List[PageSummary]
    total: int
    page: int
    per_page: int
    total_pages: int


class PageDetailResponse(BaseModel):
    url_hash: str
    url: str
    title: str
    category: str = ""
    collection: str = ""
    status: str = ""
    admin_status: str = "auto"
    content_hash: str = ""
    markdown_hash: str = ""
    markdown_path: str = ""
    markdown_content: str = ""
    chunk_ids: List[str] = []
    chunk_count: int = 0
    http_status: int = 0
    last_crawl_time: str = ""
    last_modified: str = ""
    first_seen: str = ""
    crawl_count: int = 0
    error_message: str = ""
    scraper_version: str = ""
    ingestion_version: str = ""


class ActionResponse(BaseModel):
    success: bool
    message: str
    chunks_created: int = 0
    chunks_deleted: int = 0


class SearchResult(BaseModel):
    url_hash: str
    url: str
    title: str
    collection: str = ""
    status: str = ""
    chunk_count: int = 0
    match_field: str = ""


class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    query: str
    field: str


class VerifyRequest(BaseModel):
    question: str


class VerifyResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    chunks_used: int = 0


# ── Knowledge Inspector Routes ───────────────────────────────

@router.get(
    "/admin/knowledge/pages",
    response_model=PagesListResponse,
    tags=["Admin Knowledge"],
)
async def list_pages(
    page: int = Query(default=1, ge=1, description="Page number"),
    per_page: int = Query(default=50, ge=1, le=200, description="Items per page"),
    status: str = Query(default="", description="Filter by status (active, archived, error)"),
    search: str = Query(default="", description="Quick search across URL, title, category"),
):
    """
    List all knowledge pages with pagination and filtering.

    Returns pages from the sync manifest with admin status overlay.
    """
    mgr = SyncStateManager()
    result = mgr.get_all_pages(page=page, per_page=per_page,
                                status_filter=status, search=search)
    return PagesListResponse(**result)


@router.get(
    "/admin/knowledge/pages/{url_hash}",
    response_model=PageDetailResponse,
    tags=["Admin Knowledge"],
)
async def get_page_detail(url_hash: str):
    """
    Get full details for a single knowledge page.

    Includes markdown content, chunk IDs, embedding count, content hash,
    extraction timestamps, and admin approval status.
    """
    mgr = SyncStateManager()
    detail = mgr.get_page_detail(url_hash)
    if not detail:
        raise HTTPException(status_code=404, detail="Page not found")
    return PageDetailResponse(**detail)


# ── Human Approval Routes ────────────────────────────────────

@router.post(
    "/admin/knowledge/pages/{url_hash}/approve",
    response_model=ActionResponse,
    tags=["Admin Knowledge"],
)
async def approve_page(url_hash: str):
    """Mark a page extraction as approved by admin."""
    mgr = SyncStateManager()
    detail = mgr.get_page_detail(url_hash)
    if not detail:
        raise HTTPException(status_code=404, detail="Page not found")

    mgr.approve_page(url_hash)
    return ActionResponse(success=True, message="Page approved")


@router.post(
    "/admin/knowledge/pages/{url_hash}/reject",
    response_model=ActionResponse,
    tags=["Admin Knowledge"],
)
async def reject_page(url_hash: str):
    """Mark a page extraction as rejected by admin."""
    mgr = SyncStateManager()
    detail = mgr.get_page_detail(url_hash)
    if not detail:
        raise HTTPException(status_code=404, detail="Page not found")

    mgr.reject_page(url_hash)
    return ActionResponse(success=True, message="Page rejected")


@router.post(
    "/admin/knowledge/pages/{url_hash}/re-extract",
    response_model=ActionResponse,
    tags=["Admin Knowledge"],
)
async def re_extract_page(url_hash: str):
    """
    Re-trigger extraction for a single page.

    This rebuilds the markdown and embeddings for the page.
    """
    mgr = SyncStateManager()
    detail = mgr.get_page_detail(url_hash)
    if not detail:
        raise HTTPException(status_code=404, detail="Page not found")

    result = mgr.rebuild_embeddings(url_hash)
    return ActionResponse(**result)


@router.delete(
    "/admin/knowledge/pages/{url_hash}",
    response_model=ActionResponse,
    tags=["Admin Knowledge"],
)
async def delete_page(url_hash: str):
    """
    Delete a page from the knowledge base.

    Removes the page from the manifest and deletes its embeddings from ChromaDB.
    """
    mgr = SyncStateManager()
    result = mgr.delete_page(url_hash)
    return ActionResponse(**result)


@router.post(
    "/admin/knowledge/pages/{url_hash}/rebuild-embeddings",
    response_model=ActionResponse,
    tags=["Admin Knowledge"],
)
async def rebuild_embeddings(url_hash: str):
    """
    Rebuild embeddings for a single page.

    Deletes existing chunks and re-generates embeddings from the markdown.
    """
    mgr = SyncStateManager()
    detail = mgr.get_page_detail(url_hash)
    if not detail:
        raise HTTPException(status_code=404, detail="Page not found")

    result = mgr.rebuild_embeddings(url_hash)
    return ActionResponse(**result)


# ── Search Route ─────────────────────────────────────────────

@router.get(
    "/admin/knowledge/search",
    response_model=SearchResponse,
    tags=["Admin Knowledge"],
)
async def search_knowledge(
    q: str = Query(..., min_length=1, description="Search query"),
    field: str = Query(
        default="all",
        description="Field to search: all, url, title, chunk, markdown, collection",
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
):
    """
    Search across knowledge base pages.

    Supports searching by URL, page title, chunk ID, markdown content,
    or collection name. Use field='all' to search everywhere.
    """
    mgr = SyncStateManager()
    results = mgr.search_knowledge(query=q, field=field, limit=limit)
    return SearchResponse(
        results=[SearchResult(**r) for r in results],
        total=len(results),
        query=q,
        field=field,
    )


# ── Chatbot Verification Route ──────────────────────────────

@router.post(
    "/admin/knowledge/pages/{url_hash}/verify",
    response_model=VerifyResponse,
    tags=["Admin Knowledge"],
)
async def verify_page(url_hash: str, request: VerifyRequest):
    """
    Ask the chatbot a question restricted to a specific page's chunks.

    This allows the admin to verify extraction quality by testing whether
    the chatbot can answer questions using only that page's embeddings.
    """
    mgr = SyncStateManager()
    detail = mgr.get_page_detail(url_hash)
    if not detail:
        raise HTTPException(status_code=404, detail="Page not found")

    result = mgr.verify_page_with_chatbot(url_hash, request.question)
    return VerifyResponse(**result)
