"""
Profile & Registration Route — POST /api/v1/register
Owner: Harsha
"""

import base64
import logging
from typing import Optional

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.firebase_client import register_user

logger = logging.getLogger(__name__)
router = APIRouter()


class RegisterRequest(BaseModel):
    user_id: str
    name: str
    role: str
    department: str
    interests: Optional[str] = ""
    image_base64: str


class RegisterResponse(BaseModel):
    status: str
    message: str
    user_id: str
    name: str
    role: str


@router.post("/register", response_model=RegisterResponse)
async def register(request: RegisterRequest):
    logger.info(
        f"Registration request for user_id={request.user_id}, name={request.name}, role={request.role}"
    )

    user_id = request.user_id.strip()
    name = request.name.strip()
    role = request.role.strip().lower()
    department = request.department.strip()

    if not user_id or not name or not role or not department:
        raise HTTPException(
            status_code=400, detail="SRN/ID, Name, Role, and Department are all required."
        )

    # 1. Decode base64 image
    try:
        header = "base64,"
        data = request.image_base64
        if header in data:
            data = data.split(header)[1]
        decoded_bytes = base64.b64decode(data)
    except Exception as e:
        logger.error(f"Failed to decode base64 image: {e}")
        raise HTTPException(status_code=400, detail="Invalid image encoding (must be base64).")

    # 2. Convert to OpenCV BGR image
    try:
        nparr = np.frombuffer(decoded_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("cv2.imdecode returned None")
    except Exception as e:
        logger.error(f"Failed to parse image bytes: {e}")
        raise HTTPException(
            status_code=400, detail="Could not read image. Ensure it is a valid JPEG/PNG."
        )

    # 3. Extract face embedding using FaceExtractor
    try:
        # Import dynamically so it doesn't block startup
        import os
        import sys

        # Ensure detection path is in sys.path
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
        from detection.face_extractor import face_extractor

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
                detail="Facial recognition engine is still warming up. Please try again in a few seconds.",
            )

        embedding = face_extractor.extract(img)
        if embedding is None:
            raise HTTPException(
                status_code=400,
                detail="No face detected in the captured image. Please look directly at the camera and try again.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Face extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Face extraction failed: {str(e)}")

    # 4. Save to Firebase
    interests_list = [i.strip() for i in request.interests.split(",") if i.strip()]
    if department:
        interests_list.append(department)  # Add department as an interest tag

    success = register_user(
        user_id=user_id,
        name=name,
        role=role,
        face_embedding=embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
        interests=interests_list,
        language="en",
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save user profile to database.")

    return RegisterResponse(
        status="success",
        message="Profile and face successfully registered.",
        user_id=user_id,
        name=name,
        role=role,
    )
