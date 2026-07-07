import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.session_store import get_redis
from app.navigation.navigation_engine import navigation_engine

logger = logging.getLogger(__name__)

# Fallback in-memory store if Redis is unavailable
_memory_store: Dict[str, Dict[str, Any]] = {}


class NavigationService:
    def __init__(self):
        self.ttl_seconds = 15 * 60  # 15 minutes
        self.ttl_seconds = 15 * 60  # 15 minutes

    def build_url(self, nav_id: str) -> str:
        base_url = settings.PUBLIC_WEB_APP_URL.rstrip('/') if settings.PUBLIC_WEB_APP_URL else "http://localhost:3000"
        return f"{base_url}/navigation/{nav_id}?t={int(time.time())}"

    async def create_session(self, metadata: Dict[str, Any]) -> str:
        """Creates a temporary navigation session and returns the navigation_id."""
        nav_id = str(uuid.uuid4().hex)[:10]  # Short ID

        # Delegate route generation to the A* Navigation Engine
        engine_payload = navigation_engine.generate_route(metadata)

        session_data = {
            "navigation_id": nav_id,
            "created_at": time.time(),
            "destination": engine_payload.get("destination", metadata.get("name", "Unknown Location")),
            "building": metadata.get("building", "Unknown Building"),
            "floor": metadata.get("floor", "0"),
            "room": metadata.get("room", ""),
            "path": engine_payload.get("path", []),
            "estimated_distance": engine_payload.get("estimated_distance", 0),
            "estimated_walk_time": engine_payload.get("estimated_walk_time", "0 min"),
            "directions": engine_payload.get("directions", []),
        }

        try:
            if settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN:
                clean_url = settings.UPSTASH_REDIS_REST_URL.strip('"').strip("'").rstrip('/')
                clean_token = settings.UPSTASH_REDIS_REST_TOKEN.strip('"').strip("'")

                url = f"{clean_url}/"
                headers = {"Authorization": f"Bearer {clean_token}"}
                payload = ["SET", f"nav:{nav_id}", json.dumps(session_data), "EX", self.ttl_seconds]
                async with httpx.AsyncClient(verify=False) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                logger.info(f"Created Navigation Session (Upstash REST): {nav_id} for destination '{session_data['destination']}'")
            else:
                redis = await get_redis()
                await redis.set(f"nav:{nav_id}", json.dumps(session_data), ex=self.ttl_seconds)
                logger.info(f"Created Navigation Session (Local Redis): {nav_id} for destination '{session_data['destination']}'")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to write to Upstash Redis: {e}")
            logger.warning(f"Redis unavailable, using memory store for navigation: {e}")
            _memory_store[nav_id] = session_data
            logger.info(f"Created Navigation Session (Memory): {nav_id} for destination '{session_data['destination']}'")

        return nav_id

    async def get_session(self, nav_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a navigation session payload by ID."""
        try:
            if settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN:
                url = f"{settings.UPSTASH_REDIS_REST_URL.rstrip('/')}/"
                headers = {"Authorization": f"Bearer {settings.UPSTASH_REDIS_REST_TOKEN}"}
                payload = ["GET", f"nav:{nav_id}"]
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("result"):
                            return json.loads(data["result"])
            else:
                redis = await get_redis()
                raw = await redis.get(f"nav:{nav_id}")
                if raw:
                    return json.loads(raw)
        except Exception as e:
            logger.warning(f"Error fetching navigation session: {e}")

        if nav_id in _memory_store:
            # Simple manual TTL check for memory store
            data = _memory_store[nav_id]
            if time.time() - data["created_at"] > self.ttl_seconds:
                del _memory_store[nav_id]
                return None
            return data

        return None


navigation_service = NavigationService()
