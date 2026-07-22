import pytest
from database.postgres.connection import get_db
from fastapi.testclient import TestClient

from app.main import app


# Mock database classes representing records returned from query results
class MockUserRecord:
    user_id = "usr_demo_123"
    name = "Demo User"
    role_id = "user"
    preferences = {"theme": "dark", "language": "en"}


class MockSessionRecord:
    session_id = "demo_session_id"
    user_id = "usr_demo_123"


class MockDbResult:
    def __init__(self, record):
        self.record = record

    def scalars(self):
        return self

    def first(self):
        return self.record


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
        return MockDbResult(None)

    async def commit(self):
        pass

    async def close(self):
        pass


async def mock_get_db():
    yield MockAsyncSession(return_none=False)


async def mock_get_db_empty():
    yield MockAsyncSession(return_none=True)


@pytest.fixture(autouse=True)
def run_around_tests():
    # Setup dependency override before test runs
    app.dependency_overrides[get_db] = mock_get_db
    yield
    # Clean up after test runs
    app.dependency_overrides.pop(get_db, None)


def test_get_profile(client: TestClient):
    """Test retrieving user profile information."""
    response = client.get("/api/v1/profile/usr_demo_123")
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "usr_demo_123"
    assert data["name"] == "Demo User"
    assert data["role"] == "user"
    assert data["preferences"] == {"theme": "dark", "language": "en"}


def test_get_profile_not_found(client: TestClient):
    """Test retrieving a non-existent user profile returns 404."""
    # Override database to return no records for this test case
    app.dependency_overrides[get_db] = mock_get_db_empty
    response = client.get("/api/v1/profile/non_existent_user")
    assert response.status_code == 404
    # Restore standard mock
    app.dependency_overrides[get_db] = mock_get_db


def test_get_session_resolves_profile(client: TestClient):
    """Test that session resolution successfully resolves a session to user_id."""
    response = client.get("/api/v1/session/demo_session_id")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "demo_session_id"
    assert data["user_id"] == "usr_demo_123"
