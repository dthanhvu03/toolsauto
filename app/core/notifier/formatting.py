"""HTML/Telegram message bodies for NotifierService (tách khỏi facade)."""
import html as html_mod
import os
import re
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
    msg += "━━━━━━━━━━━━━━━━━━\n"
    msg += f"📈 Tổng: <b>{total}</b> jobs"

    if total_views or total_clicks:
        msg += f"\n👁 Views: <b>{total_views:,}</b>"
        msg += f"\n🔗 Clicks: <b>{total_clicks:,}</b>"

    return msg


# ─────────── ADR-022: hai luồng KHÔNG sinh Job (material READY, caption AI) ───────────
#
# Mọi tin nhắn ở đây đi qua ``TelegramClient`` với ``parse_mode="HTML"`` (mặc định của
# ``send_message`` / ``send_video``), nên MỌI đoạn chữ do người khác viết — tiêu đề video
# bốc từ TikTok/YouTube, caption AI sinh ra, thông báo lỗi — đều phải qua
# ``html_mod.escape``; thiếu một chỗ là Telegram trả 400 và tin nhắn biến mất.

# Bóc ``[AI_GENERATE]`` và mọi cụm ``### … ###`` (ORIGINAL_VIRAL_TITLE, BOOST_CONTEXT…).
# Chép lại 3 dòng thay vì import ``_clean_title_for_context`` của
# ``app.features.viral_intake.service``: contract ``core-isolated`` (import-linter) cấm
# ``app.core`` biết tới ``app.features``.
_MARKER_BLOCK_RE = re.compile(r"\s*###.*?###\s*", re.DOTALL)
_AI_GENERATE_RE = re.compile(r"\[AI_GENERATE\]", re.IGNORECASE)


def _clean_material_title(title: Optional[str]) -> str:
    text = _AI_GENERATE_RE.sub(" ", title or "")
    text = _MARKER_BLOCK_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _mmss(seconds) -> str:
    """Giây → ``m:ss``. Dùng chung cho độ dài và mốc cắt (ADR-035)."""
    total = int(seconds or 0)
    return f"{total // 60}:{total % 60:02d}"


def material_caption_block(mat) -> str:
    """
    ADR-027 — caption + hashtag trong **một khối ``<code>``**: trên Telegram chạm vào là
    copy cả cụm, dán thẳng sang Facebook. Không có caption ⇒ chuỗi rỗng.

    Cố ý gộp caption và hashtag vào **cùng một khối**: tách hai khối thì Owner phải chạm
    hai lần rồi tự ghép, mất đúng cái tiện mà ADR này sinh ra để có.
    """
    caption = (getattr(mat, "ai_caption", None) or "").strip()
    if not caption:
        return ""
    hashtags = " ".join(getattr(mat, "ai_hashtags_list", None) or [])
    body = f"{caption}\n\n{hashtags}" if hashtags else caption
    return (
        f"✍️ <b>Caption</b> — chạm vào để chép:\n"
        f"<code>{html_mod.escape(body)}</code>"
    )


def material_ready_buttons(mat) -> list:
    """ADR-042: nút dưới tin video sẵn sàng. ``callback_data`` do ``telegram_bot`` xử lý."""
    mid = getattr(mat, "id", None)
    if not mid:
        return []
    return [[{"text": "✅ Đã đăng", "callback_data": f"dadang:{mid}"}]]


