from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse


router = APIRouter()
_DASHBOARD_FILE = Path(__file__).resolve().parents[1] / "static" / "dashboard.html"


@router.api_route("/dashboard", methods=["GET", "HEAD"], include_in_schema=False)
@router.api_route("/dashboard/", methods=["GET", "HEAD"], include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(_DASHBOARD_FILE)
