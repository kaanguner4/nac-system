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
    """radcheck tablosundan kullanıcının auth kaydını çek."""
    pool = await get_db()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT username, attribute, value
            FROM radcheck
            WHERE username = $1
              AND attribute IN ('Password-Hash', 'Device-MAC')
            ORDER BY CASE attribute
                WHEN 'Password-Hash' THEN 1
                WHEN 'Device-MAC' THEN 2
                ELSE 99
            END
            LIMIT 1
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


async def get_group_policies():
    """Tüm grup bazlı policy attribute'larını getir."""
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT groupname, attribute, value
            FROM radgroupreply
            ORDER BY groupname, attribute
            """
        )

    policies = {}
    for row in rows:
        policies.setdefault(row["groupname"], {})[row["attribute"]] = row["value"]
    return policies


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


def _serialize_accounting_row(row) -> dict:
    return {
        "session_id": row["acctsessionid"],
        "unique_id": row["acctuniqueid"],
        "username": row["username"],
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

    return {row["username"]: _serialize_accounting_row(row) for row in rows}


async def get_active_accounting_sessions():
    """radacct tablosundan halen aktif görünen oturumları getir."""
    pool = await get_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                acctsessionid,
                acctuniqueid,
                username,
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
                COALESCE(acctupdatetime, acctstarttime) AS last_activity
            FROM radacct
            WHERE acctstoptime IS NULL
              AND acctstatustype IN ('Start', 'Interim-Update')
            ORDER BY
                COALESCE(acctupdatetime, acctstarttime) DESC NULLS LAST,
                radacctid DESC
            """
        )

    sessions = []
    for row in rows:
        session = _serialize_accounting_row(row)
        session["status"] = "active"
        sessions.append(session)

    return sessions


async def create_user(
    username: str,
    attribute: str,
    value: str,
    groupname: str,
    priority: int = 1,
):
    """Yeni PAP veya MAB kimliği oluştur."""
    pool = await get_db()
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM radcheck WHERE username = $1
                ) OR EXISTS(
                    SELECT 1 FROM radusergroup WHERE username = $1
                )
                """,
                username,
            )
            if existing:
                raise ValueError("user_exists")

            group_exists = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM radgroupreply WHERE groupname = $1
                )
                """,
                groupname,
            )
            if not group_exists:
                raise ValueError("invalid_group")

            await conn.execute(
                """
                INSERT INTO radcheck (username, attribute, op, value)
                VALUES ($1, $2, ':=', $3)
                """,
                username,
                attribute,
                value,
            )
            await conn.execute(
                """
                INSERT INTO radusergroup (username, groupname, priority)
                VALUES ($1, $2, $3)
                """,
                username,
                groupname,
                priority,
            )

    return {
        "username": username,
        "attribute": attribute,
        "groupname": groupname,
        "priority": priority,
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
                acctstarttime      = CASE
                    WHEN EXCLUDED.acctstatustype = 'Start'
                    THEN NOW()
                    ELSE radacct.acctstarttime END,
                acctstoptime       = CASE
                    WHEN EXCLUDED.acctstatustype = 'Stop'  THEN NOW()
                    WHEN EXCLUDED.acctstatustype = 'Start' THEN NULL
                    ELSE radacct.acctstoptime END
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
