#!/bin/bash
#
# start.sh — Start / stop ToolsAuto via ecosystem.config.js (source of truth).
#   ./start.sh       — pm2 start ecosystem (or direct fallback)
#   ./start.sh stop  — stop all known apps
#
set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

PM2_APPS=(
    FB_Publisher_1 FB_Publisher_2
    AI_Generator_1 AI_Generator_2
    Maintenance Web_Dashboard 9Router_Gateway
    Threads_AutoReply Threads_NewsWorker Threads_Publisher
    FB_Publisher AI_Generator
)

usage() {
    echo -e "${CYAN}Usage:${NC}"
    echo "  ./start.sh         Start via PM2 ecosystem.config.js"
    echo "  ./start.sh stop    Stop all ToolsAuto PM2 apps"
    echo "  ./start.sh -h      Help"
    echo ""
    echo "Web: http://localhost:8000"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
    exit 0
fi

if [ "${1:-}" = "stop" ]; then
    echo -e "${YELLOW}Stopping ToolsAuto...${NC}"
    if command -v pm2 &>/dev/null; then
        pm2 delete "${PM2_APPS[@]}" 2>/dev/null || true
        pm2 save 2>/dev/null || true
    fi
    [ -f "./stop.sh" ] && bash ./stop.sh || true
    echo -e "${GREEN}Stopped.${NC}"
    exit 0
fi

echo -e "${BLUE}=== ToolsAuto — start ===${NC}"

if [ ! -d "venv" ]; then
    echo -e "${RED}Missing venv. Run: python -m venv venv && ./venv/bin/pip install -r requirements.txt${NC}"
    exit 1
fi

VENV_PYTHON="$APP_DIR/venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo -e "${RED}Missing $VENV_PYTHON${NC}"
    exit 1
fi

source venv/bin/activate
export PYTHONPATH="$APP_DIR"

echo -e "${YELLOW}DB schema upgrade...${NC}"
python manage.py db upgrade

if command -v ss &>/dev/null; then
    if ss -tlnp 2>/dev/null | grep -q ':8000 '; then
        echo -e "${YELLOW}Warning: port 8000 in use. Consider ./start.sh stop first.${NC}"
    fi
elif command -v lsof &>/dev/null; then
    if lsof -i :8000 &>/dev/null; then
        echo -e "${YELLOW}Warning: port 8000 in use.${NC}"
    fi
fi

echo "Cleaning previous ToolsAuto processes..."
if command -v pm2 &>/dev/null; then
    pm2 delete "${PM2_APPS[@]}" 2>/dev/null || true
fi
pkill -f "python app/features/facebook/workers/publisher.py" 2>/dev/null || true
pkill -f "python app/features/viral_intake/workers/ai_generator.py" 2>/dev/null || true
pkill -f "python app/features/system_panel/workers/maintenance.py" 2>/dev/null || true
pkill -f "python app/features/threads/workers/" 2>/dev/null || true
pkill -f "python workers/" 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "manage.py serve" 2>/dev/null || true
pkill -f "9router" 2>/dev/null || true
sleep 1

if command -v pm2 &>/dev/null; then
    echo -e "${YELLOW}Starting via ecosystem.config.js...${NC}"
    pm2 start ecosystem.config.js --update-env
    # Standby secondary publishers/AI by default (same as previous start.sh)
    pm2 stop FB_Publisher_2 AI_Generator_2 2>/dev/null || true
    pm2 save
    echo ""
    echo -e "${GREEN}Started (PM2 + ecosystem.config.js).${NC}"
    echo "  pm2 status | pm2 logs | ./start.sh stop"
    echo -e "  ${CYAN}Web: http://localhost:8000${NC}"
    exit 0
fi

echo -e "${YELLOW}PM2 not found — starting background processes...${NC}"
if ! command -v xvfb-run &>/dev/null; then
    echo -e "${YELLOW}Warning: xvfb-run missing; browser workers may open windows.${NC}"
fi

$VENV_PYTHON manage.py serve --no-reload > web.log 2>&1 &
echo $! > .run_web.pid
sleep 2
env -u DISPLAY xvfb-run -a --server-args="-screen 0 1280x1024x24 -ac +extension GLX +render -noreset" \
    $VENV_PYTHON app/features/facebook/workers/publisher.py > pub_worker.log 2>&1 &
echo $! > .run_pub.pid
env -u DISPLAY xvfb-run -a --server-args="-screen 0 1280x1024x24 -ac +extension GLX +render -noreset" \
    $VENV_PYTHON app/features/viral_intake/workers/ai_generator.py > ai_worker.log 2>&1 &
echo $! > .run_ai.pid
$VENV_PYTHON app/features/system_panel/workers/maintenance.py > maint_worker.log 2>&1 &
echo $! > .run_maint.pid
$VENV_PYTHON app/features/threads/workers/publisher.py > threads_pub.log 2>&1 &
echo $! > .run_threads_pub.pid
$VENV_PYTHON app/features/threads/workers/news_worker.py > threads_news.log 2>&1 &
echo $! > .run_threads_news.pid

if command -v 9router &>/dev/null; then
    9router > 9router.log 2>&1 &
    echo $! > .run_9router.pid
else
    echo -e "${YELLOW}9router not installed — skipped.${NC}"
fi

echo ""
echo -e "${GREEN}Started (background PIDs). Prefer: sudo npm i -g pm2 && ./start.sh${NC}"
echo -e "  ${CYAN}Web: http://localhost:8000${NC}"
