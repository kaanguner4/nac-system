import asyncpg
import os
import logging

logger = logging.getLogger(__name__)

_pool = None


async def init_db():
    global _pool
    try:
        _pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "postgres"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "radius"),
            user=os.getenv("POSTGRES_USER", "radius"),
            password=os.getenv("POSTGRES_PASSWORD"),
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("PostgreSQL bağlantı havuzu oluşturuldu")
    except Exception as e:
        logger.error(f"PostgreSQL bağlantısı kurulamadı: {e}")
        raise


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        logger.info("PostgreSQL bağlantı havuzu kapatıldı")


async def get_db():
    if _pool is None:
        raise RuntimeError("PostgreSQL bağlantı havuzu başlatılmadı")
    return _pool


# Veritabanı işlemleri için yardımcı fonksiyonlar
async def get_user(username: str):
    """radcheck tablosundan kullanıcıyı çek"""
    pool = await get_db()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT username, attribute, value
            FROM radcheck
            WHERE username = $1
              AND attribute = 'Cleartext-Password'
            """,
            username,
        )


async def get_user_group(username: str):
    """Kullanıcının grubunu getir"""
    pool = await get_db()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT groupname
            FROM radusergroup
            WHERE username = $1
            ORDER BY priority ASC
            LIMIT 1
            """,
            username,
        )


async def get_group_vlan(groupname: str):
    """Grubun VLAN attribute'larını getir"""
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT attribute, value
            FROM radgroupreply
            WHERE groupname = $1
            """,
            groupname,
        )
        return {row["attribute"]: row["value"] for row in rows}


async def get_all_users():
    """Tüm kullanıcıları listele"""
    pool = await get_db()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT r.username, r.groupname
            FROM radusergroup r
            ORDER BY r.username
            """
        )


async def get_latest_accounting_by_user():
    """Her kullanıcı için en güncel accounting kaydını getir."""
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (username)
                username,
                acctsessionid,
                acctuniqueid,
                acctstatustype,
                nasipaddress,
                callingstationid,
                framedipaddress,
                acctstarttime,
                acctupdatetime,
                acctstoptime,
                acctsessiontime,
                acctinputoctets,
                acctoutputoctets,
                COALESCE(
                    acctupdatetime,
                    acctstoptime,
                    acctstarttime
                ) AS last_activity
            FROM radacct
            ORDER BY
                username,
                COALESCE(acctupdatetime, acctstoptime, acctstarttime) DESC NULLS LAST,
                radacctid DESC
            """
        )

    return {
        row["username"]: {
            "session_id": row["acctsessionid"],
            "unique_id": row["acctuniqueid"],
            "status_type": row["acctstatustype"],
            "nas_ip": row["nasipaddress"],
            "calling_station_id": row["callingstationid"],
            "framed_ip": row["framedipaddress"],
            "start_time": row["acctstarttime"],
            "update_time": row["acctupdatetime"],
            "stop_time": row["acctstoptime"],
            "last_activity": row["last_activity"],
            "session_time": row["acctsessiontime"],
            "input_octets": row["acctinputoctets"],
            "output_octets": row["acctoutputoctets"],
        }
        for row in rows
    }


async def insert_accounting(data: dict):
    """Yeni accounting kaydı ekle ya da güncelle"""
    pool = await get_db()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO radacct (
                acctsessionid, acctuniqueid, username,
                nasipaddress, acctstarttime, acctstatustype,
                callingstationid, framedipaddress
            ) VALUES ($1,$2,$3,$4,NOW(),$5,$6,$7)
            ON CONFLICT (acctuniqueid)
            DO UPDATE SET
                acctupdatetime     = NOW(),
                acctstatustype     = EXCLUDED.acctstatustype,
                acctsessiontime    = $8,
                acctinputoctets    = $9,
                acctoutputoctets   = $10,
                acctstoptime       = CASE
                    WHEN EXCLUDED.acctstatustype = 'Stop'
                    THEN NOW() ELSE NULL END
            """,
            data.get("session_id"),
            data.get("unique_id"),
            data.get("username"),
            data.get("nas_ip"),
            data.get("status_type"),
            data.get("calling_station_id", ""),
            data.get("framed_ip", ""),
            data.get("session_time", 0),
            data.get("input_octets", 0),
            data.get("output_octets", 0),
        )
