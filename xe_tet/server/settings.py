"""Thiết lập admin (camera, hiển thị, thời gian) — lưu ở storage/db/config/xe_tet.json để qua được restart / deploy."""

import json
import logging
import os
import re
from pathlib import Path

from .game.engine import BOARD_SECONDS, REST_SECONDS
from .game.geo import DEFAULT_DEPARTURE
from .game.network import available

ROOT = Path(__file__).resolve().parents[2]
# XE_TET_SETTINGS: máy chủ thử (e2e, cổng 8811) dùng file thiết lập riêng — bấm thử không đổi thiết lập của server thật.
PATH = Path(os.getenv("XE_TET_SETTINGS") or ROOT / "storage" / "db" / "config" / "xe_tet.json")

VIEWS = ("outside", "inside")
CAMS = ("wide", "high", "side", "close")
QUALITIES = ("high", "low")

DEFAULTS: dict = {
    "view": "outside",  # outside | inside
    "cam": "wide",  # góc máy ngoài xe
    "zoom": 1.0,  # 0.6 (gần) … 1.6 (xa)
    "fade": False,  # mờ nhẹ khi đổi cảnh; tắt = cắt thẳng (tránh nhấp nháy)
    "quality": "high",  # low: ~60 % độ phân giải, tắt bóng đổ, bớt hạt (máy yếu / LIVE Studio giật)
    "auto_loxe": True,  # lơ xe tự nói theo tình huống
    "show_route": True,
    "show_loxe": True,
    "show_toasts": True,
    "show_board": True,
    "board_seconds": int(BOARD_SECONDS),
    "rest_seconds": int(REST_SECONDS),
    "tiktok_user": "",  # @username nối lần trước, để admin bấm nối lại nhanh
    "tiktok_auto": False,  # đang nối khi server tắt → bật lên tự nối lại (PM2 khởi động lại giữa live)
    "departure": DEFAULT_DEPARTURE,  # bến đi (BRD-tuyen-xe BR-8)
    "relief_auto": True,
    "music_on": True,  # nhạc trong xe (PLAN-127); tắt = chỉ còn tiếng hiệu ứng
    "music_volume": 0.5,
    "sfx_volume": 0.6,  # còi, pháo hoa, tiếng máy
    "voice_on": True,  # Anh Tư lơ xe đọc (PLAN-128)
    "voice_name": "Adam",  # giọng VieNeu (nam, miền Nam, tự nhiên)
    "voice_volume": 0.9,  # làn đủ một xe người chờ thì tự gọi xe tăng cường (PLAN-125); tắt: chỉ gọi bằng tay / quà
}

BOARD_RANGE = (20, 900)  # giây đón khách admin chỉnh được
REST_RANGE = (20, 300)
log = logging.getLogger("xe_tet")


def clean(changes: dict, current: dict | None = None) -> dict:
    """Ghép thay đổi vào thiết lập hiện tại, bỏ khoá lạ, kẹp giá trị về khoảng hợp lệ."""
    out = dict(current or DEFAULTS)
    for key, value in changes.items():
        if key not in DEFAULTS:
            continue
        if key == "view" and value in VIEWS:
            out[key] = value
        elif key == "cam" and value in CAMS:
            out[key] = value
        elif key == "quality" and value in QUALITIES:
            out[key] = value
        elif key == "departure" and value in available():  # theo dữ liệu tuyến đã dựng, không chỉ bảng code
            out[key] = value
        elif key == "voice_name":
            out[key] = str(value or "")[:40] or out[key]
        elif key in ("music_volume", "sfx_volume", "voice_volume"):
            out[key] = round(min(1.0, max(0.0, float(value))), 2)
        elif key == "zoom":
            out[key] = round(min(1.6, max(0.6, float(value))), 2)
        elif key == "board_seconds":
            out[key] = int(min(BOARD_RANGE[1], max(BOARD_RANGE[0], float(value))))
        elif key == "rest_seconds":
            out[key] = int(min(REST_RANGE[1], max(REST_RANGE[0], float(value))))
        elif key == "tiktok_user":
            text = str(value or "")
            out[key] = text if re.fullmatch(r"[A-Za-z0-9._]{0,24}", text) else out[key]
        elif isinstance(DEFAULTS[key], bool):
            out[key] = bool(value)
    return out


def load() -> dict:
    try:
        return clean(json.loads(PATH.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return dict(DEFAULTS)
    except (ValueError, OSError):
        log.exception("đọc %s lỗi, dùng mặc định", PATH)
        return dict(DEFAULTS)


def save(settings: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PATH)
