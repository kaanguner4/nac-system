import base64
import hashlib
import json
import hmac
import os
import time
from typing import Any

from fastapi import Cookie, Depends, Header, HTTPException, Response

from app.db.redis import get_session


DASHBOARD_SESSION_COOKIE = "nac_dashboard_session"
DASHBOARD_SESSION_MAX_AGE = 60 * 60 * 12


def get_api_secret_key() -> str:
    secret = os.getenv("API_SECRET_KEY", "")
    if not secret:
        raise RuntimeError("API_SECRET_KEY environment variable is not configured")
    return secret


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_api_secret_key()

    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _dashboard_signing_secret() -> bytes:
    return f"{get_api_secret_key()}:dashboard".encode("utf-8")


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(f"{encoded}{padding}".encode("utf-8"))


def create_dashboard_session_token(session_data: dict[str, Any]) -> str:
    payload = dict(session_data)
    payload["exp"] = int(time.time()) + DASHBOARD_SESSION_MAX_AGE

    encoded_payload = _urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        _dashboard_signing_secret(),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded_payload}.{signature}"


def decode_dashboard_session_token(token: str) -> dict[str, Any]:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("invalid_token_format") from exc

    expected_signature = hmac.new(
        _dashboard_signing_secret(),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("invalid_token_signature")

    payload = json.loads(_urlsafe_b64decode(encoded_payload).decode("utf-8"))
    if payload.get("exp", 0) < int(time.time()):
        raise ValueError("session_expired")

    return payload


def set_dashboard_session_cookie(
    response: Response,
    session_data: dict[str, Any],
) -> None:
    response.set_cookie(
        key=DASHBOARD_SESSION_COOKIE,
        value=create_dashboard_session_token(session_data),
        httponly=True,
        max_age=DASHBOARD_SESSION_MAX_AGE,
        samesite="lax",
        secure=True,
    )


def clear_dashboard_session_cookie(response: Response) -> None:
    response.delete_cookie(DASHBOARD_SESSION_COOKIE)


async def require_dashboard_user(
    nac_dashboard_session: str | None = Cookie(
        default=None,
        alias=DASHBOARD_SESSION_COOKIE,
    ),
) -> dict[str, Any]:
    if nac_dashboard_session is None:
        raise HTTPException(status_code=401, detail="Dashboard session required")

    try:
        user = decode_dashboard_session_token(nac_dashboard_session)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    session_id = user.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="invalid_dashboard_session")

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="dashboard_session_inactive")

    return user


async def require_admin_dashboard_user(
    user: dict[str, Any] = Depends(require_dashboard_user),
) -> dict[str, Any]:
    if user.get("groupname") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user
