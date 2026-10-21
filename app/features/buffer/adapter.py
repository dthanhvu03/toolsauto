"""Đăng bài qua Buffer API. Không mở browser.

Channel id nằm ở `target_page` của job hoặc account (id kênh Buffer, không phải URL Facebook).
Video/ảnh phải là URL https công khai — Buffer không có API upload.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.adapters.contracts import AdapterInterface, PublishResult
from app.features.buffer.client import MODES, BufferClient, BufferError

logger = logging.getLogger(__name__)

try:
    from app.config import SAFE_MODE
except ImportError:
    SAFE_MODE = False


def api_key() -> str:
    import app.config as config

    return (getattr(config, "BUFFER_API_KEY", None) or "").strip()


def channel_id_for(job) -> str:
    job_page = (getattr(job, "target_page", None) or "").strip()
    if job_page:
        return job_page
    account = getattr(job, "account", None)
    return (getattr(account, "target_page", None) or "").strip()


def _hosted_reup(job) -> str | None:
    mid = getattr(job, "viral_material_id", None)
    if not mid:
        return None
    from app.features.buffer.media import public_reup_url

    return public_reup_url(int(mid))


def public_media_url(job) -> str | None:
    raw = (
        getattr(job, "resolved_processed_media_path", None)
        or getattr(job, "processed_media_path", None)
        or getattr(job, "resolved_media_path", None)
        or getattr(job, "media_path", None)
        or ""
    )
    url = str(raw).strip()
    hosted = _hosted_reup(job)
    if not url:
        return hosted
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return url
    if hosted:
        return hosted
    raise BufferError(
        "Buffer khong nhan file local. Can URL https cong khai, con song den luc dang. "
        "Xem https://developers.buffer.com/guides/hosting-media.html"
    )


def schedule_mode(job) -> tuple[str, str | None]:
    raw = getattr(job, "schedule_ts", None)
    try:
        ts = int(raw or 0)
    except (TypeError, ValueError):
        ts = 0
    if ts <= 0:
        return "addToQueue", None
    now = int(datetime.now(timezone.utc).timestamp())
    if ts <= now:
        return "shareNow", None
    due = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return "customScheduled", due


class BufferAdapter(AdapterInterface):
    PLATFORM = "buffer"

    def __init__(self, client: BufferClient | None = None):
        self._client = client

    def open_session(self, profile_path: str) -> bool:
        if self._client is not None:
            return True
        from app.features.buffer.manager import get_buffer_manager

        mgr = get_buffer_manager()
        if not mgr.has_keys():
            logger.error("[Buffer] Thieu BUFFER_API_KEY hoac BUFFER_API_KEYS.")
            return False
        logger.info("[Buffer] Session API san sang (%d tai khoan).", len(mgr.get_clients()))
        return True

    def close_session(self):
        self._client = None

    def publish(self, job) -> PublishResult:
        logger.info("[Buffer][job_%s] publish", getattr(job, "id", "?"))
        job_type = getattr(job, "job_type", None)
        if str(job_type).upper() == "STORY":
            return self.publish_story(job)

        if SAFE_MODE:
            return PublishResult(
                ok=True,
                external_post_id="safe_mode_dry_run",
                details={"safe_mode": True},
            )
        if self._client is None and not self.open_session(""):
            return PublishResult(
                ok=False,
                is_fatal=True,
                error="Thieu BUFFER_API_KEY hoac BUFFER_API_KEYS.",
                error_code="VALIDATION",
            )

        channel = channel_id_for(job)
        text = (getattr(job, "caption", None) or "").strip()
        if not channel:
            return PublishResult(
                ok=False,
                is_fatal=True,
                error="Thieu channel id Buffer. Dien vao target_page cua job hoac account.",
                error_code="VALIDATION",
            )
        if not text:
            return PublishResult(
                ok=False,
                is_fatal=True,
                error="Thieu caption.",
                error_code="VALIDATION",
            )
        try:
            from app.features.buffer.first_comment import get_or_create_first_comment
            from app.features.buffer.manager import get_buffer_manager

            client = self._client or get_buffer_manager().get_client_for_channel(channel)
            media = public_media_url(job)
            mode, due_at = schedule_mode(job)

            # Resolve service for channel
            svc = getattr(job, "service", None) or getattr(job, "channel_service", None)
            if not svc:
                if hasattr(client, "infer_channel_service"):
                    inferred = client.infer_channel_service(channel)
                    if isinstance(inferred, str) and inferred.strip():
                        svc = inferred.strip().lower()
                    else:
                        svc = BufferClient.infer_channel_service(channel)
                else:
                    svc = BufferClient.infer_channel_service(channel)
            else:
                svc = str(svc).strip().lower()

            first_comment = None
            if svc != "tiktok":
                job_comment = (getattr(job, "auto_comment_text", None) or "").strip()
                if job_comment:
                    first_comment = job_comment
                else:
                    topic = str(getattr(job, "ai_style", "") or "")
                    first_comment = get_or_create_first_comment(caption=text, topic=topic)
                    try:
                        job.auto_comment_text = first_comment
                    except Exception:
                        pass

            try:
                post = client.create_post(
                    text=text,
                    channel_id=channel,
                    mode=mode,
                    media_url=media,
                    due_at=due_at,
                    service=svc,
                    first_comment=first_comment,
                )
            except BufferError as fc_exc:
                # Gói Free: first comment → 422 "paid plan". Đăng lại không comment (1 call thêm, tránh fail vòng).
                err_l = str(fc_exc).lower()
                if first_comment and (
                    "first comment" in err_l
                    or "paid plan" in err_l
                    or "upgrade" in err_l
                ):
                    logger.warning(
                        "[Buffer][job_%s] Bo first_comment (plan khong ho tro): %s",
                        getattr(job, "id", "?"),
                        fc_exc,
                    )
                    first_comment = None
                    try:
                        job.auto_comment_text = ""
                    except Exception:
                        pass
                    post = client.create_post(
                        text=text,
                        channel_id=channel,
                        mode=mode,
                        media_url=media,
                        due_at=due_at,
                        service=svc,
                        first_comment=None,
                    )
                else:
                    raise
        except BufferError as exc:
            logger.warning("[Buffer][job_%s] %s", getattr(job, "id", "?"), exc)
            if getattr(exc, "status_code", None) == 429 and self._client is None:
                try:
                    from app.features.buffer.manager import get_buffer_manager

                    ch = channel_id_for(job)
                    c = get_buffer_manager().get_client_for_channel(ch)
                    if c is not None and hasattr(c, "mark_rate_limited"):
                        c.mark_rate_limited(getattr(exc, "retry_after", None))
                except Exception:
                    pass
            fatal = "file local" in str(exc) or "channel" in str(exc).lower()
            return PublishResult(
                ok=False,
                is_fatal=fatal,
                error=str(exc)[:300],
                error_code="VALIDATION" if fatal else None,
            )

        return PublishResult(
            ok=True,
            external_post_id=str(post.get("id")),
            details={"dueAt": post.get("dueAt"), "mode": mode, "firstComment": first_comment},
        )

    def publish_story(self, job) -> PublishResult:
        logger.info("[Buffer][job_%s] publish_story", getattr(job, "id", "?"))
        if SAFE_MODE:
            return PublishResult(
                ok=True,
                external_post_id="safe_mode_dry_run",
                details={"safe_mode": True, "fb_type": "story"},
            )
        if self._client is None and not self.open_session(""):
            return PublishResult(
                ok=False,
                is_fatal=True,
                error="Thieu BUFFER_API_KEY hoac BUFFER_API_KEYS.",
                error_code="VALIDATION",
            )

        channel = channel_id_for(job)
        if not channel:
            return PublishResult(
                ok=False,
                is_fatal=True,
                error="Thieu channel id Buffer. Dien vao target_page cua job hoac account.",
                error_code="VALIDATION",
            )
        try:
            from app.features.buffer.manager import get_buffer_manager

            client = self._client or get_buffer_manager().get_client_for_channel(channel)
            media = public_media_url(job)
            mode, due_at = schedule_mode(job)

            # Resolve service for channel
            svc = getattr(job, "service", None) or getattr(job, "channel_service", None)
            if not svc:
                if hasattr(client, "infer_channel_service"):
                    inferred = client.infer_channel_service(channel)
                    if isinstance(inferred, str) and inferred.strip():
                        svc = inferred.strip().lower()
                    else:
                        svc = BufferClient.infer_channel_service(channel)
                else:
                    svc = BufferClient.infer_channel_service(channel)
            else:
                svc = str(svc).strip().lower()

            text = (getattr(job, "caption", None) or "").strip()

            post = client.create_post(
                text=text,
                channel_id=channel,
                mode=mode,
                media_url=media,
                due_at=due_at,
                service=svc,
                fb_type="story",
            )
        except BufferError as exc:
            logger.warning("[Buffer][job_%s] story %s", getattr(job, "id", "?"), exc)
            fatal = "file local" in str(exc) or "channel" in str(exc).lower()
            return PublishResult(
                ok=False,
                is_fatal=fatal,
                error=str(exc)[:300],
                error_code="VALIDATION" if fatal else None,
            )

        return PublishResult(
            ok=True,
            external_post_id=str(post.get("id")),
            details={"dueAt": post.get("dueAt"), "mode": mode, "fb_type": "story"},
        )

    def check_published_state(self, job) -> PublishResult:
        post_id = (getattr(job, "external_post_id", None) or "").strip()
        if not post_id or post_id == "safe_mode_dry_run":
            return PublishResult(ok=False, error="Chua co post Buffer.")
        if self._client is None and not self.open_session(""):
            return PublishResult(ok=False, error="Thieu BUFFER_API_KEY hoac BUFFER_API_KEYS.")
        try:
            from app.features.buffer.manager import get_buffer_manager

            channel = channel_id_for(job)
            mgr = get_buffer_manager()
            client = self._client or (
                mgr.get_client_for_channel(channel) if channel else mgr.get_client_for_post(post_id)
            )
            post = client.get_post(post_id)
        except BufferError as exc:
            return PublishResult(ok=False, error=str(exc)[:300])
        if not post:
            return PublishResult(ok=False, error="Khong thay post tren Buffer.")
        return PublishResult(ok=True, external_post_id=str(post.get("id")))


def normalize_mode(mode: str) -> str:
    value = (mode or "addToQueue").strip()
    if value not in MODES:
        raise BufferError(f"Mode Buffer khong hop le: {value}")
    return value
