# Debian deployment — Casual Board API

**Not production-certified until you verify on your machine.**  
UI: `https://discovery-system.grok.me`  
API hostname (Cloudflare Tunnel → loopback): `https://api.apidiscoverysolution.uk`  
FastAPI **must** bind `127.0.0.1:8090` only.

## Required environment (`/etc/casual-board.env`, mode `600`)

```bash
CASUAL_BOARD_ENV=production
CASUAL_BOARD_HOST=127.0.0.1
CASUAL_BOARD_PORT=8090
CASUAL_BOARD_DATA_DIR=/var/lib/casual-board
CASUAL_BOARD_TOKEN=<owner/admin secret — approvals only>
CASUAL_BOARD_BRIDGE_TOKEN=<distinct bridge secret — long-poll + HMAC>
CASUAL_BOARD_UI_PASSWORD=<browser login password>
CASUAL_BOARD_SESSION_SECRET=<HMAC key for short-lived UI sessions>
CASUAL_BOARD_SESSION_TTL_S=3600
CASUAL_BOARD_CORS_ORIGINS=https://discovery-system.grok.me
CASUAL_BOARD_PUBLIC_BASE_URL=https://api.apidiscoverysolution.uk
CASUAL_BOARD_TRUST_PROXY=true
CASUAL_BOARD_FORWARDED_ALLOW_IPS=127.0.0.1,::1
CASUAL_BOARD_TRUSTED_HOSTS=api.apidiscoverysolution.uk,127.0.0.1,localhost
CASUAL_BOARD_AI_PROVIDER=function
CASUAL_BOARD_LOG_LEVEL=INFO
```

Generate secrets:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

**Never** put `CASUAL_BOARD_TOKEN`, `CASUAL_BOARD_BRIDGE_TOKEN`, or
`CASUAL_BOARD_SESSION_SECRET` in any `VITE_*` variable.

## Frontend publish setting (Grok Build / rebuild)

```bash
VITE_API_BASE_URL=https://api.apidiscoverysolution.uk
```

Only that. No tokens.

## systemd unit

Install from `deploy/self-host/casual-board-api.service` (binds loopback via env).

```bash
sudo useradd -r -s /usr/sbin/nologin casual || true
sudo mkdir -p /opt/casual-board/backend /var/lib/casual-board
sudo cp -a backend/* /opt/casual-board/backend/
cd /opt/casual-board/backend
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
sudo cp /path/to/casual-board.env /etc/casual-board.env
sudo chmod 600 /etc/casual-board.env
sudo chown -R casual:casual /var/lib/casual-board
sudo cp deploy/self-host/casual-board-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now casual-board-api
```

Confirm **not** listening on `0.0.0.0`:

```bash
ss -lntp | grep 8090
# expect 127.0.0.1:8090 only
```

## Persistent data & backups

| Path | Contents |
|---|---|
| `/var/lib/casual-board/board.json` | Board snapshot |
| `/var/lib/casual-board/casual_board.sqlite3` | Durable bridge jobs + used nonces |
| `/var/lib/casual-board/actions.jsonl` | Action audit log |

```bash
# backup
sudo tar -C /var/lib -czf /root/casual-board-$(date +%F).tgz casual-board
# restore (service stopped)
sudo systemctl stop casual-board-api
sudo tar -C /var/lib -xzf /root/casual-board-YYYY-MM-DD.tgz
sudo systemctl start casual-board-api
```

## Bridge worker (outbound only)

```bash
export CASUAL_BOARD_API_URL=https://api.apidiscoverysolution.uk
export CASUAL_BOARD_BRIDGE_TOKEN=<same as server bridge token>
python -m casual_board_bridge.main doctor
python -m casual_board_bridge.main run
```

Stub executor only — **Hermes/mpv not claimed integrated**.

## Verification commands

```bash
# 1) Public health (minimal)
curl -sS https://api.apidiscoverysolution.uk/health
# {"ok":true,"service":"casual-board","version":"...","time":"..."}

# 2) Board is private
curl -sS -o /dev/null -w '%{http_code}\n' https://api.apidiscoverysolution.uk/v1/board
# 401

# 3) UI login → session → capture
TOKEN=$(curl -sS -X POST https://api.apidiscoverysolution.uk/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"password":"'"$CASUAL_BOARD_UI_PASSWORD"'"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -sS https://api.apidiscoverysolution.uk/v1/board -H "Authorization: Bearer $TOKEN" | head -c 200
curl -sS -X POST https://api.apidiscoverysolution.uk/v1/captures \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"note":"verify capture from debian"}'

# 4) Approved bridge job + lease + signed result
# enqueue host job via session, approve with OWNER token, bridge worker leases it

# 5) Restart persistence
sudo systemctl restart casual-board-api
# pending/queued jobs still in sqlite:
sudo sqlite3 /var/lib/casual-board/casual_board.sqlite3 'select id,status from bridge_jobs;'
```

## Cloudflare Tunnel

Keep routing `api.apidiscoverysolution.uk` → `http://127.0.0.1:8090` only.  
No public bind of FastAPI on Debian.
