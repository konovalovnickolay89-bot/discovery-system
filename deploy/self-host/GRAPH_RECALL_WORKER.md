# Graph Recall worker (Debian) — installation

**Not claimed live until the verification checklist passes on the real machine.**

Worker talks **only** to `http://127.0.0.1:8090` with `CASUAL_BOARD_GRAPH_RECALL_TOKEN`.  
Never uses Cloudflare URL, browser sessions, UI password, owner token, or host-bridge token.

`/opt/casual-board` is a **deployed source snapshot**, not a git checkout.  
**Do not run `git pull` inside `/opt/casual-board`.**

## 0) Hermes CLI shape (verify on the host before install)

```bash
sudo -u discovery-system -H bash -lc '
  export PATH=/home/discovery-system/.local/bin:/usr/local/bin:/usr/bin:/bin
  hermes --help | head -40
'
```

Expected:

* `hermes -z` / `--oneshot <PROMPT>` — prompt as argument, not stdin  
* **no** Hermes `--timeout` (worker uses Python `subprocess` timeout)  
* Graph Recall profile at `HERMES_HOME=~/.hermes/profiles/graph-recall` owns retrieval/tools  

Casual Board **does not** call host graph CLIs. Invocation is only:

```bash
HERMES_HOME=/home/discovery-system/.hermes/profiles/graph-recall hermes -z '<prompt>'
```

## 1) Fetch revision into a temp location (not /opt/casual-board)

```bash
REV=d3e1aa7   # replace with the commit you are installing
STAGE=$(mktemp -d /tmp/casual-board-stage.XXXXXX)
sudo -u discovery-system git clone --depth 1 \
  https://github.com/konovalovnickolay89-bot/discovery-system.git "$STAGE/repo"
sudo -u discovery-system git -C "$STAGE/repo" fetch --depth 1 origin "$REV"
sudo -u discovery-system git -C "$STAGE/repo" checkout "$REV"
```

## 2) Backup deployed backend

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
sudo mkdir -p /var/backups/casual-board
sudo tar -C /opt -czf "/var/backups/casual-board/casual-board-${TS}.tgz" casual-board
```

## 3) Synchronise backend + worker into /opt/casual-board (preserve venvs)

```bash
sudo rsync -a --delete \
  --exclude '.venv' --exclude 'data' --exclude '__pycache__' --exclude '*.pyc' \
  "$STAGE/repo/backend/" /opt/casual-board/backend/

sudo mkdir -p /opt/casual-board/debian-graph-recall-worker
sudo rsync -a --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  "$STAGE/repo/debian-graph-recall-worker/" /opt/casual-board/debian-graph-recall-worker/

sudo mkdir -p /opt/casual-board/deploy/self-host
sudo rsync -a "$STAGE/repo/deploy/self-host/" /opt/casual-board/deploy/self-host/

sudo chown -R discovery-system:discovery-system /opt/casual-board
```

## 4) API env + restart (loopback unchanged)

Ensure `/etc/casual-board.env` includes (do not print tokens):

* `CASUAL_BOARD_GRAPH_RECALL_TOKEN`
* `CASUAL_BOARD_GRAPH_RECALL_LEASE_TTL_S=300`
* `CASUAL_BOARD_EVIDENCE_AI_PROVIDER=none` (default — no second model keys required)
* Optional Mistral reviewer is **API-only** (`/etc/casual-board.env`):  
  `CASUAL_BOARD_EVIDENCE_AI_PROVIDER=mistral`,  
  `CASUAL_BOARD_EVIDENCE_AI_MODEL=mistral:mistral-small-latest`,  
  `MISTRAL_API_KEY=...`  
  Never put `MISTRAL_API_KEY` in this worker env file.

```bash
sudo systemctl restart casual-board-api
ss -lntp | grep 8090   # must be 127.0.0.1:8090 only
```

## 5) Install worker as discovery-system (preserve/create user venv)

```bash
sudo -u discovery-system -H bash -lc '
  export PATH=/home/discovery-system/.local/bin:/usr/local/bin:/usr/bin:/bin
  cd /opt/casual-board/debian-graph-recall-worker
  if [ ! -d .venv ]; then python3 -m venv .venv; fi
  .venv/bin/pip install -U pip
  .venv/bin/pip install -e .
  .venv/bin/python -m casual_board_graph_recall_worker verify-cli
'
```

`verify-cli` must exit 0 before enabling the service.

## 6) Worker env file (token copy without printing)

```bash
sudo install -d -o discovery-system -g discovery-system -m 700 \
  /home/discovery-system/.config/casual-board
sudo bash -lc '
  set -euo pipefail
  umask 077
  tok=$(grep -E "^CASUAL_BOARD_GRAPH_RECALL_TOKEN=" /etc/casual-board.env | cut -d= -f2-)
  test -n "$tok"
  cat > /home/discovery-system/.config/casual-board/graph-recall-worker.env <<EOF
CASUAL_BOARD_API_URL=http://127.0.0.1:8090
CASUAL_BOARD_GRAPH_RECALL_TOKEN=$tok
CASUAL_BOARD_GRAPH_RECALL_WORKER_ID=graph-recall@debian-minimal
CASUAL_BOARD_GRAPH_RECALL_LEASE_TTL_S=300
CASUAL_BOARD_GRAPH_RECALL_HERMES_TIMEOUT_S=240
HOME=/home/discovery-system
HERMES_HOME=/home/discovery-system/.hermes/profiles/graph-recall
PATH=/home/discovery-system/.local/bin:/usr/local/bin:/usr/bin:/bin
EOF
  chown discovery-system:discovery-system /home/discovery-system/.config/casual-board/graph-recall-worker.env
  chmod 600 /home/discovery-system/.config/casual-board/graph-recall-worker.env
'
```

## 7) Enable user worker service + linger

```bash
sudo -u discovery-system -H bash -lc '
  mkdir -p ~/.config/systemd/user
  cp /opt/casual-board/deploy/self-host/casual-board-graph-recall-worker.service \
     ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable --now casual-board-graph-recall-worker
  systemctl --user status casual-board-graph-recall-worker --no-pager
'
sudo loginctl enable-linger discovery-system
```

## 8) Cleanup stage

```bash
sudo rm -rf "$STAGE"
```

## Verification checklist (integration complete only if all pass)

1. API bound only to `127.0.0.1:8090`
2. Worker active as `discovery-system`
3. Phone safe task: queued → working → **returned** with cited Graph Recall paths
4. Worker process is `hermes -z …` only (no host graph CLI from Casual Board)
5. Stop worker → local plan usable; lease expiry → visibly **queued**
6. Restart → completes **once**
7. No token/password in logs, browser assets, or install output
