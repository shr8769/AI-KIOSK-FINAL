"""
RAG Route — POST /rag (Retrieval-Augmented Generation) & POST /query (Text Query Agent)
Owner: Harsha
"""

import json
import logging
import os
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class RAGRequest(BaseModel):
    session_id: str
    query: str
    context: Optional[str] = None
    domain: str = "admissions"
    language: str = "en"


class RAGResponse(BaseModel):
    session_id: str
    answer: str
    source_documents: list = []
    confidence: float = 0.85


@router.post("/rag", response_model=RAGResponse)
async def retrieve_and_generate(request: RAGRequest):
    """
    Retrieve relevant documents from knowledge base and generate answer using LLM.
    """
    return RAGResponse(
        session_id=request.session_id,
        answer="[MOCK] To apply for B.Tech at PES University, visit our admissions portal...",
        source_documents=[],
        confidence=0.85,
    )


# ── Text query endpoint ───────────────────────────────────────────────


class QueryRequest(BaseModel):
    session_id: str
    text: str
    language_hint: Optional[str] = None


class QueryResponse(BaseModel):
    type: str  # "answer" or "clarifying"
    text: str
    audio_url: Optional[str] = None
    sources: List[str] = []
    navigation: Optional[dict] = None
    language: str


@router.post("/query", response_model=QueryResponse)
async def process_text_query_endpoint(request: QueryRequest):
    """
    Process text query through the agent and return answer, sources and audio URL.
    """
    from app.services.query_pipeline import run_query_pipeline

    try:
        # Default to demo_session_id if not provided or empty
        session_id = request.session_id or "demo_session_id"
        result = await run_query_pipeline(
            session_id=session_id, text=request.text, language_hint=request.language_hint
        )
        return QueryResponse(
            type=result["type"],
            text=result["text"],
            audio_url=result["audio_url"],
            sources=result["sources"],
            navigation=result["navigation"],
            language=result["language"],
        )
    except Exception as e:
        logger.exception(f"API Error processing text query: {e}")
        return QueryResponse(
            type="error",
            text="I'm sorry, I encountered a temporary issue while processing your request. Please try again.",
            audio_url=None,
            sources=[],
            navigation=None,
            language="en",
        )


# ── FAQs aggregation endpoint ─────────────────────────────────────────


@router.get("/faqs")
async def get_all_faqs():
    """
    Dynamically retrieve and group FAQs from the local knowledge base files.
    """
    faqs = {}
    base_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "knowledge", "sources")
    )
    domains = ["admissions", "academics", "placements", "research", "student_services"]

    for domain in domains:
        faq_file = os.path.join(base_dir, domain, "faq.json")
        if os.path.exists(faq_file):
            try:
                with open(faq_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    domain_title = domain.replace("_", " ").title()
                    faqs[domain_title] = data
            except Exception as e:
                logger.error(f"Failed to load FAQ for {domain}: {e}")

    return faqs
