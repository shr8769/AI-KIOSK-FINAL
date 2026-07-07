import sys
import asyncio

sys.path.append("c:\\AI-KIOSK\\backend")
from app.core.config import settings
print(f"URL: {settings.UPSTASH_REDIS_REST_URL}")

async def test_nav():
    from app.services.navigation_service import navigation_service
    try:
        nav_id = await navigation_service.create_session({
            "destination_name": "Test",
            "building": "Test",
            "floor": 1,
            "room": "1"
        })
        print(f"Nav ID: {nav_id}")
    except Exception as e:
        print(f"Exception: {e}")

asyncio.run(test_nav())
