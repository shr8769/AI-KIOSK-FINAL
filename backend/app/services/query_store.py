from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from database.models.models import Query
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class QueryStore:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def store_query(
        self,
        session_id: str,
        user_id: Optional[str],
        query_text: str,
        refined_query: Optional[str],
        response_text: str,
        domain: Optional[str],
        language: str,
        ambiguity_type: str,
        latency_ms: int
    ) -> Query:
        """
        Inserts a processed user query and its response/metadata into the PostgreSQL database.
        """
        query_id = f"qry_{uuid.uuid4().hex[:12]}"

        db_query = Query(
            query_id=query_id,
            session_id=session_id,
            user_id=user_id,
            query_text=query_text,
            refined_query=refined_query,
            response_text=response_text,
            domain=domain,
            language=language,
            ambiguity_type=ambiguity_type,
            latency_ms=latency_ms,
            created_at=datetime.utcnow()
        )

        self.db.add(db_query)
        await self.db.commit()
        await self.db.refresh(db_query)

        logger.info(f"Query logged in Postgres: id={query_id} | session={session_id} | domain={domain}")
        return db_query
