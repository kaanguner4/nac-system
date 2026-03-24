import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from passlib.context import CryptContext

from app.db.postgres import get_user, get_user_group, get_group_vlan
from app.db.redis import (
    check_rate_limit,
    increment_failed_attempts,
    reset_failed_attempts,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# bcrypt context - şifre doğrulama için
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



# Request / Response şemaları

class AuthRequest(BaseModel):
    username: str
    password: str
    nas_ip: str = "127.0.0.1" # Opsiyonel, NAS IP'si
    calling_station_id: str = "" # Opsiyonel, MAB cihaz için MAC adresi


class AuthResponse(BaseModel):
    result: str           # "accept" veya "reject"
    username: str
    reason: str = ""


class AuthorizeRequest(BaseModel):
    username: str


class AuthorizeResponse(BaseModel):
    result: str
    username: str
    vlan: str = ""
    attributes: dict = {}



# Yardımcı fonksiyon - şifre doğrulama
def verify_password(plain: str, hashed: str) -> bool:
    """
    bcrypt hash ile düz metin şifreyi karşılaştır.
    Geliştirme aşamasında plaintext de desteklenir.
    """
    # Cleartext-Password ise doğrudan karşılaştır (geliştirme / test için)
    if not hashed.startswith("$2b$"):
        return plain == hashed
    # bcrypt hash ise pwd_context kullanarak doğrula (production için)
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    """ Şifreyi bcrypt ile hash'le (production için) """
    return pwd_context.hash(plain)



# POST /auth — kimlik doğrulama
# FreeRADIUS rlm_rest bu endpoint'i çağırır

@router.post("/auth", response_model=AuthResponse)
async def authenticate(req: AuthRequest):
    logger.info(f"Auth isteği: {req.username} / NAS: {req.nas_ip}")

    # 1. Rate limit kontrolü
    allowed = await check_rate_limit(req.username)
    if not allowed:
        logger.warning(f"Rate limit: {req.username} bloklu")
        return AuthResponse(
            result="reject",
            username=req.username,
            reason="too_many_attempts",
        )

    # 2. MAB kontrolü — şifre MAC adresine eşitse MAB isteği
    is_mab = (req.password == req.calling_station_id and
              req.calling_station_id != "")

    # 3. Kullanıcıyı veritabanından çek
    user = await get_user(req.username)
    if not user:
        await increment_failed_attempts(req.username)
        logger.warning(f"Kullanıcı bulunamadı: {req.username}")
        return AuthResponse(
            result="reject",
            username=req.username,
            reason="user_not_found",
        )

    # 4. Şifre doğrulama
    if is_mab:
        # MAB: MAC adresi hem username hem password olarak gelir
        password_ok = (req.username == req.calling_station_id)
    else:
        password_ok = verify_password(req.password, user["value"])

    if not password_ok:
        await increment_failed_attempts(req.username)
        logger.warning(f"Yanlış şifre: {req.username}")
        return AuthResponse(
            result="reject",
            username=req.username,
            reason="wrong_password",
        )

    # 5. Başarılı giriş — sayacı sıfırla
    await reset_failed_attempts(req.username)
    logger.info(f"Auth başarılı: {req.username} (MAB: {is_mab})")

    return AuthResponse(
        result="accept",
        username=req.username,
    )



# POST /authorize — VLAN atama
# FreeRADIUS rlm_rest bu endpoint'i çağırır

@router.post("/authorize", response_model=AuthorizeResponse)
async def authorize(req: AuthorizeRequest):
    logger.info(f"Authorize isteği: {req.username}")

    # 1. Kullanıcının grubunu bul
    group_row = await get_user_group(req.username)
    if not group_row:
        logger.warning(f"Grup bulunamadı: {req.username}")
        return AuthorizeResponse(
            result="reject",
            username=req.username,
        )

    groupname = group_row["groupname"]

    # 2. Grubun VLAN attribute'larını getir
    vlan_attrs = await get_group_vlan(groupname)
    if not vlan_attrs:
        logger.warning(f"VLAN bulunamadı: {groupname}")
        return AuthorizeResponse(
            result="reject",
            username=req.username,
        )

    vlan_id = vlan_attrs.get("Tunnel-Private-Group-Id", "")
    logger.info(f"Authorize başarılı: {req.username} → "
                f"grup={groupname} vlan={vlan_id}")

    return AuthorizeResponse(
        result="accept",
        username=req.username,
        vlan=vlan_id,
        attributes=vlan_attrs,
    )