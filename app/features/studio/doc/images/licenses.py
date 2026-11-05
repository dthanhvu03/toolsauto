"""Chuẩn hoá giấy phép ảnh internet → trạng thái quyền (PLAN-157). Danh sách tự duyệt đọc từ cấu hình."""
from __future__ import annotations

import re

from app.features.studio.doc.config import DocConfig
from app.features.studio.doc.schema import RightsStatus


def normalize(raw: str | None) -> str:
    """
    ``"CC BY-SA 4.0"`` / ``"cc-by-sa-3.0"`` / ``"by-sa"`` → ``"cc-by-sa"``; ``"CC0"`` → ``"cc0"``;
    ``"Public domain"`` / ``"pdm"`` → ``"pdm"``; trống / lạ → ``"unknown"``. ``pexels`` / ``pixabay`` giữ nguyên.
    """
    s = str(raw or "").strip().lower()
    if not s:
        return "unknown"
    if s in ("pexels", "pixabay"):
        return s
    if "cc0" in s or "zero" in s:
        return "cc0"
    if "public domain" in s or s in ("pd", "pdm") or s.startswith("pd-"):
        return "pdm"
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-?\d+(\.\d+)?$", "", s)  # bỏ số phiên bản
    s = s.removeprefix("cc-")
    parts = [p for p in s.split("-") if p in ("by", "sa", "nc", "nd")]
    if not parts or parts[0] != "by":
        return "unknown"
    return "cc-" + "-".join(parts)


def rights_for(license_: str, cfg: DocConfig) -> RightsStatus:
    """NC / ND → hạn chế (dùng thương mại / chỉnh sửa ảnh không được); trong danh sách tự duyệt → đã kiểm; còn lại → chưa rõ."""
    lic = normalize(license_)
    if "-nc" in lic or "-nd" in lic:
        return RightsStatus.RESTRICTED
    if lic in cfg.auto_verify_licenses:
        return RightsStatus.RIGHTS_VERIFIED
    return RightsStatus.UNKNOWN
