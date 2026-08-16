import asyncio
import os
import sys

# Add backend to path
sys.path.append(r"C:\AI-KIOSK\backend")

from app.services.query_pipeline import run_query_pipeline

async def test():
    result = await run_query_pipeline("test-123", "where is the cafeteria")
    print(result)

if __name__ == "__main__":
    asyncio.run(test())
