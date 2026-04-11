"""
Notifier Service — Gửi thông báo qua các kênh khác nhau (Telegram, Email, Webhook…).

Kiến trúc:
    TelegramClient     → Low-level API wrapper (telegram_client.py)
    TelegramNotifier   → app.services.notifier_services/telegram.py (kế thừa BaseNotifier)
    NotifierService    → Facade (gọi tất cả channels)
    MediaProcessor     → extract/cleanup thumbnail cho notify_job_done

Dùng:
    from app.services.notifier_service import NotifierService, TelegramNotifier
    NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))
    NotifierService.notify_job_done(job)
"""
import logging
import os
from typing import Optional

from app.services.media_processor import MediaProcessor
from app.services.notifiers import BaseNotifier, TelegramNotifier
from app.services import notifier_service as nf
from app.constants import JobStatus


logger = logging.getLogger(__name__)

__all__ = ["NotifierService", "BaseNotifier", "TelegramNotifier"]


class NotifierService:
    """Facade gửi thông báo qua tất cả channels đã đăng ký."""

    _channels: list[BaseNotifier] = []

    @classmethod
    def register(cls, channel: BaseNotifier):
        """Đăng ký thêm 1 notification channel. Tránh trùng: cùng channel_key chỉ giữ 1."""
        key = getattr(channel, "channel_key", None) and channel.channel_key()
        if key:
            for ch in cls._channels:
                if getattr(ch, "channel_key", None) and ch.channel_key() == key:
                    logger.debug("Notifier already registered for key %s, skip duplicate.", key)
                    return
        cls._channels.append(channel)
        logger.info("Registered notifier: %s", type(channel).__name__)

    @classmethod
    def _broadcast(cls, message: str):
        """Gửi text message tới tất cả channels."""
        for ch in cls._channels:
            try:
                ch.send(message)
            except Exception as e:
                logger.error("Notifier %s lỗi: %s", type(ch).__name__, e)

    @classmethod
    def _broadcast_photo(cls, photo_path: str, caption: str):
        """Gửi photo + caption tới tất cả channels."""
        for ch in cls._channels:
            try:
                ch.send_photo(photo_path, caption)
            except Exception as e:
                logger.error("Notifier %s photo lỗi: %s", type(ch).__name__, e)

    @classmethod
    def _broadcast_with_buttons(cls, message: str, buttons: list):
        """Gửi text + inline buttons tới tất cả channels."""
        for ch in cls._channels:
            try:
                ch.send_with_buttons(message, buttons)
            except Exception as e:
                logger.error("Notifier %s buttons lỗi: %s", type(ch).__name__, e)

    @classmethod
    def _broadcast_video(cls, video_path: str, caption: str, buttons: Optional[list] = None):
        """Gửi video + caption tới tất cả channels."""
        for ch in cls._channels:
            try:
                ch.send_video(video_path, caption, buttons)
            except Exception as e:
                logger.error("Notifier %s video lỗi: %s", type(ch).__name__, e)

    @classmethod
    def notify_job_done(cls, job, post_url: Optional[str] = None):
        """Thông báo khi job publish thành công (có thumbnail nếu là video)."""
        msg = nf.job_done_message(job, post_url)

        video_path = job.resolved_processed_media_path or job.resolved_media_path
        thumb_path = MediaProcessor.extract_thumbnail(video_path, job.id)

        if thumb_path:
            cls._broadcast_photo(thumb_path, msg)
            MediaProcessor.cleanup_thumbnail(thumb_path)
        else:
            cls._broadcast(msg)

    @classmethod
    def notify_job_failed(cls, job, error: str = ""):
        """Thông báo khi job thất bại (hết retry)."""
        cls._broadcast(nf.job_failed_message(job, error))

    @classmethod
    def notify_draft_ready(cls, job):
        """Thông báo khi AI Caption hoàn thành, kèm nút Approve/Cancel."""
        msg = nf.draft_ready_message(job)
        buttons = nf.draft_ready_buttons(job)

        video_path = job.resolved_processed_media_path or job.resolved_media_path
        sent_video = False
        if video_path and os.path.exists(video_path):
            try:
                if MediaProcessor.telegram_video_within_size_limit(video_path):
                    cls._broadcast_video(video_path, msg, buttons)
                    sent_video = True
                else:
                    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                    logger.warning("NotifierService: Video %.1fMB exceeds 50MB Telegram limit.", file_size_mb)
            except Exception as e:
                logger.warning("NotifierService: Video send failed (%s), falling back to text.", e)
        if not sent_video:
            cls._broadcast_with_buttons(msg, buttons)

    @classmethod
    def notify_style_selection(cls, job):
        """Thông báo khi video viral mới được bốc về, yêu cầu user chọn style Caption."""
        msg = nf.style_selection_message(job)
        buttons = nf.style_selection_buttons(job)

        video_path = job.resolved_processed_media_path or job.resolved_media_path
        sent_video = False
        if video_path and os.path.exists(video_path):
            try:
                if MediaProcessor.telegram_video_within_size_limit(video_path):
                    cls._broadcast_video(video_path, msg, buttons)
                    sent_video = True
                else:
                    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                    logger.warning("NotifierService: Video %.1fMB exceeds 50MB Telegram limit.", file_size_mb)
            except Exception as e:
                logger.warning("NotifierService: Video send failed (%s), falling back to text.", e)
        if not sent_video:
            cls._broadcast_with_buttons(msg, buttons)

    @classmethod
    def notify_account_invalid(cls, account_name: str, reason: str = ""):
        """Thông báo khi account bị vô hiệu hóa."""
        cls._broadcast(nf.account_invalid_message(account_name, reason))

    @classmethod
    def notify_worker_down(cls):
        """Thông báo khi worker không phản hồi."""
        cls._broadcast(nf.worker_down_message())

    @classmethod
    def notify_daily_summary(cls, db):
        """Báo cáo tổng hợp cuối ngày — số job theo trạng thái + metrics."""
        import time as time_mod
        from app.database.models import Job

        now = int(time_mod.time())
        since = now - 86400  # 24 hours ago

        recent = db.query(Job).filter(Job.created_at >= since).all()

        done = sum(1 for j in recent if j.status == JobStatus.DONE)
        failed = sum(1 for j in recent if j.status == JobStatus.FAILED)
        pending = sum(1 for j in recent if j.status == JobStatus.PENDING)
        draft = sum(1 for j in recent if j.status == JobStatus.DRAFT)
        running = sum(1 for j in recent if j.status == JobStatus.RUNNING)
        total = len(recent)

        total_views = sum(j.view_24h or 0 for j in recent if j.status == JobStatus.DONE)
        total_clicks = sum(j.click_count or 0 for j in recent if j.status == JobStatus.DONE)

        cls._broadcast(nf.daily_summary_message(
            done, failed, pending, draft, running, total, total_views, total_clicks,
        ))
