import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException

from app.db.postgres import get_all_users, get_latest_accounting_by_user
from app.db.redis import get_all_active_sessions, get_all_blocked_users
from app.security import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])



# GET /users
# Tüm kullanıcıları ve gruplarını listele

@router.get("/users")
async def list_users():
    try:
        rows, active_sessions, blocked_users, last_accounting = await asyncio.gather(
            get_all_users(),
            get_all_active_sessions(),
            get_all_blocked_users(),
            get_latest_accounting_by_user(),
        )

        active_sessions_by_user = {}
        for session in active_sessions:
            username = session.get("username")
            if not username:
                continue
            active_sessions_by_user.setdefault(username, []).append(session)

        users = []
        active_user_count = 0
        blocked_user_count = 0

        for row in rows:
            username = row["username"]
            sessions = active_sessions_by_user.get(username, [])
            block_ttl = blocked_users.get(username)
            is_active = len(sessions) > 0
            is_blocked = block_ttl is not None and block_ttl > 0

            if is_active:
                active_user_count += 1
            if is_blocked:
                blocked_user_count += 1

            if is_active and is_blocked:
                status = "active_blocked"
            elif is_active:
                status = "active"
            elif is_blocked:
                status = "blocked"
            else:
                status = "inactive"

            users.append(
                {
                    "username": username,
                    "groupname": row["groupname"],
                    "status": status,
                    "active": is_active,
                    "active_session_count": len(sessions),
                    "active_sessions": sessions,
                    "blocked": is_blocked,
                    "block_ttl": block_ttl if is_blocked else None,
                    "last_accounting": last_accounting.get(username),
                }
            )

        logger.info(
            "Kullanıcı listesi istendi: %s kullanıcı, %s aktif, %s bloklu",
            len(users),
            active_user_count,
            blocked_user_count,
        )
        return {
            "users": users,
            "total": len(users),
            "active_users": active_user_count,
            "blocked_users": blocked_user_count,
        }
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
