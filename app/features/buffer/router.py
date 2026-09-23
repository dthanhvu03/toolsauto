"""Phát file reup cho Buffer. Không cần đăng nhập — Buffer không gửi cookie.

Chỉ trả file khi chữ ký đúng và file `_reup.mp4` tồn tại. Không nhận đường dẫn từ client.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.features.buffer.media import sig_ok
from app.features.viral_intake.service import ViralService

router = APIRouter(prefix="/buffer-media", tags=["buffer-media"])


@router.api_route("/{material_id}/{sig}.mp4", methods=["GET", "HEAD"])
def serve_reup(material_id: int, sig: str):
    if material_id < 1 or not sig_ok(material_id, sig):
        raise HTTPException(status_code=404, detail="Khong thay file")
    path = ViralService.find_reup_path(material_id)
    if not path:
        raise HTTPException(status_code=404, detail="Chua co file reup")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"viral_{material_id}_reup.mp4",
        content_disposition_type="inline",
    )
