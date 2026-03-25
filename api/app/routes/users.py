import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException

from app.db.postgres import (
    get_active_accounting_sessions,
    get_all_users,
    get_latest_accounting_by_user,
)
from app.db.redis import get_all_active_sessions, get_all_blocked_users
from app.security import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])



# GET /users
# Tüm kullanıcıları ve gruplarını listele

def build_active_session_state(redis_sessions: list[dict], db_sessions: list[dict]):
    """Aktif oturumlar için PostgreSQL'i kaynak, Redis'i cache olarak birleştir."""
    redis_sessions_by_id = {
        session["session_id"]: session
        for session in redis_sessions
        if session.get("session_id")
    }

    merged_sessions = []
    active_sessions_by_user = {}

    for db_session in db_sessions:
        merged_session = dict(db_session)
        redis_session = redis_sessions_by_id.pop(db_session["session_id"], None)

        if redis_session:
            for key, value in redis_session.items():
                if value not in ("", None):
                    merged_session[key] = value
            merged_session["source"] = "postgres+redis"
        else:
            merged_session["source"] = "postgres"

        merged_session["status"] = "active"
        merged_sessions.append(merged_session)
        active_sessions_by_user.setdefault(
            merged_session["username"], []
        ).append(merged_session)

    orphaned_cache_sessions = []
    for redis_session in redis_sessions_by_id.values():
        orphan = dict(redis_session)
        orphan["source"] = "redis_orphan"
        orphan["status"] = "cache_only"
        orphaned_cache_sessions.append(orphan)

    return merged_sessions, active_sessions_by_user, orphaned_cache_sessions


@router.get("/users")
async def list_users():
    try:
        (
            rows,
            redis_sessions,
            blocked_users,
            last_accounting,
            db_active_sessions,
        ) = await asyncio.gather(
            get_all_users(),
            get_all_active_sessions(),
            get_all_blocked_users(),
            get_latest_accounting_by_user(),
            get_active_accounting_sessions(),
        )

        (
            merged_active_sessions,
            active_sessions_by_user,
            orphaned_cache_sessions,
        ) = build_active_session_state(redis_sessions, db_active_sessions)

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

        if orphaned_cache_sessions:
            logger.warning(
                "Redis'te veritabanıyla eşleşmeyen %s session bulundu",
                len(orphaned_cache_sessions),
            )

        logger.info(
            "Kullanıcı listesi istendi: %s kullanıcı, %s aktif, %s bloklu, %s aktif session",
            len(users),
            active_user_count,
            blocked_user_count,
            len(merged_active_sessions),
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
        redis_sessions, db_active_sessions = await asyncio.gather(
            get_all_active_sessions(),
            get_active_accounting_sessions(),
        )
        sessions, _, orphaned_cache_sessions = build_active_session_state(
            redis_sessions,
            db_active_sessions,
        )

        if orphaned_cache_sessions:
            logger.warning(
                "Aktif oturum sorgusunda %s cache-only session bulundu",
                len(orphaned_cache_sessions),
            )

        logger.info(
            "Aktif oturum sorgusu: %s oturum, %s cache-only kayıt",
            len(sessions),
            len(orphaned_cache_sessions),
        )
        return {
            "sessions": sessions,
            "total": len(sessions),
            "cache_only_sessions": len(orphaned_cache_sessions),
            "source_of_truth": "postgres",
        }
    except Exception as e:
        logger.error(f"Oturum listesi alınamadı: {e}")
        raise HTTPException(status_code=500, detail="Redis hatası")
