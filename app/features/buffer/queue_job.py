"""Xếp video reup + caption AI vào hàng chờ Buffer. Gọi từ nút Telegram.

Job platform=buffer, không account. Publisher Facebook chỉ lấy job facebook nên không đụng.
File reup không ghi vào media_path — dọn file job DONE sẽ xóa nhầm bản Buffer còn phải tải.
"""
from __future__ import annotations

import logging

from app.constants import JobStatus
from app.core.database.models import Job, ViralMaterial
from app.core.database.models.base import now_ts
from app.features.buffer.adapter import BufferAdapter
from app.features.buffer.client import BufferError
from app.features.buffer.when import accept_ts, due_iso, format_ict

logger = logging.getLogger(__name__)


def _channels() -> list[dict]:
    from app.core import settings as runtime_settings

    data = runtime_settings.get_json("BUFFER_CHANNELS") or []
    rows = []
    for item in data:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            rows.append(
                {
                    "id": str(item["id"]).strip(),
                    "name": str(item.get("name") or item["id"]).strip(),
                }
            )
    return rows


def assign_page(db, material_id: int, channel_id: str) -> tuple[bool, str]:
    """Gắn video với một page Buffer. Không xếp hàng, không gọi API."""
    allowed = {row["id"] for row in _channels()}
    if channel_id not in allowed:
        return False, "Page không có trong danh sách Buffer."
    mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if not mat:
        return False, "Không thấy video."
    mat.target_page = channel_id
    db.commit()
    return True, f"#{material_id} thuộc {channel_name(channel_id)}."


def taken_slots(db, channel_id: str) -> list[int]:
    """Mốc giờ đã giữ của kênh. Job lỗi không giữ ô.

    Bài không hẹn giờ (schedule_ts = 0) vẫn tính vào ngày tạo, để không đăng quá 3.
    """
    rows = (
        db.query(Job.schedule_ts, Job.created_at)
        .filter(
            Job.platform == "buffer",
            Job.target_page == channel_id,
            Job.status.in_([JobStatus.DONE, JobStatus.RUNNING]),
        )
        .all()
    )
    stamps: list[int] = []
    for schedule_ts, created_at in rows:
        if schedule_ts and int(schedule_ts) > 0:
            stamps.append(int(schedule_ts))
        elif created_at:
            stamps.append(int(created_at))
    return stamps


def _stop_scheduling(msg: str) -> bool:
    """Hết suất cả tuần, đầy hàng chờ hoặc Buffer chặn nhịp thì không thử ngày khác."""
    text = (msg or "").lower()
    return (
        "429" in text
        or "hết suất tuần" in text
        or "limit reached" in text
        or "đã kín" in text
    )


def auto_schedule_ready(db, material_id: int) -> tuple[bool, str]:
    """Video đã có page Buffer và caption thì lấy ô kế của kênh và hẹn giờ.

    Đủ 3 bài trong ngày thì sang ngày sau. Hết suất hôm nay thì thử ngày mai.
    Hết suất tuần hoặc Buffer 429 thì dừng, không gọi tiếp.
    """
    from datetime import datetime

    from app.features.buffer.slots import next_free_slot
    from app.features.buffer.when import ICT

    mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if not mat:
        return False, "Không thấy video."
    channel_id = (mat.target_page or "").strip()
    if not channel_id:
        return False, ""
    if channel_id not in {row["id"] for row in _channels()}:
        return False, "Page không có trong danh sách Buffer."
    if not caption_of(mat):
        return False, "Chưa có caption AI."
    if _done_job(db, material_id, channel_id):
        job = _done_job(db, material_id, channel_id)
        when = f" lúc {format_ict(job.schedule_ts)}" if job and job.schedule_ts else ""
        return True, f"Đã có lịch {channel_name(channel_id)}{when}."
    running = (
        db.query(Job)
        .filter(
            Job.platform == "buffer",
            Job.viral_material_id == material_id,
            Job.target_page == channel_id,
            Job.status == JobStatus.RUNNING,
        )
        .first()
    )
    if running:
        return True, "Đang xếp lịch."

    name = channel_name(channel_id)
    skip_days: set = set()
    last = "Không có ô giờ."
    for _ in range(3):
        when_ts, err = next_free_slot(name, taken_slots(db, channel_id), skip_days=skip_days)
        if err or not when_ts:
            return False, err or last
        ok, msg = schedule_reup(db, material_id, channel_id, int(when_ts))
        if ok:
            return True, msg
        last = msg
        if _stop_scheduling(msg):
            return False, msg
        if "Hết suất hôm nay" in (msg or ""):
            skip_days.add(datetime.fromtimestamp(int(when_ts), ICT).date())
            continue
        return False, msg
    return False, last


