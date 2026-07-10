import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import sys
import os

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from backend.app.core.config import settings

async def verify_db_connection():
    print("Testing PostgreSQL database connectivity...")
    database_url = settings.DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"DATABASE_URL: {database_url}")
    try:
        engine = create_async_engine(database_url, echo=False)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version();"))
            row = result.fetchone()
            print("\n====================================================")
            print("Database connection successful!")
            print(f"PostgreSQL Version: {row[0]}")
            
            # Check pgvector extension status
            vec_res = await conn.execute(
                text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
            )
            vec_row = vec_res.fetchone()
            if vec_row:
                print(f"pgvector extension enabled: version {vec_row[1]}")
            else:
                print("WARNING: pgvector extension is NOT enabled in the database!")
            print("====================================================\n")
            
        await engine.dispose()
    except Exception as e:
        print(f"\nError connecting to database: {e}\n")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(verify_db_connection())
