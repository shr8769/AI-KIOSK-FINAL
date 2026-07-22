from typing import List, Optional

from database.postgres.connection import get_db
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory_manager import MemoryManager

router = APIRouter()


class StoreMemoryRequest(BaseModel):
    user_id: str
    content: str


class StoreMemoryResponse(BaseModel):
    memory_id: str
    summary: str
    topic: str


class MemoryItem(BaseModel):
    memory_id: str
    user_id: str
    content: str
    topic: str
    created_at: str


@router.post("/memory/store", response_model=StoreMemoryResponse)
async def store_memory(request: StoreMemoryRequest, db: AsyncSession = Depends(get_db)):
    """
    Orchestrate summarizing, embedding, and storing conversation content into user's past memories.
    """
    manager = MemoryManager(db)
    try:
        result = await manager.store_conversation_segment(
            user_id=request.user_id,
            conversation_text=request.content
        )
        return StoreMemoryResponse(
            memory_id=result["memory_id"],
            summary=result["summary"],
            topic=result["topic"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/{user_id}", response_model=List[MemoryItem])
async def get_memories(
    user_id: str,
    query: Optional[str] = "",
    limit: Optional[int] = 3,
    db: AsyncSession = Depends(get_db)
):
    """
    Query the long-term memory vector store for user memories related to a topic.
    """
    manager = MemoryManager(db)
    try:
        memories = await manager.retriever_service.retrieve_memories(
            user_id=user_id,
            query_text=query,
            limit=limit
        )
        response_list = []
        for mem in memories:
            response_list.append(MemoryItem(
                memory_id=mem.memory_id,
                user_id=mem.user_id,
                content=mem.content,
                topic=mem.topic or "general",
                created_at=mem.created_at.isoformat() if mem.created_at else ""
            ))
        return response_list
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
