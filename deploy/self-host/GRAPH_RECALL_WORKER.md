# Graph Recall worker (Debian) — installation

**Not claimed live until verification checklist at the bottom passes.**

Worker talks **only** to `http://127.0.0.1:8090` with `CASUAL_BOARD_GRAPH_RECALL_TOKEN`.  
Never uses Cloudflare URL, browser sessions, UI password, owner token, or host-bridge token.

## 1) API already running (loopback)

```bash
ss -lntp | grep 8090
# expect 127.0.0.1:8090 only
```

Ensure `/etc/casual-board.env` has:

```bash
CASUAL_BOARD_GRAPH_RECALL_TOKEN=<same secret used by worker>
CASUAL_BOARD_GRAPH_RECALL_LEASE_TTL_S=300
```

```bash
sudo systemctl restart casual-board-api
```

## 2) Install worker package as user `discovery-system`

```bash
sudo -u discovery-system -H bash -lc '
  mkdir -p /opt/casual-board
  cd /opt/casual-board && git pull origin main
  cd debian-graph-recall-worker
  python3 -m venv .venv
  .venv/bin/pip install -e .
'
```

## 3) Root-admin: copy token into worker env (do not print token)

```bash
sudo install -d -o discovery-system -g discovery-system -m 700 /home/discovery-system/.config/casual-board
# extract token without echoing it:
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
EOF
  chown discovery-system:discovery-system /home/discovery-system/.config/casual-board/graph-recall-worker.env
  chmod 600 /home/discovery-system/.config/casual-board/graph-recall-worker.env
'
```

## 4) Hermes profile + restricted toolset

```bash
sudo -u discovery-system -H bash -lc '
  mkdir -p "$HOME/.hermes/profiles/graph-recall"
  # Configure Hermes toolset "graph-recall-read-first":
  # allow Logseq/graph read+retrieve only
  # deny: shell, sudo, host admin, graph writes, journal writes, Casual Board owner
'
```

Worker invokes:

```text
hermes -z --toolset graph-recall-read-first --timeout <n>
```

(no `--yolo`)

## 5) User systemd service + lingering

```bash
sudo -u discovery-system -H bash -lc '
  mkdir -p ~/.config/systemd/user
  cp /opt/casual-board/deploy/self-host/casual-board-graph-recall-worker.service \
     ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable --now casual-board-graph-recall-worker
  systemctl --user status casual-board-graph-recall-worker --no-pager
'
# boot persistence without login:
sudo loginctl enable-linger discovery-system
```

## 6) Verification checklist (integration complete only if all pass)

1. API bound only to `127.0.0.1:8090`
2. `systemctl --user status casual-board-graph-recall-worker` active as discovery-system
3. Phone: safe Cook Studio task progresses  
   Safety checked → Local plan ready → Kitchen memory queued → working → returned
4. Kitchen memory items have validated Logseq paths under `/home/discovery-system/Logseq/graph`
5. Stop worker → local plan still usable; after lease expiry task visibly **queued** again
6. Restart worker → pending task completes **exactly once**
7. No token/password in logs, browser assets, task data, or install command output
