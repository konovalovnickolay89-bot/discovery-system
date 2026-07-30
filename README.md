# Casual Board

Personal ops board for a **chef + Debian tinkerer**.

**Published web UI:** `https://discovery-system.grok.me`  
**Authoritative API:** **not** on grok.me — separate Python host (see below).

---

## Final public architecture

```text
┌─────────────────────────────────────────────────────────────┐
│  Phone / desktop browser                                    │
│  https://discovery-system.grok.me                           │
│  (Grok Build publish · Nitro/Node · Vite UI only)           │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTPS + WSS
                            │ VITE_API_BASE_URL = https://api.…
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI + Pydantic (+ optional PydanticAI)                 │
│  Public https via Cloudflare Tunnel (free) or your reverse  │
│  proxy — runs on Debian (or any Linux you control)          │
│  CORS allowlist: https://discovery-system.grok.me           │
└───────────────▲─────────────────────────────▲───────────────┘
                │ outbound only                 │ outbound only
                │                               │
     ┌──────────┴──────────┐         ┌─────────┴──────────┐
     │ debian-client CLI   │         │ debian-bridge      │
     │ status/dash/watch   │         │ Hermes allowlist   │
     │ local cache         │         │ no public inbound  │
     └─────────────────────┘         └────────────────────┘
```

### Verified: what grok.me actually hosts

From this repo’s production build pipeline:

| Check | Result |
| --- | --- |
| Build plugin | `nitro({ preset: "vercel" })` in `vite.config.ts` |
| Output | `.vercel/output` → Node function `__server` + static `/assets` |
| Routes | `/(.*)` → `__server` (Node SSR), not Python |
| Python FastAPI | **Does not run on `*.grok.me`** |
| Same-origin `/v1` on grok.me | **Would not hit FastAPI** (404 / wrong runtime) |

So grok.me provides **the web app** (SSR + static), **not** a general-purpose
Python API host. There is no same-origin FastAPI route after publish unless
you add a **separate** backend and point the UI at it with `VITE_API_BASE_URL`.

---

## 1. Where does FastAPI run after publish?

| Environment | Web UI | FastAPI |
| --- | --- | --- |
| Grok Build **preview** (this sandbox) | Vite `:8080` | uvicorn `:8090` (proxied) |
| **Production** `discovery-system.grok.me` | Grok.me Nitro/Node | **Your host** (Debian + Tunnel recommended) |

**Recommended free production target (no paid provider selected):**

→ [`deploy/self-host/README.md`](deploy/self-host/README.md)

Debian `systemd` unit + **Cloudflare Tunnel (free)** for `https`/`wss`.  
Docker Compose alternative included. **Ask before adding any paid host.**

---

## 2. Exact `VITE_API_BASE_URL` values

| Mode | Value | Effect |
| --- | --- | --- |
| **Development** (Grok Build / local) | **empty / unset** | Same-origin `/v1`, `/health` → Vite proxy → `127.0.0.1:8090` |
| **Production** (grok.me) | **`https://api.your-domain.tld`** (no trailing slash) | Browser calls external FastAPI over HTTPS/WSS |

Examples:

```bash
# Dev — do not set, or:
VITE_API_BASE_URL=

# Prod web build for discovery-system.grok.me:
VITE_API_BASE_URL=https://api.your-domain.tld
```

**Wrong in production:**

```bash
VITE_API_BASE_URL=                    # empty on grok.me → API failure banner
VITE_API_BASE_URL=http://127.0.0.1:8090   # phone cannot reach your LAN/loopback
VITE_API_BASE_URL=http://api…         # mixed content blocked on https grok.me
```

Optional browser token (prefer avoiding long-lived secrets in the client):

```bash
```

---

## 3. Copy-paste environment blocks

### A) Local / Grok Build preview

