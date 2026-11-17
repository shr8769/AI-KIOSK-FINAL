import json
import logging
import os
import pathlib
import time
import uuid
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.session_store import get_redis
from app.navigation.navigation_engine import navigation_engine

logger = logging.getLogger(__name__)

# Persistent disk-backed store for navigation sessions
_DATA_DIR = pathlib.Path(__file__).resolve().parents[3] / "data"
_SESSIONS_FILE = _DATA_DIR / "navigation_sessions.json"

def _load_disk_store() -> Dict[str, Dict[str, Any]]:
    try:
        if _SESSIONS_FILE.exists():
            return json.loads(_SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _save_disk_store(store: Dict[str, Dict[str, Any]]):
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        now = time.time()
        active = {k: v for k, v in store.items() if (now - v.get("created_at", 0)) < 1800}
        _SESSIONS_FILE.write_text(json.dumps(active, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not persist navigation sessions: {e}")

_memory_store: Dict[str, Dict[str, Any]] = _load_disk_store()


class NavigationService:
    def __init__(self):
        self.ttl_seconds = 15 * 60  # 15 minutes
        self.ttl_seconds = 15 * 60  # 15 minutes

    def _get_tunnel_url(self) -> str:
        """Get live ngrok public URL from local ngrok API or tunnel.json."""
        # 1. Check local ngrok client API (instant, 100% accurate live public URL)
        try:
            import httpx as _httpx
            resp = _httpx.get("http://127.0.0.1:4040/api/tunnels", timeout=0.3)
            if resp.status_code == 200:
                tunnels = resp.json().get("tunnels", [])
                for t in tunnels:
                    p_url = t.get("public_url", "")
                    if p_url and p_url.startswith("https://"):
                        return p_url.rstrip("/")
        except Exception:
            pass

        # 2. Check tunnel.json file fallback
        import pathlib
        try:
            tunnel_path = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "public" / "tunnel.json"
            if tunnel_path.exists():
                import json as _json
                data = _json.loads(tunnel_path.read_text(encoding="utf-8"))
                url = data.get("publicUrl", "").strip().rstrip("/")
                if url and url.startswith("http"):
                    return url
        except Exception:
            pass
        return ""

    def build_url(self, nav_id: str) -> str:
        """
        Build the QR-code URL for a navigation session.
        Priority:
          1. PUBLIC_WEB_APP_URL (Vercel cloud — requires maps deployed there)
          2. Live ngrok tunnel URL from tunnel.json (works anywhere, maps served locally)
          3. PUBLIC_BASE_URL setting (explicit override)
          4. LAN IP of this machine (works on same campus WiFi)
          5. http://localhost:3000 last-resort fallback
        """
        # 1. Vercel cloud URL (Prioritized)
        if settings.PUBLIC_WEB_APP_URL:
            base_url = settings.PUBLIC_WEB_APP_URL.rstrip('/')
            logger.info(f"Navigation QR will use Vercel URL: {base_url}")
            return f"{base_url}/navigation/{nav_id}?t={int(time.time())}"

        # 2. Live ngrok tunnel
        ngrok = self._get_tunnel_url()
        if ngrok:
            logger.info(f"Navigation QR will use ngrok tunnel: {ngrok}")
            return f"{ngrok}/navigation/{nav_id}?t={int(time.time())}"

        # 3. Explicit public base URL override
        if settings.PUBLIC_BASE_URL:
            base_url = settings.PUBLIC_BASE_URL.rstrip('/')
            logger.info(f"Navigation QR will use PUBLIC_BASE_URL: {base_url}")
            return f"{base_url}/navigation/{nav_id}?t={int(time.time())}"

        # 4. LAN IP — phones on the same WiFi can reach this
        from app.core.config import get_local_ip
        lan_ip = get_local_ip()
        if lan_ip and lan_ip not in ("localhost", "127.0.0.1"):
            lan_url = f"http://{lan_ip}:3000"
            logger.info(f"Navigation QR will use LAN IP: {lan_url}")
            return f"{lan_url}/navigation/{nav_id}?t={int(time.time())}"

        # 5. Last-resort local fallback
        return f"http://localhost:3000/navigation/{nav_id}?t={int(time.time())}"

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

        # Always store in memory store and persist to disk for instant local and LAN access
        _memory_store[nav_id] = session_data
        _save_disk_store(_memory_store)

        if settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN:
            try:
                clean_url = settings.UPSTASH_REDIS_REST_URL.strip('"').strip("'").rstrip('/')
                clean_token = settings.UPSTASH_REDIS_REST_TOKEN.strip('"').strip("'")

                url = f"{clean_url}/"
                headers = {"Authorization": f"Bearer {clean_token}"}
                payload = ["SET", f"nav:{nav_id}", json.dumps(session_data), "EX", self.ttl_seconds]
                async with httpx.AsyncClient(verify=False, timeout=1.5) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()
                logger.info(f"Created Navigation Session (Upstash REST): {nav_id} for destination '{session_data['destination']}'")
            except Exception as e:
                logger.warning(f"Upstash write bypassed, using memory store for navigation: {e}")

        return nav_id

    async def get_session(self, nav_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a navigation session payload by ID."""
        # 1. Fast in-memory check (instant response for local/LAN kiosk)
        if nav_id in _memory_store:
            data = _memory_store[nav_id]
            if time.time() - data.get("created_at", 0) <= self.ttl_seconds:
                return data
            else:
                del _memory_store[nav_id]

        # 2. Check persistent disk store (survives uvicorn reloads and restarts)
        disk_store = _load_disk_store()
        if nav_id in disk_store:
            disk_data = disk_store[nav_id]
            if time.time() - disk_data.get("created_at", 0) <= self.ttl_seconds:
                _memory_store[nav_id] = disk_data
                return disk_data

        # 3. Upstash check if configured
        if settings.UPSTASH_REDIS_REST_URL and settings.UPSTASH_REDIS_REST_TOKEN:
            try:
                clean_url = settings.UPSTASH_REDIS_REST_URL.strip('"').strip("'").rstrip('/')
                clean_token = settings.UPSTASH_REDIS_REST_TOKEN.strip('"').strip("'")
                url = f"{clean_url}/"
                headers = {"Authorization": f"Bearer {clean_token}"}
                payload = ["GET", f"nav:{nav_id}"]
                async with httpx.AsyncClient(timeout=1.5) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("result"):
                            return json.loads(data["result"])
            except Exception as e:
                logger.warning(f"Error fetching navigation session from Upstash: {e}")

        return None

class LocationResolver:
    """Minimal fuzzy string matcher to resolve campus locations, replacing RIAR's EntityResolver."""
    def __init__(self):
        import os
        import re

        from rapidfuzz import fuzz
        self.fuzz = fuzz
        self.re = re
        self.gazetteer = []
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "knowledge", "sources", "navigation"))
        file_path = os.path.join(base_dir, "navigation_locations.json")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                locations = json.load(f)
            for loc in locations:
                for alias in loc.get("aliases", []):
                    self.gazetteer.append((self.normalize(alias), alias, loc))
                self.gazetteer.append((self.normalize(loc["name"]), loc["name"], loc))
        except Exception as e:
            logger.error(f"Failed to load navigation_locations.json for LocationResolver: {e}")

    def normalize(self, text: str) -> str:
        text = text.lower()
        fillers = [
            r"\bwhere is\b", r"\bhow do i get to\b", r"\btake me to\b", r"\bnavigate to\b",
            r"\bfind\b", r"\bcan you tell me where\b", r"\blocate\b", r"\bshow me\b",
            r"\bi want to go to\b", r"\bdirection to\b", r"\bdirections to\b", r"\bthe way to\b",
            r"\btell me the way to\b", r"\bway to\b", r"\bthe\b"
        ]
        for filler in fillers:
            text = self.re.sub(filler, "", text)
        text = self.re.sub(r"[^\w\s]", "", text)
        return self.re.sub(r"\s+", " ", text).strip()

    def resolve(self, query: str) -> Optional[Dict[str, Any]]:
        norm_query = self.normalize(query)
        if not norm_query or not self.gazetteer:
            return None
        matches = []
        for norm_alias, orig_alias, loc_dict in self.gazetteer:
            score = self.fuzz.token_set_ratio(norm_query, norm_alias)
            matches.append((score, orig_alias, loc_dict))
        matches.sort(key=lambda x: x[0], reverse=True)

        if matches and matches[0][0] > 80:
            best_score = matches[0][0]
            top_locs = set()
            for score, orig_alias, loc in matches:
                if score == best_score:
                    top_locs.add(loc["name"])
                else:
                    break

            if len(top_locs) > 1:
                # Ambiguous query like "lab" matches multiple different labs
                return None

            best_loc = matches[0][2].copy()
            best_loc["matched_name"] = matches[0][1].title()
            return best_loc
        return None

navigation_service = NavigationService()
location_resolver = LocationResolver()
