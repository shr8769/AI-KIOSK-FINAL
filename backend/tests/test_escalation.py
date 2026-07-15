import pytest
from backend.app.core.config import settings
from database.models.models import OfficeEscalation
from database.models.models import Role as PGRole
from database.models.models import Session as PGSession
from database.models.models import User as PGUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.pool import NullPool

from app.services.query_pipeline import run_query_pipeline


def _make_test_engine():
    """Build a NullPool engine to avoid asyncpg connection-reuse conflicts when running in a suite."""
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(url, poolclass=NullPool, echo=False)


@pytest.mark.anyio
async def test_escalation_triggers_correctly():
    engine = _make_test_engine()
    TestSession = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    session_id = "test_escalation_session_123"
    user_id = "PES1202300001"

    # 1. Seed the database — each block gets its own fresh connection via NullPool
    async with TestSession() as db:
        role_res = await db.execute(select(PGRole).where(PGRole.role_id == "student"))
        if not role_res.scalar_one_or_none():
            db.add(PGRole(role_id="student", permissions=["read", "ask"]))
            await db.commit()

    async with TestSession() as db:
        user_res = await db.execute(select(PGUser).where(PGUser.user_id == user_id))
        if not user_res.scalar_one_or_none():
            db.add(PGUser(
                user_id=user_id,
                name="Escalation Test Student",
                role_id="student",
                preferences={"phone_number": "+91 9999988888"}
            ))
            await db.commit()

    async with TestSession() as db:
        sess_res = await db.execute(select(PGSession).where(PGSession.session_id == session_id))
        if not sess_res.scalar_one_or_none():
            db.add(PGSession(session_id=session_id, user_id=user_id))
            await db.commit()

    await engine.dispose()

    # 2. Seed the SQLite/Redis cache session
    from app.core.session_store import create_session, get_session, update_session_metadata
    cached_sess = await get_session(session_id)
    if not cached_sess:
        await create_session(session_id=session_id)

    await update_session_metadata(
        session_id=session_id,
        updates={"user_id": user_id, "user_name": "Escalation Test Student"}
    )

    # 3. Run the pipeline with an unresolvable query to trigger fallback/escalation
    query = "Where is the secret time machine in campus?"
    res = await run_query_pipeline(session_id=session_id, text=query, language_hint="en")

    # 4. Assert pipeline response contains office fallback info
    assert res is not None
    assert "text" in res
    assert any(w in res["text"].lower() for w in ("office", "escalate", "contact", "university")), \
        f"Response text '{res['text']}' did not contain office fallback info."

    # 5. Verify escalation record was written to PostgreSQL using a fresh NullPool engine
    engine2 = _make_test_engine()
    TestSession2 = async_sessionmaker(bind=engine2, class_=AsyncSession, expire_on_commit=False)
    async with TestSession2() as db:
        esc_res = await db.execute(
            select(OfficeEscalation).where(OfficeEscalation.customer_name == "Escalation Test Student")
        )
        escalations = esc_res.scalars().all()
        assert len(escalations) >= 1
        latest_esc = escalations[-1]
        assert latest_esc.contact_number in ("+91 9999988888", user_id)
        assert "time machine" in latest_esc.issue_encountering.lower()
        print(f"Verified escalation logged: {latest_esc.id} - {latest_esc.customer_name} - {latest_esc.issue_encountering}")
    await engine2.dispose()
