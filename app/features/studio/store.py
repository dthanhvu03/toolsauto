"""
Dữ liệu dùng chung giữa các bước. Bước nào cũng được import file này (bước không import nhau).

- ``analysis`` / ``lines_for``: đọc cache phân tích.
- ``template_for``: mẫu + tham số đang áp cho một quy trình (compose, dub, caption cùng đọc).
- ``add_asset``: đưa một file vào kho (intake, dub, và về sau voice / visuals).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.database.models import StudioAnalysis, StudioAsset, StudioChannel, StudioTemplate
from app.core.media.content_hash import sha256_file
from app.features.studio import paths


def analysis(db: Session, asset_id: int, kind: str):
    """Kết quả phân tích ``kind`` của asset, ``None`` khi chưa phân tích."""
    row = db.query(StudioAnalysis).filter_by(asset_id=asset_id, kind=kind).first()
    return None if row is None else row.data


def lines_for(db: Session, asset_id: int, source: str) -> list[dict]:
    """Câu thoại theo giây của asset: ``transcript`` (Whisper) hoặc ``dub`` (câu đã dịch). Không có → ``[]``."""
    data = analysis(db, asset_id, source) or {}
    if source == "dub" and not data.get("ok"):
        return []
    return list(data.get("lines") or [])


def template_for(
    db: Session, payload: dict | None,
) -> tuple[str, dict, StudioTemplate | None, StudioChannel | None]:
    """
    ``(kind, params, template, channel)`` của một quy trình. Mẫu: payload ``template_id`` → mẫu của
    kênh → ``basic``. Tham số: của mẫu, payload ``params`` ghi đè.
    """
    p = payload or {}
    channel = db.get(StudioChannel, p["channel_id"]) if p.get("channel_id") else None
    template_id = p.get("template_id") or (channel.template_id if channel else None)
    template = db.get(StudioTemplate, template_id) if template_id else None
    params = {**((template.params if template else None) or {}), **(p.get("params") or {})}
    return (template.kind if template else "basic"), params, template, channel


def _store(src: Path, sha: str, *, move: bool) -> Path:
    dest = paths.assets_dir() / f"{sha[:20]}{src.suffix.lower()}"
    if not dest.exists():
        if move:
            shutil.move(str(src), dest)
            return dest
        try:
            os.link(src, dest)  # cùng ổ thì không tốn thêm dung lượng
        except OSError:
            shutil.copy2(src, dest)
    if move and src.exists() and src.resolve() != dest.resolve():
        src.unlink()
    return dest


def add_asset(db: Session, src: Path, *, kind: str, origin: str, move: bool = False, **fields) -> tuple[StudioAsset, bool]:
    """
    File → ``StudioAsset`` (commit). Trùng sha256 thì trả asset cũ và ``False`` (``move`` vẫn xoá file
    nguồn). ``fields``: các cột khác của asset (``credit``, ``title``, ``duration``…).
    """
    sha = sha256_file(src)
    if not sha:
        raise OSError(f"không đọc được file: {src}")
    existing = db.query(StudioAsset).filter(StudioAsset.sha256 == sha).first()
    if existing is not None:
        if move:
            src.unlink(missing_ok=True)
        return existing, False
    asset = StudioAsset(kind=kind, origin=origin, path=str(_store(src, sha, move=move)), sha256=sha, **fields)
    db.add(asset)
    db.commit()
    return asset, True
