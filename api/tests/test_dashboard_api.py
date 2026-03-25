import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app import security as security_module
from app.routes.dashboard_api import (
    DashboardCreateUserRequest,
    DashboardLoginRequest,
)


class DashboardRequestValidationTests(unittest.TestCase):
    def test_dashboard_login_rejects_blank_username(self):
        with self.assertRaises(ValidationError):
            DashboardLoginRequest(username="   ", password="admin123")

    def test_dashboard_login_rejects_blank_password(self):
        with self.assertRaises(ValidationError):
            DashboardLoginRequest(username="admin01", password="")

    def test_dashboard_create_user_rejects_blank_username(self):
        with self.assertRaises(ValidationError):
            DashboardCreateUserRequest(
                username="   ",
                groupname="guest",
                auth_type="pap",
                password="guest123",
            )

    def test_dashboard_create_user_rejects_invalid_mab_identifier(self):
        with self.assertRaises(ValidationError):
            DashboardCreateUserRequest(
                username="not-a-mac",
                groupname="employee",
                auth_type="mab",
            )

    def test_dashboard_create_user_normalizes_valid_mab_identifier(self):
        request = DashboardCreateUserRequest(
            username="AA:BB:CC:DD:EE:FF",
            groupname="employee",
            auth_type="mab",
        )

        self.assertEqual(request.username, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(request.password, "aa:bb:cc:dd:ee:ff")


class DashboardSessionSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_require_dashboard_user_accepts_active_session(self):
        token = security_module.create_dashboard_session_token(
            {
                "username": "admin01",
                "groupname": "admin",
                "session_id": "dash-1",
                "started_at": 0,
            }
        )

        with patch(
            "app.security.get_session",
            AsyncMock(return_value={"session_id": "dash-1", "status": "active"}),
        ):
            payload = await security_module.require_dashboard_user(token)

        self.assertEqual(payload["session_id"], "dash-1")
        self.assertEqual(payload["username"], "admin01")

    async def test_require_dashboard_user_rejects_inactive_session(self):
        token = security_module.create_dashboard_session_token(
            {
                "username": "admin01",
                "groupname": "admin",
                "session_id": "dash-2",
                "started_at": 0,
            }
        )

        with patch("app.security.get_session", AsyncMock(return_value={})):
            with self.assertRaises(HTTPException) as ctx:
                await security_module.require_dashboard_user(token)

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "dashboard_session_inactive")
