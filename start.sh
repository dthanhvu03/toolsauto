#!/bin/bash
# start.sh - Kịch bản khởi động Auto Publisher Kiến Trúc Multi-Worker
# Chạy 1 lệnh này sẽ tự động khởi động cả Web API và 3 chuyên viên Worker độc lập

cd "$(dirname "$0")" || exit 1

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
magenta='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Chuẩn bị môi trường ===${NC}"

# Dọn dẹp tiến trình cũ (rác) nếu có
echo "Đang dọn dẹp các tiến trình bot & browser cũ (nếu có)..."
pkill -f "python workers/publisher.py" 2>/dev/null
pkill -f "python workers/ai_generator.py" 2>/dev/null
pkill -f "python workers/maintenance.py" 2>/dev/null
pkill -f "python worker.py" 2>/dev/null
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "chrome|chromedriver" 2>/dev/null
sleep 1

if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Ensure Python can find the 'app' module
export PYTHONPATH="$(pwd)"

# 1. Khởi động Web API
echo -e "${YELLOW}Khởi động Web API (FastAPI)...${NC}"
uvicorn app.main:app --host 0.0.0.0 --port 8000 > web.log 2>&1 &
WEB_PID=$!
echo -e "Web API đang chạy (PID: $WEB_PID). Log: web.log"
sleep 2

# 2. Khởi động Publisher Worker (Có Xvfb cho Playwright Facebook)
echo -e "${YELLOW}Khởi động Publisher Worker (Chuyên Đăng Bài)...${NC}"
xvfb-run -a python workers/publisher.py > pub_worker.log 2>&1 &
PUB_PID=$!
echo -e "Publisher đang chạy (PID: $PUB_PID). Log: pub_worker.log"

# 3. Khởi động AI Generator Worker (Có Xvfb cho Selenium Gemini)
echo -e "${YELLOW}Khởi động AI Generator Worker (Chuyên Mớm Prompt)...${NC}"
xvfb-run -a python workers/ai_generator.py > ai_worker.log 2>&1 &
AI_PID=$!
echo -e "AI Generator đang chạy (PID: $AI_PID). Log: ai_worker.log"

# 4. Khởi động Maintenance Worker (Không cần UI/Xvfb)
echo -e "${YELLOW}Khởi động Maintenance Worker (Chuyên Quét Dọn & Report)...${NC}"
python workers/maintenance.py > maint_worker.log 2>&1 &
MAINT_PID=$!
echo -e "Maintenance đang chạy (PID: $MAINT_PID). Log: maint_worker.log"

echo ""
echo -e "${GREEN}✅ HỆ THỐNG MULTI-WORKER ĐÃ KHỞI ĐỘNG XONG!${NC}"
echo "========================================="
echo "🌍 Truy cập Web: http://localhost:8000"
echo "🤖 Telegram Bot: Dùng lệnh /status để kiểm tra"
echo "========================================="

# Lưu PID
echo "$WEB_PID" > .run_web.pid
echo "$PUB_PID" > .run_pub.pid
echo "$AI_PID" > .run_ai.pid
echo "$MAINT_PID" > .run_maint.pid
