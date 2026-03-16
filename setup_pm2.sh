#!/bin/bash

echo "========================================="
echo " Cài đặt PM2 & Cấu hình cho Auto Publisher "
echo "========================================="

# 1. Install Node.js and PM2 if not installed
if ! command -v pm2 &> /dev/null
then
    echo "[!] PM2 chưa được cài đặt. Tiến hành cài Node.js & PM2..."
    sudo apt update
    sudo apt install -y nodejs npm
    sudo npm install -g pm2
    echo "[V] Đã cài đặt xong PM2."
else
    echo "[V] PM2 đã được cài đặt sẵn."
fi

# 2. Xóa các process cũ nếu có
pm2 delete FB_Publisher &> /dev/null
pm2 delete AI_Generator &> /dev/null
pm2 delete Maintenance &> /dev/null
pm2 delete Web_Dashboard &> /dev/null

echo "=> Khởi chạy các Worker qua PM2..."

# 3. Start Workers with explicitly defined venv Python and current working directory
APP_DIR=$(pwd)
VENV_PYTHON="$APP_DIR/venv/bin/python"

# Export PYTHONPATH so the 'app' module can be resolved from anywhere
export PYTHONPATH="$APP_DIR"

pm2 start "xvfb-run -a $VENV_PYTHON workers/publisher.py" --name "FB_Publisher" --cwd "$APP_DIR" --update-env
pm2 start "xvfb-run -a $VENV_PYTHON workers/ai_generator.py" --name "AI_Generator" --cwd "$APP_DIR" --update-env
pm2 start "$VENV_PYTHON workers/maintenance.py" --name "Maintenance" --cwd "$APP_DIR" --update-env
pm2 start "$VENV_PYTHON run_web.py" --name "Web_Dashboard" --cwd "$APP_DIR" --update-env

# 4. Save PM2 configuration to start on boot
echo "=> Lưu cấu hình PM2 để tự khởi động cùng máy chủ (nếu cần)..."
pm2 save

echo "========================================="
echo " HOÀN TẤT!"
echo " Bạn có thể dùng các lệnh sau để quản lý:"
echo "   pm2 status       # Xem trạng thái các worker + Web_Dashboard"
echo "   pm2 logs         # Xem logs realtime"
echo "   pm2 restart all  # Khởi động lại tất cả (worker + web)"
echo "========================================="
