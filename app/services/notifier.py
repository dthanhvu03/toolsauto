"""
Notifier Service — Gửi thông báo qua các kênh khác nhau (Telegram, Email, Webhook...).

Kiến trúc:
    TelegramClient  → Low-level API wrapper (telegram_client.py)
    TelegramNotifier → Channel adapter (kế thừa BaseNotifier)
    NotifierService  → Facade (gọi tất cả channels)

Dùng:
    from app.services.notifier import NotifierService
    NotifierService.notify_job_done(job)
    NotifierService.notify_job_failed(job, "Login expired")
    NotifierService.notify_draft_ready(job)
"""
import os
import subprocess
import logging
import tempfile
import html as html_mod
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Base Notifier (mở rộng kênh mới kế thừa class này)
# ─────────────────────────────────────────────
class BaseNotifier(ABC):
    """Interface cho mọi notification channel."""

    @abstractmethod
    def send(self, message: str) -> bool:
        """Gửi tin nhắn text. Trả True nếu thành công."""
        ...

    def send_photo(self, photo_path: str, caption: str) -> bool:
        """Gửi ảnh + caption. Default: fallback to text."""
        return self.send(caption)

    def send_with_buttons(self, message: str, buttons: list) -> bool:
        """Gửi text + inline buttons. Default: fallback to text."""
        return self.send(message)

    def send_video(self, video_path: str, caption: str = "", buttons: Optional[list] = None) -> bool:
        """Gửi video + caption. Default: fallback to text+buttons."""
        if buttons:
            return self.send_with_buttons(caption, buttons)
        return self.send(caption)


# ─────────────────────────────────────────────
# Telegram Channel (dùng TelegramClient)
# ─────────────────────────────────────────────
class TelegramNotifier(BaseNotifier):
    """Gửi tin nhắn qua Telegram Bot API dùng TelegramClient."""

    def __init__(self, bot_token: str, chat_id: str):
        from app.services.telegram_client import TelegramClient
        self.client = TelegramClient(bot_token, chat_id)

    def send(self, message: str) -> bool:
        result = self.client.send_message(message)
        return result is not None

    def send_photo(self, photo_path: str, caption: str) -> bool:
        result = self.client.send_photo(photo_path, caption)
        return result is not None

    def send_with_buttons(self, message: str, buttons: list) -> bool:
        """buttons = [[{"text": "Label", "callback_data": "action:id"}, ...]]"""
        reply_markup = {"inline_keyboard": buttons}
        result = self.client.send_message(message, reply_markup=reply_markup)
        return result is not None

    def send_video(self, video_path: str, caption: str = "", buttons: Optional[list] = None) -> bool:
        reply_markup = {"inline_keyboard": buttons} if buttons else None
        result = self.client.send_video(video_path, caption, reply_markup=reply_markup)
        return result is not None


# ─────────────────────────────────────────────
# Thumbnail Helper
# ─────────────────────────────────────────────
def _extract_thumbnail(video_path: str, job_id: int) -> Optional[str]:
    """
    Extract 1 frame từ video bằng FFmpeg → trả path tới ảnh JPEG.
    Trả None nếu thất bại (caller sẽ fallback text-only).
    """
    if not video_path or not os.path.exists(video_path):
        return None

    thumb_path = os.path.join(tempfile.gettempdir(), f"thumb_{job_id}.jpg")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", "00:00:01",
            "-frames:v", "1",
            "-q:v", "5",
            thumb_path,
        ]
        subprocess.run(
            cmd, capture_output=True, timeout=10,
            check=True,
        )
        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            return thumb_path
    except Exception as e:
        logger.debug("Thumbnail extraction failed for job %s: %s", job_id, e)

    return None


def _cleanup_thumbnail(thumb_path: Optional[str]):
    """Xóa thumbnail tạm sau khi đã gửi."""
    if thumb_path and os.path.exists(thumb_path):
        try:
            os.remove(thumb_path)
        except OSError:
            pass


