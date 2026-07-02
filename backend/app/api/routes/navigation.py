from fastapi import APIRouter, HTTPException

from app.services.navigation_service import navigation_service

router = APIRouter()


@router.get("/navigation/{nav_id}")
async def get_navigation_session(nav_id: str):
    """
    Retrieves the navigation payload for the mobile QR view.
    """
    session = await navigation_service.get_session(nav_id)
    if not session:
        raise HTTPException(status_code=404, detail="Navigation session expired or not found")

    return {"status": "success", "data": session}
