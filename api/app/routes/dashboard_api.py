import asyncio
import json
import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, model_validator
from starlette.responses import JSONResponse

from app.db.postgres import (
    create_user,
    get_all_users,
    get_group_policies,
    get_group_vlan,
    get_latest_accounting_by_user,
    get_active_accounting_sessions,
    get_user_group,
)
from app.db.redis import get_all_active_sessions, get_all_blocked_users, get_session
from app.routes.accounting import AccountingRequest, accounting
from app.routes.auth import AuthRequest, authenticate, hash_password
from app.routes.users import build_active_session_state
from app.security import (
    clear_dashboard_session_cookie,
    require_admin_dashboard_user,
    require_dashboard_user,
    set_dashboard_session_cookie,
)


router = APIRouter(prefix="/dashboard-api", tags=["dashboard"])


ROLE_LABELS = {
    "admin": "ADMINISTRATOR",
    "employee": "EMPLOYEE",
    "guest": "GUEST",
    "mab": "DEVICE (MAB)",
}


class DashboardLoginRequest(BaseModel):
    username: str
    password: str
    calling_station_id: str = ""


class DashboardPulseRequest(BaseModel):
    session_time: int = Field(ge=0)
    input_octets: int = Field(ge=0)
    output_octets: int = Field(ge=0)


class DashboardCreateUserRequest(BaseModel):
    username: str
    groupname: Literal["admin", "employee", "guest"]
    auth_type: Literal["pap", "mab"] = "pap"
    password: str | None = None

    @model_validator(mode="after")
    def validate_payload(self):
        self.username = self.username.strip().lower() if self.auth_type == "mab" else self.username.strip()
        self.groupname = self.groupname.strip().lower()

        if self.auth_type == "pap":
            if not self.password:
                raise ValueError("password_required_for_pap")
        else:
            self.password = self.username

        return self


def _response_payload(response):
    if isinstance(response, JSONResponse):
        return json.loads(response.body)
    if hasattr(response, "model_dump"):
        return response.model_dump()
    return response


def _pseudo_mac(seed: str) -> str:
    digest = secrets.token_hex(3)
    seed_bytes = seed.encode("utf-8")
    parts = [
        f"{(seed_bytes[index % len(seed_bytes)] + index * 11) % 256:02x}"
        for index in range(5)
    ]
    return ":".join(["02"] + parts[:-1] + [digest[:2]])


def _framed_ip_for_group(groupname: str, username: str) -> str:
    host = 10 + (sum(username.encode("utf-8")) % 200)
    if groupname == "admin":
        return f"10.10.0.{host}"
    if groupname == "employee":
        return f"192.168.20.{host}"
    return f"172.16.30.{host}"


