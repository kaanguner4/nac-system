# NAC System — Network Access Control

RADIUS protokolü (RFC 2865/2866) üzerine kurulu, tam AAA (Authentication, Authorization, Accounting) desteği sunan bir Network Access Control sistemi. FreeRADIUS 3.2, FastAPI policy engine, PostgreSQL ve Redis bileşenlerini Docker Compose ile bir arada çalıştırır.

---

## Mimari

```
NAS / Radtest / Radclient
         │
         │  RADIUS (UDP 1812 / 1813)
         ▼
 ┌─────────────────┐
 │   FreeRADIUS    │   rlm_rest modülü ile her karar FastAPI'ye delege edilir
 │  (Port 1812/13) │
 └────────┬────────┘
          │  HTTP (REST)
          ▼
 ┌─────────────────┐
 │   FastAPI API   │   Policy engine — kimlik doğrulama, yetkilendirme, oturum kaydı
 │  (Port 8000)    │
 └────┬───────┬────┘
      │       │
      ▼       ▼
 PostgreSQL  Redis
 (Kalıcı)   (Cache + Rate-limit)
```

### Servisler

| Servis | Image | Port | Rol |
|---|---|---|---|
| `nac_freeradius` | `freeradius/freeradius-server:latest-3.2` | 1812/UDP, 1813/UDP | RADIUS sunucusu |
| `nac_api` | `python:3.13-slim` | 8000/TCP | FastAPI policy engine |
| `nac_postgres` | `postgres:18-alpine` | — (iç ağ) | Kullanıcı ve oturum verisi |
| `nac_redis` | `redis:8-alpine` | — (iç ağ) | Oturum cache, rate-limiting |

Tüm servisler `nac_network` adlı bridge ağında haberleşir. Dışarıya sadece `8000`, `1812`, `1813` açıktır.

---

## Kurulum

### Gereksinimler

- Docker >= 24
- Docker Compose v2 (`docker compose` komutu)

### 1. Repoyu klonla

```bash
git clone <repo-url>
cd nac-system
```

### 2. Ortam değişkenlerini yapılandır

`.env.example` dosyasını kopyala ve doldur:

```bash
cp .env.example .env
```

`.env` içeriği:

```env
POSTGRES_DB=radius
POSTGRES_USER=radius
POSTGRES_PASSWORD=<guclu-bir-sifre>

REDIS_PASSWORD=<guclu-bir-sifre>

RADIUS_SHARED_SECRET=<nas-ile-paylasilan-secret>

API_SECRET_KEY=<rastgele-uzun-bir-string>
```

> `.env` dosyası git'e commit edilmez (`.gitignore` tarafından hariç tutulur).

### 3. Sistemi başlat

```bash
docker compose up -d
```

Tüm servisler ayağa kalktıktan sonra healthcheck'lerin geçmesini bekle:

```bash
docker compose ps
```

Tüm servisler `healthy` durumuna geçtiğinde sistem hazırdır (~30–60 saniye).

### 4. Doğrulama

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Veritabanı Şeması

`postgres/init.sql` dosyası container ilk başlatıldığında otomatik çalışır. Aşağıdaki tabloları ve test verilerini oluşturur:

| Tablo | Açıklama |
|---|---|
| `radcheck` | Kullanıcı kimlik bilgileri (bcrypt hash + MAB MAC adresleri) |
| `radreply` | Kullanıcıya özel RADIUS reply attribute'ları |
| `radusergroup` | Kullanıcı → grup eşleşmeleri |
| `radgroupreply` | Grup bazlı VLAN ve policy attribute'ları |
| `radacct` | Accounting kayıtları (Start/Interim-Update/Stop) |
| `nas` | NAS envanter tablosu |

### Varsayılan Test Kullanıcıları

| Kullanıcı | Şifre | Grup | VLAN |
|---|---|---|---|
| `admin01` | `admin123` | admin | 10 |
| `employee01` | `employee123` | employee | 20 |
| `guest01` | `guest123` | guest | 30 |

### Varsayılan MAB Cihazı

| MAC Adresi | Grup | VLAN |
|---|---|---|
| `aa:bb:cc:dd:ee:ff` | employee | 20 |

---

## FastAPI Policy Engine

### Endpoint'ler

