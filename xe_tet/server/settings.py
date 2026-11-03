"""Thiết lập admin (camera, hiển thị, thời gian) — lưu ở storage/db/config/xe_tet.json để qua được restart / deploy."""

import json
import logging
import os
import re
from pathlib import Path

from .game.engine import BOARD_SECONDS, FEATURE_MODES, REST_SECONDS, TRIP_MINUTES
from .game.geo import DEFAULT_DEPARTURE
from .game.network import available
from .game.talk import TALK_STYLES

ROOT = Path(__file__).resolve().parents[2]
# XE_TET_SETTINGS: máy chủ thử (e2e, cổng 8811) dùng file thiết lập riêng — bấm thử không đổi thiết lập của server thật.
PATH = Path(os.getenv("XE_TET_SETTINGS") or ROOT / "storage" / "db" / "config" / "xe_tet.json")

VIEWS = ("outside", "inside")
CAMS = ("wide", "high", "side", "close")
QUALITIES = ("high", "medium", "low")

DEFAULTS: dict = {
    "view": "outside",  # outside | inside
    "cam": "wide",  # góc máy ngoài xe
    "zoom": 1.0,  # 0.6 (gần) … 1.6 (xa)
    "fade": False,  # mờ nhẹ khi đổi cảnh; tắt = cắt thẳng (tránh nhấp nháy)
    "quality": "medium",  # high | medium (75 % độ phân giải, bóng cách khung — khi live) | low (~60 %, tắt bóng)
    "auto_loxe": True,  # lơ xe tự nói theo tình huống
    "ai_reply": False,  # lơ xe trả lời câu hỏi trong comment bằng AI Gemini (PLAN-135; câu hay gặp luôn trả lời sẵn)
    "show_route": True,
    "show_loxe": True,
    "show_toasts": True,
    "show_board": True,
    "board_seconds": int(BOARD_SECONDS),
    "rest_seconds": int(REST_SECONDS),
    "tiktok_user": "",  # @username nối lần trước, để admin bấm nối lại nhanh
    "tiktok_auto": False,  # đang nối khi server tắt → bật lên tự nối lại (PM2 khởi động lại giữa live)
    "departure": DEFAULT_DEPARTURE,  # bến đi (BRD-tuyen-xe BR-8)
    "relief_auto": True,  # làn đủ một xe người chờ thì tự gọi xe tăng cường (PLAN-125); tắt: chỉ gọi bằng tay / quà
    "music_on": True,  # nhạc trong xe (PLAN-127); tắt = chỉ còn tiếng hiệu ứng
    "music_auto": True,  # hết bài tự qua bài kế (mỗi xe một đài chạy liên tục)
    "music_volume": 0.5,
    "sfx_volume": 0.6,  # còi, pháo hoa, tiếng máy
    "voice_on": True,  # Anh Tư lơ xe đọc (PLAN-128)
    "voice_name": "Adam",  # giọng VieNeu (nam, miền Nam, tự nhiên)
    "voice_volume": 0.9,
    "voice_rate": 1.15,  # tốc độ đọc (phát nhanh hơn, giữ cao độ): 0,8 chậm → 1,6 nhanh
    "trip_minutes": TRIP_MINUTES,  # chuyến xa nhất chạy đường bao nhiêu phút (PLAN-130); chuyến gần ngắn hơn theo km
    "auto_feature": "events",  # tự chiếu xe: off | events (theo chuyện hay) | rotate (xoay vòng)
    "rotate_seconds": 60,
    "mix": "balanced",  # trộn tiếng: balanced | music (nhạc nổi) | voice (lơ xe nổi)
    "hud_scale": 0.8,  # cỡ chữ + khung trên live (PLAN-133): 0,6 nhỏ → 1,2 to
    "talk_style": "mix",  # kiểu nói lơ xe (PLAN-131): mix | ben (bến xe) | genz | geny
    "blocks_on": True,  # trạm thu phí / công an chặn xe, góp quà đi tiếp (PLAN-148)
    "goal_xu": 1000,  # mục tiêu buổi live (xu) — thanh chung cả phòng, mỗi mốc mở cảnh vui (anh 03/11: 100k / giờ)
    "vnd_per_xu": 100,  # quy đổi để /control báo tiền (người live nhận ~100 đ / xu)
    "target_vnd": 100000,  # mục tiêu tiền / giờ trên bảng doanh thu
    "show_on": True,  # bảng quảng cáo: xe đang chạy dừng xem video anh tải lên (anh 03/11)
    "show_every_min": 10,  # mỗi bao nhiêu phút chiếu một video (xoay vòng danh sách)
    "show_max_seconds": 120,  # video dài hơn thì chỉ chiếu chừng này giây
    "show_sound": True,  # phát tiếng video (nhạc trong xe nhỏ lại)
    "fee_auto": True,  # phí / phạt tự theo lượng quà của phòng (phòng ít quà: 1 xu là qua), tối đa toll_xu / fine_xu
    "toll_xu": 20,  # phí qua trạm (xu)
    "fine_xu": 10,  # tiền phạt công an (xu); quá tốc độ phạt gấp 3
    "cover_on": True,  # tự bù lỗ: góp chưa đủ sau cover_seconds giây thì Anh Tư bù phần thiếu, xe đi (anh 03/11: 60 giây)
    "cover_seconds": 60,
    "vendor_on": True,  # cô bán hàng lên xe (anh 03/11): góp đủ vendor_xu xu thì cô lên bán nem, bì, bánh mì
    "vendor_xu": 10,
    "roll_on": True,  # điểm danh (anh 03/11): tới lượt lên xe mà im lặng lâu → gọi tên, chờ trả lời mới xếp giường
    "roll_idle_min": 15,  # im lặng quá chừng này phút thì điểm danh
    "roll_wait_s": 45,  # giây chờ người được gọi tên thả tim / bình luận
    # đổi gió (anh 03/11: game lặp lại chán, TikTok tưởng phát video quay sẵn)
    "quiz_on": True,  # đố vui A / B / C về các tỉnh lúc xe chạy
    "quiz_every_min": 3,
    "incidents_on": True,  # sự cố dọc đường: xẹp lốp, kẹt xe, trâu qua đường — tự xong, tim làm nhanh hơn, quà xong ngay
    "incident_xu": 5,
}

