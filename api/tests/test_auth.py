import json
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from app.routes import auth as auth_module
from app.routes.auth import AuthRequest, AuthorizeRequest


class AuthHelperTests(unittest.TestCase):
    def test_auth_request_rejects_blank_username(self):
        with self.assertRaises(ValidationError):
            AuthRequest(username="   ", password="admin123")

    def test_auth_request_rejects_blank_password(self):
        with self.assertRaises(ValidationError):
            AuthRequest(username="admin01", password="")

    def test_authorize_request_rejects_blank_username(self):
        with self.assertRaises(ValidationError):
            AuthorizeRequest(username="   ")

    def test_verify_password_accepts_valid_bcrypt_hash(self):
        hashed = auth_module.hash_password("admin123")

        self.assertTrue(auth_module.verify_password("admin123", hashed))
        self.assertFalse(auth_module.verify_password("wrongpass", hashed))

    def test_build_radius_reply_formats_rlm_rest_payload(self):
        reply = auth_module.build_radius_reply(
            {
                "Tunnel-Type": "13",
                "Tunnel-Private-Group-Id": "10",
            }
        )

        self.assertEqual(reply["reply:Tunnel-Type"]["op"], ":=")
        self.assertEqual(reply["reply:Tunnel-Type"]["value"], ["13"])
        self.assertEqual(
            reply["reply:Tunnel-Private-Group-Id"]["value"],
            ["10"],
        )


class AuthRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticate_accepts_pap_credentials(self):
        hashed = auth_module.hash_password("admin123")
        request = AuthRequest(username="admin01", password="admin123")

        with (
            patch("app.routes.auth.check_rate_limit", AsyncMock(return_value=True)),
            patch(
                "app.routes.auth.get_user",
                AsyncMock(return_value={"attribute": "Password-Hash", "value": hashed}),
            ),
            patch("app.routes.auth.reset_failed_attempts", AsyncMock()) as reset_mock,
            patch("app.routes.auth.increment_failed_attempts", AsyncMock()),
        ):
            response = await auth_module.authenticate(request)

        self.assertEqual(response.result, "accept")
        self.assertEqual(response.username, "admin01")
        self.assertEqual(response.reason, "pap_authentication_successful")
        reset_mock.assert_awaited_once_with("admin01")

    async def test_authenticate_returns_429_when_rate_limited(self):
        request = AuthRequest(username="admin01", password="admin123")

        with patch("app.routes.auth.check_rate_limit", AsyncMock(return_value=False)):
            response = await auth_module.authenticate(request)

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(body["result"], "reject")
        self.assertEqual(body["reason"], "too_many_attempts")

    async def test_authenticate_accepts_registered_mab_device(self):
        request = AuthRequest(
            username="aa:bb:cc:dd:ee:ff",
            password="aa:bb:cc:dd:ee:ff",
            calling_station_id="aa:bb:cc:dd:ee:ff",
        )

        with (
            patch("app.routes.auth.check_rate_limit", AsyncMock(return_value=True)),
            patch(
                "app.routes.auth.get_user",
                AsyncMock(
                    return_value={
                        "attribute": "Device-MAC",
                        "value": "aa:bb:cc:dd:ee:ff",
                    }
                ),
            ),
            patch("app.routes.auth.reset_failed_attempts", AsyncMock()) as reset_mock,
            patch("app.routes.auth.increment_failed_attempts", AsyncMock()),
        ):
            response = await auth_module.authenticate(request)

        self.assertEqual(response.result, "accept")
        self.assertEqual(response.reason, "mab_authentication_successful")
        reset_mock.assert_awaited_once_with("aa:bb:cc:dd:ee:ff")

    async def test_authenticate_rejects_unknown_user(self):
        request = AuthRequest(username="ghost", password="badpass")

        with (
            patch("app.routes.auth.check_rate_limit", AsyncMock(return_value=True)),
            patch("app.routes.auth.get_user", AsyncMock(return_value=None)),
            patch("app.routes.auth.increment_failed_attempts", AsyncMock()) as fail_mock,
        ):
            response = await auth_module.authenticate(request)

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(body["reason"], "user_not_found")
        fail_mock.assert_awaited_once_with("ghost")

    async def test_authorize_returns_vlan_attributes(self):
        request = AuthorizeRequest(username="admin01")

        with (
            patch(
                "app.routes.auth.get_user_group",
                AsyncMock(return_value={"groupname": "admin"}),
            ),
            patch(
                "app.routes.auth.get_group_vlan",
                AsyncMock(
                    return_value={
                        "Tunnel-Type": "13",
                        "Tunnel-Medium-Type": "6",
                        "Tunnel-Private-Group-Id": "10",
                    }
                ),
            ),
        ):
            response = await auth_module.authorize(request)

        body = json.loads(response.body)
        self.assertEqual(body["reply:Tunnel-Type"]["value"], ["13"])
        self.assertEqual(body["reply:Tunnel-Private-Group-Id"]["value"], ["10"])
        self.assertEqual(body["reply:Reply-Message"]["value"], ["group=admin, vlan=10"])
