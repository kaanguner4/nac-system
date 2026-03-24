import logging
from fastapi import APIRouter
from pydantic import BaseModel

from app.db.postgres import insert_accounting
from app.db.redis import set_session, delete_session

logger = logging.getLogger(__name__)
router = APIRouter()



# Request şeması
class AccountingRequest(BaseModel):
    status_type: str        # Start, Interim-Update, Stop
    session_id: str
    unique_id: str
    username: str
    nas_ip: str = ""
    calling_station_id: str = ""
    framed_ip: str = ""
    session_time: int = 0
    input_octets: int = 0
    output_octets: int = 0



# POST /accounting
# FreeRADIUS rlm_rest bu endpoint'i çağırır

@router.post("/accounting")
async def accounting(req: AccountingRequest):
    logger.info(
        f"Accounting: {req.status_type} | "
        f"user={req.username} | session={req.session_id}"
    )

    # PostgreSQL'e yaz
    await insert_accounting({
        "session_id":        req.session_id,
        "unique_id":         req.unique_id,
        "username":          req.username,
        "nas_ip":            req.nas_ip,
        "status_type":       req.status_type,
        "calling_station_id": req.calling_station_id,
        "framed_ip":         req.framed_ip,
        "session_time":      req.session_time,
        "input_octets":      req.input_octets,
        "output_octets":     req.output_octets,
    })

    # Redis session cache yönetimi
    if req.status_type == "Start":
        await set_session(req.session_id, {
            "username":    req.username,
            "nas_ip":      req.nas_ip,
            "framed_ip":   req.framed_ip,
            "status":      "active",
            "session_id":  req.session_id,
        })
        logger.info(f"Oturum başladı: {req.username}")

    elif req.status_type == "Interim-Update":
        await set_session(req.session_id, {
            "username":       req.username,
            "nas_ip":         req.nas_ip,
            "framed_ip":      req.framed_ip,
            "status":         "active",
            "session_id":     req.session_id,
            "session_time":   str(req.session_time),
            "input_octets":   str(req.input_octets),
            "output_octets":  str(req.output_octets),
        })
        logger.info(f"Oturum güncellendi: {req.username}")

    elif req.status_type == "Stop":
        await delete_session(req.session_id)
        logger.info(f"Oturum bitti: {req.username}")

    return {"result": "ok"}