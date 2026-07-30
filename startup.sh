#!/bin/sh
set -eu
cd /workspace

# Authoritative Python API (backend/)
if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8090/health; then
  mkdir -p /workspace/backend/data
  export CASUAL_BOARD_DATA_DIR=/workspace/backend/data
  # open-dev for local preview; set CASUAL_BOARD_TOKEN for real deploys
  export CASUAL_BOARD_TOKEN="${CASUAL_BOARD_TOKEN:-}"
  export CASUAL_BOARD_ENABLE_AI=true
  (
    cd /workspace/backend
    PYTHONPATH=/workspace/backend \
      python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8090 \
      >>/tmp/casual-board-api.log 2>&1 &
  )
  i=0
  while [ "$i" -lt 40 ]; do
    if curl -sf -o /dev/null --max-time 1 http://127.0.0.1:8090/health; then
      break
    fi
    i=$((i + 1))
    sleep 0.25
  done
fi

# Web preview
if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
  exit 0
fi
npm run dev >>/tmp/app-startup.log 2>&1 &
