#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT/.pids"

if [ -f "$PID_FILE" ]; then
  echo "Already running (found .pids). Run ./stop.sh first."
  exit 1
fi

echo "Starting backend..."
cd "$ROOT/backend"
uvicorn api.main:app --reload --port 8000 &> "$ROOT/backend.log" &
BACKEND_PID=$!

echo "Starting frontend..."
cd "$ROOT/frontend"
npm run dev &> "$ROOT/frontend.log" &
FRONTEND_PID=$!

echo "$BACKEND_PID $FRONTEND_PID" > "$PID_FILE"

echo ""
echo "Backend  → http://localhost:8000  (PID $BACKEND_PID)"
echo "Frontend → http://localhost:5173  (PID $FRONTEND_PID)"
echo ""
echo "Logs: backend.log / frontend.log"
echo "Stop with: ./stop.sh"
