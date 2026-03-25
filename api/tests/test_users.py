import unittest
from unittest.mock import AsyncMock, patch

from app.routes import users as users_module


class UserSessionStateTests(unittest.TestCase):
    def test_build_active_session_state_merges_database_and_cache(self):
        redis_sessions = [
            {
                "session_id": "sess-1",
                "username": "admin01",
                "status": "active",
                "input_octets": "128",
            }
        ]
        db_sessions = [
            {
                "session_id": "sess-1",
                "unique_id": "uniq-1",
                "username": "admin01",
                "status_type": "Start",
                "nas_ip": "10.0.0.10",
                "calling_station_id": "aa:aa:aa:aa:aa:aa",
                "framed_ip": "192.168.1.10",
                "start_time": "2026-03-25T10:00:00Z",
                "update_time": None,
                "stop_time": None,
                "last_activity": "2026-03-25T10:00:00Z",
                "session_time": 10,
                "input_octets": 64,
                "output_octets": 32,
            }
        ]

        sessions, active_by_user, orphaned = users_module.build_active_session_state(
            redis_sessions,
            db_sessions,
        )

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["source"], "postgres+redis")
        self.assertEqual(sessions[0]["input_octets"], "128")
        self.assertEqual(active_by_user["admin01"][0]["session_id"], "sess-1")
        self.assertEqual(orphaned, [])

    def test_build_active_session_state_marks_cache_orphans(self):
        sessions, _, orphaned = users_module.build_active_session_state(
            [{"session_id": "ghost-1", "username": "ghost"}],
            [],
        )

        self.assertEqual(sessions, [])
        self.assertEqual(orphaned[0]["source"], "redis_orphan")
        self.assertEqual(orphaned[0]["status"], "cache_only")


class UserRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_users_aggregates_statuses_and_counts(self):
        with (
            patch(
                "app.routes.users.get_all_users",
                AsyncMock(
                    return_value=[
                        {"username": "admin01", "groupname": "admin"},
                        {"username": "guest01", "groupname": "guest"},
                    ]
                ),
            ),
            patch(
                "app.routes.users.get_all_active_sessions",
                AsyncMock(
                    return_value=[
                        {
                            "session_id": "sess-1",
                            "username": "admin01",
                            "status": "active",
                            "input_octets": "128",
                        }
                    ]
                ),
            ),
            patch(
                "app.routes.users.get_all_blocked_users",
                AsyncMock(return_value={"guest01": 300}),
            ),
            patch(
                "app.routes.users.get_latest_accounting_by_user",
                AsyncMock(return_value={"admin01": {"session_id": "sess-1"}}),
            ),
            patch(
                "app.routes.users.get_active_accounting_sessions",
                AsyncMock(
                    return_value=[
                        {
                            "session_id": "sess-1",
                            "unique_id": "uniq-1",
                            "username": "admin01",
                            "status_type": "Start",
                            "nas_ip": "10.0.0.10",
                            "calling_station_id": "aa:aa:aa:aa:aa:aa",
                            "framed_ip": "192.168.1.10",
                            "start_time": "2026-03-25T10:00:00Z",
                            "update_time": None,
                            "stop_time": None,
                            "last_activity": "2026-03-25T10:00:00Z",
                            "session_time": 10,
                            "input_octets": 64,
                            "output_octets": 32,
                        }
                    ]
                ),
            ),
        ):
            response = await users_module.list_users()

        self.assertEqual(response["total"], 2)
        self.assertEqual(response["active_users"], 1)
        self.assertEqual(response["blocked_users"], 1)
        self.assertEqual(response["users"][0]["status"], "active")
        self.assertEqual(response["users"][1]["status"], "blocked")

    async def test_active_sessions_returns_postgres_source_of_truth(self):
        with (
            patch(
                "app.routes.users.get_all_active_sessions",
                AsyncMock(
                    return_value=[
                        {
                            "session_id": "cache-only",
                            "username": "guest01",
                            "status": "active",
                        }
                    ]
                ),
            ),
            patch(
                "app.routes.users.get_active_accounting_sessions",
                AsyncMock(
                    return_value=[
                        {
                            "session_id": "sess-1",
                            "unique_id": "uniq-1",
                            "username": "admin01",
                            "status_type": "Interim-Update",
                            "nas_ip": "10.0.0.10",
                            "calling_station_id": "aa:aa:aa:aa:aa:aa",
                            "framed_ip": "192.168.1.10",
                            "start_time": "2026-03-25T10:00:00Z",
                            "update_time": "2026-03-25T10:01:00Z",
                            "stop_time": None,
                            "last_activity": "2026-03-25T10:01:00Z",
                            "session_time": 60,
                            "input_octets": 128,
                            "output_octets": 256,
                        }
                    ]
                ),
            ),
        ):
            response = await users_module.active_sessions()

        self.assertEqual(response["total"], 1)
        self.assertEqual(response["cache_only_sessions"], 1)
        self.assertEqual(response["source_of_truth"], "postgres")
        self.assertEqual(response["sessions"][0]["session_id"], "sess-1")
