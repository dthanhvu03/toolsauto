"""HTML/Telegram message bodies for NotifierService (tách khỏi facade)."""
import html as html_mod
from typing import Optional


def job_done_message(job, post_url: Optional[str]) -> str:
    caption_text = html_mod.escape((job.caption or "N/A").strip())
    account_name = html_mod.escape(job.account.name if job.account else "Unknown")
    link_line = f"\n🔗 <a href=\"{post_url}\">{html_mod.escape(post_url)}</a>" if post_url else ""

    return (
        f"✅ <b>Đăng thành công!</b>\n"
        f"📋 Job #{job.id} | {job.platform} ({account_name})\n"
        f"📝 <i>{caption_text}</i>{link_line}\n"
        f"⏰ Tries: {job.tries}/{job.max_tries}"
    )


def job_failed_message(job, error: str) -> str:
    account_name = html_mod.escape(job.account.name if job.account else "Unknown")
    error_preview = html_mod.escape((error or job.last_error or "Unknown")[:100])

    return (
        f"❌ <b>Đăng thất bại!</b>\n"
        f"📋 Job #{job.id} | {job.platform} ({account_name})\n"
        f"⚠️ {error_preview}\n"
        f"🔄 Tries: {job.tries}/{job.max_tries}"
    )


def draft_ready_message(job) -> str:
    caption_preview = html_mod.escape((job.caption or "").strip())
    account_name = html_mod.escape(job.account.name if job.account else "Unknown")

    keywords_str = ""
    if hasattr(job, "_ai_keywords") and job._ai_keywords:
        kw_escaped = html_mod.escape(", ".join(job._ai_keywords))
        keywords_str = f"🔑 <b>SEO Keywords:</b> <i>{kw_escaped}</i>\n\n"

    return (
        f"📝 <b>AI Caption sẵn sàng — Chờ duyệt!</b>\n"
        f"📋 Job #{job.id} | {job.platform} ({account_name})\n\n"
        f"{keywords_str}"
        f"✍️ <i>{caption_preview}</i>\n"
    )


def draft_ready_buttons(job) -> list:
    return [[
        {"text": "✅ Approve", "callback_data": f"approve:{job.id}"},
        {"text": "❌ Cancel", "callback_data": f"cancel:{job.id}"},
    ]]


def style_selection_message(job) -> str:
    account_name = html_mod.escape(job.account.name if job.account else "Unknown")

    return (
        f"🎬 <b>Video mới đã sẵn sàng!</b>\n"
        f"📋 Job #{job.id} | {job.platform} ({account_name})\n\n"
        f"🤖 Bạn muốn AI viết Caption theo phong cách nào?\n"
        f"<i>(Nếu không chọn, AI sẽ tự động viết kiểu NGẮN GỌN sau 30 phút)</i>"
    )


def style_selection_buttons(job) -> list:
    return [
        [
            {"text": "💰 Bán hàng (Sales)", "callback_data": f"style_sales:{job.id}"},
            {"text": "⚡ Ngắn gọn (Short)", "callback_data": f"style_short:{job.id}"},
        ],
        [
            {"text": "☕ Đời thường (Daily)", "callback_data": f"style_daily:{job.id}"},
            {"text": "😂 Hài hước (Humor)", "callback_data": f"style_humor:{job.id}"},
        ],
        [
            {"text": "⏭️ Bỏ qua (Skip AI)", "callback_data": f"style_skip:{job.id}"},
        ],
    ]


def account_invalid_message(account_name: str, reason: str) -> str:
    return (
        f"🔴 <b>Account bị vô hiệu!</b>\n"
        f"👤 {html_mod.escape(account_name)}\n"
        f"⚠️ {html_mod.escape(reason[:150])}"
    )


def worker_down_message() -> str:
    return "⚠️ <b>Worker không phản hồi!</b>\nHeartbeat quá hạn. Kiểm tra hệ thống!"


def daily_summary_message(
    done: int,
    failed: int,
    pending: int,
    draft: int,
    running: int,
    total: int,
    total_views: int,
    total_clicks: int,
) -> str:
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

    return msg
