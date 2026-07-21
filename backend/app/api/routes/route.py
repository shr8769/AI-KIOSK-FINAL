"""
Route Classification Route — POST /route
Owner: Harsha
"""

import logging
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Instantiate the Coordinator Agent if real agents are enabled
coordinator = None
if settings.USE_REAL_AGENTS:
    try:
        from agents.coordinator.coordinator_agent import CoordinatorAgent
        coordinator = CoordinatorAgent()
        logger.info("Real Coordinator Agent loaded successfully in Routing route.")
    except Exception as e:
        logger.error(f"Failed to load real Coordinator Agent: {e}")


class RouteRequest(BaseModel):
    session_id: str
    refined_query: str
    domain: str = "admissions"
    language: str = "en"
    top_k: int = 5


class RouteResponse(BaseModel):
    session_id: str
    domain: str
    confidence: float
    context_window: Optional[str] = None
    top_k_results: List[dict] = []


@router.post("/route", response_model=RouteResponse)
async def route_to_domain(request: RouteRequest):
    """
    Route query to appropriate domain (admissions, placements, academics, etc).

    """
    if settings.USE_REAL_AGENTS and coordinator:
        try:
            logger.info(f"Routing query: '{request.refined_query}' (session: {request.session_id})")
            domain, confidence, reason, matches = coordinator.route(request.refined_query)
            if not domain:
                domain = "navigation"  # default fallback
                
            return RouteResponse(
                session_id=request.session_id,
                domain=domain,
                confidence=confidence,
                context_window=f"Routing Reason: {reason} | Matched: {', '.join(matches)}" if matches else reason,
                top_k_results=[]
            )
        except Exception as e:
            logger.error(f"Error executing real routing check: {e}")
            
    # Mock fallback
    return RouteResponse(
        session_id=request.session_id,
        domain=request.domain,
        confidence=0.92,
        context_window="[MOCK] B.Tech admissions requirement documents",
        top_k_results=[],
    )
