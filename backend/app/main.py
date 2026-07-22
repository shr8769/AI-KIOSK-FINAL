"""
FastAPI Application Entry Point
Owner: Harsha (Engineering Lead)

Starts the VidyaSahayak backend API server.
Run: uvicorn app.main:app --reload
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

# Add parent directory to sys.path to resolve 'database' imports when running from backend directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import Depends, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    asr,
    events,
    memory,
    navigation,
    profile,
    rag,
    route,
    session,
    tts,
)
from app.core.config import settings
from app.core.dependencies import ConnectionManager, get_connection_manager
from app.core.warmup import startup_state, warmup_services
from app.websockets.session_ws import websocket_session_handler

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    logger.info("🚀 VidyaSahayak backend starting...")
    logger.info(f"   Mode: {'DEBUG' if settings.DEBUG else 'PRODUCTION'}")
    logger.info(f"   Using mock services: {settings.USE_MOCK_SERVICES}")

    # Initialize SQLite database schema
    from app.core.session_store import get_session, init_db

    await init_db()

    # Seed demo session for frontend local development
    try:
        demo_session = await get_session("demo_session_id")
        if not demo_session:
            logger.info("Seeding demo_session_id for development/testing...")
            import json
            from datetime import datetime

            import aiosqlite

            os.makedirs(os.path.dirname(settings.SQLITE_DB_PATH) or ".", exist_ok=True)
            async with aiosqlite.connect(settings.SQLITE_DB_PATH) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO sessions (session_id, created_at, status, metadata) VALUES (?,?,?,?)",
                    ("demo_session_id", datetime.utcnow().isoformat(), "active", "{}"),
                )
                await db.commit()

            try:
                from app.core.session_store import get_redis

                redis = await get_redis()
                await redis.set(
                    "session:demo_session_id",
                    json.dumps(
                        {
                            "session_id": "demo_session_id",
                            "created_at": datetime.utcnow().isoformat(),
                            "status": "active",
                            "metadata": {},
                        }
                    ),
                    ex=settings.SESSION_TTL_SECONDS,
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Could not seed demo session: {e}")

    # Warm up all models and connections in a background thread executor
    import asyncio

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, warmup_services)

    yield

    # Clean up connections
    try:
        from app.core.session_store import close_redis

        await close_redis()
    except Exception:
        pass
    logger.info("⏹  VidyaSahayak backend shutting down...")


app = FastAPI(
    title="VidyaSahayak API",
    description="AI Avatar Kiosk Backend — PES University Research Project",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow frontend (React on :3000) to call backend
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files folder
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Register Routers ────────────────────────────────────────────────────────
app.include_router(events.router, prefix="/api/v1", tags=["Detection"])
app.include_router(asr.router, prefix="/api/v1", tags=["ASR"])

app.include_router(route.router, prefix="/api/v1", tags=["Routing"])
app.include_router(rag.router, prefix="/api/v1", tags=["RAG"])
app.include_router(tts.router, prefix="/api/v1", tags=["TTS"])
app.include_router(session.router, prefix="/api/v1", tags=["Session"])
app.include_router(navigation.router, prefix="/api/v1", tags=["Navigation"])
app.include_router(profile.router, prefix="/api/v1", tags=["Profile"])
app.include_router(memory.router, prefix="/api/v1", tags=["Memory"])

# WebSocket Route
@app.websocket("/ws/session/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket, session_id: str, mgr: ConnectionManager = Depends(get_connection_manager)
):
    await websocket_session_handler(websocket, session_id, mgr)


@app.get("/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "0.1.0", "project": "VidyaSahayak"}


@app.get("/ready", tags=["Health"])
async def ready():
    from app.core.config import get_local_ip
    return {
        "ready": startup_state.ready,
        "warming": startup_state.warming,
        "errors": startup_state.errors,
        "messages": startup_state.messages,
        "metrics": startup_state.metrics,
        "kiosk_ip": get_local_ip(),
    }


@app.get("/api/v1/faqs", tags=["Kiosk"])
async def get_faqs(lang: str = "en"):
    # Basic grouped FAQs for the kiosk UI
    faqs = {
        "en": {
            "Admissions & Fees": [
                {"question": "What is the minimum attendance required?", "answer": "You need 85% attendance.", "topic": "Admissions"},
                {"question": "How to pay college fees?", "answer": "Fees can be paid online via the portal.", "topic": "Admissions"},
                {"question": "Are there scholarships available?", "answer": "Yes, merit-based scholarships are available.", "topic": "Admissions"}
            ],
            "Campus Navigation": [
                {"question": "Where is the central library?", "answer": "The central library is on the 3rd floor of the B block.", "topic": "Navigation"},
                {"question": "Where is the student lounge?", "answer": "The lounge is near the main cafeteria.", "topic": "Navigation"},
                {"question": "How to find the placement office?", "answer": "The placement office is in the administrative block.", "topic": "Navigation"}
            ],
            "Academics": [
                {"question": "How do I check my results?", "answer": "Check your results on the student portal.", "topic": "Academics"},
                {"question": "Where can I find the exam schedule?", "answer": "Exam schedules are posted on the notice board and portal.", "topic": "Academics"}
            ]
        },
        "kn": {
            "ಪ್ರವೇಶ ಮತ್ತು ಶುಲ್ಕ": [
                {"question": "ಕನಿಷ್ಠ ಹಾಜರಾತಿ ಎಷ್ಟು ಬೇಕು?", "answer": "೮೫% ಹಾಜರಾತಿ ಕಡ್ಡಾಯ.", "topic": "Admissions"},
                {"question": "ಶುಲ್ಕವನ್ನು ಹೇಗೆ ಪಾವತಿಸುವುದು?", "answer": "ಆನ್‌ಲೈನ್ ಪೋರ್ಟಲ್ ಮೂಲಕ ಪಾವತಿಸಬಹುದು.", "topic": "Admissions"}
            ],
            "ಕ್ಯಾಂಪಸ್ ನ್ಯಾವಿಗೇಶನ್": [
                {"question": "ಕೇಂದ್ರ ಗ್ರಂಥಾಲಯ ಎಲ್ಲಿದೆ?", "answer": "ಬಿ ಬ್ಲಾಕ್‌ನ ೩ನೇ ಮಹಡಿಯಲ್ಲಿದೆ.", "topic": "Navigation"}
            ]
        },
        "hi": {
            "प्रवेश और फीस": [
                {"question": "न्यूनतम उपस्थिति कितनी चाहिए?", "answer": "85% उपस्थिति अनिवार्य है।", "topic": "Admissions"},
                {"question": "फीस कैसे जमा करें?", "answer": "फीस ऑनलाइन पोर्टल के माध्यम से जमा कर सकते हैं।", "topic": "Admissions"}
            ],
            "परिसर नेविगेशन": [
                {"question": "केंद्रीय पुस्तकालय कहाँ है?", "answer": "बी ब्लॉक की तीसरी मंजिल पर है।", "topic": "Navigation"}
            ]
        }
    }
    return faqs.get(lang, faqs["en"])
