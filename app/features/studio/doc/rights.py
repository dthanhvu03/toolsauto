"""Cổng quyền ảnh — chặn dựng / xuất khi ảnh chưa đủ quyền. Luật đọc từ ``DocConfig`` (``doc.rights_*``)."""
from __future__ import annotations

from dataclasses import dataclass

from app.features.studio.doc.config import DocConfig
from app.features.studio.doc.schema import DocState, RightsStatus, Shot

_OK = {
    "verified_or_approved": frozenset({RightsStatus.RIGHTS_VERIFIED, RightsStatus.APPROVED}),
    "approved_only": frozenset({RightsStatus.APPROVED}),
}


@dataclass(frozen=True)
class RightsGateResult:
    ok: bool
    blockers: list[str]
    missing_images: list[str]


def allowed(cfg: DocConfig) -> frozenset[RightsStatus]:
    return _OK.get(cfg.rights_ok, _OK["verified_or_approved"])


def shot_blocks_export(shot: Shot, cfg: DocConfig) -> str | None:
    if shot.selected is None:
        return f"{shot.shot_id}: chưa có ảnh"
    st = shot.selected.rights_status
    if st not in allowed(cfg):
        return f"{shot.shot_id}: quyền {st.value} (asset #{shot.selected.asset_id})"
    if cfg.rights_need_proof and not (shot.selected.license or shot.selected.proof_note or shot.selected.illustration):
        return f"{shot.shot_id}: thiếu license/proof (hoặc đánh dấu minh họa)"
    return None


def check_export(state: DocState, cfg: DocConfig, *, end_ms: int) -> RightsGateResult:
    """Chỉ xét cảnh bắt đầu trước ``end_ms`` (mốc cuối bản dựng)."""
    blockers: list[str] = []
    missing: list[str] = []
    for shot in state.shots:
        if shot.start_ms >= end_ms or shot.end_ms <= 0:
            continue
        msg = shot_blocks_export(shot, cfg)
        if msg is None:
            continue
        if shot.selected is None:
            missing.append(shot.shot_id)
        blockers.append(msg)
    return RightsGateResult(ok=not blockers, blockers=blockers, missing_images=missing)