def sweep_unscheduled_ready(db, limit: int = 4) -> int:
    """Tự động xếp lịch cho các video READY chưa có bài, nếu kênh còn slot trống (<10 bài)."""
    if limit <= 0:
        return 0

    candidates = (
        db.query(ViralMaterial)
        .filter(
            ViralMaterial.status == "READY",
            ViralMaterial.target_page.isnot(None),
            ViralMaterial.target_page != "",
        )
        .order_by(ViralMaterial.id.asc())
        .all()
    )

    scheduled = 0
    blocked_channels: set[str] = set()

    for mat in candidates:
        if scheduled >= limit:
            break
        channel_id = str(mat.target_page or "").strip()
        if not channel_id or channel_id in blocked_channels:
            continue

        done = _done_job(db, mat.id, channel_id)
        if done:
            continue

        ok, msg = auto_schedule_ready(db, mat.id)
        if ok:
            scheduled += 1
            logger.info("[Buffer] Tu xep lich thanh cong video #%d vao %s: %s", mat.id, channel_id, msg)
        else:
            if _stop_scheduling(msg):
                blocked_channels.add(channel_id)
                logger.info("[Buffer] Tam dung quet cho kenh %s: %s", channel_id, msg)

    return scheduled


def channel_name(channel_id: str) -> str:
    for row in _channels():
        if row["id"] == channel_id:
            return row["name"]
    return channel_id


def caption_of(mat) -> str:
    text = (getattr(mat, "ai_caption", None) or "").strip()
    tags = " ".join(getattr(mat, "ai_hashtags_list", None) or [])
    if text and tags:
        return f"{text}\n\n{tags}"
    return text


