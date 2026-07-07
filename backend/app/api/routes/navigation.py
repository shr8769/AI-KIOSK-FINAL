from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.services.navigation_service import navigation_service
from app.core.config import settings

router = APIRouter()


@router.get("/navigation/{nav_id}")
async def get_navigation_session(request: Request, nav_id: str):
    """
    Retrieves the navigation payload for the mobile QR view.

    Behavior:
    - If the incoming client prefers HTML and a public frontend URL is configured,
      redirect the browser to the frontend navigation page (PUBLIC_WEB_APP_URL/navigation/{nav_id}).
    - Otherwise, return the JSON payload so API clients can fetch it directly.
    """
    session = await navigation_service.get_session(nav_id)
    if not session:
        raise HTTPException(status_code=404, detail="Navigation session expired or not found")

    accept = request.headers.get("accept", "")
    # If a human scans the QR code, their browser will request HTML; prefer redirecting to the frontend UI
    if "text/html" in accept:
        frontend_base = settings.PUBLIC_WEB_APP_URL or settings.PUBLIC_BASE_URL
        if frontend_base:
            target = f"{frontend_base.rstrip('/')}/navigation/{nav_id}"
            return RedirectResponse(url=target)

    return JSONResponse({"status": "success", "data": session})
