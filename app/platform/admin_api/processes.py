"""Bảng tiến trình PM2 trên trang «Panel hệ thống» (PLAN-115). Đăng nhập: middleware cookie chung của app."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core import process_control, windows_host

router = APIRouter()


@router.get("/processes")
def processes() -> dict:
    return process_control.snapshot()


@router.get("/processes/windows")
def windows() -> dict:
    """Máy Windows chứa WSL: RAM / CPU / ổ đĩa / chương trình tốn nhất (chỉ đọc, giữ 8 giây)."""
    return windows_host.snapshot()


@router.post("/processes/{name}/{action}")
def process_action(name: str, action: str) -> dict:
    try:
        return {"ok": True, "message": process_control.act(name, action)}
    except process_control.ProcessError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