| Endpoint | Metot | Auth | Açıklama |
|---|---|---|---|
| `/health` | GET | — | Servis sağlık kontrolü |
| `/auth` | POST | X-API-Key | Kullanıcı doğrulama (PAP + MAB) |
| `/authorize` | POST | X-API-Key | VLAN ve policy attribute döndürme |
| `/accounting` | POST | X-API-Key | Oturum verisi kaydetme |
| `/users` | GET | X-API-Key | Tüm kullanıcılar ve durum bilgisi |
| `/sessions/active` | GET | X-API-Key | Aktif oturumlar (Redis + PostgreSQL) |
| `/dashboard` | GET | Cookie | Web arayüzü |

Tüm RADIUS endpoint'leri `X-API-Key` header'ı gerektirir. Key değeri `.env` dosyasındaki `API_SECRET_KEY` ile eşleşmelidir.

### Örnek İstekler

**Authentication:**

```bash
curl -X POST http://localhost:8000/auth \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_SECRET_KEY>" \
  -d '{"username": "admin01", "password": "admin123"}'
```

```json
{"result": "accept", "username": "admin01", "reason": "pap_authentication_successful"}
```

**Authorization (VLAN ataması):**

```bash
curl -X POST http://localhost:8000/authorize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_SECRET_KEY>" \
  -d '{"username": "admin01"}'
```

```json
{
  "reply:Tunnel-Type": {
    "op": ":=",
    "value": ["13"]
  },
  "reply:Tunnel-Medium-Type": {
    "op": ":=",
    "value": ["6"]
  },
  "reply:Tunnel-Private-Group-Id": {
    "op": ":=",
    "value": ["10"]
  },
  "reply:Reply-Message": {
    "op": ":=",
    "value": ["group=admin, vlan=10"]
  }
}
```

**Accounting Start:**

```bash
curl -X POST http://localhost:8000/accounting \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_SECRET_KEY>" \
  -d '{
    "status_type": "Start",
    "session_id": "sess-001",
    "unique_id": "uniq-001",
    "username": "admin01",
    "nas_ip": "10.0.0.1",
    "calling_station_id": "aa:bb:cc:dd:ee:01",
    "framed_ip": "192.168.10.5",
    "session_time": "0",
    "input_octets": "0",
    "output_octets": "0"
  }'
```

`unique_id` gönderilmezse API otomatik olarak `session_id` değerini fallback olarak kullanır.

**Aktif oturumlar:**

```bash
curl http://localhost:8000/sessions/active \
  -H "X-API-Key: <API_SECRET_KEY>"
```

---

## FreeRADIUS ile Test

FreeRADIUS container içindeki araçlarla RADIUS trafiği doğrudan test edilebilir.

### PAP Authentication (radtest)

```bash
docker exec nac_freeradius sh -lc \
  'radtest admin01 admin123 127.0.0.1 0 "$RADIUS_SHARED_SECRET"'
```

Beklenen çıktıda `Access-Accept` ve `Tunnel-Private-Group-Id:0 = "10"` görünmelidir.

### MAB Authentication (radclient)

**Bilinen cihaz — kabul:**

```bash
docker exec nac_freeradius sh -lc 'printf "User-Name = \"aa:bb:cc:dd:ee:ff\"\nUser-Password = \"aa:bb:cc:dd:ee:ff\"\nCalling-Station-Id = \"aa:bb:cc:dd:ee:ff\"\nNAS-IP-Address = 127.0.0.1\n" | radclient -x 127.0.0.1 auth "$RADIUS_SHARED_SECRET"'
```

**Bilinmeyen cihaz — red:**

```bash
docker exec nac_freeradius sh -lc 'printf "User-Name = \"de:ad:be:ef:00:01\"\nUser-Password = \"de:ad:be:ef:00:01\"\nCalling-Station-Id = \"de:ad:be:ef:00:01\"\nNAS-IP-Address = 127.0.0.1\n" | radclient -x 127.0.0.1 auth "$RADIUS_SHARED_SECRET"'
```

Beklenen: `Access-Reject` ve `Reply-Message = "Access denied"`.

### Accounting Testi (radclient)

```bash
# Accounting-Start
docker exec nac_freeradius sh -lc 'printf "Acct-Status-Type = Start\nUser-Name = \"guest01\"\nAcct-Session-Id = \"test-session-1\"\nNAS-IP-Address = 10.0.0.20\nCalling-Station-Id = \"cc:cc:cc:cc:cc:cc\"\nFramed-IP-Address = 192.168.1.30\nAcct-Session-Time = 0\nAcct-Input-Octets = 0\nAcct-Output-Octets = 0\n" | radclient -x 127.0.0.1:1813 acct "$RADIUS_SHARED_SECRET"'

# Accounting-Stop
docker exec nac_freeradius sh -lc 'printf "Acct-Status-Type = Stop\nUser-Name = \"guest01\"\nAcct-Session-Id = \"test-session-1\"\nNAS-IP-Address = 10.0.0.20\nAcct-Session-Time = 300\nAcct-Input-Octets = 1024\nAcct-Output-Octets = 2048\n" | radclient -x 127.0.0.1:1813 acct "$RADIUS_SHARED_SECRET"'
```

