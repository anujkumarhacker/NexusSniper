#!/usr/bin/env bash
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"
mkdir -p logs

SHUTTING_DOWN=0
ENGINE_BACKOFF=5

cleanup() {
    if [ "$SHUTTING_DOWN" -eq 1 ]; then exit 0; fi
    SHUTTING_DOWN=1
    echo -e "\n\033[1;91m🛑 Shutting down NexusSniper...\033[0m"
    [ -n "$DASHBOARD_PID" ] && kill -TERM "$DASHBOARD_PID" 2>/dev/null
    [ -n "$ENGINE_PID" ] && kill -TERM "$ENGINE_PID" 2>/dev/null
    sleep 1
    [ -n "$DASHBOARD_PID" ] && kill -9 "$DASHBOARD_PID" 2>/dev/null
    [ -n "$ENGINE_PID" ] && kill -9 "$ENGINE_PID" 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

clear
echo -e "\033[1;96m═══════════════════════════════════════════════════════════════════════════\033[0m"
echo -e "\033[1;97m ⚡ NEXUSSNIPER (NP) PRODUCTION LAUNCHER & SUPERVISOR\033[0m"
echo -e "\033[1;96m═══════════════════════════════════════════════════════════════════════════\033[0m\n"

echo -e "\033[1;90m[1/3] Mounting SQLite WAL Database...\033[0m"
python3 -c "import state_store; state_store.init_db()"

echo -e "\033[1;90m[2/3] Launching FastAPI Web Dashboard (http://127.0.0.1:8000)...\033[0m"
# FIX 6: Bind exclusively to localhost for security
python3 -m uvicorn web_dashboard:app --host 127.0.0.1 --port 8000 --no-access-log --log-level warning &
DASHBOARD_PID=$!
sleep 2

echo -e "\033[1;90m[3/3] Starting NexusSniper Algorithmic Trading Supervisor...\033[0m"
python3 engine.py &
ENGINE_PID=$!

echo -e "\033[1;92m✔ All microservices deployed successfully. Press Ctrl+C to stop.\033[0m\n"

while true; do
    sleep $ENGINE_BACKOFF
    if ! kill -0 $ENGINE_PID 2>/dev/null; then
        if [ "$SHUTTING_DOWN" -eq 0 ]; then
            # FIX 12: Exponential backoff on engine crashes
            echo -e "\033[1;91m⚠️ Engine process exited! Restarting engine in ${ENGINE_BACKOFF}s...\033[0m"
            python3 engine.py &
            ENGINE_PID=$!
            ENGINE_BACKOFF=$(( ENGINE_BACKOFF * 2 ))
            if [ $ENGINE_BACKOFF -gt 60 ]; then ENGINE_BACKOFF=60; fi
        fi
    else
        ENGINE_BACKOFF=5 # Reset backoff if stable
    fi

    if ! kill -0 $DASHBOARD_PID 2>/dev/null; then
        if [ "$SHUTTING_DOWN" -eq 0 ]; then
            echo -e "\033[1;91m⚠️ Dashboard exited! Restarting uvicorn...\033[0m"
            python3 -m uvicorn web_dashboard:app --host 127.0.0.1 --port 8000 --no-access-log --log-level warning &
            DASHBOARD_PID=$!
        fi
    fi
done
