"""
Bước ``fetch`` — đúng một việc: tải MỘT video từ link (``payload.url``) vào ``inbox/`` để ``intake`` nhận (PLAN-113).

Không quét kênh (trang «Lấy từ TikTok» quét trước, người dùng chọn), không chống trùng (``intake`` lo theo sha256),
không đặt nguồn / kênh / mẫu (``entry.take_links`` đã ghi sẵn trong payload, đi suốt flow).
Video không còn / riêng tư → lỗi không thử lại; mạng chập chờn → thử lại theo ``max_attempts``.
"""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.database.models import StudioTask
from app.core.yt_dlp_path import impersonate_args, yt_dlp_cmd
from app.features.studio import paths
from app.features.studio.contracts import StageError, StageResult

MAX_FILESIZE = "500M"
DOWNLOAD_TIMEOUT_SEC = 600
_GONE = ("private", "removed", "not available", "unavailable", "does not exist", "http error 404", "max-filesize")


def _cleanup(folder: Path, stem: str) -> None:
    for f in folder.glob(f"{stem}*"):
        f.unlink(missing_ok=True)


def _reason(stderr: str) -> str:
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    errors = [ln for ln in lines if ln.startswith("ERROR")]
    return ((errors or lines or ["yt-dlp không báo gì"])[-1])[:300]


def run(db: Session, task: StudioTask) -> StageResult:
    url = str((task.payload or {}).get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise StageError("thiếu link video", retryable=False)
    folder = paths.inbox_dir()
    stem = f"link{task.id}-{uuid.uuid4().hex[:8]}"
    cmd = yt_dlp_cmd(
        "--no-playlist", "--no-warnings", "--max-filesize", MAX_FILESIZE, "--merge-output-format", "mp4",
        *impersonate_args(), "-o", str(folder / f"{stem}.%(ext)s"), url,
    )
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DOWNLOAD_TIMEOUT_SEC)
    except subprocess.TimeoutExpired as exc:
        _cleanup(folder, stem)
        raise StageError(f"tải quá {DOWNLOAD_TIMEOUT_SEC // 60} phút chưa xong") from exc
    done = [f for f in folder.glob(f"{stem}.*") if f.is_file() and f.suffix != ".part" and f.stat().st_size > 0]
    if proc.returncode != 0 or not done:
        _cleanup(folder, stem)
        reason = _reason(proc.stderr) if proc.returncode != 0 else "không thấy file (có thể vượt 500 MB)"
        raise StageError(f"tải hỏng: {reason}", retryable=not any(m in reason.lower() for m in _GONE))
    return StageResult(payload={"path": str(done[0]), "move": True, "source_url": url}, note=f"đã tải {done[0].stat().st_size / 1e6:.1f} MB")
