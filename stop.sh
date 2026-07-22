#!/bin/bash
# stop.sh — Stop ToolsAuto background / leftover processes

cd "$(dirname "$0")" || exit 1

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}=== STOP TOOLSAUTO ===${NC}"

kill_from_pid() {
    FILE=$1
    NAME=$2
    if [ -f "$FILE" ]; then
        PID=$(cat "$FILE")
        kill -15 "$PID" 2>/dev/null || true
        rm -f "$FILE"
        echo -e "${YELLOW}Stopped $NAME (PID: $PID)${NC}"
    fi
}

kill_from_pid ".run_web.pid" "Web"
kill_from_pid ".run_pub.pid" "FB Publisher"
kill_from_pid ".run_ai.pid" "AI Generator"
kill_from_pid ".run_maint.pid" "Maintenance"
kill_from_pid ".run_threads_pub.pid" "Threads Publisher"
kill_from_pid ".run_threads_news.pid" "Threads News"
kill_from_pid ".run_9router.pid" "9Router"
kill_from_pid ".run_w1.pid" "Legacy worker"

echo "pkill fallback..."
pkill -f "python app/features/facebook/workers/publisher.py" 2>/dev/null || true
pkill -f "python app/features/viral_intake/workers/ai_generator.py" 2>/dev/null || true
pkill -f "python app/features/system_panel/workers/maintenance.py" 2>/dev/null || true
pkill -f "python app/features/threads/workers/" 2>/dev/null || true
pkill -f "python workers/" 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "manage.py serve" 2>/dev/null || true

echo -e "${RED}Done.${NC}"