BOARD_RANGE = (20, 900)  # giây đón khách admin chỉnh được
REST_RANGE = (20, 300)
VOICE_RATE = (0.8, 1.6)
TRIP_RANGE = (3, 15)  # phút
HUD_SCALE = (0.6, 1.2)
ROTATE_RANGE = (20, 300)  # giây
MIXES = ("balanced", "music", "voice")
BLOCK_XU = (1, 1000)
COVER_RANGE = (10, 600)
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
        elif key == "auto_feature" and value in FEATURE_MODES:
            out[key] = value
        elif key == "talk_style" and value in TALK_STYLES:
            out[key] = value
        elif key == "mix" and value in MIXES:
            out[key] = value
        elif key == "trip_minutes":
            out[key] = round(min(TRIP_RANGE[1], max(TRIP_RANGE[0], float(value))), 1)
        elif key == "rotate_seconds":
            out[key] = int(min(ROTATE_RANGE[1], max(ROTATE_RANGE[0], float(value))))
        elif key == "voice_name":
            out[key] = str(value or "")[:40] or out[key]
        elif key == "voice_rate":
            out[key] = round(min(VOICE_RATE[1], max(VOICE_RATE[0], float(value))), 2)
        elif key in ("music_volume", "sfx_volume", "voice_volume"):
            out[key] = round(min(1.0, max(0.0, float(value))), 2)
        elif key == "hud_scale":
            out[key] = round(min(HUD_SCALE[1], max(HUD_SCALE[0], float(value))), 2)
        elif key == "zoom":
            out[key] = round(min(1.6, max(0.6, float(value))), 2)
        elif key == "board_seconds":
            out[key] = int(min(BOARD_RANGE[1], max(BOARD_RANGE[0], float(value))))
        elif key == "rest_seconds":
            out[key] = int(min(REST_RANGE[1], max(REST_RANGE[0], float(value))))
        elif key == "show_every_min":
            out[key] = int(min(120, max(1, float(value))))
        elif key == "show_max_seconds":
            out[key] = int(min(900, max(5, float(value))))
        elif key == "goal_xu":
            out[key] = int(min(100000, max(10, float(value))))
        elif key in ("vnd_per_xu", "target_vnd"):
            out[key] = int(min(10_000_000, max(1, float(value))))
        elif key in ("toll_xu", "fine_xu"):
            out[key] = int(min(BLOCK_XU[1], max(BLOCK_XU[0], float(value))))
        elif key == "cover_seconds":  # bản trước: 0 = chờ tới khi đủ (giờ là công tắc cover_on) → về mặc định 60
            out[key] = int(min(COVER_RANGE[1], max(COVER_RANGE[0], float(value)))) if float(value) > 0 else DEFAULTS[key]
        elif key == "vendor_xu":
            out[key] = int(min(1000, max(1, float(value))))
        elif key == "roll_idle_min":
            out[key] = int(min(120, max(1, float(value))))
        elif key == "quiz_every_min":
            out[key] = int(min(30, max(1, float(value))))
        elif key == "incident_xu":
            out[key] = int(min(1000, max(1, float(value))))
        elif key == "roll_wait_s":
            out[key] = int(min(180, max(15, float(value))))
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
