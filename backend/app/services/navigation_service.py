import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from app.core.session_store import get_redis

logger = logging.getLogger(__name__)

# Fallback in-memory store if Redis is unavailable
_memory_store: Dict[str, Dict[str, Any]] = {}

class NavigationService:
    def __init__(self):
        self.ttl_seconds = 15 * 60  # 15 minutes

    async def create_session(self, metadata: Dict[str, Any]) -> str:
        """Creates a temporary navigation session and returns the navigation_id."""
        nav_id = str(uuid.uuid4().hex)[:10] # Short ID

        session_data = {
            "navigation_id": nav_id,
            "created_at": time.time(),
            "destination": metadata.get("destination_name", metadata.get("name", "Unknown Location")),
            "building": metadata.get("building", "Unknown Building"),
            "floor": metadata.get("floor", "0"),
            "room": metadata.get("room", ""),
            "map_coords": metadata.get("map_coords", {"x": 0, "y": 0}),
            "directions": metadata.get("directions", [])
        }

        try:
            redis = await get_redis()
            await redis.set(
                f"nav:{nav_id}",
                json.dumps(session_data),
                ex=self.ttl_seconds
            )
            logger.info(f"Created Navigation Session (Redis): {nav_id}")
        except Exception as e:
            logger.warning(f"Redis unavailable, using memory store for navigation: {e}")
            _memory_store[nav_id] = session_data
            logger.info(f"Created Navigation Session (Memory): {nav_id}")

        return nav_id

    async def get_session(self, nav_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a navigation session payload by ID."""
        try:
            redis = await get_redis()
            raw = await redis.get(f"nav:{nav_id}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass

        if nav_id in _memory_store:
            # Simple manual TTL check for memory store
            data = _memory_store[nav_id]
            if time.time() - data["created_at"] > self.ttl_seconds:
                del _memory_store[nav_id]
                return None
            return data

        return None

navigation_service = NavigationService()
