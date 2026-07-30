# Web client

The phone/desktop **Casual Board** UI lives at the **repository root** (`src/`, Vite, TanStack Start) so Grok Build’s live preview and publish pipeline work without path hacks.

Treat this folder as a pointer:

| Concern | Location |
| --- | --- |
| Components / styles | `/src` |
| Dev server | `npm run dev` (root) |
| API base URL | `VITE_API_BASE_URL` (empty = same-origin proxy) |

Published on **grok.me**, the UI should call your **external** Python API (`VITE_API_BASE_URL`), because Grok hosting does not run the FastAPI package in `backend/`.
