#!/bin/zsh
set -e
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

BUNDLED_PYTHON="/Users/x.wang/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
if [[ -x "$BUNDLED_PYTHON" ]]; then
  PYTHON_BIN="$BUNDLED_PYTHON"
else
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" server.py &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM
sleep 1
open "http://${POSTER_HOST:-127.0.0.1}:${POSTER_PORT:-8788}"
wait "$SERVER_PID"