def queue_reup(db, material_id: int, channel_id: str) -> tuple[bool, str]:
    """Trả (ok, câu tiếng Việt cho Telegram). Không gọi Buffer khi thiếu caption hoặc page lạ."""
    allowed = {row["id"] for row in _channels()}
    if channel_id not in allowed:
        return False, "Page không có trong danh sách Buffer."

    mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if not mat:
        return False, "Không thấy video."
    text = caption_of(mat)
    if not text:
        return False, "Chưa có caption AI."

    name = channel_name(channel_id)
    if (mat.target_page or "") != channel_id:
        mat.target_page = channel_id
        db.commit()
    existing = (
        db.query(Job)
        .filter(
            Job.platform == "buffer",
            Job.viral_material_id == material_id,
            Job.target_page == channel_id,
            Job.status == JobStatus.DONE,
        )
        .first()
    )
    if existing:
        return True, f"Đã xếp vào {name} rồi (job #{existing.id})."

    job = Job(
        platform="buffer",
        caption=text,
        viral_material_id=material_id,
        target_page=channel_id,
        schedule_ts=0,
        status=JobStatus.RUNNING,
        is_approved=True,
        media_path=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    result = BufferAdapter().publish(job)
    if not result.ok:
        job.status = JobStatus.FAILED
        job.last_error = (result.error or "Buffer từ chối")[:300]
        job.finished_at = now_ts()
        db.commit()
        logger.warning("[Buffer][job_%s] %s", job.id, job.last_error)
        return False, job.last_error

    job.status = JobStatus.DONE
    job.external_post_id = result.external_post_id
    job.finished_at = now_ts()
    job.last_error = None
    db.commit()
    due = ""
    if isinstance(result.details, dict) and result.details.get("dueAt"):
        due = f" · slot {result.details['dueAt']}"
    return True, f"Đã xếp vào hàng chờ {name}{due}."


def _done_job(db, material_id: int, channel_id: str):
    return (
        db.query(Job)
        .filter(
            Job.platform == "buffer",
            Job.viral_material_id == material_id,
            Job.target_page == channel_id,
            Job.status == JobStatus.DONE,
        )
        .order_by(Job.id.desc())
        .first()
    )


def _buffer_client(channel_id: str | None = None, post_id: str | None = None):
    from app.features.buffer.manager import get_buffer_manager

    mgr = get_buffer_manager()
    if channel_id:
        c = mgr.get_client_for_channel(channel_id)
        if c:
            return c
    if post_id:
        c = mgr.get_client_for_post(post_id)
        if c:
            return c
    clients = mgr.get_clients()
    if clients:
        return clients[0]

    import app.config as config
    from app.features.buffer.client import BufferClient

    key = (getattr(config, "BUFFER_API_KEY", None) or "").strip()
    if not key:
        raise BufferError("Chưa có khóa Buffer.")
    return BufferClient(key)


def _quota_block(channel_id: str, when_ts: int) -> str | None:
    """Chỉ lúc tạo lịch mới. Không khóa thì không chặn (ca máy không gọi mạng)."""
    import app.config as config

    if not config.BUFFER_API_KEYS and not getattr(config, "BUFFER_API_KEY", None):
        return None
    try:
        return _buffer_client(channel_id=channel_id).schedule_block_reason(channel_id, when_ts)
    except BufferError as exc:
        return str(exc)


def _post_status(post_id: str) -> str:
    snap = _buffer_client(post_id=post_id).post_snapshot(post_id)
    return str(snap.get("status") or "")


def _edit_due(post_id: str, due_at: str) -> None:
    _buffer_client(post_id=post_id).edit_post(post_id, mode="customScheduled", due_at=due_at)


def _delete_post(post_id: str) -> None:
    _buffer_client(post_id=post_id).delete_post(post_id)


def _reject_when(when_ts: int) -> str | None:
    _ts, err = accept_ts(when_ts)
    return err


def _apply_reschedule(db, job, when_ts: int, name: str) -> tuple[bool, str]:
    """Sửa đúng mã bài. Không tính suất. Nơi đăng từ chối thì không báo đã đổi."""
    post_id = str(job.external_post_id or "").strip()
    if not post_id:
        return False, f"Job #{job.id} chưa có mã bài."
    try:
        status = _post_status(post_id)
    except BufferError as exc:
        return False, str(exc)
    if status == "sent":
        return False, "Bài đã đăng."
    try:
        _edit_due(post_id, due_iso(when_ts))
    except BufferError as exc:
        return False, str(exc)
    job.schedule_ts = int(when_ts)
    db.commit()
    logger.info("[Buffer][job_%s] doi gio %s", job.id, format_ict(when_ts))
    return True, f"Đã đổi giờ {name} lúc {format_ict(when_ts)}."


def schedule_reup(db, material_id: int, channel_id: str, when_ts: int) -> tuple[bool, str]:
    """Hẹn giờ. Giờ sai thì dừng trước khi gọi nơi đăng. Cùng video cùng kênh thì sửa bài cũ."""
    err = _reject_when(when_ts)
    if err:
        return False, err
    allowed = {row["id"] for row in _channels()}
    if channel_id not in allowed:
        return False, "Page không có trong danh sách Buffer."
    mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
    if not mat:
        return False, "Không thấy video."
    text = caption_of(mat)
    if not text:
        return False, "Chưa có lời bài."

    name = channel_name(channel_id)
    if (mat.target_page or "") != channel_id:
        mat.target_page = channel_id
        db.commit()

    existing = _done_job(db, material_id, channel_id)
    if existing:
        return _apply_reschedule(db, existing, int(when_ts), name)

    block = _quota_block(channel_id, int(when_ts))
    if block:
        return False, block

    now = now_ts()
    future_count = (
        db.query(Job)
        .filter(
            Job.platform == "buffer",
            Job.target_page == channel_id,
            Job.status == JobStatus.DONE,
            Job.schedule_ts > now,
        )
        .count()
    )
    if future_count >= 10:
        return False, f"Hàng chờ {name} đã kín ({future_count}/10 bài)."

    job = Job(
        platform="buffer",
        caption=text,
        viral_material_id=material_id,
        target_page=channel_id,
        schedule_ts=int(when_ts),
        status=JobStatus.RUNNING,
        is_approved=True,
        media_path=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    result = BufferAdapter().publish(job)
    if not result.ok:
        job.status = JobStatus.FAILED
        job.last_error = (result.error or "Buffer từ chối")[:300]
        job.finished_at = now_ts()
        db.commit()
        logger.warning("[Buffer][job_%s] %s", job.id, job.last_error)
        return False, job.last_error

    job.status = JobStatus.DONE
    job.external_post_id = result.external_post_id
    job.finished_at = now_ts()
    job.last_error = None
    db.commit()
    logger.info("[Buffer][job_%s] hen %s", job.id, format_ict(when_ts))
    return True, f"Đã hẹn {name} lúc {format_ict(when_ts)}."


def reschedule_by_post(db, post_id: str, when_ts: int) -> tuple[bool, str]:
    """Đổi giờ bài đã có. Không thấy mã thì không tạo bài mới."""
    err = _reject_when(when_ts)
    if err:
        return False, err
    pid = (post_id or "").strip()
    if not pid:
        return False, "Không thấy bài."
    job = (
        db.query(Job)
        .filter(Job.platform == "buffer", Job.external_post_id == pid, Job.status == JobStatus.DONE)
        .order_by(Job.id.desc())
        .first()
    )
    if not job:
        return False, "Không thấy bài."
    return _apply_reschedule(db, job, int(when_ts), channel_name(job.target_page or ""))


def cancel_material_schedule(db, material_id: int) -> tuple[bool, str]:
    """Hủy lịch của một video. Không có mã bài thì không gọi nơi đăng."""
    job = (
        db.query(Job)
        .filter(
            Job.platform == "buffer",
            Job.viral_material_id == material_id,
            Job.status == JobStatus.DONE,
        )
        .order_by(Job.id.desc())
        .first()
    )
    if not job or not str(job.external_post_id or "").strip():
        return False, "Video này chưa có lịch để hủy."
    return cancel_schedule(db, str(job.external_post_id))


def cancel_schedule(db, post_id: str) -> tuple[bool, str]:
    """Xóa bài chưa đăng. Bài đã đăng thì không nói đã hủy. Không xóa dòng job."""
    pid = (post_id or "").strip()
    if not pid:
        return False, "Không thấy bài."
    try:
        status = _post_status(pid)
    except BufferError as exc:
        return False, str(exc)
    if status == "sent":
        return False, "Bài đã đăng."
    try:
        _delete_post(pid)
    except BufferError as exc:
        return False, str(exc)
    job = (
        db.query(Job)
        .filter(Job.platform == "buffer", Job.external_post_id == pid, Job.status == JobStatus.DONE)
        .order_by(Job.id.desc())
        .first()
    )
    if job:
        job.status = JobStatus.CANCELLED
        job.schedule_ts = 0
        db.commit()
        logger.info("[Buffer][job_%s] huy lich", job.id)
    return True, "Đã hủy lịch. Bài không tự đăng."
