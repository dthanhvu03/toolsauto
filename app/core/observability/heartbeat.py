"""
Ping "còn sống" ra healthchecks.io — ADR-014.

Hệ chỉ biết báo khi có lỗi, không ai báo khi **im lặng** (Postgres tự tắt, Drive
hỏng âm thầm, tài khoản chết 5 tuần mới biết). Mô hình dead man's switch: worker
ping `hc-ping.com/<uuid>` đều đặn, quá hạn thì dịch vụ báo về Telegram/email.

Hai nguyên tắc, đừng phá khi sửa về sau:

1. **Chưa dán URL thì im lặng bỏ qua.** Owner dán URL ở trang /app/settings
   (nhóm "Giam sat"); trống nghĩa là tắt, không phải lỗi.
2. **Ping thất bại không bao giờ làm việc chính thất bại.** Mất mạng, DB chưa lên,
   healthchecks sập — chỉ ghi log warning rồi trả False. KHÔNG raise.
"""
from __future__ import annotations

import requests

from app.utils.logger import setup_shared_logger

logger = setup_shared_logger(__name__)

TIMEOUT_SEC = 5.0

# Khoá setting của 3 điểm ping. Khai báo SettingSpec ở app/core/settings.py.
KEY_BACKUP = "monitor.hc_url_backup"
KEY_MAINTENANCE = "monitor.hc_url_maintenance"
KEY_PUBLISHER = "monitor.hc_url_publisher"


def _read_url(setting_key: str, db=None) -> str:
    """Đọc URL từ runtime settings (DB ghi đè env). Import trong hàm để tránh vòng import."""
    from app.core import settings as runtime_settings

    return (runtime_settings.get_str(setting_key, "", db=db) or "").strip()


def ping(setting_key: str, *, fail: bool = False, db=None) -> bool:
    """
    GET tới URL lưu ở `setting_key`; `fail=True` gọi `<url>/fail` để báo thất bại.

    Trả True khi ping đi được, False khi tắt (URL rỗng) hoặc lỗi. Không bao giờ
    ném lỗi ra ngoài: người gọi là lệnh backup và vòng lặp worker.
    """
    try:
        url = _read_url(setting_key, db=db)
    except Exception as exc:
        logger.warning("[heartbeat] khong doc duoc %s: %s", setting_key, exc)
        return False
    if not url:
        return False

    target = url.rstrip("/") + "/fail" if fail else url
    try:
        resp = requests.get(target, timeout=TIMEOUT_SEC)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("[heartbeat] ping %s that bai: %s", setting_key, exc)
        return False
    logger.debug("[heartbeat] ping %s ok (fail=%s)", setting_key, fail)
    return True
