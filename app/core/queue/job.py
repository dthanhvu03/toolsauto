"""
Service layer for managing Job entities and their lifecycle.
"""
import os
import re
import time
from typing import Any, Optional

from sqlalchemy.orm import Session, selectinload

from app.core.database.core import SessionLocal
from app.core.database.models import Job, JobEvent, Account
from app.config import COMMENT_JOB_DELAY_MAX_SEC, COMMENT_JOB_DELAY_MIN_SEC, CONTENT_MEDIA_DIR
from app.constants import JobStatus, JobType
from app.utils.logger import setup_shared_logger

logger = setup_shared_logger(__name__)

_AI_TITLE_RE = re.compile(r"###\s*ORIGINAL_VIRAL_TITLE:\s*(.*?)\s*###", re.DOTALL | re.IGNORECASE)
_AI_BOOST_RE = re.compile(r"###\s*BOOST_CONTEXT:\s*(.*?)\s*###", re.DOTALL | re.IGNORECASE)

_STATUS_LABELS_VI = {
    JobStatus.AWAITING_STYLE: "Chờ chọn style",
    JobStatus.DRAFT: "Nháp",
    JobStatus.PENDING: "Chờ đăng",
    JobStatus.RUNNING: "Đang đăng",
    JobStatus.AI_PROCESSING: "AI đang viết",
    JobStatus.DONE: "Xong",
    JobStatus.FAILED: "Lỗi",
    JobStatus.CANCELLED: "Đã hủy",
}

# (needle_lower, title_vi, hint_vi) — first match wins
_MESSAGE_HUMANIZE: list[tuple[str, str, str]] = [
    (
        "file_inputs",
        "Lỗi kỹ thuật khi mở form đăng Reel",
        "Hệ thống gặp bug nội bộ lúc quét nút upload. Đã vá — thử Đăng lại / Retry nếu bài chưa lên.",
    ),
    (
        "apply_runtime_overrides_to_config",
        "Lỗi sau khi đăng (bước nghỉ)",
        "Bài có thể đã đăng thành công; chỉ lệch bước cooldown. Kiểm tra link bài / page trước khi đăng lại.",
    ),
    (
        "page mismatch",
        "Không khớp fanpage đích",
        "Trình duyệt đang ở page khác với Target Page. Kiểm tra cookie / quyền quản lý page.",
    ),
    (
        "unexpected playwright error",
        "Lỗi trình duyệt khi đăng",
        "Playwright gặp sự cố giữa chừng. Thường retry được — xem chi tiết kỹ thuật bên dưới.",
    ),
    (
        "playwright error",
        "Lỗi trình duyệt khi đăng",
        "Không hoàn tất thao tác trên Facebook. Thử lại hoặc kiểm tra session tài khoản.",
    ),
    (
        "job_forced",
        "Đã đẩy chạy ngay",
        "Lịch đăng được kéo về hiện tại để worker lấy job.",
    ),
    (
        "job approved and moved to pending",
        "Đã duyệt — đưa vào hàng chờ đăng",
        "Publisher sẽ nhận job khi đến lịch / hết cooldown.",
    ),
    (
        "job approved",
        "Đã duyệt — chờ đăng",
        "Job chuyển sang hàng chờ Publisher.",
    ),
    (
        "owner deploy: skip ai",
        "Đã bỏ AI — dùng caption tay",
        "Không chờ AI viết caption; nội dung do người vận hành nhập.",
    ),
    (
        "skip ai + manual caption",
        "Đã bỏ AI — dùng caption tay",
        "Không chờ AI viết caption; nội dung do người vận hành nhập.",
    ),
    (
        "job marked done",
        "Đăng thành công",
        "Job đã hoàn tất trên hệ thống.",
    ),
    (
        "restored after successful publish",
        "Khôi phục trạng thái Xong",
        "Bài đã đăng; hệ thống chỉnh lại trạng thái sau lỗi phụ.",
    ),
    (
        "manual short caption",
        "Đã lưu caption thủ công",
        "Caption do người vận hành nhập (không qua AI).",
    ),
    (
        "style skipped",
        "Đã bỏ qua AI (Skip)",
        "Job sang nháp để sửa caption tay rồi duyệt.",
    ),
    (
        "style set to",
        "Đã chọn style caption",
        "AI worker sẽ viết caption theo style đã chọn.",
    ),
    (
        "cancelled",
        "Đã hủy job",
        "Job bị dừng thủ công hoặc do hệ thống.",
    ),
    (
        "checkpoint",
        "Facebook yêu cầu xác minh tài khoản",
        "Cần mở trình duyệt / cookie và xử lý checkpoint trước khi đăng tiếp.",
    ),
]


def now_ts() -> int:
    return int(time.time())


