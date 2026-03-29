#!/usr/bin/env bash

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT/.pids"

if [ ! -f "$PID_FILE" ]; then
  echo "Nothing running (no .pids file found)."
  exit 0
fi

read -r BACKEND_PID FRONTEND_PID < "$PID_FILE"

stop_pid() {
  local pid=$1 name=$2
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" && echo "Stopped $name (PID $pid)"
  else
    echo "$name (PID $pid) was not running"
  fi
}

stop_pid "$BACKEND_PID"  "backend"
stop_pid "$FRONTEND_PID" "frontend"

rm -f "$PID_FILE"
echo "Done."