def material_ready_message(
    mat,
    media_path: Optional[str] = None,
    *,
    with_caption: bool = True,
    drive_path: Optional[str] = None,
    duration: Optional[float] = None,
    source_duration: Optional[float] = None,
) -> str:
    """
    ADR-018 + ADR-022 + ADR-027: video reup xong, không có account ⇒ Owner đăng tay.

    ``with_caption=False`` dùng khi tin quá dài phải tách: phần đầu đi kèm video, khối
    caption đi ở tin thứ hai (xem ``NotifierService.notify_material_ready``).

    ``drive_path`` (ADR-030) là **vị trí trong Drive**, KHÔNG phải link bấm được — Drive for
    Desktop chỉ gắn ổ đĩa nên tool không biết link ``drive.google.com``. Nhãn trong tin phải
    nói đúng thứ nó là; hứa "link" rồi đưa ra chữ không bấm được là nhãn nói dối (ADR-023).
    """
    title = _clean_material_title(getattr(mat, "title", None)) or "(không có tiêu đề)"
    platform = str(getattr(mat, "platform", "") or "—")
    views = int(getattr(mat, "views", 0) or 0)
    file_name = os.path.basename(str(media_path)) if media_path else ""
    file_line = f"📁 <code>{html_mod.escape(file_name)}</code>\n" if file_name else ""

    drive_line = (
        f"📂 Trong Drive: <code>{html_mod.escape(str(drive_path))}</code>\n" if drive_path else ""
    )
    # ADR-035: Owner nhận video mà không biết dài bao nhiêu, cắt từ đâu — phải mở ra xem mới
    # biết, đúng việc ADR-032 vừa bỏ công loại bỏ.
    length_line = ""
    if duration:
        start = int(getattr(mat, "clip_start_sec", None) or 0)
        goc = f" (gốc {_mmss(source_duration)})" if source_duration else ""
        length_line = f"⏱ Dài {_mmss(duration)} · cắt từ {_mmss(start) if start else 'đầu'}{goc}\n"
        # 2026-09-11 Owner hỏi "sao tự cắt vậy": tin nói cắt mà không nói VÌ SAO và chỉnh Ở ĐÂU.
        # Cắt theo số chung (không đặt độ dài riêng) và ngắn hơn gốc rõ rệt ⇒ chỉ đường ngay.
        if source_duration and not getattr(mat, "clip_length_sec", None) and source_duration > duration + 2:
            length_line += "   ↳ cắt theo Thiết lập « Độ dài tối đa » — đặt 0 ở đó nếu muốn giữ nguyên video\n"
    # ADR-041: phần con của video đã chia — Owner đăng theo thứ tự nên phải thấy ngay "phần mấy".
    part_line = ""
    if getattr(mat, "parent_material_id", None) and getattr(mat, "part_index", None):
        part_line = (
            f"🧩 <b>Phần {mat.part_index}/{getattr(mat, 'part_total', '?')}</b>"
            f" của video #{mat.parent_material_id}\n"
        )
    head = (
        f"🎬 <b>Video sẵn sàng đăng tay</b>\n"
        f"{part_line}"
        f"📋 Material #{getattr(mat, 'id', '?')} | {html_mod.escape(platform)}\n"
        f"📝 <i>{html_mod.escape(title)}</i>\n"
        f"👁 {views:,} lượt xem\n"
        f"{length_line}"
        f"{file_line}"
        f"{drive_line}"
    )
    if not with_caption:
        return head.rstrip("\n")

    block = material_caption_block(mat)
    if block:
        # File đã đính kèm ngay trong tin này nên không nhắc mở web nữa.
        return f"{head}\n{block}"

    reason = (getattr(mat, "ai_caption_error", None) or "").strip()
    if reason:
        return f"{head}⚠️ Chưa có caption: {html_mod.escape(reason[:200])}"
    return f"{head}⬇️ Mở <b>/app/viral</b> rồi bấm <b>Tải file</b> để tải video về đăng."


def caption_ready_message(mat) -> str:
    """ADR-021 + ADR-022: AI viết caption xong cho material — hoặc báo vì sao không viết được."""
    caption = (getattr(mat, "ai_caption", None) or "").strip()
    if not caption:
        reason = (getattr(mat, "ai_caption_error", None) or "Không rõ lý do").strip()
        return (
            f"⚠️ <b>Viết caption thất bại</b>\n"
            f"📋 Material #{getattr(mat, 'id', '?')}\n"
            f"❌ {html_mod.escape(reason[:200])}"
        )

    hashtags = " ".join(getattr(mat, "ai_hashtags_list", None) or [])
    hashtag_line = f"\n🏷 {html_mod.escape(hashtags)}" if hashtags else ""

    return (
        f"✍️ <b>Caption đã viết xong</b>\n"
        f"📋 Material #{getattr(mat, 'id', '?')}\n\n"
        f"<i>{html_mod.escape(caption)}</i>{hashtag_line}\n\n"
        f"🔖 Mở <b>/app/viral</b> rồi bấm <b>Sao chép</b> để lấy caption."
    )
