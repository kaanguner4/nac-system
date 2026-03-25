import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.db.postgres import get_active_accounting_sessions, init_db, close_db
from app.db.redis import clear_all_sessions, init_redis, close_redis, set_session
from app.routes.auth import router as auth_router
from app.routes.accounting import router as accounting_router
from app.routes.users import router as users_router

logger = logging.getLogger(__name__)


async def restore_active_session_cache():
    """Redis session cache'ini veritabanındaki aktif oturumlardan yeniden kur."""
    active_sessions = await get_active_accounting_sessions()

    await clear_all_sessions()

    for session in active_sessions:
        await set_session(
            session["session_id"],
            {
                "username": session["username"],
                "nas_ip": session.get("nas_ip") or "",
                "framed_ip": session.get("framed_ip") or "",
                "status": "active",
                "session_id": session["session_id"],
                "unique_id": session.get("unique_id") or "",
                "session_time": str(session.get("session_time") or 0),
                "input_octets": str(session.get("input_octets") or 0),
                "output_octets": str(session.get("output_octets") or 0),
            },
        )

    logger.info(
        "Redis session cache veritabanından yeniden kuruldu: %s aktif oturum",
        len(active_sessions),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uygulama başlarken
    await init_db()
    await init_redis()
    await restore_active_session_cache()
    yield
    # Uygulama kapanırken
    await close_db()
    await close_redis()


app = FastAPI(
    title="NAC Policy Engine",
    description="FreeRADIUS ile entegre çalışan AAA policy engine",
    version="1.0.0",
    lifespan=lifespan,
)

# Router'ları bağla
app.include_router(auth_router)
app.include_router(accounting_router)
app.include_router(users_router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
