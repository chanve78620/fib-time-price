#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8765}"
export PORT

# Free port if an old server is already bound (python http.server / flask)
if command -v ss >/dev/null 2>&1; then
  OLD_PIDS=$(ss -lptn "sport = :$PORT" 2>/dev/null | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | sort -u || true)
elif command -v lsof >/dev/null 2>&1; then
  OLD_PIDS=$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
else
  OLD_PIDS=""
fi
if [[ -n "${OLD_PIDS}" ]]; then
  echo "Stopping process(es) on port $PORT: $OLD_PIDS"
  # shellcheck disable=SC2086
  kill $OLD_PIDS 2>/dev/null || true
  sleep 0.4
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

# Ensure deps present
.venv/bin/python -c "import flask, yfinance" 2>/dev/null || .venv/bin/pip install -q yfinance flask

echo "Fib Time & Price → http://127.0.0.1:${PORT}/"
exec .venv/bin/python server.py
