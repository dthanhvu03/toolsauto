#!/bin/bash
#
# start.sh — Khởi động / dừng toàn bộ Auto Publisher (Web + 4 Worker).
#   ./start.sh       — Khởi động (PM2 nếu có, không thì chạy 4 process nền).
#   ./start.sh stop  — Dừng toàn bộ.
#
set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

# ─── Colors ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ─── Help ───────────────────────────────────────────────────────────────
usage() {
    echo -e "${CYAN}Usage:${NC}"
    echo "  ./start.sh         Khởi động Web + 4 Worker (PM2 nếu có, không thì nền)"
    echo "  ./start.sh stop    Dừng toàn bộ"
    echo "  ./start.sh -h      Hiện trợ giúp"
    echo ""
    echo "Sau khi chạy: Web http://localhost:8000 | Telegram /status"
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
    exit 0
fi

# ─── Stop ───────────────────────────────────────────────────────────────
if [ "${1:-}" = "stop" ]; then
    echo -e "${YELLOW}Đang dừng Auto Publisher...${NC}"
    if command -v pm2 &>/dev/null; then
        pm2 delete FB_Publisher AI_Generator Maintenance Web_Dashboard 2>/dev/null || true
        pm2 save 2>/dev/null || true
    fi
    [ -f "./stop.sh" ] && bash ./stop.sh || true
    echo -e "${GREEN}Đã dừng.${NC}"
    exit 0
fi

# ─── Preflight ───────────────────────────────────────────────────────────
echo -e "${BLUE}=== Auto Publisher — Khởi động ===${NC}"

if [ ! -d "venv" ]; then
    echo -e "${RED}Lỗi: Chưa có thư mục venv. Chạy: python -m venv venv && ./venv/bin/pip install -r requirements.txt${NC}"
    exit 1
fi

VENV_PYTHON="$APP_DIR/venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo -e "${RED}Lỗi: Không tìm thấy $VENV_PYTHON${NC}"
    exit 1
fi

source venv/bin/activate
export PYTHONPATH="$APP_DIR"

# Run database migrations (auto-sync schema)
echo -e "${YELLOW}Kiểm tra/Cập nhật Database Schema...${NC}"
python manage.py db upgrade

# Kiểm tra port 8000 (tránh bind failed)
if command -v ss &>/dev/null; then
    if ss -tlnp 2>/dev/null | grep -q ':8000 '; then
        echo -e "${YELLOW}Cảnh báo: Port 8000 đang được dùng. Dừng tiến trình cũ hoặc chạy ./start.sh stop trước.${NC}"
    fi
elif command -v lsof &>/dev/null; then
    if lsof -i :8000 &>/dev/null; then
        echo -e "${YELLOW}Cảnh báo: Port 8000 đang được dùng.${NC}"
    fi
fi

# ─── Dọn tiến trình cũ (chỉ tiến trình của project, không kill Chrome hệ thống) ─
echo "Dọn tiến trình cũ của project..."
pm2 delete FB_Publisher AI_Generator Maintenance Web_Dashboard 2>/dev/null || true
pkill -f "python workers/publisher.py" 2>/dev/null || true
pkill -f "python workers/ai_generator.py" 2>/dev/null || true
pkill -f "python workers/maintenance.py" 2>/dev/null || true
pkill -f "python worker.py" 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "run_web.py" 2>/dev/null || true
sleep 1

# ─── Khởi động qua PM2 ────────────────────────────────────────────────────
# Dùng bash -c 'unset DISPLAY; exec xvfb-run...' để PM2 không truyền DISPLAY=:0 → tránh Chrome mở cửa sổ thật
if command -v pm2 &>/dev/null; then
    echo -e "${YELLOW}Khởi động qua PM2...${NC}"
    # Guardrails for 8GB RAM machines (override via env if needed)
    PM2_MEM_PUBLISHER="${PM2_MEM_PUBLISHER:-1200M}"
    PM2_MEM_AI="${PM2_MEM_AI:-900M}"
    PM2_MEM_MAINT="${PM2_MEM_MAINT:-800M}"
    PM2_MEM_WEB="${PM2_MEM_WEB:-500M}"

    pm2 start "bash -c 'unset DISPLAY; exec env -u DISPLAY xvfb-run --server-num=99 --server-args=\"-screen 0 1280x1024x24 -ac +extension GLX +render -noreset\" $VENV_PYTHON workers/publisher.py'" \
        --name "FB_Publisher" --cwd "$APP_DIR" --update-env --time --max-memory-restart "$PM2_MEM_PUBLISHER"
    pm2 start "bash -c 'unset DISPLAY; exec env -u DISPLAY xvfb-run --server-num=100 --server-args=\"-screen 0 1280x1024x24 -ac +extension GLX +render -noreset\" $VENV_PYTHON workers/ai_generator.py'" \
        --name "AI_Generator" --cwd "$APP_DIR" --update-env --time --max-memory-restart "$PM2_MEM_AI"
    pm2 start "$VENV_PYTHON workers/maintenance.py" \
        --name "Maintenance" --cwd "$APP_DIR" --update-env --time --max-memory-restart "$PM2_MEM_MAINT"
    pm2 start "$VENV_PYTHON manage.py serve --no-reload" \
        --name "Web_Dashboard" --cwd "$APP_DIR" --update-env --time --max-memory-restart "$PM2_MEM_WEB"
    pm2 save
    echo ""
    echo -e "${GREEN}✅ Đã khởi động (PM2).${NC}"
    echo "  pm2 status        — trạng thái"
    echo "  pm2 logs         — log realtime"
    echo "  pm2 restart all  — khởi động lại"
    echo "  ./start.sh stop  — dừng"
    echo -e "  ${CYAN}Web: http://localhost:8000${NC}"
    exit 0
fi

# ─── Khởi động trực tiếp (không PM2) ─────────────────────────────────────
echo -e "${YELLOW}Khởi động trực tiếp (không PM2)...${NC}"

if ! command -v xvfb-run &>/dev/null; then
    echo -e "${YELLOW}Cảnh báo: xvfb-run chưa cài. Worker Facebook/AI có thể mở cửa sổ trình duyệt.${NC}"
    echo "  Cài: sudo apt install xvfb"
fi

$VENV_PYTHON manage.py serve --no-reload > web.log 2>&1 &
WEB_PID=$!
sleep 2
env -u DISPLAY xvfb-run --server-num=99 --server-args="-screen 0 1280x1024x24 -ac +extension GLX +render -noreset" $VENV_PYTHON workers/publisher.py > pub_worker.log 2>&1 &
PUB_PID=$!
env -u DISPLAY xvfb-run --server-num=100 --server-args="-screen 0 1280x1024x24 -ac +extension GLX +render -noreset" $VENV_PYTHON workers/ai_generator.py > ai_worker.log 2>&1 &
AI_PID=$!
$VENV_PYTHON workers/maintenance.py > maint_worker.log 2>&1 &
MAINT_PID=$!

echo $WEB_PID > .run_web.pid
echo $PUB_PID > .run_pub.pid
echo $AI_PID > .run_ai.pid
echo $MAINT_PID > .run_maint.pid

echo ""
echo -e "${GREEN}✅ Đã khởi động (4 process nền).${NC}"
echo "  ./start.sh stop  — dừng"
echo "  Log: web.log, pub_worker.log, ai_worker.log, maint_worker.log"
echo -e "  ${CYAN}Web: http://localhost:8000${NC}"
echo -e "${YELLOW}Gợi ý: Cài PM2 (sudo npm i -g pm2) rồi chạy lại ./start.sh để quản lý gọn hơn.${NC}"
