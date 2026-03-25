import redis.asyncio as aioredis
import os
import logging

logger = logging.getLogger(__name__)

_redis = None



# Redis bağlantı yönetimi

async def init_redis():
    global _redis
    try:
        _redis = await aioredis.from_url(
            f"redis://:{os.getenv('REDIS_PASSWORD')}@"
            f"{os.getenv('REDIS_HOST', 'redis')}:6379",
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
        )
        await _redis.ping()
        logger.info("Redis bağlantısı kuruldu")
    except Exception as e:
        logger.error(f"Redis bağlantısı kurulamadı: {e}")
        raise


async def close_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        logger.info("Redis bağlantısı kapatıldı")


async def get_redis():
    if _redis is None:
        raise RuntimeError("Redis bağlantısı henüz başlatılmadı")
    return _redis



# Session cache - aktif oturumlar

async def set_session(session_id: str, data: dict, ttl: int = 86400):
    """
    Aktif oturumu Redis'e yaz.
    ttl: saniye cinsinden süre (varsayılan 24 saat)
    """
    r = await get_redis()
    key = f"session:{session_id}"
    await r.hset(key, mapping=data)
    await r.expire(key, ttl)
    logger.debug(f"Oturum kaydedildi: {key}")


async def get_session(session_id: str):
    """Oturumu Redis'ten oku"""
    r = await get_redis()
    key = f"session:{session_id}"
    return await r.hgetall(key)


async def delete_session(session_id: str):
    """Oturum bitince Redis'ten sil"""
    r = await get_redis()
    key = f"session:{session_id}"
    await r.delete(key)
    logger.debug(f"Oturum silindi: {key}")


async def get_all_active_sessions():
    """Tüm aktif oturumları listele"""
    r = await get_redis()
    keys = await r.keys("session:*")
    sessions = []
    for key in keys:
        data = await r.hgetall(key)
        if data:
            sessions.append(data)
    return sessions


async def get_all_blocked_users():
    """Rate-limit nedeniyle bloklu kullanıcıları ve kalan TTL değerlerini getir"""
    r = await get_redis()
    keys = await r.keys("blocked:*")
    blocked_users = {}

    for key in keys:
        username = key.split(":", 1)[1]
        blocked_users[username] = await r.ttl(key)

    return blocked_users



# Rate limiting - başarısız giriş sayacı

RATE_LIMIT_MAX      = 5    # maksimum başarısız deneme
RATE_LIMIT_WINDOW   = 300  # 5 dakika (saniye)
RATE_LIMIT_BLOCK    = 900  # blok süresi: 15 dakika


async def check_rate_limit(username: str) -> bool:
    """
    Kullanıcı bloklu mu kontrol et.
    True  → giriş yapabilir
    False → bloklu, giriş yapamaz
    """
    r = await get_redis()
    block_key = f"blocked:{username}"

    if await r.exists(block_key):
        ttl = await r.ttl(block_key)
        logger.warning(
            f"Bloklu kullanıcı giriş denemesi: {username} "
            f"({ttl} saniye kaldı)"
        )
        return False
    return True


async def increment_failed_attempts(username: str) -> int:
    """
    Başarısız deneme sayacını artır.
    Limit aşılırsa kullanıcıyı blokla.
    Kaç deneme kaldığını döner.
    """
    r = await get_redis()
    fail_key  = f"fail:{username}"
    block_key = f"blocked:{username}"

    count = await r.incr(fail_key)

    if count == 1:
        # İlk başarısız denemede pencereyi başlat
        await r.expire(fail_key, RATE_LIMIT_WINDOW)

    logger.debug(f"Başarısız deneme: {username} → {count}/{RATE_LIMIT_MAX}")

    if count >= RATE_LIMIT_MAX:
        await r.set(block_key, "1", ex=RATE_LIMIT_BLOCK)
        await r.delete(fail_key)
        logger.warning(
            f"Kullanıcı bloklandı: {username} "
            f"({RATE_LIMIT_BLOCK} saniye)"
        )

    return count


async def reset_failed_attempts(username: str):
    """
    Başarılı girişte sayacı sıfırla.
    """
    r = await get_redis()
    await r.delete(f"fail:{username}")
    logger.debug(f"Başarısız deneme sayacı sıfırlandı: {username}")
