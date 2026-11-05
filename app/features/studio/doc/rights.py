"""Cổng quyền ảnh — khóa export/preview phát hành khi còn RIGHTS_UNKNOWN / RESTRICTED."""
from __future__ import annotations

from dataclasses import dataclass

from app.features.studio.doc.schema import EXPORTABLE_RIGHTS, DocState, RightsStatus, Shot


@dataclass(frozen=True)
class RightsGateResult:
    ok: bool
    blockers: list[str]
    missing_images: list[str]


def shot_blocks_export(shot: Shot) -> str | None:
    if shot.selected is None:
        return f"{shot.shot_id}: chưa có ảnh"
    st = shot.selected.rights_status
    if st in (RightsStatus.UNKNOWN, RightsStatus.RESTRICTED, RightsStatus.REJECTED, RightsStatus.DISCOVERED):
        return f"{shot.shot_id}: quyền {st.value} (asset #{shot.selected.asset_id})"
    if st not in EXPORTABLE_RIGHTS:
        return f"{shot.shot_id}: quyền chưa duyệt ({st.value})"
    if not (shot.selected.license or shot.selected.proof_note or shot.selected.illustration):
        return f"{shot.shot_id}: thiếu license/proof (hoặc đánh dấu minh họa)"
    return None


def check_export(state: DocState, *, end_ms: int | None = None) -> RightsGateResult:
    """Chỉ xét shot nằm trong cửa sổ preview/export (mặc định toàn bộ tới preview_end_ms)."""
    limit = end_ms if end_ms is not None else state.preview_end_ms
    blockers: list[str] = []
    missing: list[str] = []
    for shot in state.shots:
        if shot.start_ms >= limit:
            continue
        if shot.end_ms <= 0:
            continue
        msg = shot_blocks_export(shot)
        if msg is None:
            continue
        if shot.selected is None:
            missing.append(shot.shot_id)
        blockers.append(msg)
    return RightsGateResult(ok=not blockers, blockers=blockers, missing_images=missing)
