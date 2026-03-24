from fastapi import APIRouter

router = APIRouter()


@router.post("/accounting")
async def accounting():
    return {"result": "ok"}