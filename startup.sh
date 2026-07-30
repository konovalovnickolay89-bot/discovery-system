#!/bin/sh
set -eu
cd /workspace

if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8090/health; then
  mkdir -p /workspace/backend/data
  export CASUAL_BOARD_DATA_DIR=/workspace/backend/data
  export CASUAL_BOARD_HOST=127.0.0.1
  export CASUAL_BOARD_PORT=8090
  export CASUAL_BOARD_TOKEN="${CASUAL_BOARD_TOKEN:-dev-owner-token}"
  export CASUAL_BOARD_BRIDGE_TOKEN="${CASUAL_BOARD_BRIDGE_TOKEN:-dev-bridge-token}"
  export CASUAL_BOARD_UI_PASSWORD="${CASUAL_BOARD_UI_PASSWORD:-dev-ui-password}"
  export CASUAL_BOARD_SESSION_SECRET="${CASUAL_BOARD_SESSION_SECRET:-dev-session-secret}"
  export CASUAL_BOARD_AI_PROVIDER=function
  export CASUAL_BOARD_TRUSTED_HOSTS=127.0.0.1,localhost,testserver
  export CASUAL_BOARD_CORS_ORIGINS="https://discovery-system.grok.me,http://127.0.0.1:8080"
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

if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
  exit 0
fi
npm run dev >>/tmp/app-startup.log 2>&1 &
