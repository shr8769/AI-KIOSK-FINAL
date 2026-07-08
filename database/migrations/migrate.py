import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import sys
import os

# Add parent directory to sys.path to resolve imports correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from backend.app.core.config import settings

async def run_migrations():
    print("Running database migrations...")
    database_url = settings.DATABASE_URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    print(f"Connecting to database: {database_url}")
    engine = create_async_engine(database_url, echo=True)
    
    migrations = ["001_init.sql", "002_memory.sql", "003_queries.sql"]
    async with engine.begin() as conn:
        for migration in migrations:
            print(f"Executing: {migration}")
            migration_path = os.path.join(os.path.dirname(__file__), migration)
            with open(migration_path, "r", encoding="utf-8") as f:
                sql_commands = f.read()
            for cmd in sql_commands.split(";"):
                cmd_strip = cmd.strip()
                if cmd_strip:
                    await conn.execute(text(cmd_strip))
        
    print("Migrations completed successfully!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migrations())
