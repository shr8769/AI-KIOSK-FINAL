"""
backend/app/services/riar_service.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thin async wrapper around the RIAR pipeline.
The pipeline object itself is owned by app.core.dependencies.get_riar_pipeline().
This file contains ZERO heavy imports — it delegates entirely to dependencies.py.
"""

import logging

from app.models.schemas import RIARRequest

logger = logging.getLogger(__name__)


import asyncio

class RIARService:
    async def classify(self, request: RIARRequest):
        # Delegates to the lazily-initialized pipeline from dependencies.py
        from app.core.dependencies import (
            get_riar_pipeline,  # noqa: E402
        )

        pipeline = get_riar_pipeline()
        return await asyncio.to_thread(
            pipeline.run,
            query=request.query,
            session_history=request.session_history,
            language=request.language,
        )


riar_service = RIARService()
