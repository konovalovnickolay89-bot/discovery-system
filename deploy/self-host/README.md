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
CASUAL_BOARD_GRAPH_RECALL_TOKEN=<distinct Graph Recall worker secret>
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

# Optional evidence reviewer (API systemd only — never VITE_*, never worker env)
# Default: none (deterministic Pydantic evidence gate only)
CASUAL_BOARD_EVIDENCE_AI_PROVIDER=none
CASUAL_BOARD_EVIDENCE_AI_MODEL=
```

### Optional Mistral evidence reviewer (API process only)

Leave provider `none` unless you want a second model call after Graph Recall.
When enabled, add **only** to `/etc/casual-board.env` (API unit `EnvironmentFile`):

```bash
CASUAL_BOARD_EVIDENCE_AI_PROVIDER=mistral
CASUAL_BOARD_EVIDENCE_AI_MODEL=mistral:mistral-small-latest
MISTRAL_API_KEY=...
```

- Reviewer is **tool-less** (no browser, shell, graph, or retrieval tools).
- Deterministic evidence gate remains final authority.
- Missing/invalid key or provider failure → `insufficient_evidence` (never uncited “verified”).
- **Do not** put `MISTRAL_API_KEY` in the Graph Recall worker env, browser, or any `VITE_*` variable.
- Never print the key in install logs.

Generate secrets:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

**Never** put `CASUAL_BOARD_TOKEN`, `CASUAL_BOARD_BRIDGE_TOKEN`,
`CASUAL_BOARD_SESSION_SECRET`, or `MISTRAL_API_KEY` in any `VITE_*` variable.

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
| `/var/lib/casual-board/casual_board.sqlite3` | Durable bridge jobs + kitchen + evidence |
| `/var/lib/casual-board/actions.jsonl` | Action audit log |

```bash
sudo tar -C /var/lib -czf /var/backups/casual-board-data-$(date -u +%Y%m%d).tgz casual-board
```

## Health / smoke

```bash
curl -sS http://127.0.0.1:8090/health
```
