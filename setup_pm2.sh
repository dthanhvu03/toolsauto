#!/bin/bash
# Cài PM2 (nếu chưa có) rồi chạy start.sh — start.sh sẽ tự dùng PM2 để khởi động.
cd "$(dirname "$0")" || exit 1
if ! command -v pm2 &>/dev/null; then
    echo "[!] Đang cài PM2..."
    sudo apt update
    sudo apt install -y nodejs npm
    sudo npm install -g pm2
fi
exec ./start.sh
