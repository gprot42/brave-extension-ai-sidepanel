#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

# Default ports
BACKEND_PORT=8000
FRONTEND_PORT=3000

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    stop)
      echo "Stopping processes on ports $BACKEND_PORT and $FRONTEND_PORT..."
      lsof -ti :$BACKEND_PORT -ti :$FRONTEND_PORT 2>/dev/null | xargs kill 2>/dev/null || true
      echo "Done."
      exit 0
      ;;
    --backend-port) BACKEND_PORT="$2"; shift 2 ;;
    --frontend-port) FRONTEND_PORT="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [stop] [--backend-port PORT] [--frontend-port PORT]"
      echo "  stop             Kill running backend/frontend processes"
      echo "  --backend-port   Backend API port (default: 8000)"
      echo "  --frontend-port  Frontend dev server port (default: 3000)"
      exit 0
      ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Kill any stale processes on the target ports
for port in $BACKEND_PORT $FRONTEND_PORT; do
  pids=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Killing stale process on port $port..."
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 1
  fi
done

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
  exit 0
}
trap cleanup INT TERM

# Backend
cd "$DIR"
source backend/.venv/bin/activate
python -c "import uvicorn; uvicorn.run('backend.api.main:app', host='0.0.0.0', port=$BACKEND_PORT, log_level='info')" &
BACKEND_PID=$!

# Wait for backend to be ready
echo "Starting backend (port $BACKEND_PORT)..."
for i in $(seq 1 10); do
  sleep 1
  if curl -s http://127.0.0.1:$BACKEND_PORT/api/device > /dev/null 2>&1; then
    echo "Backend ready."
    break
  fi
done

# Frontend
cd "$DIR/frontend"
VITE_BACKEND_PORT=$BACKEND_PORT npx vite --port $FRONTEND_PORT --strictPort &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo ""
echo "Click 'Connect' in the dashboard to connect to the Helio Strap."
echo "Press Ctrl+C to stop.  (Or: ./start.sh stop)"
echo ""

wait
