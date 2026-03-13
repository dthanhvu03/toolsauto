#!/bin/bash
# Script dừng dự án một cách an toàn và dọn dẹp không gian tmux

cd "$(dirname "$0")" || exit 1

SESSION_NAME="worker_ngam"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== BẮT ĐẦU DỌN DẸP DỰ ÁN ===${NC}"

# Bước 1: Gửi lệnh tắt an toàn qua stop.sh trước
if [ -f "./stop.sh" ]; then
    echo "Đang dừng các tiến trình qua stop.sh..."
    bash ./stop.sh
else
    echo "Không tìm thấy file stop.sh, sẽ dùng pkill để dọn dẹp..."
    pkill -f "python worker.py" 2>/dev/null
    pkill -f "uvicorn app.main:app" 2>/dev/null
fi

# Bước 2: Tắt luôn không gian bộ nhớ tmux đang chạy ngầm
tmux has-session -t $SESSION_NAME 2>/dev/null
if [ $? == 0 ]; then
    echo "Đang tắt session tmux '$SESSION_NAME'..."
    tmux kill-session -t $SESSION_NAME 2>/dev/null
    echo -e "${GREEN}Đã xóa sạch session chạy ngầm.${NC}"
else
    echo -e "${YELLOW}Không có session nào đang chạy.${NC}"
fi

# Bước 3: Dọn dẹp rác & Chrome/Chromium dư thừa phòng trường hợp kẹt
echo "Kiểm tra và dọn dẹp trình duyệt kẹt (nếu có)..."
pkill -f "chrome|chromedriver|chromium" 2>/dev/null

echo "========================================================="
echo -e "${GREEN}✅ HỆ THỐNG ĐÃ ĐƯỢC TẮT VÀ DỌN DẸP SẠCH SẼ!${NC}"
echo "========================================================="
