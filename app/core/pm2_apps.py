"""Single source of PM2 app names used by syspanel UI and log whitelist.

Keep in sync with ``ecosystem.config.js`` ``apps[].name``.
"""

from __future__ import annotations

# Names from ecosystem.config.js. PLAN-166: FB_Publisher / AI_Generator / Threads cũ đã bỏ (đăng qua Buffer).
PM2_SAFE_NAMES: frozenset[str] = frozenset({
    "Maintenance",
    "Web_Dashboard",
    "9Router_Gateway",
    "Threads_Growth",  # PLAN-158 kéo khách về bot
    # Studio (ADR-061) + sao lưu DB — trước PLAN-115 thiếu nên trang Panel không điều khiển được
    "Studio_Heavy",
    "Studio_Light",
    "VieNeu_TTS",
    "DB_Backup",
    "shopee-mcp",
})

# PM2 log filename stems (PM2 turns '_' → '-' in log file names).
PM2_LOG_MAP: dict[str, dict[str, str]] = {
    "Maintenance": {"out": "Maintenance-out.log", "error": "Maintenance-error.log"},
    "Web_Dashboard": {"out": "Web-Dashboard-out.log", "error": "Web-Dashboard-error.log"},
    "Threads_Growth": {"out": "Threads-Growth-out.log", "error": "Threads-Growth-error.log"},
    "Studio_Heavy": {"out": "Studio-Heavy-out.log", "error": "Studio-Heavy-error.log"},
    "Studio_Light": {"out": "Studio-Light-out.log", "error": "Studio-Light-error.log"},
    "VieNeu_TTS": {"out": "VieNeu-TTS-out.log", "error": "VieNeu-TTS-error.log"},
    "9Router_Gateway": {"out": "9Router-Gateway-out.log", "error": "9Router-Gateway-error.log"},
    "shopee-mcp": {"out": "shopee-mcp-out.log", "error": "shopee-mcp-error.log"},
    "DB_Backup": {"out": "DB-Backup-out.log", "error": "DB-Backup-error.log"},
}


# PLAN-115 — mô tả cho bảng tiến trình trên web: tên dễ hiểu, làm gì, tắt thì sao.
# ``can_stop=False``: không cho tắt từ web (Web_Dashboard tắt là mất luôn trang đang bấm).
APP_INFO: dict[str, dict] = {
    "Web_Dashboard": {"label": "Web quản trị", "role": "Trang web anh đang dùng + API",
                      "if_stopped": "Mất trang web — không tắt từ đây được, chỉ khởi động lại", "can_stop": False},
    "Maintenance": {"label": "Bảo trì", "role": "Xếp lịch Buffer, dọn file, đồng bộ trạng thái",
                    "if_stopped": "Video READY không được tự hẹn lên Buffer", "can_stop": True},
    "Studio_Heavy": {"label": "Studio · việc nặng", "role": "Phân tích (Whisper), lồng tiếng, render, caption",
                     "if_stopped": "Video dừng ở bước đang chờ, bật lại thì chạy tiếp", "can_stop": True},
    "Studio_Light": {"label": "Studio · việc nhẹ", "role": "Tải link, nhận file, dựng, gửi Telegram, chuyển Buffer",
                     "if_stopped": "Video dừng ở bước đang chờ, bật lại thì chạy tiếp", "can_stop": True},
    "VieNeu_TTS": {"label": "Giọng đọc VieNeu (GPU)", "role": "Giữ sẵn model giọng Việt cho bước lồng tiếng",
                   "if_stopped": "Lồng tiếng tự dùng giọng edge-tts; bật lại mất ~1 phút nạp model", "can_stop": True},
    "9Router_Gateway": {"label": "Cổng AI (9Router)", "role": "Cổng gọi AI (caption, dịch, viết nội dung)",
                        "if_stopped": "Caption AI / dịch có thể lỗi hoặc đổi sang đường dự phòng", "can_stop": True},
    "Threads_Growth": {"label": "Threads · kéo khách", "role": "Quét Threads theo từ khóa, tự reply kéo khách về 2 bot",
                       "if_stopped": "Không quét / reply nữa; bài đã duyệt nằm chờ tới khi bật lại", "can_stop": True},
    "DB_Backup": {"label": "Sao lưu DB", "role": "3 giờ sáng tự sao lưu Postgres (giữ 14 bản) rồi dừng",
                  "if_stopped": "«Đã dừng» là bình thường; bấm Bật = sao lưu ngay một bản", "can_stop": True},
}


# Bot chạy bằng systemd (không qua PM2) — Panel hệ thống chỉ XEM trạng thái, không bật / tắt từ web
# (chủ bot tự restart: `systemctl restart cashback-bot cashback-zalo`, `systemctl restart store-bot store-api`).
SYSTEMD_SERVICES: dict[str, dict] = {
    "cashback-bot": {"label": "Cashback · Telegram", "group": "Bot Cashback (@zt_shopee_bot)",
                     "role": "Bot hoàn tiền Shopee / TikTok trên Telegram",
                     "manage": "systemctl restart cashback-bot cashback-zalo"},
    "cashback-zalo": {"label": "Cashback · Zalo", "group": "Bot Cashback (@zt_shopee_bot)",
                      "role": "Kênh Zalo của bot hoàn tiền",
                      "manage": "systemctl restart cashback-bot cashback-zalo"},
    "store-bot": {"label": "AI Pass Store · Telegram", "group": "Bot AI Pass Store (@aipass_shop_bot)",
                  "role": "Bot bán tài khoản AI trên Telegram",
                  "manage": "systemctl restart store-bot store-api"},
    "store-api": {"label": "AI Pass Store · API", "group": "Bot AI Pass Store (@aipass_shop_bot)",
                  "role": "API đại lý + webhook nạp tiền",
                  "manage": "systemctl restart store-bot store-api"},
}
