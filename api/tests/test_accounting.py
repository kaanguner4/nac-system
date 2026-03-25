import unittest
from unittest.mock import AsyncMock, patch

from app.routes import accounting as accounting_module
from app.routes.accounting import AccountingRequest


class AccountingRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_accounting_falls_back_to_session_id_when_unique_id_blank(self):
        request = AccountingRequest(
            status_type="Start",
            session_id="sess-fallback",
            unique_id="",
            username="guest01",
        )

        with (
            patch("app.routes.accounting.insert_accounting", AsyncMock()) as insert_mock,
            patch("app.routes.accounting.set_session", AsyncMock()) as set_mock,
            patch("app.routes.accounting.delete_session", AsyncMock()),
        ):
            await accounting_module.accounting(request)

        insert_payload = insert_mock.await_args.args[0]
        self.assertEqual(insert_payload["unique_id"], "sess-fallback")
        cache_payload = set_mock.await_args.args[1]
        self.assertEqual(cache_payload["unique_id"], "sess-fallback")

    async def test_accounting_start_writes_db_and_cache(self):
        request = AccountingRequest(
            status_type="Start",
            session_id="sess-1",
            unique_id="uniq-1",
            username="guest01",
            nas_ip="10.0.0.20",
            calling_station_id="cc:cc:cc:cc:cc:cc",
            framed_ip="192.168.1.30",
            session_time=0,
            input_octets=0,
            output_octets=0,
        )

        with (
            patch("app.routes.accounting.insert_accounting", AsyncMock()) as insert_mock,
            patch("app.routes.accounting.set_session", AsyncMock()) as set_mock,
            patch("app.routes.accounting.delete_session", AsyncMock()),
        ):
            response = await accounting_module.accounting(request)

        self.assertEqual(response, {"result": "ok"})
        insert_mock.assert_awaited_once()
        set_mock.assert_awaited_once_with(
            "sess-1",
            {
                "username": "guest01",
                "nas_ip": "10.0.0.20",
                "framed_ip": "192.168.1.30",
                "status": "active",
                "session_id": "sess-1",
                "unique_id": "uniq-1",
                "session_time": "0",
                "input_octets": "0",
                "output_octets": "0",
            },
        )

    async def test_accounting_interim_update_refreshes_cache(self):
        request = AccountingRequest(
            status_type="Interim-Update",
            session_id="sess-1",
            unique_id="uniq-1",
            username="guest01",
            nas_ip="10.0.0.20",
            calling_station_id="cc:cc:cc:cc:cc:cc",
            framed_ip="192.168.1.30",
            session_time=60,
            input_octets=128,
            output_octets=256,
        )

        with (
            patch("app.routes.accounting.insert_accounting", AsyncMock()) as insert_mock,
            patch("app.routes.accounting.set_session", AsyncMock()) as set_mock,
            patch("app.routes.accounting.delete_session", AsyncMock()),
        ):
            response = await accounting_module.accounting(request)

        self.assertEqual(response, {"result": "ok"})
        insert_mock.assert_awaited_once()
        set_mock.assert_awaited_once_with(
            "sess-1",
            {
                "username": "guest01",
                "nas_ip": "10.0.0.20",
                "framed_ip": "192.168.1.30",
                "status": "active",
                "session_id": "sess-1",
                "unique_id": "uniq-1",
                "session_time": "60",
                "input_octets": "128",
                "output_octets": "256",
            },
        )

    async def test_accounting_stop_deletes_cache_entry(self):
        request = AccountingRequest(
            status_type="Stop",
            session_id="sess-1",
            unique_id="uniq-1",
            username="guest01",
            session_time=120,
            input_octets=128,
            output_octets=256,
        )

        with (
            patch("app.routes.accounting.insert_accounting", AsyncMock()) as insert_mock,
            patch("app.routes.accounting.set_session", AsyncMock()),
            patch("app.routes.accounting.delete_session", AsyncMock()) as delete_mock,
        ):
            response = await accounting_module.accounting(request)

        self.assertEqual(response, {"result": "ok"})
        insert_mock.assert_awaited_once()
        delete_mock.assert_awaited_once_with("sess-1")
