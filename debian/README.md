# Casual Board on debian-minimal

One **FastAPI** process is the source of truth. Phone web, your raw CLI, and the **Hermes** maintainer agent all talk to it.

```text
┌─────────────┐     ┌──────────────────────────┐     ┌─────────────────┐
│ Phone web   │◄───►│  Casual Board API :8090   │◄───►│ Debian CLI      │
│ (browser)   │ WS  │  Pydantic + PydanticAI    │ HTTP│ `python -m app` │
└─────────────┘     │  board.json persistence   │     └─────────────────┘
                    │         ▲                 │
                    │         │ token           │
                    │  ┌──────┴───────┐         │     ┌─────────────────┐
                    │  │ Hermes agent │◄────────┼────►│ mpv + ytdl +    │
                    │  └──────────────┘         │     │ ffmpeg cassette │
                    └──────────────────────────┘     └─────────────────┘
```

## 1. Install API on Debian

```bash
sudo mkdir -p /opt/casual-board /var/lib/casual-board
# copy the `python/` tree → /opt/casual-board/python
cd /opt/casual-board/python
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# secret for Hermes + admin CLI (required before LAN/public expose)
export CASUAL_BOARD_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
echo "CASUAL_BOARD_TOKEN=$CASUAL_BOARD_TOKEN" | sudo tee /etc/casual-board.env
echo "CASUAL_BOARD_DATA=/var/lib/casual-board/board.json" | sudo tee -a /etc/casual-board.env
```

Systemd unit: see `casual-board.service`.

```bash
sudo systemctl enable --now casual-board
curl -s http://127.0.0.1:8090/api/health
```

## 2. CLI dashboard (replaces raw terminal glue)

```bash
export CASUAL_BOARD_URL=http://127.0.0.1:8090
export CASUAL_BOARD_TOKEN=...   # same as service

cd /opt/casual-board/python
. .venv/bin/activate
python -m app status
python -m app dash
python -m app watch --interval 2
python -m app capture "check duck confit for Friday"
python -m app media play
python -m app media cassette-on
python -m app hermes status
```

Optional symlink:

```bash
sudo ln -sf /opt/casual-board/python/.venv/bin/python /usr/local/bin/casual-board-py
# wrapper:
echo '#!/bin/sh
cd /opt/casual-board/python && . .venv/bin/activate && exec python -m app "$@"' | sudo tee /usr/local/bin/cb
sudo chmod +x /usr/local/bin/cb
cb dash
```

## 3. Hermes maintainer agent

Hermes (same machine) administers via **Bearer token**:

```http
POST /api/hermes
Authorization: Bearer $CASUAL_BOARD_TOKEN
Content-Type: application/json

{"action":"status","agent":"hermes"}
{"action":"add_today","payload":{"text":"defrost pastry"},"agent":"hermes"}
{"action":"set_machine","payload":{"disk_pct":71,"apt_updates":12},"agent":"hermes"}
{"action":"capture","payload":{"note":"line open late — note for tomorrow"},"agent":"hermes"}
{"action":"reset_board","agent":"hermes"}
```

Or:

```bash
python -m app hermes ping
python -m app hermes add_today --text "walk-in check 06:30"
```

Wire Hermes tools to these HTTP actions (or shell out to `python -m app hermes …`).

## 4. Phone web

**Option A — API on Debian, static/web UI on same host or LAN**

- Bind API `0.0.0.0:8090` (firewall carefully)
- Serve the Vite build or reverse-proxy both
- Phone opens `http://<tailscale-ip>/`

**Option B — Grok-published UI + your API**

- Grok hosts the **frontend** only
- Point the UI at your API only if the phone can reach Debian (Tailscale / Cloudflare Tunnel)
- Set `CASUAL_BOARD_TOKEN` and do **not** leave admin open on the public internet

Recommended for home: **Tailscale** on phone + Debian; no public ports.

## 5. Bidirectional sync

| Path | Mechanism |
|---|---|
| Any client → all others | `POST` mutates board → event fan-out |
| Live UI | `WebSocket /api/ws?role=web\|cli\|hermes\|host` |
| Phone media buttons | `POST /api/media/command` |
| Real mpv after play | Host worker listens WS / polls, runs mpv, then `PUT /api/media/state` |

## 6. Real mpv (host worker sketch)

```bash
# pseudo — Hermes or a small python worker:
# on media_command event → mpv --playlist=… / ipc
# then PUT /api/media/state with authoritative MediaSection
```

Cassette on = insert FFmpeg tape profile in the audio path (your existing emulator).

## Security checklist

- [ ] `CASUAL_BOARD_TOKEN` set before any non-localhost expose  
- [ ] Prefer Tailscale over port-forward  
- [ ] Hermes token only on disk mode `0600`  
- [ ] Do not commit tokens into git  