```bash
# backend
export CASUAL_BOARD_ENV=development
export CASUAL_BOARD_DATA_DIR=./backend/data
export CASUAL_BOARD_TOKEN=          # open-dev OK locally
export CASUAL_BOARD_CORS_ORIGINS=*

# web — empty base URL (proxy)
export VITE_API_BASE_URL=

cd backend && PYTHONPATH=. python -m uvicorn app.main:app --host 127.0.0.1 --port 8090
# other terminal:
npm run dev
```

### B) Production API (Debian)

```bash
# /etc/casual-board.env
CASUAL_BOARD_ENV=production
CASUAL_BOARD_HOST=127.0.0.1
CASUAL_BOARD_PORT=8090
CASUAL_BOARD_DATA_DIR=/var/lib/casual-board
CASUAL_BOARD_TOKEN=<secrets.token_urlsafe(32)>
CASUAL_BOARD_CORS_ORIGINS=https://discovery-system.grok.me
CASUAL_BOARD_PUBLIC_BASE_URL=https://api.your-domain.tld
CASUAL_BOARD_TRUST_PROXY=true
CASUAL_BOARD_TRUSTED_HOSTS=api.your-domain.tld
```

### C) Production web (rebuild for grok.me)

```bash
VITE_API_BASE_URL=https://api.your-domain.tld npm run build
# then publish via Grok Build
```

### D) Debian client / Hermes

```bash
export CASUAL_BOARD_API_URL=https://api.your-domain.tld
export CASUAL_BOARD_TOKEN=<same-as-server>
python -m casual_board_client.cli doctor
python -m casual_board_bridge.main doctor
```

Full templates: [`.env.example`](.env.example), [`.env.production.example`](.env.production.example).

---

## Monorepo layout

```text
backend/                 FastAPI + Pydantic v2 + optional PydanticAI
src/                     Web client (React) — Grok Build / grok.me entry
web/README.md            Pointer: web package is repo-root src/
debian-client/           Outbound CLI + offline cache + dashboard adapter port
debian-bridge/           Outbound Hermes allowlist bridge
deploy/self-host/        Free production target (systemd, Docker, Tunnel notes)
docs/
```

---

## API surface

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/health` | Liveness + revision |
| GET | `/v1/board` | Snapshot |
| GET | `/v1/board/stream` | SSE (HTTPS-friendly) |
| WS | `/v1/board/ws` | Live revisions (`wss://` in prod) |
| POST | `/v1/captures` | Structured capture |
| POST | `/v1/commands` | Allowlisted commands |
| GET | `/v1/actions/{id}` | Audit record |
| POST | `/v1/actions/{id}/approval` | System-changing approvals |
| POST | `/v1/chat` | Hermes panel — **no shell** |

Auth: `Authorization: Bearer $CASUAL_BOARD_TOKEN` when token set.  
Production **refuses** empty token (`CASUAL_BOARD_ENV=production`).

CORS in production defaults / requires  
`https://discovery-system.grok.me` (wildcard `*` is stripped).

---

## Production hardening (implemented)

- Explicit CORS for `https://discovery-system.grok.me`
- `proxy_headers` / `X-Forwarded-Proto` for HTTPS termination
- WebSocket origin check in production
- Env validation (token required in production; `https://` public URL)
- UI **API failure banner** when misconfigured / unreachable / auth fail
- Client-side validation of `VITE_API_BASE_URL` on `*.grok.me`

---

## Tests

```bash
cd backend && pip install -r requirements.txt && PYTHONPATH=. pytest -q
cd ../debian-client && pip install -r requirements.txt && PYTHONPATH=. pytest -q
```

---

## Security checklist

- [ ] `CASUAL_BOARD_TOKEN` set before any public API expose  
- [ ] CORS only `https://discovery-system.grok.me`  
- [ ] API only via HTTPS/WSS (Tunnel or reverse proxy)  
- [ ] Debian: no raw public `:8090`; tunnel to loopback  
- [ ] Chat / bridge never unrestricted shell  
- [ ] Never put owner/bridge tokens in VITE_* or browser JS  

**Not fully production-live** until API host + tunnel + token + rebuild of the
web app with `VITE_API_BASE_URL` are verified end-to-end.
