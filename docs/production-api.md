# Production API arrangement — discovery-system.grok.me

## Answers (authoritative)

### 1. Where will FastAPI run after the Vite UI is published?

**Not on grok.me.**  
Publish places the **web UI** at `https://discovery-system.grok.me` using the
Nitro/`vercel` Node runtime. The FastAPI package in `backend/` must run on a
**separate Python process** you control (recommended: Debian + Cloudflare Tunnel).

### 2. What exact value should `VITE_API_BASE_URL` have?

| Environment | Exact value |
| --- | --- |
| Development (preview) | **empty string / unset** |
| Production (grok.me UI) | **`https://<your-api-host>`** with no trailing slash |

Example production: `https://api.example.com`  
Not: `http://…`, not `localhost`, not empty on grok.me.

### 3. Does grok.me provide same-origin server/API routes for FastAPI?

**No for Python/FastAPI.**  
Grok.me runs the **Node Nitro server** (`__server`) + static assets. It can host
TanStack server functions written in this Node app, but **this project’s board
API is FastAPI** and is **not** compiled into that runtime. Calling
`https://discovery-system.grok.me/v1/board` after publish does **not** reach
uvicorn unless you separately reverse-proxy that path to Python (not provided
by default).

### 4. Separate host configuration

See **`deploy/self-host/`** — free self-host + Cloudflare Tunnel.  
No paid provider was selected; choose one only if you ask for it.

### 5. Hardening delivered

- CORS allowlist for `https://discovery-system.grok.me`
- HTTPS proxy headers + WSS-capable WebSocket endpoint
- Production env validation (token required)
- UI failure banner for misconfig / unreachable API
