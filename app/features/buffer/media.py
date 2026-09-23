"""URL https ổn định cho file reup. Buffer tải lúc đăng, nên link không hết hạn.

Chữ ký HMAC không đưa SECRET_KEY vào URL. Ai không có chữ ký thì không đoán được file.
"""
from __future__ import annotations

import hashlib
import hmac

def media_sig(material_id: int) -> str:
    import app.config as config

    key = (getattr(config, "SECRET_KEY", None) or "").encode()
    if not key:
        return ""
    msg = f"buffer-media:{int(material_id)}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:32]


def sig_ok(material_id: int, sig: str) -> bool:
    expected = media_sig(material_id)
    given = (sig or "").strip()
    if not expected or len(given) != len(expected):
        return False
    return hmac.compare_digest(given, expected)


def media_base() -> str:
    from app.core import settings as runtime_settings

    return (runtime_settings.get_str("BUFFER_MEDIA_BASE_URL") or "").strip().rstrip("/")


def public_reup_url(material_id: int) -> str | None:
    """None khi chưa có base https, chưa có chữ ký, hoặc chưa có file reup."""
    base = media_base()
    if not base.startswith("https://"):
        return None
    sig = media_sig(material_id)
    if not sig:
        return None
    from app.features.viral_intake.service import ViralService

    if not ViralService.find_reup_path(int(material_id)):
        return None
    return f"{base}/buffer-media/{int(material_id)}/{sig}.mp4"
