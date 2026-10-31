"""Single source of PM2 app names used by syspanel UI and log whitelist.

Keep in sync with ``ecosystem.config.js`` ``apps[].name``.
"""

from __future__ import annotations

# Names from ecosystem.config.js (plus legacy single-instance aliases).
PM2_SAFE_NAMES: frozenset[str] = frozenset({
    "FB_Publisher_1",
    "FB_Publisher_2",
    "AI_Generator_1",
    "AI_Generator_2",
    "Maintenance",
    "Web_Dashboard",
    "9Router_Gateway",
    "Threads_AutoReply",
    "Threads_NewsWorker",
    "Threads_Publisher",
    # Studio (ADR-061) + sao lưu DB — trước PLAN-115 thiếu nên trang Panel không điều khiển được
    "Studio_Heavy",
    "Studio_Light",
    "VieNeu_TTS",
    "DB_Backup",
    # Legacy (pre _1/_2 scaling)
    "FB_Publisher",
    "AI_Generator",
})

# PM2 log filename stems (PM2 turns '_' → '-' in log file names).
PM2_LOG_MAP: dict[str, dict[str, str]] = {
    "FB_Publisher_1": {"out": "FB-Publisher-1-out.log", "error": "FB-Publisher-1-error.log"},
    "FB_Publisher_2": {"out": "FB-Publisher-2-out.log", "error": "FB-Publisher-2-error.log"},
    "AI_Generator_1": {"out": "AI-Generator-1-out.log", "error": "AI-Generator-1-error.log"},
    "AI_Generator_2": {"out": "AI-Generator-2-out.log", "error": "AI-Generator-2-error.log"},
    "Maintenance": {"out": "Maintenance-out.log", "error": "Maintenance-error.log"},
    "Web_Dashboard": {"out": "Web-Dashboard-out.log", "error": "Web-Dashboard-error.log"},
    "Threads_Publisher": {"out": "Threads-Publisher-out.log", "error": "Threads-Publisher-error.log"},
    "Threads_NewsWorker": {"out": "Threads-NewsWorker-out.log", "error": "Threads-NewsWorker-error.log"},
    "Threads_AutoReply": {"out": "Threads-AutoReply-out.log", "error": "Threads-AutoReply-error.log"},
    "Studio_Heavy": {"out": "Studio-Heavy-out.log", "error": "Studio-Heavy-error.log"},
    "Studio_Light": {"out": "Studio-Light-out.log", "error": "Studio-Light-error.log"},
    "VieNeu_TTS": {"out": "VieNeu-TTS-out.log", "error": "VieNeu-TTS-error.log"},
    "9Router_Gateway": {"out": "9Router-Gateway-out.log", "error": "9Router-Gateway-error.log"},
    # Legacy aliases → primary instance logs
    "FB_Publisher": {"out": "FB-Publisher-1-out.log", "error": "FB-Publisher-1-error.log"},
    "AI_Generator": {"out": "AI-Generator-1-out.log", "error": "AI-Generator-1-error.log"},
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
    "DB_Backup": {"label": "Sao lưu DB", "role": "3 giờ sáng tự sao lưu Postgres (giữ 14 bản) rồi dừng",
                  "if_stopped": "«Đã dừng» là bình thường; bấm Bật = sao lưu ngay một bản", "can_stop": True},
}
