"""
Pytest Configuration and Fixtures
Owner: Engineering Team

Provides shared test configuration, fixtures, and utilities.
Runs BEFORE any test session to set up environment and provide shared fixtures.
"""

import os
import sys
import asyncio
import pytest
from typing import Generator
from datetime import datetime




if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── SET ENVIRONMENT VARIABLES BEFORE IMPORTING APP (CRITICAL!)
# This must happen first, before app initialization
os.environ.setdefault("PYTHONPATH", ".")
os.environ.setdefault("USE_MOCK_SERVICES", "true")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# ── NOW import app after environment is configured
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from database.postgres.connection import get_db  # noqa: E402

# ── Mock Database Layer for Global Test Overrides ──
class MockUserRecord:
    user_id = "usr_demo_123"
    name = "Demo User"
    role_id = "user"
    preferences = {"theme": "dark", "language": "en"}


class MockSessionRecord:
    session_id = "demo_session_id"
    user_id = "usr_demo_123"


class MockMemoryRecord:
    memory_id = "mem_123"
    user_id = "usr_demo_123"
    content = "This is a mock past memory content."
    topic = "general"
    created_at = datetime.now()


class MockDbResult:
    def __init__(self, record):
        self.record = record
        
    def scalars(self):
        return self
        
    def first(self):
        return self.record

    def all(self):
        return [self.record] if self.record else []


class MockAsyncSession:
    def __init__(self, return_none=False):
        self.return_none = return_none

    async def execute(self, statement):
        if self.return_none:
            return MockDbResult(None)
            
        stmt_str = str(statement).lower()
        if "from users" in stmt_str:
            return MockDbResult(MockUserRecord())
        elif "from sessions" in stmt_str:
            return MockDbResult(MockSessionRecord())
        elif "from memories" in stmt_str:
            return MockDbResult(MockMemoryRecord())
        return MockDbResult(None)

    def add(self, instance):
        pass

    async def commit(self):
        pass

    async def refresh(self, instance):
        pass

    async def close(self):
        pass


async def global_mock_get_db():
    yield MockAsyncSession(return_none=False)


@pytest.fixture(autouse=True)
def mock_db_override():
    """Globally override get_db dependency to use the MockAsyncSession."""
    app.dependency_overrides[get_db] = global_mock_get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session")
def test_app():
    """Provide FastAPI application instance for the entire test session."""
    return app


@pytest.fixture
def client() -> Generator:
    """Provide FastAPI TestClient for making HTTP requests to endpoints."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def dispose_engine():
    yield
    import asyncio
    import threading
    from database.postgres.connection import engine
    
    def run_dispose():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()
            
    t = threading.Thread(target=run_dispose)
    t.start()
    t.join()
