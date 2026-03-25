import hmac
import os

from fastapi import Header, HTTPException


def get_api_secret_key() -> str:
    secret = os.getenv("API_SECRET_KEY", "")
    if not secret:
        raise RuntimeError("API_SECRET_KEY environment variable is not configured")
    return secret


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_api_secret_key()

    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