async def _build_dashboard_user_rows():
    (
        rows,
        redis_sessions,
        blocked_users,
        last_accounting,
        db_active_sessions,
        group_policies,
    ) = await asyncio.gather(
        get_all_users(),
        get_all_active_sessions(),
        get_all_blocked_users(),
        get_latest_accounting_by_user(),
        get_active_accounting_sessions(),
        get_group_policies(),
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

    return {
        "users": users,
        "sessions": merged_active_sessions,
        "group_policies": group_policies,
        "summary": {
            "total_users": len(users),
            "active_users": active_user_count,
            "blocked_users": blocked_user_count,
            "active_sessions": len(merged_active_sessions),
            "cache_only_sessions": len(orphaned_cache_sessions),
            "source_of_truth": "postgres",
        },
    }


def _filter_overview_for_viewer(overview: dict, viewer: dict):
    if viewer.get("groupname") == "admin":
        return overview

    username = viewer["username"]
    session_id = viewer.get("session_id")

    users = [user for user in overview["users"] if user["username"] == username]
    sessions = [
        session
        for session in overview["sessions"]
        if session["username"] == username or session["session_id"] == session_id
    ]
    groupname = viewer.get("groupname", "guest")

    return {
        "users": users,
        "sessions": sessions,
        "group_policies": {
            groupname: overview["group_policies"].get(groupname, {})
        },
        "summary": {
            "total_users": len(users),
            "active_users": sum(1 for user in users if user["active"]),
            "blocked_users": sum(1 for user in users if user["blocked"]),
            "active_sessions": len(sessions),
            "cache_only_sessions": 0,
            "source_of_truth": "postgres",
        },
    }


async def _start_dashboard_session(
    username: str,
    groupname: str,
    auth_method: str,
    calling_station_id: str,
):
    vlan_attrs = await get_group_vlan(groupname)
    vlan_id = vlan_attrs.get("Tunnel-Private-Group-Id", "")

    session_id = f"dash-{secrets.token_hex(6)}"
    unique_id = session_id
    nas_ip = "10.0.0.5" if auth_method == "mab" else "10.0.0.1"
    framed_ip = _framed_ip_for_group(groupname, username)
    effective_calling_station = calling_station_id or _pseudo_mac(username)

    await accounting(
        AccountingRequest(
            status_type="Start",
            session_id=session_id,
            unique_id=unique_id,
            username=username,
            nas_ip=nas_ip,
            calling_station_id=effective_calling_station,
            framed_ip=framed_ip,
            session_time=0,
            input_octets=0,
            output_octets=0,
        )
    )

    return {
        "username": username,
        "groupname": groupname,
        "role_label": ROLE_LABELS.get(groupname, groupname.upper()),
        "auth_method": auth_method,
        "vlan": vlan_id,
        "reply_attributes": vlan_attrs,
        "session_id": session_id,
        "unique_id": unique_id,
        "nas_ip": nas_ip,
        "framed_ip": framed_ip,
        "calling_station_id": effective_calling_station,
        "started_at": int(time.time()),
    }


@router.post("/login")
async def dashboard_login(request: DashboardLoginRequest, response: Response):
    username = request.username.strip()
    password = request.password
    calling_station_id = request.calling_station_id.strip().lower()

    if not calling_station_id and ":" in username and password == username:
        calling_station_id = username.lower()
    if calling_station_id:
        username = username.lower()
        password = password.lower()

    auth_result = await authenticate(
        AuthRequest(
            username=username,
            password=password,
            calling_station_id=calling_station_id,
            nas_ip="10.0.0.1",
        )
    )

    if isinstance(auth_result, JSONResponse):
        payload = _response_payload(auth_result)
        raise HTTPException(status_code=auth_result.status_code, detail=payload)

    group_row = await get_user_group(username)
    if not group_row:
        raise HTTPException(status_code=404, detail="group_not_found")

    auth_method = "mab" if calling_station_id else "pap"
    viewer = await _start_dashboard_session(
        username=username,
        groupname=group_row["groupname"],
        auth_method=auth_method,
        calling_station_id=calling_station_id,
    )
    set_dashboard_session_cookie(response, viewer)

    return {
        "viewer": viewer,
        "can_manage_users": viewer["groupname"] == "admin",
    }


@router.get("/me")
async def dashboard_me(viewer: dict = Depends(require_dashboard_user)):
    return {
        "viewer": viewer,
        "can_manage_users": viewer.get("groupname") == "admin",
    }


@router.get("/overview")
async def dashboard_overview(viewer: dict = Depends(require_dashboard_user)):
    overview = await _build_dashboard_user_rows()
    filtered = _filter_overview_for_viewer(overview, viewer)

    current_user = next(
        (user for user in overview["users"] if user["username"] == viewer["username"]),
        None,
    )
    current_session = next(
        (
            session
            for session in overview["sessions"]
            if session["session_id"] == viewer.get("session_id")
        ),
        None,
    )

    return {
        "viewer": viewer,
        "current_user": current_user,
        "current_session": current_session,
        "can_manage_users": viewer.get("groupname") == "admin",
        **filtered,
    }


@router.post("/pulse")
async def dashboard_pulse(
    request: DashboardPulseRequest,
    viewer: dict = Depends(require_dashboard_user),
):
    await accounting(
        AccountingRequest(
            status_type="Interim-Update",
            session_id=viewer["session_id"],
            unique_id=viewer["unique_id"],
            username=viewer["username"],
            nas_ip=viewer["nas_ip"],
            calling_station_id=viewer.get("calling_station_id", ""),
            framed_ip=viewer.get("framed_ip", ""),
            session_time=request.session_time,
            input_octets=request.input_octets,
            output_octets=request.output_octets,
        )
    )
    return {"result": "ok"}


@router.post("/logout")
async def dashboard_logout(
    response: Response,
    viewer: dict = Depends(require_dashboard_user),
):
    session_cache = await get_session(viewer["session_id"])

    session_time = int(
        session_cache.get("session_time")
        or max(int(time.time()) - int(viewer.get("started_at", time.time())), 0)
    )
    input_octets = int(session_cache.get("input_octets") or 0)
    output_octets = int(session_cache.get("output_octets") or 0)

    await accounting(
        AccountingRequest(
            status_type="Stop",
            session_id=viewer["session_id"],
            unique_id=viewer["unique_id"],
            username=viewer["username"],
            nas_ip=viewer["nas_ip"],
            calling_station_id=viewer.get("calling_station_id", ""),
            framed_ip=viewer.get("framed_ip", ""),
            session_time=session_time,
            input_octets=input_octets,
            output_octets=output_octets,
        )
    )
    clear_dashboard_session_cookie(response)
    return {"result": "ok"}


@router.post("/users")
async def dashboard_create_user(
    request: DashboardCreateUserRequest,
    admin: dict = Depends(require_admin_dashboard_user),
):
    del admin

    attribute = "Password-Hash" if request.auth_type == "pap" else "Device-MAC"
    value = hash_password(request.password) if request.auth_type == "pap" else request.username

    try:
        created_user = await create_user(
            username=request.username,
            attribute=attribute,
            value=value,
            groupname=request.groupname,
        )
    except ValueError as exc:
        if str(exc) == "user_exists":
            raise HTTPException(status_code=409, detail="user_exists") from exc
        if str(exc) == "invalid_group":
            raise HTTPException(status_code=400, detail="invalid_group") from exc
        raise

    vlan_attrs = await get_group_vlan(request.groupname)
    return {
        "result": "created",
        "user": created_user,
        "vlan": vlan_attrs.get("Tunnel-Private-Group-Id"),
    }
