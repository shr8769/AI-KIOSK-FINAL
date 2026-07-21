import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import sys
import os

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from backend.app.core.config import settings
from database.models.models import Role, User, Session

async def run_seeds():
    print("Seeding database...")
    database_url = settings.DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    engine = create_async_engine(database_url, echo=True)
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with AsyncSessionLocal() as db:
        # 1. Create roles
        user_role = Role(role_id="user", permissions=["read", "ask"])
        admin_role = Role(role_id="admin", permissions=["read", "ask", "write", "manage"])
        guest_role = Role(role_id="guest", permissions=["read"])
        student_role = Role(role_id="student", permissions=["read", "ask"])
        professor_role = Role(role_id="professor", permissions=["read", "ask", "write"])
        
        await db.merge(user_role)
        await db.merge(admin_role)
        await db.merge(guest_role)
        await db.merge(student_role)
        await db.merge(professor_role)
        
        # 2. Create demo user
        embedding = [0.1] * 512
        demo_user = User(
            user_id="usr_demo_123",
            name="Demo User",
            role_id="user",
            face_embedding=embedding,
            preferences={"theme": "dark", "language": "en"}
        )
        await db.merge(demo_user)
        
        # Create a guest user fallback for sessions
        guest_user = User(
            user_id="usr_guest",
            name="Guest User",
            role_id="guest",
            face_embedding=None,
            preferences={"language": "en"}
        )
        await db.merge(guest_user)
        
        # Create a student user
        student_user = User(
            user_id="usr_student_123",
            name="Gowtham Student",
            role_id="student",
            face_embedding=[0.2] * 512,
            preferences={"interests": ["placements", "academics"]}
        )
        await db.merge(student_user)

        # Create a professor user
        professor_user = User(
            user_id="usr_professor_123",
            name="Harsha Professor",
            role_id="professor",
            face_embedding=[0.3] * 512,
            preferences={"interests": ["research", "academics"]}
        )
        await db.merge(professor_user)
        # 3. Create demo session mapping
        demo_session = Session(
            session_id="demo_session_id",
            user_id="usr_demo_123"
        )
        await db.merge(demo_session)
        
        await db.commit()
        
    print("Seeding completed successfully!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_seeds())
