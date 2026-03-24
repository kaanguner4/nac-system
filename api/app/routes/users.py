import logging
from fastapi import APIRouter, HTTPException

from app.db.postgres import get_all_users
from app.db.redis import get_all_active_sessions

logger = logging.getLogger(__name__)
router = APIRouter()



# GET /users
# Tüm kullanıcıları ve gruplarını listele

@router.get("/users")
async def list_users():
    try:
        rows = await get_all_users()
        users = [
            {
                "username":  row["username"],
                "groupname": row["groupname"],
            }
            for row in rows
        ]
        logger.info(f"Kullanıcı listesi istendi: {len(users)} kullanıcı")
        return {"users": users, "total": len(users)}
    except Exception as e:
        logger.error(f"Kullanıcı listesi alınamadı: {e}")
        raise HTTPException(status_code=500, detail="Veritabanı hatası")



# GET /sessions/active
# Redis'teki aktif oturumları listele

@router.get("/sessions/active")
async def active_sessions():
    try:
        sessions = await get_all_active_sessions()
        logger.info(f"Aktif oturum sorgusu: {len(sessions)} oturum")
        return {"sessions": sessions, "total": len(sessions)}
    except Exception as e:
        logger.error(f"Oturum listesi alınamadı: {e}")
        raise HTTPException(status_code=500, detail="Redis hatası")