class JobService:
    # Single source of truth for accepted media. Anything advertised in an error
    # message must be accepted by create_job, and vice versa.
    VIDEO_EXTENSIONS = ('.mp4', '.mov', '.webm', '.mkv')
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png')
    VALID_EXTENSIONS = VIDEO_EXTENSIONS + IMAGE_EXTENSIONS
    # Facebook POST/Reels composer only accepts video — images cause UI dead-ends (Job #6).
    FACEBOOK_POST_VIDEO_EXTENSIONS = VIDEO_EXTENSIONS

    # error_type values that describe operator/content input, not an unhealthy
    # account: they must never move the account circuit breaker.
    ERROR_TYPE_VALIDATION = "VALIDATION"
    NON_ACCOUNT_ERROR_TYPES = frozenset({"VALIDATION", "COMPLIANCE"})

    # Loại job Facebook KHÔNG đi qua composer Reels nên không bắt buộc video.
    NON_REELS_JOB_TYPES = frozenset({"COMMENT", "FEED"})

    @staticmethod
    def assert_feed_media(media_path: str | None) -> None:
        """
        Bài feed: media là tùy chọn. Có thì phải là ảnh hoặc video hợp lệ.

        Bài chữ thuần (media_path=None) là hợp lệ — đó chính là điểm khác Reels.
        """
        if not media_path or not str(media_path).strip():
            return
        ext = os.path.splitext(str(media_path))[1].lower()
        allowed = JobService.VIDEO_EXTENSIONS + JobService.IMAGE_EXTENSIONS
        if ext not in allowed:
            raise ValueError(
                "Bài feed Facebook chỉ nhận ảnh hoặc video "
                f"({JobService._fmt_extensions(allowed)}). Nhận được '{ext or '(none)'}'."
            )

    @staticmethod
    def _fmt_extensions(extensions: tuple[str, ...]) -> str:
        return "/".join(extensions)

    @staticmethod
    def is_video_media_path(media_path: str | None) -> bool:
        if not media_path:
            return False
        ext = os.path.splitext(str(media_path).strip())[1].lower()
        return ext in JobService.VIDEO_EXTENSIONS

    @staticmethod
    def assert_facebook_post_media(
        platform: str | None,
        media_path: str | None,
        job_type: str | None = "POST",
        require_media: bool = False,
    ) -> None:
        """
        Raise ValueError if a Facebook POST would upload non-video into Reels.

        `require_media=False` (creation time) keeps caption-only manual jobs
        creatable — the manual form advertises Media as optional. `require_media=True`
        (publish time) rejects a missing file, because the Reels composer cannot
        publish without one.
        """
        plat = ((platform or "").split(",")[0].strip().lower())
        jt = (job_type or "POST").strip().upper()
        if plat != "facebook" or jt in JobService.NON_REELS_JOB_TYPES:
            # COMMENT không có media; FEED đi qua composer nên nhận cả ảnh lẫn
            # bài chữ thuần — chỉ Reels (POST) mới bắt buộc video.
            if jt == "FEED":
                JobService.assert_feed_media(media_path)
            return
        if not media_path or not str(media_path).strip():
            if require_media:
                raise ValueError(
                    "Facebook Reels/POST cần file video "
                    f"({JobService._fmt_extensions(JobService.VIDEO_EXTENSIONS)}). Thiếu media."
                )
            return
        if not JobService.is_video_media_path(media_path):
            ext = os.path.splitext(str(media_path))[1].lower() or "(none)"
            raise ValueError(
                "Facebook Reels/POST chỉ nhận video "
                f"({JobService._fmt_extensions(JobService.VIDEO_EXTENSIONS)}). "
                f"Nhận được '{ext}' — không đăng ảnh vào Reels."
            )

    @staticmethod
    def get_job_by_id(db: Session, job_id: int) -> Optional[Job]:
        return db.query(Job).filter(Job.id == job_id).first()

    @staticmethod
    def get_job_events(db: Session, job_id: int, limit: int = 50) -> list[JobEvent]:
        return db.query(JobEvent).filter(JobEvent.job_id == job_id).order_by(JobEvent.id.desc()).limit(limit).all()

    @staticmethod
    def status_label_vi(status: str | None) -> str:
        key = (status or "").strip()
        return _STATUS_LABELS_VI.get(key, key or "—")

    @staticmethod
    def humanize_job_message(message: str | None) -> dict[str, Any]:
        """Map raw job/event text → title + hint for operators (keep raw for support)."""
        raw = (message or "").strip()
        if not raw:
            return {"title": "—", "hint": "", "raw": "", "is_technical": False}
        low = raw.lower()
        for needle, title, hint in _MESSAGE_HUMANIZE:
            if needle in low:
                return {"title": title, "hint": hint, "raw": raw, "is_technical": True}
        # Soft ops labels
        if low.startswith("job ") or "_" in raw and raw.upper() == raw:
            return {"title": raw.replace("_", " ").strip(), "hint": "", "raw": raw, "is_technical": False}
        return {"title": raw, "hint": "", "raw": raw, "is_technical": False}

    @staticmethod
    def humanize_event_meta(meta: str | None) -> str:
        """is_fatal=False, tries=4/3 → tiếng Việt ngắn."""
        raw = (meta or "").strip()
        if not raw or raw == "{}":
            return ""
        low = raw.lower()
        if "restored after successful publish" in low:
            return "Khôi phục sau khi đăng thành công"
        if raw.strip().lower() == "success":
            return "Thành công"
        fatal_m = re.search(r"is_fatal\s*=\s*(True|False)", raw, re.I)
        tries_m = re.search(r"tries\s*=\s*(\d+)\s*/\s*(\d+)", raw, re.I)
        parts: list[str] = []
        if fatal_m:
            parts.append(
                "Lỗi chặn hẳn" if fatal_m.group(1).lower() == "true" else "Có thể thử lại"
            )
        if tries_m:
            parts.append(f"Lần thử {tries_m.group(1)}/{tries_m.group(2)}")
        if parts:
            return " · ".join(parts)
        return raw

    @staticmethod
    def parse_caption_for_ui(caption: str | None) -> dict[str, Any]:
        """Split AI metadata caption into human-readable fields for Job details modal."""
        raw = caption or ""
        awaiting_ai = "[AI_GENERATE]" in raw
        title_m = _AI_TITLE_RE.search(raw)
        boost_m = _AI_BOOST_RE.search(raw)
        viral_title = (title_m.group(1).strip() if title_m else "") or ""
        boost_context = (boost_m.group(1).strip() if boost_m else "") or ""
        display = raw
        if awaiting_ai:
            display = viral_title or "(Chưa có caption — chờ AI sau khi chọn style)"
        return {
            "raw": raw,
            "awaiting_ai": awaiting_ai,
            "viral_title": viral_title,
            "boost_context": boost_context,
            "display": display,
            "char_count": len(display),
        }

    @staticmethod
    def build_job_milestones(job: Job) -> list[dict[str, Any]]:
        """Synthetic timeline when JobEvent rows are empty (common right after viral create)."""
        items: list[dict[str, Any]] = []
        created = getattr(job, "created_at", None) or 0
        if created:
            items.append({
                "ts": int(created),
                "level": "INFO",
                "message": "Job được tạo",
                "meta": f"status ban đầu → {job.status}",
            })
        if job.viral_material_id:
            items.append({
                "ts": int(created or 0),
                "level": "INFO",
                "message": f"Gắn viral material #{job.viral_material_id}",
                "meta": "Pipeline viral → job",
            })
        if job.media_path and "_reup" in (job.media_path or "").replace("\\", "/"):
            items.append({
                "ts": int(created or 0),
                "level": "INFO",
                "message": "Media đã qua reup (anti-dupe)",
                "meta": os.path.basename(job.media_path or ""),
            })
        if job.content_hash:
            items.append({
                "ts": int(created or 0),
                "level": "INFO",
                "message": "Đã gắn content_hash (media guard)",
                "meta": (job.content_hash or "")[:16] + "…",
            })
        if job.status == JobStatus.AWAITING_STYLE:
            items.append({
                "ts": int(created or 0),
                "level": "WARN",
                "message": "Đang chờ chọn style trên Telegram",
                "meta": "≈30 phút không chọn → tự short",
            })
        if job.finished_at:
            items.append({
                "ts": int(job.finished_at),
                "level": "INFO" if job.status == JobStatus.DONE else "WARN",
                "message": f"Kết thúc với trạng thái {JobService.status_label_vi(job.status)}",
                "meta": job.status,
            })
        return items

    @staticmethod
    def get_job_details_context(db: Session, job_id: int) -> Optional[dict[str, Any]]:
        job = JobService.get_job_by_id(db, job_id)
        if not job:
            return None
        events = JobService.get_job_events(db, job_id, limit=20)
        caption_view = JobService.parse_caption_for_ui(job.caption)
        milestones = [] if events else JobService.build_job_milestones(job)
        media_name = os.path.basename(job.media_path) if job.media_path else ""
        event_views = []
        for event in events:
            view = JobService.humanize_job_message(event.message)
            event_views.append(
                {
                    "level": event.level,
                    "ts": event.ts,
                    "title": view["title"],
                    "hint": view["hint"],
                    "raw": view["raw"],
                    "is_technical": view["is_technical"],
                    "meta_label": JobService.humanize_event_meta(event.meta_json),
                    "meta_raw": event.meta_json or "",
                }
            )
        last_error_view = JobService.humanize_job_message(job.last_error)
        return {
            "job": job,
            "events": events,
            "event_views": event_views,
            "milestones": milestones,
            "caption_view": caption_view,
            "status_label": JobService.status_label_vi(job.status),
            "media_name": media_name,
            "has_reup": bool(job.media_path and "_reup" in (job.media_path or "").replace("\\", "/")),
            "last_error_view": last_error_view,
        }
    
    @staticmethod
    def create_job(
        db: Session,
        account_id: int,
        media_path: str,
        caption: str,
        schedule_ts: int,
        randomize_caption: bool,
        dedupe_key: str = None,
        affiliate_url: str = None,
        target_page: str = None,
        viral_material_id: int | None = None,
        content_hash: str | None = None,
    ) -> Job:
        """Creates a new PENDING job with strict validations."""
        # 1. Validate Account
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            raise ValueError(f"Account ID {account_id} does not exist.")
            
        # 2. Validate Schedule
        if schedule_ts < now_ts():
            raise ValueError("Schedule time cannot be in the past.")
            
        # 3. Normalize and Validate Media Path
        norm_path = os.path.abspath(media_path.strip())
        _, ext = os.path.splitext(norm_path)
        if ext.lower() not in JobService.VALID_EXTENSIONS:
            raise ValueError(f"Media extension {ext} not supported. Must be one of {JobService.VALID_EXTENSIONS}")
            
        if not os.path.exists(norm_path):
            raise ValueError(f"Media file not found at path: {norm_path}")

        # Job.platform must be a single adapter key — never copy "facebook,threads" wholesale.
        raw_platform = (account.platform or "").strip()
        job_platform = raw_platform.split(",")[0].strip() if raw_platform else raw_platform

        JobService.assert_facebook_post_media(job_platform, norm_path, job_type="POST")

        from app.core.media.content_hash import assert_media_not_blocked, sha256_file

        resolved_hash = content_hash or sha256_file(norm_path)
        assert_media_not_blocked(
            db,
            platform=job_platform,
            content_hash=resolved_hash,
            viral_material_id=viral_material_id,
        )
            
        # 4. Create Job with tracking
        import uuid
        tracking_code = str(uuid.uuid4())[:8]
        tracking_url = f"/r/{tracking_code}"
        
        initial_status = JobStatus.DRAFT if caption and "[AI_GENERATE]" in caption else JobStatus.PENDING
        
        new_job = Job(
            platform=job_platform,
            account_id=account.id,
            media_path=norm_path,
            caption=caption,
            schedule_ts=schedule_ts,
            status=initial_status,
            tries=0,
            dedupe_key=dedupe_key,
            tracking_code=tracking_code,
            tracking_url=tracking_url,
            affiliate_url=affiliate_url.strip() if affiliate_url and affiliate_url.strip() else None,
            target_page=target_page.strip() if target_page and target_page.strip() else None,
            content_hash=resolved_hash,
            viral_material_id=viral_material_id,
        )
        
        from sqlalchemy.exc import IntegrityError
        
        db.add(new_job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError(
                "Duplicate job detected (same account+file or cross-account media guard). Skipped."
            )
        db.refresh(new_job)
        
        # 5. Handle Caption Randomization with Deterministic Salt
        if randomize_caption:
            import hashlib
            # Create a mathematically unique salt guaranteed to belong only to this specific job
            raw_string = f"{new_job.id}-{new_job.created_at}"
            salt = hashlib.sha256(raw_string.encode()).hexdigest()[:8]
            new_job.caption = f"{caption}\n\n[ref:{salt}]"
            
            db.commit()
            db.refresh(new_job)
            
        # Log creation
        JobService._log_event(db, new_job.id, "INFO", "Job manually created via UI")
        
        # 6. Register tracking code on Vercel (non-blocking)
        JobService._register_vercel_tracking(new_job)
        
        return new_job

    @staticmethod
    def create_job_from_upload(
        db: Session, 
        account_id: int, 
        media_file, 
        caption: str, 
        schedule_ts: int, 
        randomize_caption: bool, 
        affiliate_url: str = "", 
        target_page: str = ""
    ) -> Job:
        import uuid
        import shutil
        import hashlib
        
        if not media_file.filename:
            raise ValueError("No file uploaded.")
            
        ext = os.path.splitext(media_file.filename)[1].lower() or (".mp4" if "video" in media_file.content_type else ".jpg")
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        media_dir = str(CONTENT_MEDIA_DIR)
        os.makedirs(media_dir, exist_ok=True)
        saved_path = os.path.join(media_dir, unique_filename)
        
        with open(saved_path, "wb") as f:
            shutil.copyfileobj(media_file.file, f)
        
        dedupe_raw = f"{account_id}:{unique_filename}"
        dedupe_key = hashlib.sha256(dedupe_raw.encode()).hexdigest()[:16]
        
        return JobService.create_job(db, account_id, saved_path, caption, schedule_ts, randomize_caption, dedupe_key, affiliate_url, target_page.strip())
    
    @staticmethod
    def _register_vercel_tracking(job: Job):
        """
        Register tracking code on Vercel redirect service.
        Non-blocking: failure is silently logged, local tracking still works.
        """
        from app.config import VERCEL_REDIRECT_URL
        vercel_url = VERCEL_REDIRECT_URL
        
        if not vercel_url or not job.affiliate_url or not job.tracking_code:
            return
            
        try:
            import requests
            resp = requests.post(
                f"{vercel_url}/api/register",
                json={"code": job.tracking_code, "url": job.affiliate_url},
                timeout=5
            )
            if resp.ok:
                job.tracking_url = f"{vercel_url}/r/{job.tracking_code}"
        except Exception:
            pass  # Non-blocking — local tracking still works
    
    @staticmethod
    def mark_done(db: Session, job: Job, details: str = None, external_post_id: str = None, post_url: str = None):
        """Transitions RUNNING -> DONE."""
        job.status = JobStatus.DONE
        job.finished_at = now_ts()
        job.last_error = None
        if external_post_id:
            job.external_post_id = external_post_id
        if post_url:
            job.post_url = post_url
        
        if job.account:
            job.account.last_post_ts = now_ts()
            job.account.consecutive_fatal_failures = 0  # Reset circuit breaker
            
        JobService._log_event(db, job.id, "INFO", "Job marked DONE", details)
        
        # Auto-create COMMENT job if POST has auto_comment_text
        if job.job_type == JobType.POST and job.auto_comment_text and (post_url or job.post_url):
            import random
            delay = random.randint(COMMENT_JOB_DELAY_MIN_SEC, COMMENT_JOB_DELAY_MAX_SEC)
            comment_job = Job(
                job_type=JobType.COMMENT,
                platform=job.platform,
                account_id=job.account_id,
                parent_job_id=job.id,
                post_url=post_url or job.post_url,
                auto_comment_text=job.auto_comment_text,
                status=JobStatus.PENDING,
                scheduled_at=now_ts() + delay,
                schedule_ts=now_ts() + delay,  # Also set for compatibility
                media_path=job.media_path,
                caption="",
            )
            db.add(comment_job)
            JobService._log_event(db, job.id, "INFO", 
                f"Auto COMMENT job created (delay={delay}s)")
        
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def mark_failed_or_retry(db: Session, job: Job, error_msg: str, is_fatal: bool, error_type: Optional[str] = None):
        """
        Transitions RUNNING -> FAILED or RUNNING -> PENDING explicitly based on errors.
        """
        job.tries += 1
        job.last_error = error_msg
        job.error_type = error_type or ("FATAL" if is_fatal else "RETRYABLE")
        
        JobService._log_event(db, job.id, "ERROR", error_msg, f"is_fatal={is_fatal}, tries={job.tries}/{job.max_tries}")
        
        # Circuit Breaker logic — operator input errors (bad media, blocked
        # content) say nothing about account health, so they never trip it.
        if is_fatal and job.account and job.error_type not in JobService.NON_ACCOUNT_ERROR_TYPES:
            job.account.consecutive_fatal_failures += 1
            if job.account.consecutive_fatal_failures >= 3:
                job.account.is_active = False
                JobService._log_event(db, job.id, "WARN", f"Circuit breaker activated for account {job.account.name}")
        
        if is_fatal or job.tries >= job.max_tries:
            job.status = JobStatus.FAILED
            job.finished_at = now_ts()
        else:
            job.status = JobStatus.PENDING
            # Exponential backoff
            backoff_mins = 5 if job.tries == 1 else 15
            job.schedule_ts = now_ts() + (backoff_mins * 60)
            
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        
    @staticmethod
    def update_heartbeat(db: Session, job_id: int):
        """Updates the heartbeat of a RUNNING job with silent retries for locking."""
        import sqlalchemy.exc
        import time as _time
        for attempt in range(3):
            try:
                db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.RUNNING).update(
                    {"last_heartbeat_at": int(_time.time())}
                )
                db.commit()
                break
            except sqlalchemy.exc.OperationalError:
                db.rollback()
                if attempt < 2:
                    _time.sleep(0.5 * (attempt + 1))
                continue
            except Exception:
                db.rollback()
                break
        
    @staticmethod
    def get_jobs_paged(
        db: Session,
        status: str = "active",
        page: int = 1,
        per_page: int = 20,
        q: str = "",
        platform: str = "",
    ) -> dict:
        from sqlalchemy import or_
        query = db.query(Job)
        
        # Status filter
        if status == "active":
            query = query.filter(Job.status.in_([JobStatus.AWAITING_STYLE, JobStatus.DRAFT, JobStatus.PENDING, JobStatus.RUNNING, JobStatus.AI_PROCESSING]))
        elif status in (JobStatus.DRAFT, JobStatus.PENDING, JobStatus.RUNNING, JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            query = query.filter(Job.status == status)

        platform = (platform or "").strip().lower()
        if platform and platform != "all":
            query = query.filter(Job.platform == platform)

        # Search filter
        q = (q or "").strip()
        if q:
            if q.isdigit():
                query = query.filter(Job.id == int(q))
            else:
                query = query.join(Account, Job.account_id == Account.id).filter(
                    or_(
                        Account.name.ilike(f"%{q}%"),
                        Job.target_page.ilike(f"%{q}%"),
                        Job.caption.ilike(f"%{q}%"),
                        Job.post_url.ilike(f"%{q}%"),
                    )
                )
        
        total = query.count()
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        
        jobs = (
            query.options(selectinload(Job.account))
            .order_by(Job.schedule_ts.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        # Align UI ETA with claim gate: last DONE.finished_at per (account, platform)
        JobService._attach_claim_cooldown_etas(db, jobs)
        JobService._attach_metrics_etas(db, jobs)
        return {
            "jobs": jobs,
            "total": total,
            "total_pages": total_pages,
            "page": page
        }

    @staticmethod
    def _metrics_check_hours() -> float:
        try:
            return float(os.getenv("METRICS_CHECK_HOURS", "24"))
        except (TypeError, ValueError):
            return 24.0

    @staticmethod
    def _attach_metrics_etas(db: Session, jobs: list) -> None:
        """Set job.metrics_eta = earliest unix ts MetricsChecker may pick this DONE job.

        Rules (mirror MetricsChecker): finished_at + METRICS_CHECK_HOURS; max 1 check/account/day
        so if account already checked today → wait until next local midnight; older unchecked
        siblings on the same account each consume a day slot.
        """
        from app.core.observability.metrics_checker import today_start_ts

        targets = [
            j
            for j in jobs
            if j.status == JobStatus.DONE
            and not j.metrics_checked
            and j.finished_at
            and j.post_url
            and j.view_24h is None
        ]
        for j in jobs:
            setattr(j, "metrics_eta", 0)

        if not targets:
            return

        hours = JobService._metrics_check_hours()
        day_start = today_start_ts()
        tomorrow = day_start + 86400
        account_ids = {int(j.account_id) for j in targets if j.account_id}

        checked_today: set[int] = set()
        if account_ids:
            rows = (
                db.query(Job.account_id)
                .filter(
                    Job.account_id.in_(account_ids),
                    Job.last_metrics_check_ts >= day_start,
                )
                .distinct()
                .all()
            )
            checked_today = {int(r[0]) for r in rows if r[0] is not None}

        waiting_by_acc: dict[int, list] = {}
        if account_ids:
            waiting = (
                db.query(Job)
                .filter(
                    Job.account_id.in_(account_ids),
                    Job.status == JobStatus.DONE,
                    Job.post_url.isnot(None),
                    Job.finished_at.isnot(None),
                    Job.metrics_checked.is_(False),
                )
                .order_by(Job.finished_at.asc(), Job.id.asc())
                .all()
            )
            for w in waiting:
                waiting_by_acc.setdefault(int(w.account_id), []).append(w)

        delay = int(hours * 3600)
        for job in targets:
            aid = int(job.account_id) if job.account_id else 0
            queue = waiting_by_acc.get(aid) or [job]
            cursor = tomorrow if aid in checked_today else day_start
            eta_for_job = 0
            for qj in queue:
                eligible = int(qj.finished_at or 0) + delay
                slot = max(eligible, cursor)
                if qj.id == job.id:
                    eta_for_job = slot
                    break
                slot_day = day_start + max(0, (slot - day_start) // 86400) * 86400
                cursor = slot_day + 86400
            setattr(job, "metrics_eta", int(eta_for_job or (int(job.finished_at) + delay)))

    @staticmethod
    def _attach_claim_cooldown_etas(db: Session, jobs: list) -> None:
        """Set job.claim_cooldown_eta = last_finished_at + cooldown_seconds (claim source of truth)."""
        from sqlalchemy import func

        pairs = {
            (j.account_id, (j.platform or "").strip().lower())
            for j in jobs
            if j.account_id and j.status == JobStatus.PENDING
        }
        if not pairs:
            return

        account_ids = {a for a, _ in pairs}
        rows = (
            db.query(Job.account_id, Job.platform, func.max(Job.finished_at))
            .filter(
                Job.account_id.in_(account_ids),
                Job.status == JobStatus.DONE,
                Job.finished_at.isnot(None),
            )
            .group_by(Job.account_id, Job.platform)
            .all()
        )
        last_by_pair = {
            (int(aid), (plat or "").strip().lower()): int(ts or 0)
            for aid, plat, ts in rows
        }
        for job in jobs:
            if job.status != JobStatus.PENDING or not job.account_id:
                continue
            plat = (job.platform or "").strip().lower()
            last_ts = last_by_pair.get((int(job.account_id), plat), 0)
            cooldown = int(getattr(job.account, "cooldown_seconds", 0) or 0) if job.account else 0
            if last_ts > 0 and cooldown > 0:
                setattr(job, "claim_cooldown_eta", last_ts + cooldown)
            else:
                setattr(job, "claim_cooldown_eta", 0)

    @staticmethod
    def create_high_priority_manual_job(
        db: Session,
        account_id: int,
        target_page: str,
        caption: str = None,
        media_path: str = None,
        job_type: str = JobType.POST,
    ) -> Job:
        from app.core.media.content_hash import assert_media_not_blocked, sha256_file

        platform = "facebook"
        # POST = Reels (bắt buộc video). FEED = bài chữ/ảnh, media tùy chọn.
        jt = (str(job_type) or JobType.POST).strip().upper()
        JobService.assert_facebook_post_media(platform, media_path, job_type=jt)
        content_hash = None
        if media_path:
            content_hash = sha256_file(media_path)
            assert_media_not_blocked(
                db,
                platform=platform,
                content_hash=content_hash,
            )
        job = Job(
            platform=platform,
            account_id=account_id,
            target_page=target_page,
            caption=caption,
            media_path=media_path,
            job_type=jt,
            status=JobStatus.PENDING,
            schedule_ts=int(time.time()) - 999999,  # Priority boost
            tries=0,
            max_tries=3,
            content_hash=content_hash,
        )
        from sqlalchemy.exc import IntegrityError

        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError(
                "Duplicate job detected (same account+file or cross-account media guard). Skipped."
            )
        db.refresh(job)
        JobService._log_event(db, job.id, "INFO", "High-priority manual job created")
        return job

    @staticmethod
    def create_manual_job_with_file(
        db: Session,
        account_id: int,
        target_page: str,
        caption: str,
        media_file,
        job_type: str = JobType.POST,
    ) -> Job:
        import uuid
        import shutil
        from app.config import CONTENT_DIR
        MANUAL_DIR = str(CONTENT_DIR / "manual")

        jt = (str(job_type) or JobType.POST).strip().upper()
        # Reels mặc định .mp4; bài feed không có đuôi thì coi là ảnh .jpg.
        default_ext = "jpg" if jt == JobType.FEED else "mp4"

        media_path = None
        if media_file and media_file.filename:
            ext = media_file.filename.rsplit(".", 1)[-1] if "." in media_file.filename else default_ext
            candidate = os.path.join(MANUAL_DIR, f"manual_{uuid.uuid4().hex[:8]}.{ext}")
            # Validate before writing anything to disk — a rejected upload must
            # not leave a file behind.
            JobService.assert_facebook_post_media("facebook", candidate, job_type=jt)
            os.makedirs(MANUAL_DIR, exist_ok=True)
            with open(candidate, "wb") as f:
                shutil.copyfileobj(media_file.file, f)
            media_path = candidate

        try:
            return JobService.create_high_priority_manual_job(
                db, account_id, target_page, caption, media_path, job_type=jt
            )
        except Exception:
            JobService._discard_files([media_path])
            raise

    @staticmethod
    def _discard_files(paths: list[str | None]) -> None:
        """Best-effort removal of files written for a job that was never created."""
        for path in paths:
            if not path:
                continue
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                logger.warning("[JobService] Could not remove orphan upload %s: %s", path, e)

    @staticmethod
    def apply_style(db: Session, job_id: int, style: str) -> Job:
        """Web/Telegram parity: AWAITING_STYLE → DRAFT with ai_style or Skip AI."""
        allowed = {"sales", "short", "daily", "humor", "skip"}
        style = (style or "").strip().lower()
        if style not in allowed:
            raise ValueError(f"Style không hợp lệ: {style}")

        job = JobService.get_job_by_id(db, job_id)
        if not job:
            raise ValueError("Không tìm thấy job.")
        if job.status != JobStatus.AWAITING_STYLE:
            raise ValueError("Chỉ chọn style khi job đang AWAITING_STYLE.")

        if style == "skip":
            job.status = JobStatus.DRAFT
            if job.caption:
                job.caption = job.caption.replace("[AI_GENERATE]", "").strip()
            JobService._log_event(db, job.id, "INFO", "Style skipped — DRAFT for manual caption")
        else:
            job.ai_style = style
            job.status = JobStatus.DRAFT
            JobService._log_event(db, job.id, "INFO", f"Style set to {style} — DRAFT for AI caption")
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def approve_job(db: Session, job_id: int):
        job = JobService.get_job_by_id(db, job_id)
        if job and job.status == JobStatus.DRAFT:
            job.status = JobStatus.PENDING
            db.commit()
            JobService._log_event(db, job.id, "INFO", "Job approved and moved to PENDING")

    @staticmethod
    def update_job_caption(db: Session, job_id: int, caption: str):
        job = JobService.get_job_by_id(db, job_id)
        if job:
            job.caption = caption
            db.commit()
            JobService._log_event(db, job.id, "INFO", "Job caption updated manually")

    @staticmethod
    def update_job_auto_comment(db: Session, job_id: int, auto_comment_text: str):
        """Operator edits affiliate comment before Approve (DRAFT)."""
        job = JobService.get_job_by_id(db, job_id)
        if not job or job.status != JobStatus.DRAFT:
            raise ValueError("Chỉ sửa auto-comment khi job ở DRAFT.")
        cleaned = (auto_comment_text or "").strip() or None
        job.auto_comment_text = cleaned
        db.commit()
        JobService._log_event(db, job.id, "INFO", "Job auto_comment updated manually")

    @staticmethod
    def attach_affiliate_to_job(
        job: Job,
        *,
        affiliate_url: str,
        comment_template: str,
    ) -> None:
        """
        Parity với bulk create: tracking_code + affiliate_url + comment dùng tracking URL.
        Gọi trước db.commit(); có thể gọi _register_vercel_tracking sau commit nếu cần.
        """
        import uuid
        import app.config as config

        url = (affiliate_url or "").strip()
        if not url:
            return

        tracking_code = job.tracking_code or str(uuid.uuid4())[:8]
        job.tracking_code = tracking_code
        job.affiliate_url = url

        vurl = (getattr(config, "VERCEL_REDIRECT_URL", None) or "").strip().rstrip("/")
        full_turl = f"{vurl}/r/{tracking_code}" if vurl else f"/r/{tracking_code}"
        job.tracking_url = full_turl

        template = comment_template or ""
        comment = template.replace("[LINK]", full_turl).replace("{tracking_url}", full_turl)
        job.auto_comment_text = comment.strip() or None

    @staticmethod
    def bulk_create_jobs(db: Session, account_id: int, files_data: list) -> str:
        """
        files_data: list of dict { 'final_path', 'caption', 'adjusted_ts', 'dedupe_key', 'tracking_code', 'clean_affiliate', 'final_auto_comment', 'target_page', 'initial_status' }
        """
        import uuid
        import hashlib
        batch_id = uuid.uuid4().hex
        jobs_to_insert = []

        # Validate the whole batch before touching the DB so one bad file cannot
        # leave the batch half-inserted.
        for data in files_data:
            JobService.assert_facebook_post_media(
                data.get("platform"),
                data.get("final_path"),
                job_type=data.get("job_type") or "POST",
            )

        for data in files_data:
            from app.core.media.content_hash import assert_media_not_blocked, sha256_file

            media_hash = data.get("content_hash") or sha256_file(data["final_path"])
            assert_media_not_blocked(
                db,
                platform=data["platform"],
                content_hash=media_hash,
                viral_material_id=data.get("viral_material_id"),
            )
            job = Job(
                platform=data['platform'],
                account_id=account_id,
                media_path=data['final_path'],
                caption=data['caption'],
                schedule_ts=data['adjusted_ts'],
                status=data['initial_status'],
                tries=0,
                dedupe_key=data['dedupe_key'],
                batch_id=batch_id,
                tracking_code=data['tracking_code'],
                tracking_url=f"/r/{data['tracking_code']}",
                affiliate_url=data['clean_affiliate'],
                auto_comment_text=data['final_auto_comment'],
                target_page=data['target_page'],
                content_hash=media_hash,
                viral_material_id=data.get("viral_material_id"),
            )
            jobs_to_insert.append(job)

        for job in jobs_to_insert:
            db.add(job)
        db.flush() 

        # Handle Caption Randomization
        for job in jobs_to_insert:
            raw_string = f"{job.id}-{job.created_at}"
            salt = hashlib.sha256(raw_string.encode()).hexdigest()[:8]
            job.caption = f"{job.caption}\n\n[ref:{salt}]"

        db.commit()
        return batch_id

    @staticmethod
    def bulk_create_jobs_from_uploads(
        db: Session,
        account_id: int,
        media_files: list,
        captions: list,
        schedule_times: list,
        randomize_caption: bool,
        affiliate_url: str = "",
        auto_comment_text: str = "",
        target_page: str = ""
    ) -> str:
        import uuid
        import shutil
        import hashlib
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.config import MAX_FILES_PER_BATCH, TIMEZONE
        from app.core.account import AccountService
        
        if len(media_files) > MAX_FILES_PER_BATCH:
            raise ValueError(f"Limit {MAX_FILES_PER_BATCH} files.")
        
        account = AccountService.get_account_by_id(db, account_id)
        if not account or not account.is_active:
            raise ValueError("Invalid account.")
        
        media_dir = str(CONTENT_MEDIA_DIR)

        # Validate every filename BEFORE a single byte is written: a batch that
        # is going to be rejected must not leave uploads in content/media/.
        selected = [(i, mf) for i, mf in enumerate(media_files) if mf and mf.filename]
        for _i, media_file in selected:
            ext = os.path.splitext(media_file.filename)[1].lower()
            if ext not in JobService.VALID_EXTENSIONS:
                raise ValueError(
                    f"Định dạng {ext or '(none)'} không được hỗ trợ. "
                    f"Chấp nhận: {JobService._fmt_extensions(JobService.VALID_EXTENSIONS)}"
                )
            JobService.assert_facebook_post_media(
                account.platform, media_file.filename, job_type="POST"
            )

        os.makedirs(media_dir, exist_ok=True)

        files_data = []
        written_paths: list[str] = []
        last_valid_ts = account.last_post_ts or 0
        clean_affiliate = affiliate_url.strip() if affiliate_url else None
        clean_auto_comment = auto_comment_text.strip() if auto_comment_text else None

        try:
            for i, media_file in selected:
                dt_naive = datetime.strptime(schedule_times[i], "%Y-%m-%dT%H:%M")
                dt_aware = dt_naive.replace(tzinfo=ZoneInfo(TIMEZONE))
                row_ts = int(dt_aware.timestamp())
                adjusted_ts = max(row_ts, last_valid_ts + account.cooldown_seconds if last_valid_ts > 0 else row_ts)
                last_valid_ts = adjusted_ts

                ext = os.path.splitext(media_file.filename)[1].lower()
                unique_filename = f"{uuid.uuid4().hex}{ext}"
                final_path = os.path.join(media_dir, unique_filename)

                with open(final_path, "wb") as f:
                    shutil.copyfileobj(media_file.file, f)
                written_paths.append(final_path)

                dedupe_key = hashlib.sha256(f"{account_id}:{unique_filename}".encode()).hexdigest()[:16]
                tracking_code = str(uuid.uuid4())[:8]

                final_comment = clean_auto_comment
                if final_comment:
                    from app.config import VERCEL_REDIRECT_URL
                    vurl = (VERCEL_REDIRECT_URL or "").strip().rstrip("/")
                    full_turl = f"{vurl}/r/{tracking_code}" if vurl else f"/r/{tracking_code}"
                    final_comment = final_comment.replace("{tracking_url}", full_turl)

                files_data.append({
                    'platform': account.platform,
                    'final_path': final_path,
                    'caption': captions[i],
                    'adjusted_ts': adjusted_ts,
                    'dedupe_key': dedupe_key,
                    'tracking_code': tracking_code,
                    'clean_affiliate': clean_affiliate,
                    'final_auto_comment': final_comment,
                    'target_page': target_page.strip() if target_page else None,
                    'initial_status': JobStatus.DRAFT if "[AI_GENERATE]" in captions[i] else JobStatus.PENDING
                })

            return JobService.bulk_create_jobs(db, account_id, files_data)
        except Exception:
            # Any failure (validation, hash guard, DB) rolls the batch back to
            # "nothing happened" — no half-written uploads left behind.
            db.rollback()
            JobService._discard_files(written_paths)
            raise

    @staticmethod
    def rollback_to_pending(db: Session, job: Job, reason: str):
        """Rolls back a locked job to PENDING if pre-dispatch validation fails."""
        job.status = JobStatus.PENDING
        # Delay it briefly to avoid immediate re-lock looping
        job.schedule_ts = now_ts() + 60
        JobService._log_event(db, job.id, "WARN", f"Rolled back to PENDING: {reason}")
        db.commit()
        
    @staticmethod
    def retry_job(db: Session, job_id: int):
        """Transitions FAILED -> PENDING. Does not reset tries."""
        job = db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.FAILED).first()
        if not job:
            raise ValueError("Job is not in FAILED state or does not exist.")
            
        # Verify media file exists before allowing retry
        if not job.resolved_media_path:
            raise ValueError("Cannot retry: media file has been deleted")

        now = now_ts()
        job.status = JobStatus.PENDING
        job.schedule_ts = now
        
        db.commit()
        JobService._log_event(db, job_id, "INFO", "MANUAL_RETRY")

    @staticmethod
    def reset_to_draft(db: Session, job_id: int):
        """Transitions AI_PROCESSING/FAILED/PENDING -> DRAFT for re-processing."""
        rows_affected = db.query(Job).filter(
            Job.id == job_id,
            Job.status.in_([JobStatus.AI_PROCESSING, JobStatus.FAILED, JobStatus.PENDING, JobStatus.RUNNING])
        ).update({
            "status": JobStatus.DRAFT,
            "last_error": None,
            "tries": 0,
        }, synchronize_session="fetch")
        if rows_affected == 0:
            raise ValueError("Job is not in a resettable state or does not exist.")
        db.commit()
        JobService._log_event(db, job_id, "INFO", "RESET_TO_DRAFT")

    @staticmethod
    def cancel_job(db: Session, job_id: int):
        """Transitions PENDING, DRAFT, or AI_PROCESSING -> CANCELLED."""
        rows_affected = db.query(Job).filter(Job.id == job_id, Job.status.in_([JobStatus.PENDING, JobStatus.DRAFT, JobStatus.AI_PROCESSING])).update({
            "status": JobStatus.CANCELLED
        }, synchronize_session="fetch")
        if rows_affected == 0:
            raise ValueError("Job is not in PENDING/DRAFT/AI_PROCESSING state or does not exist.")
        db.commit()
        JobService._log_event(db, job_id, "INFO", "JOB_CANCELLED")
        
    @staticmethod
    def reschedule_job(db: Session, job_id: int, new_ts: int):
        """Updates schedule_ts for a PENDING job."""
        if new_ts < now_ts():
            raise ValueError("Schedule time cannot be in the past.")
        rows_affected = db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.PENDING).update({
            "schedule_ts": new_ts
        })
        if rows_affected == 0:
            raise ValueError("Job is not in PENDING state or does not exist.")
        db.commit()
        JobService._log_event(db, job_id, "INFO", "JOB_RESCHEDULED")

    @staticmethod
    def force_run_job(db: Session, job_id: int):
        """Sets schedule_ts to now for a PENDING job."""
        job = db.query(Job).filter(Job.id == job_id, Job.status == JobStatus.PENDING).first()
        if not job:
            raise ValueError("Job is not in PENDING state or does not exist.")
        # Force-run means "publish now": apply the publish-time rules so the
        # operator learns immediately instead of watching the job fail.
        JobService.assert_facebook_post_media(
            job.platform,
            job.media_path,
            job_type=getattr(job, "job_type", None) or "POST",
            require_media=True,
        )
        job.schedule_ts = now_ts()
        db.commit()
        JobService._log_event(db, job_id, "INFO", "JOB_FORCED")

    @staticmethod
    def _log_event(db: Session, job_id: int, level: str, message: str, meta: str = None):
        """Best-effort event logging that must never break business state transitions."""
        payload = {
            "job_id": job_id,
            "level": level,
            "message": message,
            "meta_json": meta,
        }

        last_err = None
        for attempt in range(2):
            event_db = SessionLocal()
            try:
                event_db.add(JobEvent(**payload))
                event_db.commit()
                return
            except Exception as exc:
                last_err = exc
                event_db.rollback()
                if attempt == 0:
                    logger.warning(
                        "[Job %s] _log_event failed on attempt %s, retrying once: %s",
                        job_id,
                        attempt + 1,
                        exc,
                    )
                    continue
            finally:
                event_db.close()

        logger.error("[Job %s] _log_event failed after retry: %s", job_id, last_err)
