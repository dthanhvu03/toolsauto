#!/bin/bash
# stop.sh - Dừng toàn bộ hệ thống Multi-Worker Auto Publisher

cd "$(dirname "$0")" || exit 1

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${RED}=== DỪNG AUTO PUBLISHER ===${NC}"

# Hàm kill đọc từ file PID
kill_from_pid() {
    FILE=$1
    NAME=$2
    if [ -f "$FILE" ]; then
        PID=$(cat "$FILE")
        kill -15 "$PID" 2>/dev/null
        rm -f "$FILE"
        echo -e "${YELLOW}Đã gửi tín hiệu dừng $NAME (PID: $PID)${NC}"
    fi
}

kill_from_pid ".run_web.pid" "Web API"
kill_from_pid ".run_pub.pid" "Publisher Worker"
kill_from_pid ".run_ai.pid" "AI Generator Worker"
kill_from_pid ".run_maint.pid" "Maintenance Worker"
kill_from_pid ".run_w1.pid" "Old Worker 1"

echo "Dọn dẹp..."

echo "Kiểm tra và dọn dẹp các tiến trình sót lại (Pkill fallback)..."
pkill -f "python workers/publisher.py"
pkill -f "python workers/ai_generator.py"
pkill -f "python workers/maintenance.py"
pkill -f "python worker.py"
pkill -f "uvicorn app.main:app"

echo -e "${RED}Tất cả đã dừng hoàn toàn.${NC}"
