"""
Bước ``fetch`` — đúng một việc: tải MỘT video từ link (``payload.url``) vào ``inbox/`` để ``intake`` nhận (PLAN-113).

Không quét kênh (trang «Lấy từ TikTok» quét trước, người dùng chọn), không chống trùng (``intake`` lo theo sha256),
không đặt nguồn / kênh / mẫu (``entry.take_links`` đã ghi sẵn trong payload, đi suốt flow).
Video không còn / riêng tư → lỗi không thử lại; mạng chập chờn → thử lại theo ``max_attempts``.
"""
from __future__ import annotations

import re
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
# lỗi yt-dlp hay gặp → câu tiếng Việt (giữ nguyên câu gốc trong ngoặc để tra)
_HUMAN = (
    ("private", "video riêng tư"),
    ("removed", "video đã bị xoá"),
    ("does not exist", "video không tồn tại"),
    ("http error 404", "video không tồn tại"),
    ("not available", "video không xem được ở vùng này / đã ẩn"),
    ("unavailable", "video không xem được ở vùng này / đã ẩn"),
    ("429", "TikTok đang chặn vì tải nhiều — sẽ thử lại"),
    ("timed out", "mạng chậm / mất kết nối — sẽ thử lại"),
    ("connection", "mạng chập chờn — sẽ thử lại"),
)
_PREFIX = re.compile(r"^ERROR:\s*(\[[^\]]+\]\s*)?([\w-]+:\s*)?", re.IGNORECASE)


def _cleanup(folder: Path, stem: str) -> None:
    for f in folder.glob(f"{stem}*"):
        f.unlink(missing_ok=True)


def _reason(stderr: str) -> str:
    """Dòng lỗi cuối của yt-dlp, bỏ tiền tố ``ERROR: [TikTok] <id>:``, kèm câu tiếng Việt nếu nhận ra."""
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    errors = [ln for ln in lines if ln.startswith("ERROR")]
    raw = _PREFIX.sub("", (errors or lines or ["yt-dlp không báo gì"])[-1]).strip()[:240]
    human = next((vi for key, vi in _HUMAN if key in raw.lower()), None)
    return f"{human} ({raw})" if human else raw


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
        raise StageError(reason, retryable=not any(m in reason.lower() for m in _GONE))
    return StageResult(payload={"path": str(done[0]), "move": True, "source_url": url}, note=f"đã tải {done[0].stat().st_size / 1e6:.1f} MB")
