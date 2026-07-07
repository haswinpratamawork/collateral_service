#!/usr/bin/env bash
# Start the Rumah123 listing-extractor API (FastAPI + uvicorn).
#
# Usage (from anywhere):
#   ./api/run_api.sh                # serve on 0.0.0.0:8030
#   ./api/run_api.sh 127.0.0.1 9100 # custom host + port
#   HOST=0.0.0.0 PORT=8030 RELOAD=1 ./api/run_api.sh
set -euo pipefail

# The script lives in api/, but uvicorn must run from the repo root so the `api`
# package and the project .venv resolve.
cd "$(dirname "$0")/.."

HOST="${1:-${HOST:-0.0.0.0}}"
PORT="${2:-${PORT:-8030}}"
RELOAD="${RELOAD:-1}"   # 1 = auto-reload on code change (dev); set 0 for production

# Prefer the project virtualenv if present.
if [ -x ".venv/bin/uvicorn" ]; then
  UVICORN=".venv/bin/uvicorn"
elif [ -x ".venv/bin/python" ]; then
  UVICORN=".venv/bin/python -m uvicorn"
else
  UVICORN="uvicorn"
fi

# Warn (don't fail) if the geocoding key is missing — LT/LB still work, kode pos/kelurahan won't.
if [ -f .env ] && ! grep -qE '^GOOGLE_MAPS_API_KEY=.+' .env; then
  echo "WARNING: GOOGLE_MAPS_API_KEY is empty in .env — kode_pos/kelurahan will be null." >&2
fi

RELOAD_FLAG=""
[ "$RELOAD" = "1" ] && RELOAD_FLAG="--reload"

echo "Starting API on http://${HOST}:${PORT}  (docs: http://${HOST}:${PORT}/docs)"
exec $UVICORN api.main:app --host "$HOST" --port "$PORT" $RELOAD_FLAG