---

## Testler

### Unit Testler

```bash
docker exec nac_api python -m pytest tests/ -v
```

Test dosyaları:
- `api/tests/test_auth.py` — Kimlik doğrulama ve rate limiting
- `api/tests/test_users.py` — Kullanıcı listeleme ve oturum birleştirme
- `api/tests/test_accounting.py` — Accounting akışı
- `api/tests/test_dashboard_api.py` — Dashboard doğrulama ve oturum güvenliği

### Entegrasyon Testleri

```bash
docker exec nac_api python -m pytest test_nac.py -v
```

9 test sınıfı: Health, Security, Auth, RateLimit, MAB, Authorize, Accounting, Users, FullFlow.

### Smoke Testler (Canlı RADIUS Trafiği)

Sistem çalışır durumdayken:

```bash
sh tests/smoke_radius.sh
```

7 adımlı test: health check → REST doğrulama → radtest PAP → radclient MAB kabul → MAB red → accounting Start/Interim/Stop döngüsü → kullanıcı listesi.

---

## Web Dashboard

Tarayıcıda `http://localhost:8000/dashboard` adresine git.

Retro terminal temalı dashboard üzerinden:
- Tüm kullanıcıların durumunu (active / blocked / inactive) görüntüleme
- Aktif oturumları ve trafik istatistiklerini izleme
- Admin kullanıcılar için yeni PAP veya MAB kullanıcısı oluşturma

Giriş bilgileri: yukarıdaki test kullanıcıları geçerlidir.

---

## Kimlik Doğrulama Akışı

```
NAS → FreeRADIUS (Access-Request)
         │
         ├── authorize { rest } → POST /authorize
         │     ← VLAN attribute'ları (Tunnel-Type, Tunnel-Medium-Type, Tunnel-Private-Group-Id)
         │
         └── Auth-Type PAP { rest } → POST /auth
               ├── PAP: bcrypt hash kontrolü
               └── MAB: User-Password == Calling-Station-Id ise MAC lookup
               ← accept / reject
```

**Rate Limiting:** Aynı kullanıcıdan 5 dakika içinde 5 başarısız deneme gelirse hesap 15 dakika bloke edilir (Redis tabanlı).

---

## Proje Yapısı

```
nac-system/
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # Uygulama başlatma, lifespan, router bağlama
│       ├── security.py          # API key doğrulama, dashboard session yönetimi
│       ├── db/
│       │   ├── postgres.py      # asyncpg bağlantı havuzu ve sorgular
│       │   └── redis.py         # Oturum cache ve rate limiting
│       ├── routes/
│       │   ├── auth.py          # /auth ve /authorize
│       │   ├── accounting.py    # /accounting
│       │   ├── users.py         # /users ve /sessions/active
│       │   ├── dashboard.py     # /dashboard (HTML servis)
│       │   └── dashboard_api.py # /dashboard-api/* (web UI backend)
│       └── static/
│           ├── dashboard.html
│           ├── dashboard.css
│           └── dashboard.js
├── freeradius/
│   ├── Dockerfile
│   ├── clients.conf             # NAS client tanımları
│   ├── mods-enabled/rest        # rlm_rest yapılandırması
│   └── sites-enabled/default   # RADIUS virtual server policy
├── postgres/
│   └── init.sql                 # Şema + test verileri
├── tests/
│   └── smoke_radius.sh          # Canlı RADIUS smoke testi
├── test_nac.py                  # Entegrasyon test paketi
├── docker-compose.yml
├── .env.example
└── .gitignore
```

---

## Bağımlılıklar

| Paket | Versiyon | Amaç |
|---|---|---|
| fastapi | 0.115.6 | Web framework |
| uvicorn | 0.32.1 | ASGI sunucu |
| asyncpg | 0.30.0 | PostgreSQL async driver |
| redis | 5.2.1 | Redis async client |
| bcrypt | 5.0.0 | Şifre hashing |
| pydantic | 2.10.3 | Veri doğrulama |
| python-jose | 3.3.0 | JWT / token |
| httpx | 0.28.1 | HTTP test client |

---

## Sistem Durdurma

```bash
# Servisleri durdur, verileri koru
docker compose down

# Servisleri durdur ve tüm verileri sil (volume'lar dahil)
docker compose down -v
```
