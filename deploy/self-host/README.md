# Free self-host target for Casual Board API

**No paid cloud is selected.** This is the default production path for
`discovery-system.grok.me` until you choose otherwise.

## Why separate from grok.me?

Verified from this project’s build output (`.vercel/output/config.json` +
`nitro({ preset: "vercel" })`):

- Published apps are **Node/Nitro** (SSR function `__server` + static assets).
- There is **no Python/FastAPI runtime** on `*.grok.me`.
- Same-origin `/v1/*` on grok.me would hit the Node server and **404** for FastAPI.

So:

| Surface | Host |
| --- | --- |
| Web UI | `https://discovery-system.grok.me` |
| FastAPI | **Your machine** (Debian recommended) + public HTTPS via **Cloudflare Tunnel (free)** |

Debian stays **outbound-capable**; tunnel only exposes the API process, not your whole box.

## Architecture

```text
Phone browser
  │
  │  https://discovery-system.grok.me     ← Grok.me (Vite/Nitro UI only)
  │  fetch/wss → VITE_API_BASE_URL
  ▼
https://<your-tunnel-or-domain>          ← Cloudflare Tunnel (free)
  │
  ▼
127.0.0.1:8090 FastAPI                   ← Debian (or any always-on Linux)
  ▲
  │ outbound HTTPS only
Debian CLI + Hermes bridge
```

## 1. Run API on Debian (local loopback)

```bash
sudo useradd -r -s /usr/sbin/nologin casual || true
sudo mkdir -p /opt/casual-board/backend /var/lib/casual-board
sudo cp -a backend/* /opt/casual-board/backend/
cd /opt/casual-board/backend
sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

sudo tee /etc/casual-board.env >/dev/null <<'EOF'
CASUAL_BOARD_ENV=production
CASUAL_BOARD_HOST=127.0.0.1
CASUAL_BOARD_PORT=8090
CASUAL_BOARD_DATA_DIR=/var/lib/casual-board
CASUAL_BOARD_TOKEN=replace-with-long-random-secret
CASUAL_BOARD_CORS_ORIGINS=https://discovery-system.grok.me
CASUAL_BOARD_PUBLIC_BASE_URL=https://REPLACE.example.com
CASUAL_BOARD_TRUST_PROXY=true
CASUAL_BOARD_ENABLE_AI=true
CASUAL_BOARD_LOG_LEVEL=INFO
EOF
sudo chmod 600 /etc/casual-board.env

sudo cp deploy/self-host/casual-board-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now casual-board-api
curl -s http://127.0.0.1:8090/health
```

Generate a token:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

## 2. Cloudflare Tunnel (free) — public HTTPS + WSS

Install `cloudflared` on the same Debian host, then:

```bash
cloudflared tunnel login
cloudflared tunnel create casual-board-api
# note Tunnel ID

# DNS route (your zone) OR use a free trycloudflare quick tunnel for a trial:
# cloudflared tunnel --url http://127.0.0.1:8090

cloudflared tunnel route dns casual-board-api api.your-domain.tld
```

`config.yml` example (`~/.cloudflared/config.yml`):

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/you/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: api.your-domain.tld
    service: http://127.0.0.1:8090
  - service: http_status:404
```

```bash
sudo systemctl enable --now cloudflared
curl -s https://api.your-domain.tld/health
```

Update:

```bash
# /etc/casual-board.env
CASUAL_BOARD_PUBLIC_BASE_URL=https://api.your-domain.tld
sudo systemctl restart casual-board-api
```

WebSocket path: `wss://api.your-domain.tld/v1/board/ws`  
(Cloudflare Tunnel supports WebSockets by default.)

## 3. Point the grok.me web UI at the API

Rebuild / republish the web app with:

```bash
# build-time (Vite embeds this)
VITE_API_BASE_URL=https://api.your-domain.tld
```

**Security:** the published web UI never receives `CASUAL_BOARD_TOKEN` or
`CASUAL_BOARD_BRIDGE_TOKEN`. Board reads/writes that are server-side are public
but CORS-locked to `https://discovery-system.grok.me`. Owner token is for
approvals/admin only; bridge token is for the Debian worker.

## 4. Debian CLI / bridge (outbound)

```bash
export CASUAL_BOARD_API_URL=https://api.your-domain.tld
export CASUAL_BOARD_TOKEN=replace-with-long-random-secret
python -m casual_board_client.cli doctor
python -m casual_board_client.cli watch
```

No inbound ports on Debian beyond what Cloudflare egresses.

## 5. Docker Compose alternative (still free, still self-host)

See `docker-compose.yml` in this folder. Bind to `127.0.0.1:8090` and put
Cloudflare Tunnel in front — same as systemd.

## Checklist before calling it “live”

- [ ] `curl https://api…/health` returns `ok: true`
- [ ] CORS allows only `https://discovery-system.grok.me`
- [ ] `CASUAL_BOARD_TOKEN` set; open-dev disabled
- [ ] Phone on grok.me shows **live** (not API failure banner)
- [ ] `wss://…/v1/board/ws` connects
- [ ] Debian `casual-board doctor` OK
- [ ] Persistence dir survives reboot (`/var/lib/casual-board`)