# ─────────────────────────────────────────────
# Notifier Service (Facade — gọi tất cả channels)
# ─────────────────────────────────────────────
class NotifierService:
    """Facade gửi thông báo qua tất cả channels đã đăng ký."""

    _channels: list[BaseNotifier] = []

    @classmethod
    def register(cls, channel: BaseNotifier):
        """Đăng ký thêm 1 notification channel."""
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

    # ─── Convenience Methods cho Worker ───

    @classmethod
    def notify_job_done(cls, job, post_url: Optional[str] = None):
        """Thông báo khi job publish thành công (có thumbnail nếu là video)."""
        caption_text = html_mod.escape((job.caption or "N/A").strip())
        account_name = html_mod.escape(job.account.name if job.account else "Unknown")
        link_line = f"\n🔗 <a href=\"{post_url}\">{html_mod.escape(post_url)}</a>" if post_url else ""

        msg = (
            f"✅ <b>Đăng thành công!</b>\n"
            f"📋 Job #{job.id} | {job.platform} ({account_name})\n"
            f"📝 <i>{caption_text}</i>{link_line}\n"
            f"⏰ Tries: {job.tries}/{job.max_tries}"
        )

        # Try thumbnail cho video
        video_path = job.processed_media_path or job.media_path
        thumb_path = _extract_thumbnail(video_path, job.id)

        if thumb_path:
            cls._broadcast_photo(thumb_path, msg)
            _cleanup_thumbnail(thumb_path)
        else:
            cls._broadcast(msg)

    @classmethod
    def notify_job_failed(cls, job, error: str = ""):
        """Thông báo khi job thất bại (hết retry)."""
        account_name = html_mod.escape(job.account.name if job.account else "Unknown")
        error_preview = html_mod.escape((error or job.last_error or "Unknown")[:100])

        msg = (
            f"❌ <b>Đăng thất bại!</b>\n"
            f"📋 Job #{job.id} | {job.platform} ({account_name})\n"
            f"⚠️ {error_preview}\n"
            f"🔄 Tries: {job.tries}/{job.max_tries}"
        )
        cls._broadcast(msg)

    @classmethod
    def notify_draft_ready(cls, job):
        """Thông báo khi AI Caption hoàn thành, kèm nút Approve/Cancel."""
        caption_preview = html_mod.escape((job.caption or "").strip())
        account_name = html_mod.escape(job.account.name if job.account else "Unknown")

        # Hiển thị keyword SEO nếu có
        keywords_str = ""
        if hasattr(job, '_ai_keywords') and job._ai_keywords:
            kw_escaped = html_mod.escape(", ".join(job._ai_keywords))
            keywords_str = f"🔑 <b>SEO Keywords:</b> <i>{kw_escaped}</i>\n\n"

        msg = (
            f"📝 <b>AI Caption sẵn sàng — Chờ duyệt!</b>\n"
            f"📋 Job #{job.id} | {job.platform} ({account_name})\n\n"
            f"{keywords_str}"
            f"✍️ <i>{caption_preview}</i>\n"
        )

        buttons = [[
            {"text": "✅ Approve", "callback_data": f"approve:{job.id}"},
            {"text": "❌ Cancel", "callback_data": f"cancel:{job.id}"},
        ]]
        
        video_path = job.processed_media_path or job.media_path
        if video_path and os.path.exists(video_path):
            cls._broadcast_video(video_path, msg, buttons)
        else:
            cls._broadcast_with_buttons(msg, buttons)

    @classmethod
    def notify_style_selection(cls, job):
        """Thông báo khi video viral mới được bốc về, yêu cầu user chọn style Caption."""
        account_name = html_mod.escape(job.account.name if job.account else "Unknown")
        
        msg = (
            f"🎬 <b>Video mới đã sẵn sàng!</b>\n"
            f"📋 Job #{job.id} | {job.platform} ({account_name})\n\n"
            f"🤖 Bạn muốn AI viết Caption theo phong cách nào?\n"
            f"<i>(Nếu không chọn, AI sẽ tự động viết kiểu NGẮN GỌN sau 30 phút)</i>"
        )
        
        buttons = [
            [
                {"text": "💰 Bán hàng (Sales)", "callback_data": f"style_sales:{job.id}"},
                {"text": "⚡ Ngắn gọn (Short)", "callback_data": f"style_short:{job.id}"}
            ],
            [
                {"text": "☕ Đời thường (Daily)", "callback_data": f"style_daily:{job.id}"},
                {"text": "😂 Hài hước (Humor)", "callback_data": f"style_humor:{job.id}"}
            ],
            [
                {"text": "⏭️ Bỏ qua (Skip AI)", "callback_data": f"style_skip:{job.id}"}
            ]
        ]
        
        video_path = job.processed_media_path or job.media_path
        if video_path and os.path.exists(video_path):
            cls._broadcast_video(video_path, msg, buttons)
        else:
            cls._broadcast_with_buttons(msg, buttons)

    @classmethod
    def notify_account_invalid(cls, account_name: str, reason: str = ""):
        """Thông báo khi account bị vô hiệu hóa."""
        msg = (
            f"🔴 <b>Account bị vô hiệu!</b>\n"
            f"👤 {html_mod.escape(account_name)}\n"
            f"⚠️ {html_mod.escape(reason[:150])}"
        )
        cls._broadcast(msg)

    @classmethod
    def notify_worker_down(cls):
        """Thông báo khi worker không phản hồi."""
        msg = "⚠️ <b>Worker không phản hồi!</b>\nHeartbeat quá hạn. Kiểm tra hệ thống!"
        cls._broadcast(msg)

    @classmethod
    def notify_daily_summary(cls, db):
        """Báo cáo tổng hợp cuối ngày — số job theo trạng thái + metrics."""
        import time as time_mod
        from app.database.models import Job

        now = int(time_mod.time())
        since = now - 86400  # 24 hours ago

        # Query last 24h jobs
        recent = db.query(Job).filter(Job.created_at >= since).all()

        done = sum(1 for j in recent if j.status == "DONE")
        failed = sum(1 for j in recent if j.status == "FAILED")
        pending = sum(1 for j in recent if j.status == "PENDING")
        draft = sum(1 for j in recent if j.status == "DRAFT")
        running = sum(1 for j in recent if j.status == "RUNNING")
        total = len(recent)

        # Metrics from DONE jobs
        total_views = sum(j.view_24h or 0 for j in recent if j.status == "DONE")
        total_clicks = sum(j.click_count or 0 for j in recent if j.status == "DONE")

        msg = (
            f"📊 <b>Báo cáo ngày</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✅ Thành công: <b>{done}</b>\n"
            f"❌ Thất bại: <b>{failed}</b>\n"
            f"⏳ Đang chờ: <b>{pending}</b>\n"
            f"📝 Draft: <b>{draft}</b>\n"
        )
        if running:
            msg += f"🔄 Đang chạy: <b>{running}</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        msg += f"📈 Tổng: <b>{total}</b> jobs"

        if total_views or total_clicks:
            msg += f"\n👁 Views: <b>{total_views:,}</b>"
            msg += f"\n🔗 Clicks: <b>{total_clicks:,}</b>"

        cls._broadcast(msg)

