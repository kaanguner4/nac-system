import logging
import bcrypt as _bcrypt
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.responses import JSONResponse, Response

from app.db.postgres import get_user, get_user_group, get_group_vlan
from app.db.redis import (
    check_rate_limit,
    increment_failed_attempts,
    reset_failed_attempts,
)
from app.security import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_api_key)])


# ─────────────────────────────────────────
# Request / Response şemaları
# ─────────────────────────────────────────

class AuthRequest(BaseModel):
    username: str
    password: str
    nas_ip: str = "127.0.0.1"
    calling_station_id: str = ""


class AuthResponse(BaseModel):
    result: str
    username: str
    reason: str = ""


class AuthorizeRequest(BaseModel):
    username: str


# ─────────────────────────────────────────
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    """bcrypt hash ile düz metin şifreyi karşılaştır."""
    try:
        return _bcrypt.checkpw(
            plain.encode("utf-8"),
            hashed.encode("utf-8")
        )
    except Exception:
        return False


def hash_password(plain: str) -> str:
    """Şifreyi bcrypt ile hashle."""
    return _bcrypt.hashpw(
        plain.encode("utf-8"),
        _bcrypt.gensalt()
    ).decode("utf-8")


def build_radius_reply(attributes: dict) -> dict:
    """FreeRADIUS rlm_rest için reply attribute gövdesi oluştur."""
    return {
        f"reply:{attribute}": {
            "op": ":=",
            "value": [value],
        }
        for attribute, value in attributes.items()
    }


# ─────────────────────────────────────────
# POST /auth — kimlik doğrulama
# ─────────────────────────────────────────

@router.post("/auth", response_model=AuthResponse)
async def authenticate(req: AuthRequest):
    logger.info(f"Auth isteği: {req.username} / NAS: {req.nas_ip}")

    # 1. Rate limit kontrolü
    allowed = await check_rate_limit(req.username)
    if not allowed:
        logger.warning(f"Rate limit: {req.username} bloklu")
        return JSONResponse(
            status_code=429,
            content=AuthResponse(
                result="reject",
                username=req.username,
                reason="too_many_attempts",
            ).model_dump(),
        )

    # 2. MAB kontrolü
    is_mab = (req.password == req.calling_station_id and
              req.calling_station_id != "")

    # 3. Kullanıcıyı veritabanından çek
    user = await get_user(req.username)
    if not user:
        await increment_failed_attempts(req.username)
        logger.warning(f"Kullanıcı bulunamadı: {req.username}")
        return JSONResponse(
            status_code=401,
            content=AuthResponse(
                result="reject",
                username=req.username,
                reason="user_not_found",
            ).model_dump(),
        )

    # 4. Şifre doğrulama
    if is_mab:
        password_ok = (req.username == req.calling_station_id)
    else:
        password_ok = verify_password(req.password, user["value"])

    if not password_ok:
        await increment_failed_attempts(req.username)
        logger.warning(f"Yanlış şifre: {req.username}")
        return JSONResponse(
            status_code=401,
            content=AuthResponse(
                result="reject",
                username=req.username,
                reason="wrong_password",
            ).model_dump(),
        )

    # 5. Başarılı giriş
    await reset_failed_attempts(req.username)
    logger.info(f"Auth başarılı: {req.username} (MAB: {is_mab})")

    return AuthResponse(
        result="accept",
        username=req.username,
    )


# ─────────────────────────────────────────
# POST /authorize — VLAN atama
# ─────────────────────────────────────────

@router.post("/authorize")
async def authorize(req: AuthorizeRequest):
    logger.info(f"Authorize isteği: {req.username}")

    # 1. Kullanıcının grubunu bul
    group_row = await get_user_group(req.username)
    if not group_row:
        logger.warning(f"Grup bulunamadı: {req.username}")
        return Response(status_code=404)

    groupname = group_row["groupname"]

    # 2. Grubun VLAN attribute'larını getir
    vlan_attrs = await get_group_vlan(groupname)
    if not vlan_attrs:
        logger.warning(f"VLAN bulunamadı: {groupname}")
        return Response(status_code=404)

    vlan_id = vlan_attrs.get("Tunnel-Private-Group-Id", "")
    logger.info(
        f"Authorize başarılı: {req.username} → "
        f"grup={groupname} vlan={vlan_id}"
    )

    radius_reply = build_radius_reply(vlan_attrs)
    radius_reply["reply:Reply-Message"] = {
        "op": ":=",
        "value": [f"group={groupname}, vlan={vlan_id}"],
    }

    return JSONResponse(content=radius_reply)
