from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.db.postgres import init_db, close_db
from app.db.redis import init_redis, close_redis
from app.routes.auth import router as auth_router
from app.routes.accounting import router as accounting_router
from app.routes.users import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uygulama başlarken
    await init_db()
    await init_redis()
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

