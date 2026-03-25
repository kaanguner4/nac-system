"""
NAC Policy Engine — Unit & Integration Test Suite
Çalıştırmak için:
    pip install pytest pytest-asyncio httpx
    API_BASE_URL=http://localhost:8000 API_SECRET_KEY=your_key pytest test_nac.py -v
"""

import os
import pytest
import httpx
import asyncio

# ─── Config ────────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_KEY  = os.getenv("API_SECRET_KEY", "supersecretkey123")
HEADERS  = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=10) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_returns_ok(self, client):
        """API ayakta ve sağlıklı mı?"""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_health_no_auth_required(self):
        """/health endpoint'i API anahtarı gerektirmemeli."""
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            resp = c.get("/health")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GÜVENLİK — API Key Koruma
# ═══════════════════════════════════════════════════════════════════════════════

class TestSecurity:
    def test_auth_rejects_missing_api_key(self):
        """X-API-Key başlığı yoksa 401 dönmeli."""
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            resp = c.post("/auth", json={"username": "admin01", "password": "admin123"})
        assert resp.status_code == 401

    def test_auth_rejects_wrong_api_key(self):
        """Yanlış X-API-Key ile 401 dönmeli."""
        with httpx.Client(base_url=BASE_URL, headers={"X-API-Key": "YANLIS_ANAHTAR"}, timeout=10) as c:
            resp = c.post("/auth", json={"username": "admin01", "password": "admin123"})
        assert resp.status_code == 401

    def test_users_rejects_missing_api_key(self):
        """/users endpoint'i korumalı olmalı."""
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            resp = c.get("/users")
        assert resp.status_code == 401

    def test_accounting_rejects_missing_api_key(self):
        """/accounting endpoint'i korumalı olmalı."""
        with httpx.Client(base_url=BASE_URL, timeout=10) as c:
            resp = c.post("/accounting", json={
                "status_type": "Start", "session_id": "s1",
                "unique_id": "u1", "username": "admin01", "nas_ip": "10.0.0.1"
            })
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 3. PAP KİMLİK DOĞRULAMA — /auth
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuth:
    def test_admin_login_success(self, client):
        """admin01 doğru şifreyle giriş yapabilmeli."""
        resp = client.post("/auth", json={
            "username": "admin01",
            "password": "admin123",
            "nas_ip": "10.0.0.1"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] == "accept"
        assert body["username"] == "admin01"

    def test_employee_login_success(self, client):
        """employee01 doğru şifreyle giriş yapabilmeli."""
        resp = client.post("/auth", json={
            "username": "employee01",
            "password": "employee123",
            "nas_ip": "10.0.0.1"
        })
        assert resp.status_code == 200
        assert resp.json()["result"] == "accept"

    def test_guest_login_success(self, client):
        """guest01 doğru şifreyle giriş yapabilmeli."""
        resp = client.post("/auth", json={
            "username": "guest01",
            "password": "guest123",
            "nas_ip": "10.0.0.1"
        })
        assert resp.status_code == 200
        assert resp.json()["result"] == "accept"

    def test_wrong_password_rejected(self, client):
        """Yanlış şifreyle 401 ve reject dönmeli."""
        resp = client.post("/auth", json={
            "username": "admin01",
            "password": "yanlis_sifre",
            "nas_ip": "10.0.0.1"
        })
        assert resp.status_code == 401
        assert resp.json()["result"] == "reject"
        assert resp.json()["reason"] == "wrong_password"

    def test_nonexistent_user_rejected(self, client):
        """Var olmayan kullanıcı reddedilmeli."""
        resp = client.post("/auth", json={
            "username": "hayalet_kullanici",
            "password": "deneme",
            "nas_ip": "10.0.0.1"
        })
        assert resp.status_code == 401
        assert resp.json()["reason"] == "user_not_found"

    def test_empty_username_rejected(self, client):
        """Boş kullanıcı adı reddedilmeli."""
        resp = client.post("/auth", json={
            "username": "",
            "password": "deneme",
        })
        # 401 veya 422 (validation) kabul edilir
        assert resp.status_code in (401, 422)

    def test_auth_response_schema(self, client):
        """Auth yanıtı result, username alanlarını içermeli."""
        resp = client.post("/auth", json={
            "username": "admin01",
            "password": "admin123",
        })
        body = resp.json()
        assert "result" in body
        assert "username" in body


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RATE LIMITING
# ═══════════════════════════════════════════════════════════════════════════════

class TestRateLimit:
    def test_rate_limit_triggers_after_5_failures(self, client):
        """5 başarısız denemeden sonra 429 dönmeli."""
        username = "ratetest_user_xyz"
        payload = {"username": username, "password": "yanlis"}

        for i in range(5):
            resp = client.post("/auth", json=payload)
            # İlk 5 denemede 401 bekliyoruz (kullanıcı yok olabilir)
            assert resp.status_code in (401, 429), f"Deneme {i+1}: beklenmedik status {resp.status_code}"

        # 6. denemede artık 429 veya zaten bloklanmış olmalı
        resp = client.post("/auth", json=payload)
        assert resp.status_code == 429, "5+ başarısız denemeden sonra rate limit devreye girmeli"
        assert resp.json()["reason"] == "too_many_attempts"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. MAB (MAC Authentication Bypass)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMAB:
    def test_known_mac_accepted(self, client):
        """Kayıtlı MAC adresi kabul edilmeli."""
        mac = "aa:bb:cc:dd:ee:ff"
        resp = client.post("/auth", json={
            "username": mac,
            "password": mac,
            "calling_station_id": mac,
            "nas_ip": "10.0.0.1"
        })
        assert resp.status_code == 200
        assert resp.json()["result"] == "accept"

    def test_unknown_mac_rejected(self, client):
        """Kayıtsız MAC adresi reddedilmeli."""
        mac = "ff:ff:ff:ff:ff:ff"
        resp = client.post("/auth", json={
            "username": mac,
            "password": mac,
            "calling_station_id": mac,
            "nas_ip": "10.0.0.1"
        })
        assert resp.status_code == 401
        assert resp.json()["result"] == "reject"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. YETKİLENDİRME — /authorize (VLAN Atama)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthorize:
    def test_admin_gets_vlan_10(self, client):
        """admin01 → VLAN 10 almalı."""
        resp = client.post("/authorize", json={"username": "admin01"})
        assert resp.status_code == 200
        body = resp.json()
        vlan = body.get("reply:Tunnel-Private-Group-Id", {}).get("value", [None])[0]
        assert vlan == "10", f"VLAN 10 beklendi, {vlan} geldi"

    def test_employee_gets_vlan_20(self, client):
        """employee01 → VLAN 20 almalı."""
        resp = client.post("/authorize", json={"username": "employee01"})
        assert resp.status_code == 200
        body = resp.json()
        vlan = body.get("reply:Tunnel-Private-Group-Id", {}).get("value", [None])[0]
        assert vlan == "20"

    def test_guest_gets_vlan_30(self, client):
        """guest01 → VLAN 30 almalı."""
        resp = client.post("/authorize", json={"username": "guest01"})
        assert resp.status_code == 200
        body = resp.json()
        vlan = body.get("reply:Tunnel-Private-Group-Id", {}).get("value", [None])[0]
        assert vlan == "30"

    def test_authorize_returns_tunnel_attributes(self, client):
        """Yanıt Tunnel-Type ve Tunnel-Medium-Type içermeli."""
        resp = client.post("/authorize", json={"username": "admin01"})
        body = resp.json()
        assert "reply:Tunnel-Type" in body
        assert "reply:Tunnel-Medium-Type" in body
        assert "reply:Tunnel-Private-Group-Id" in body

    def test_unknown_user_authorize_returns_404(self, client):
        """Var olmayan kullanıcı için 404 dönmeli."""
        resp = client.post("/authorize", json={"username": "yokolankullanici"})
        assert resp.status_code == 404

    def test_mab_device_gets_vlan(self, client):
        """MAB cihazı da VLAN almalı."""
        resp = client.post("/authorize", json={"username": "aa:bb:cc:dd:ee:ff"})
        assert resp.status_code == 200
        body = resp.json()
        assert "reply:Tunnel-Private-Group-Id" in body


# ═══════════════════════════════════════════════════════════════════════════════
# 7. ACCOUNTING — Oturum Yönetimi
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccounting:
    SESSION_ID = "test-session-unit-01"
    UNIQUE_ID  = "test-unique-unit-01"

    def _payload(self, status_type: str, **kwargs) -> dict:
        base = {
            "status_type": status_type,
            "session_id": self.SESSION_ID,
            "unique_id": self.UNIQUE_ID,
            "username": "employee01",
            "nas_ip": "10.0.0.1",
            "calling_station_id": "00:11:22:33:44:55",
            "framed_ip": "192.168.1.100",
            "session_time": 0,
            "input_octets": 0,
            "output_octets": 0,
        }
        base.update(kwargs)
        return base

    def test_accounting_start(self, client):
        """Accounting Start kaydı oluşturulabilmeli."""
        resp = client.post("/accounting", json=self._payload("Start"))
        assert resp.status_code == 200
        assert resp.json()["result"] == "ok"

    def test_accounting_interim_update(self, client):
        """Interim-Update mevcut oturumu güncelleyebilmeli."""
        resp = client.post("/accounting", json=self._payload(
            "Interim-Update", session_time=120, input_octets=5000, output_octets=10000
        ))
        assert resp.status_code == 200
        assert resp.json()["result"] == "ok"

    def test_accounting_stop(self, client):
        """Accounting Stop oturumu kapatabilmeli."""
        resp = client.post("/accounting", json=self._payload(
            "Stop", session_time=300, input_octets=20000, output_octets=50000
        ))
        assert resp.status_code == 200
        assert resp.json()["result"] == "ok"

    def test_accounting_missing_fields_rejected(self, client):
        """Zorunlu alan eksikliğinde 422 dönmeli."""
        resp = client.post("/accounting", json={"status_type": "Start"})
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# 8. KULLANICILAR & OTURUMLAR
# ═══════════════════════════════════════════════════════════════════════════════

class TestUsers:
    def test_users_list_returns_list(self, client):
        """/users endpoint'i kullanıcı listesi dönmeli."""
        resp = client.get("/users")
        assert resp.status_code == 200
        body = resp.json()
        assert "users" in body
        assert "total" in body
        assert isinstance(body["users"], list)

    def test_users_list_contains_test_users(self, client):
        """Test kullanıcıları listede görünmeli."""
        resp = client.get("/users")
        usernames = {u["username"] for u in resp.json()["users"]}
        assert "admin01" in usernames
        assert "employee01" in usernames
        assert "guest01" in usernames

    def test_user_has_required_fields(self, client):
        """Her kullanıcı kaydı zorunlu alanları içermeli."""
        resp = client.get("/users")
        for user in resp.json()["users"]:
            assert "username" in user
            assert "groupname" in user
            assert "status" in user
            assert "active" in user
            assert "blocked" in user

    def test_active_sessions_endpoint(self, client):
        """/sessions/active endpoint'i çalışıyor olmalı."""
        resp = client.get("/sessions/active")
        assert resp.status_code == 200
        body = resp.json()
        assert "sessions" in body
        assert "total" in body
        assert "source_of_truth" in body
        assert body["source_of_truth"] == "postgres"

    def test_admin_is_in_admin_group(self, client):
        """admin01 kullanıcısı admin grubunda olmalı."""
        resp = client.get("/users")
        users = {u["username"]: u for u in resp.json()["users"]}
        assert users["admin01"]["groupname"] == "admin"

    def test_employee_is_in_employee_group(self, client):
        """employee01 kullanıcısı employee grubunda olmalı."""
        resp = client.get("/users")
        users = {u["username"]: u for u in resp.json()["users"]}
        assert users["employee01"]["groupname"] == "employee"

    def test_guest_is_in_guest_group(self, client):
        """guest01 kullanıcısı guest grubunda olmalı."""
        resp = client.get("/users")
        users = {u["username"]: u for u in resp.json()["users"]}
        assert users["guest01"]["groupname"] == "guest"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. FULL FLOW — Uçtan Uca Senaryo
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullFlow:
    """
    Gerçek bir ağ erişim senaryosunu simüle eder:
    Auth → Authorize (VLAN) → Accounting Start → ... → Stop
    """

    def test_full_auth_authorize_accounting_flow(self, client):
        """employee01 için eksiksiz bir oturum döngüsü."""
        # 1. Authentication
        auth_resp = client.post("/auth", json={
            "username": "employee01",
            "password": "employee123",
            "nas_ip": "10.0.0.10"
        })
        assert auth_resp.status_code == 200
        assert auth_resp.json()["result"] == "accept"

        # 2. Authorization (VLAN)
        authz_resp = client.post("/authorize", json={"username": "employee01"})
        assert authz_resp.status_code == 200
        vlan = authz_resp.json()["reply:Tunnel-Private-Group-Id"]["value"][0]
        assert vlan == "20"

        session_id = "e2e-flow-employee-001"
        unique_id  = "e2e-uniq-001"

        # 3. Accounting Start
        start_resp = client.post("/accounting", json={
            "status_type": "Start", "session_id": session_id,
            "unique_id": unique_id, "username": "employee01",
            "nas_ip": "10.0.0.10", "calling_station_id": "aa:aa:aa:bb:bb:bb",
            "framed_ip": "192.168.20.100", "session_time": 0,
            "input_octets": 0, "output_octets": 0,
        })
        assert start_resp.status_code == 200

        # 4. Interim Update
        update_resp = client.post("/accounting", json={
            "status_type": "Interim-Update", "session_id": session_id,
            "unique_id": unique_id, "username": "employee01",
            "nas_ip": "10.0.0.10", "session_time": 60,
            "input_octets": 1024, "output_octets": 4096,
        })
        assert update_resp.status_code == 200

        # 5. Accounting Stop
        stop_resp = client.post("/accounting", json={
            "status_type": "Stop", "session_id": session_id,
            "unique_id": unique_id, "username": "employee01",
            "nas_ip": "10.0.0.10", "session_time": 180,
            "input_octets": 8192, "output_octets": 32768,
        })
        assert stop_resp.status_code == 200
