"""
Dữ liệu dùng chung giữa các bước. Bước nào cũng được import file này (bước không import nhau).

- ``analysis`` / ``lines_for``: đọc cache phân tích.
- ``template_for``: mẫu + tham số đang áp cho một quy trình (compose, dub, caption cùng đọc).
- ``add_asset``: đưa một file vào kho (intake, dub, và về sau voice / visuals).
- ``group_of`` / ``look``: nhóm biến thể A/B (gốc + các bản ``parent_project_id``) và thứ phân biệt chúng.
- ``techniques``: nhãn các kỹ thuật một dự án đang dùng — đọc từ spec nên luôn khớp bản render.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.database.models import (
    StudioAnalysis,
    StudioAsset,
    StudioChannel,
    StudioProject,
    StudioTask,
    StudioTemplate,
)
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


def group_of(db: Session, project: StudioProject) -> tuple[StudioProject, list[StudioProject]]:
    """(dự án gốc, mọi bản trong nhóm gồm cả gốc). Dự án không có biến thể → nhóm 1 phần tử."""
    root = (db.get(StudioProject, project.parent_project_id) if project.parent_project_id else None) or project
    variants = db.query(StudioProject).filter(StudioProject.parent_project_id == root.id).order_by(StudioProject.id).all()
    return root, [root, *variants]


def look(spec: dict, asset_id: int) -> tuple[bool, str | None]:
    """(lật, LUT) của một bản — thứ phân biệt các biến thể."""
    flip = any(c.get("hflip") for c in spec.get("clips", []) if c.get("asset") == asset_id)
    return flip, (spec.get("canvas") or {}).get("lut")


def pending_variants(db: Session, root: StudioProject) -> int:
    """
    Biến thể đã xếp nhưng **chưa thành dự án** (việc compose của flow ``recompose`` còn trong hàng). Hàng việc làm xong
    từng dự án nên bản đầu có thể tới «chờ duyệt» khi bản sau còn chưa được tạo — phải đếm cả những bản này.
    """
    return (
        db.query(StudioTask)
        .filter(
            StudioTask.flow == "recompose",
            StudioTask.asset_id == root.asset_id,
            StudioTask.project_id.is_(None),
            StudioTask.status.in_(["QUEUED", "RUNNING"]),
        )
        .count()
    )


TEMPLATE_LABEL = {"basic": "Mẫu cơ bản", "reup_dub": "Mẫu lồng tiếng", "own_footage": "Mẫu tự quay", "ab_montage": "Mẫu montage"}


def techniques(spec: dict, asset_id: int | None, *, origin: str | None = None, template: str | None = None) -> list[str]:
    """
    Nhãn ngắn cho thẻ / trình edit: nguồn, mẫu, rồi từng kỹ thuật có trong spec. Thứ tự cố định để các thẻ so được nhau.
    ``template``: tên mẫu anh đặt (hoặc kind) — None = mẫu cơ bản.
    """
    clips = spec.get("clips") or []
    main = [c for c in clips if c.get("asset") == asset_id]
    others = [i for i, c in enumerate(clips) if c.get("asset") != asset_id]
    first_main = next((i for i, c in enumerate(clips) if c.get("asset") == asset_id), 0)
    tags = ["Sưu tầm" if origin == "reup" else "Của tôi", template or TEMPLATE_LABEL["basic"]]
    if len(main) > 1:
        tags.append(f"Cắt {len(main)} đoạn")
    elif main and (float(main[0].get("start") or 0) > 0 or main[0].get("end") is not None):
        tags.append("Cắt đầu / cuối")
    flip, lut = look(spec, asset_id or 0)
    if flip:
        tags.append("Lật gương")
    if lut:
        tags.append(f"Màu {lut.removesuffix('.cube')}")
    if any(c.get("audio") for c in main):
        tags.append("Lồng tiếng")
    sub = spec.get("subtitles") or {}
    if sub.get("enabled"):
        tags.append("Phụ đề dịch" if sub.get("source") == "dub" else "Phụ đề")
    if spec.get("texts"):
        tags.append("Hook")
    if (spec.get("audio") or {}).get("tracks"):
        tags.append("Nhạc nền")
    if any(i < first_main for i in others):
        tags.append("Intro")
    if any(i > first_main for i in others):
        tags.append("Outro")
    if spec.get("logo"):
        tags.append("Logo")
    if spec.get("credit"):
        tags.append("Ghi nguồn")
    return tags

