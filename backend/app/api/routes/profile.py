from typing import Any, Dict

from database.models.models import User

# We import the DB dependency and models from our database layer
from database.postgres.connection import get_db
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

router = APIRouter()


class ProfileResponse(BaseModel):
    user_id: str
    name: str
    role: str
    preferences: Dict[str, Any]


@router.get("/profile/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve user profile information by user_id.
    """
    result = await db.execute(
        select(User).filter(User.user_id == user_id)
    )
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return ProfileResponse(
        user_id=user.user_id,
        name=user.name,
        role=user.role_id,
        preferences=user.preferences
    )
