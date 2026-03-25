#!/bin/sh

set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo ".env file is required" >&2
  exit 1
fi

set -a
. ./.env
set +a

require_line() {
  haystack="$1"
  needle="$2"
  if ! printf "%s" "$haystack" | grep -q "$needle"; then
    echo "Expected to find '$needle' in command output" >&2
    printf "%s\n" "$haystack" >&2
    exit 1
  fi
}

echo "1/7 curl /health"
health_output="$(curl -fsS http://localhost:8000/health)"
require_line "$health_output" "\"status\":\"ok\""

echo "2/7 curl /auth ve /authorize"
auth_output="$(curl -fsS -X POST http://localhost:8000/auth \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_SECRET_KEY" \
  -d '{"username":"admin01","password":"admin123"}')"
require_line "$auth_output" "\"result\":\"accept\""

authorize_output="$(curl -fsS -X POST http://localhost:8000/authorize \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_SECRET_KEY" \
  -d '{"username":"admin01"}')"
require_line "$authorize_output" "reply:Tunnel-Private-Group-Id"
require_line "$authorize_output" "\"10\""

echo "3/7 radtest PAP auth"
pap_output="$(docker exec nac_freeradius sh -lc 'radtest admin01 admin123 127.0.0.1 0 "$RADIUS_SHARED_SECRET"' 2>&1)"
require_line "$pap_output" "Access-Accept"
require_line "$pap_output" "Tunnel-Private-Group-Id:0 = \"10\""

echo "4/7 radclient MAB accept"
mab_accept_output="$(docker exec nac_freeradius sh -lc 'printf "User-Name = \"aa:bb:cc:dd:ee:ff\"\nUser-Password = \"aa:bb:cc:dd:ee:ff\"\nCalling-Station-Id = \"aa:bb:cc:dd:ee:ff\"\nNAS-IP-Address = 127.0.0.1\n" | radclient -x 127.0.0.1 auth "$RADIUS_SHARED_SECRET"' 2>&1)"
require_line "$mab_accept_output" "Access-Accept"
require_line "$mab_accept_output" "Tunnel-Private-Group-Id:0 = \"20\""

echo "5/7 radclient MAB reject"
mab_reject_output="$(docker exec nac_freeradius sh -lc 'printf "User-Name = \"de:ad:be:ef:00:01\"\nUser-Password = \"de:ad:be:ef:00:01\"\nCalling-Station-Id = \"de:ad:be:ef:00:01\"\nNAS-IP-Address = 127.0.0.1\n" | radclient -x 127.0.0.1 auth "$RADIUS_SHARED_SECRET"' 2>&1 || true)"
require_line "$mab_reject_output" "Access-Reject"
require_line "$mab_reject_output" "Reply-Message = \"Access denied\""

session_id="smoke-sess-$$"

echo "6/7 radclient accounting Start/Interim/Stop"
acct_start_output="$(docker exec nac_freeradius sh -lc 'session="'"$session_id"'"; printf "Acct-Status-Type = Start\nUser-Name = \"guest01\"\nAcct-Session-Id = \"$session\"\nNAS-IP-Address = 10.0.0.20\nCalling-Station-Id = \"cc:cc:cc:cc:cc:cc\"\nFramed-IP-Address = 192.168.1.30\nAcct-Session-Time = 0\nAcct-Input-Octets = 0\nAcct-Output-Octets = 0\n" | radclient -x 127.0.0.1:1813 acct "$RADIUS_SHARED_SECRET"' 2>&1)"
require_line "$acct_start_output" "Accounting-Response"

sleep 1

active_sessions_output="$(curl -fsS -H "X-API-Key: $API_SECRET_KEY" http://localhost:8000/sessions/active)"
require_line "$active_sessions_output" "$session_id"

acct_interim_output="$(docker exec nac_freeradius sh -lc 'session="'"$session_id"'"; printf "Acct-Status-Type = Interim-Update\nUser-Name = \"guest01\"\nAcct-Session-Id = \"$session\"\nNAS-IP-Address = 10.0.0.20\nCalling-Station-Id = \"cc:cc:cc:cc:cc:cc\"\nFramed-IP-Address = 192.168.1.30\nAcct-Session-Time = 60\nAcct-Input-Octets = 128\nAcct-Output-Octets = 256\n" | radclient -x 127.0.0.1:1813 acct "$RADIUS_SHARED_SECRET"' 2>&1)"
require_line "$acct_interim_output" "Accounting-Response"

acct_stop_output="$(docker exec nac_freeradius sh -lc 'session="'"$session_id"'"; printf "Acct-Status-Type = Stop\nUser-Name = \"guest01\"\nAcct-Session-Id = \"$session\"\nNAS-IP-Address = 10.0.0.20\nCalling-Station-Id = \"cc:cc:cc:cc:cc:cc\"\nFramed-IP-Address = 192.168.1.30\nAcct-Session-Time = 120\nAcct-Input-Octets = 256\nAcct-Output-Octets = 512\n" | radclient -x 127.0.0.1:1813 acct "$RADIUS_SHARED_SECRET"' 2>&1)"
require_line "$acct_stop_output" "Accounting-Response"

sleep 1

post_stop_sessions_output="$(curl -fsS -H "X-API-Key: $API_SECRET_KEY" http://localhost:8000/sessions/active)"
if printf "%s" "$post_stop_sessions_output" | grep -q "$session_id"; then
  echo "Session still active after Accounting Stop" >&2
  printf "%s\n" "$post_stop_sessions_output" >&2
  exit 1
fi

echo "7/7 curl /users"
users_output="$(curl -fsS -H "X-API-Key: $API_SECRET_KEY" http://localhost:8000/users)"
require_line "$users_output" "\"users\""
require_line "$users_output" "\"guest01\""

echo "Smoke tests passed"
