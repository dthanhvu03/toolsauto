"""Khi Buffer báo bài đã gửi, đánh dấu video đã đăng như nút Telegram.

Không tạo trạng thái mới. Bài còn lịch hoặc lỗi thì để yên. Một video nhiều kênh:
kênh đầu đã gửi là đủ để dời file, vì file trong thư mục đã đăng vẫn được tìm thấy.
"""
from __future__ import annotations

import logging
import time

from app.constants import JobStatus, ViralStatus
from app.core.database.models import Job, ViralMaterial
from app.features.buffer.client import BufferError

logger = logging.getLogger(__name__)

INTERVAL_SEC = 60 * 60  # 250 request/ngày mỗi key: hỏi trạng thái 24 lần/ngày là đủ
_STATUS_BATCH = 25
_last_sync_ts = 0.0
_status_offset = 0


def ready_post_ids(db) -> dict[int, list[str]]:
    """Video đang READY và có mã bài Buffer thật."""
    rows = (
        db.query(Job.viral_material_id, Job.external_post_id)
        .join(ViralMaterial, ViralMaterial.id == Job.viral_material_id)
        .filter(
            Job.platform == "buffer",
            Job.status == JobStatus.DONE,
            Job.viral_material_id.isnot(None),
            Job.external_post_id.isnot(None),
            Job.external_post_id != "",
            Job.external_post_id != "safe_mode_dry_run",
            ViralMaterial.status == ViralStatus.READY,
        )
        .all()
    )
    grouped: dict[int, list[str]] = {}
    for material_id, post_id in rows:
        pid = str(post_id or "").strip()
        if not pid:
            continue
        grouped.setdefault(int(material_id), []).append(pid)
    return grouped


def apply_sent(db, grouped: dict[int, list[str]], status_of, marker) -> list[tuple[int, str]]:
    """Trả các video vừa đánh dấu, kèm câu của nút Đã đăng."""
    done: list[tuple[int, str]] = []
    for material_id, post_ids in grouped.items():
        sent = False
        for post_id in post_ids:
            try:
                status = str(status_of(post_id) or "").strip().lower()
            except Exception as exc:
                logger.warning("[Buffer][material_%s] không đọc được bài %s: %s", material_id, post_id, exc)
                continue
            if status == "sent":
                sent = True
                break
        if not sent:
            continue
        ok, msg = marker(db, material_id)
        if ok:
            logger.info("[Buffer][material_%s] tu danh dau da dang", material_id)
            done.append((material_id, msg))
    return done


def apply_errors(db, grouped: dict[int, list[str]], status_of, deleter=None) -> list[tuple[int, str]]:
    """Xử lý bài Buffer bị lỗi (status == 'error'): đánh dấu Job FAILED và xóa bài trên Buffer để giải phóng slot."""
    errors: list[tuple[int, str]] = []
    for material_id, post_ids in grouped.items():
        for post_id in post_ids:
            try:
                st = str(status_of(post_id) or "").strip().lower()
            except Exception:
                continue
            if st != "error":
                continue
            job = (
                db.query(Job)
                .filter(
                    Job.platform == "buffer",
                    Job.external_post_id == post_id,
                    Job.status == JobStatus.DONE,
                )
                .first()
            )
            if not job:
                continue
            job.status = JobStatus.FAILED
            job.last_error = "Buffer báo lỗi đăng bài (status=error)"
            db.commit()
            if deleter:
                try:
                    deleter(post_id)
                    logger.info("[Buffer][job_%s] Da xoa post loi %s de nha slot", job.id, post_id)
                except Exception as exc:
                    logger.warning("[Buffer][job_%s] Khong xoa duoc post loi %s: %s", job.id, post_id, exc)
            msg = f"⚠️ [Buffer] Bài đăng Job #{job.id} (Video #{material_id}) thất bại trên Buffer"
            logger.warning(msg)
            errors.append((material_id, msg))
    return errors


def _status_slice(post_ids: list[str]) -> list[str]:
    """Một vòng chỉ hỏi một cụm, rồi vòng sau hỏi cụm kế. Không bắn hết một lúc."""
    global _status_offset
    if len(post_ids) <= _STATUS_BATCH:
        _status_offset = 0
        return post_ids
    start = _status_offset % len(post_ids)
    _status_offset = start + _STATUS_BATCH
    end = start + _STATUS_BATCH
    if end <= len(post_ids):
        return post_ids[start:end]
    return post_ids[start:] + post_ids[: end - len(post_ids)]


def sync_sent_marks(db, *, now: float | None = None, force: bool = False) -> list[int]:
    """Gọi từ vòng bảo trì. Không có khóa hoặc chưa tới lượt thì không gọi mạng."""
    global _last_sync_ts
    moment = time.time() if now is None else float(now)
    if not force and (moment - _last_sync_ts) < INTERVAL_SEC:
        return []

    from app.features.buffer.client import any_key_ready
    from app.features.buffer.manager import get_buffer_manager
    manager = get_buffer_manager()
    if not manager.has_keys():
        return []
    if not any_key_ready(manager.get_keys()):
        logger.info("[Buffer] Bo qua hoi trang thai bai — moi key dang cooldown")
        return []

    _last_sync_ts = moment
    from app.core.notifier.service import NotifierService
    from app.features.viral_intake.service import ViralService

    grouped = ready_post_ids(db)
    flat: list[str] = []
    seen: set[str] = set()
    for post_ids in grouped.values():
        for post_id in post_ids:
            if post_id in seen:
                continue
            seen.add(post_id)
            flat.append(post_id)
    asked = _status_slice(flat)
    try:
        found = manager.post_statuses(asked, db=db)
    except BufferError as exc:
        if exc.status_code == 429:
            _last_sync_ts = moment + INTERVAL_SEC
            logger.warning("[Buffer] dung hoi trang thai vi Buffer HTTP 429")
            return []
        raise

    asked_set = set(asked)
    limited = {
        material_id: [post_id for post_id in post_ids if post_id in asked_set]
        for material_id, post_ids in grouped.items()
    }
    limited = {material_id: post_ids for material_id, post_ids in limited.items() if post_ids}

    def status_of(post_id: str) -> str:
        return found.get(post_id, "")

    marked = apply_sent(db, limited, status_of, ViralService.mark_posted)
    for _material_id, msg in marked:
        try:
            NotifierService._broadcast(msg)
        except Exception as exc:
            logger.warning("[Buffer] khong gui duoc tin da dang: %s", exc)

    def delete_fn(pid: str):
        try:
            manager.delete_post(pid, db=db)
        except Exception as exc:
            logger.warning("[Buffer] Loi khi xoa post %s: %s", pid, exc)

    errors = apply_errors(db, limited, status_of, delete_fn)
    for _material_id, msg in errors:
        try:
            NotifierService._broadcast(msg)
        except Exception as exc:
            logger.warning("[Buffer] khong gui duoc tin loi: %s", exc)

    return [material_id for material_id, _msg in marked]
