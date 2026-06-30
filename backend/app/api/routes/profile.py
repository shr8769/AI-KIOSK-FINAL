from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    import cv2
    import numpy as np
    from database.models.models import Role, User
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.future import select

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_db():
    """Lazy import so database.postgres is not required at module import time."""
    from database.postgres.connection import get_db  # noqa: PLC0415
    return get_db


class RegisterRequest(BaseModel):
    user_id: str  # SRN or Employee ID
    name: str
    role: str  # student or professor / faculty
    department: str
    interests: Optional[str] = ""
    image_base64: str  # Base64 encoded JPEG/PNG image data


class RegisterResponse(BaseModel):
    status: str
    message: str
    user_id: str
    name: str
    role: str


class ProfileResponse(BaseModel):
    user_id: str
    name: str
    role: str
    preferences: Dict[str, Any]


@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest, db: AsyncSession = Depends(_get_db())):
    logger.info(f"Registration request for user_id={request.user_id}, name={request.name}, role={request.role}")

    # 1. Validate inputs
    user_id = request.user_id.strip()
    name = request.name.strip()
    role = request.role.strip().lower()
    department = request.department.strip()

    if not user_id or not name or not role or not department:
        raise HTTPException(status_code=400, detail="SRN/ID, Name, Role, and Department are all required.")

    # Map roles to DB role_id
    if role in ["student", "user"]:
        db_role = "student"
    elif role in ["faculty", "professor", "admin"]:
        db_role = "professor"
    else:
        db_role = "student"  # Fallback

    # 2. Decode base64 image
    try:
        header = "base64,"
        data = request.image_base64
        if header in data:
            data = data.split(header)[1]
        decoded_bytes = base64.b64decode(data)
    except Exception as e:
        logger.error(f"Failed to decode base64 image: {e}")
        raise HTTPException(status_code=400, detail="Invalid image encoding (must be base64).")

    # 3. Convert to OpenCV BGR image
    try:
        nparr = np.frombuffer(decoded_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("cv2.imdecode returned None")
    except Exception as e:
        logger.error(f"Failed to parse image bytes: {e}")
        raise HTTPException(status_code=400, detail="Could not read image. Ensure it is a valid JPEG/PNG.")

    # 4. Extract face embedding using FaceExtractor
    try:
        from detection.face_extractor import face_extractor

        # Check if model is loaded yet
        if not face_extractor.is_ready:
            logger.info("InsightFace is loading in background. Waking up model...")
            import time
            for _ in range(50):
                if face_extractor.is_ready:
                    break
                time.sleep(0.1)

        if not face_extractor.is_ready:
            raise HTTPException(
                status_code=503,
                detail="Facial recognition engine is still warming up. Please try again in a few seconds."
            )

        embedding = face_extractor.extract(img)
        if embedding is None:
            raise HTTPException(
                status_code=400,
                detail="No face detected in the captured image. Please look directly at the camera and try again."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Face extraction failed: {str(e)}")

    # 5. Save to PostgreSQL database
    try:
        # Check if role exists
        role_res = await db.execute(select(Role).filter(Role.role_id == db_role))
        if not role_res.scalars().first():
            # If role doesn't exist, create it dynamically
            new_role = Role(role_id=db_role, permissions=["read", "ask"])
            db.add(new_role)
            await db.commit()

        # Create or update user
        interests_list = [i.strip() for i in request.interests.split(",") if i.strip()]
        user_obj = User(
            user_id=user_id,
            name=name,
            role_id=db_role,
            face_embedding=embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
            preferences={
                "department": department,
                "interests": interests_list
            }
        )
        await db.merge(user_obj)
        await db.commit()
        logger.info(f"User {user_id} registered successfully in PostgreSQL database.")
    except Exception as db_e:
        logger.error(f"PostgreSQL user registration failed: {db_e}")
        raise HTTPException(status_code=500, detail=f"Database write failed: {str(db_e)}")

    return RegisterResponse(
        status="success",
        message="Profile and face successfully registered in database.",
        user_id=user_id,
        name=name,
        role=db_role
    )


@router.get("/profile/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: str, db: AsyncSession = Depends(_get_db())):
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
