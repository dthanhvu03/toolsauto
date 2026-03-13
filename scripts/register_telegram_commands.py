import sys
import os

# Ensure app module can be found
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import httpx
from app.config import TELEGRAM_BOT_TOKEN

commands = [
    {"command": "jobs", "description": "Danh sách jobs đang chờ"},
    {"command": "drafts", "description": "Xem & duyệt DRAFT jobs"},
    {"command": "done", "description": "5 bài đăng gần nhất"},
    {"command": "failed", "description": "Jobs lỗi + nút Retry"},
    {"command": "retry", "description": "Retry 1 job (VD: /retry 123)"},
    {"command": "cancel", "description": "Hủy job (VD: /cancel 123)"},
    {"command": "status", "description": "Trạng thái worker"},
    {"command": "pause", "description": "Tạm dừng worker"},
    {"command": "resume", "description": "Tiếp tục worker"},
    {"command": "safemode", "description": "Bật/tắt Safe Mode"},
    {"command": "restart", "description": "Restart worker"},
    {"command": "health", "description": "Health score hệ thống"},
    {"command": "sys", "description": "Thống số hệ thống"},
    {"command": "stats", "description": "Thống kê hôm nay"},
    {"command": "spy", "description": "Thêm đối thủ (VD: /spy TenAcc URL)"},
    {"command": "reup", "description": "Reup video (VD: /reup URL_TikTok)"},
    {"command": "help", "description": "Hiện menu trợ giúp"}
]

if not TELEGRAM_BOT_TOKEN:
    print("No TELEGRAM_BOT_TOKEN in config")
    sys.exit(1)

url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setMyCommands"
resp = httpx.post(url, json={"commands": commands})

if resp.status_code == 200:
    print("✅ Successfully registered Telegram Menu commands!")
else:
    print(f"❌ Failed: {resp.text}")
