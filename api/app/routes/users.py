from fastapi import APIRouter

router = APIRouter()


@router.get("/users")
async def list_users():
    return {"users": []}


@router.get("/sessions/active")
async def active_sessions():
    return {"sessions": []}
