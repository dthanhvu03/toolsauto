"""Màn /admin → 📋 Điều khoản (PLAN-077).

Xem các phiên bản điều khoản, đọc từng mục, tạo bản nháp từ mẫu V1 (`terms_content`), công bố bản nháp sau khi
xác nhận đúng hash nội dung đã xem. Công bố là quyết định của chủ bot: không bắt khách đồng ý, không gửi tin
hàng loạt; khách thấy ở /dieukien. Không có nút sửa bản đã công bố.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cashback_bot import terms
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.terms_content import DRAFT_SECTIONS, DRAFT_TITLE, DRAFT_VERSION

ICT = ZoneInfo("Asia/Ho_Chi_Minh")
HOME = "c:tm:home"
BACK_MENU = (("◀️ Tổng quan", "c:menu:home"),)
BACK_HOME = (("◀️ Điều khoản", HOME),)
STATUS_LABELS = {"DRAFT": "📝 Bản nháp", "PUBLISHED": "🟢 Đang công bố", "SUPERSEDED": "⚪ Đã thay"}
_VERSION = re.compile(r"^c:tm:v:(\d{1,9})$")
_SECTION = re.compile(r"^c:tm:s:(\d{1,9}):(\d{1,2})$")
_PUBLISH = re.compile(r"^c:tm:pub:(\d{1,9})(?::([0-9a-f]{12}):ok)?$")


def _vn(stamp: str | None) -> str:
    if not stamp:
        return "-"
    moment = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return moment.astimezone(ICT).strftime("%H:%M %d/%m/%Y")


class TermsAdmin:
    def __init__(self, repo: TrackingRepository, audit=None):
        self.repo = repo
        self.audit = audit

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == HOME:
            return self._home(now)
        if data == "c:tm:new":
            return self._new_draft(admin_id, now)
        if (matched := _VERSION.fullmatch(data)) is not None:
            return self._version(int(matched.group(1)))
        if (matched := _SECTION.fullmatch(data)) is not None:
            return self._section(int(matched.group(1)), int(matched.group(2)))
        if (matched := _PUBLISH.fullmatch(data)) is not None:
            return self._publish(admin_id, int(matched.group(1)), matched.group(2), now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=(BACK_HOME,))

    def _home(self, now: datetime, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            items = terms.versions(conn)
            live = terms.current(conn, now)
            accepted = (
                0 if live is None else int(conn.execute(
                    "SELECT COUNT(*) FROM customer_terms_acceptances WHERE terms_version_id = ?", (live.id,)
                ).fetchone()[0])
            )
            users = int(conn.execute("SELECT COUNT(*) FROM telegram_users").fetchone()[0])
        lines = ["⚙️ Quản trị › <b>Điều khoản &amp; phiên bản</b>", ""]
        if notice:
            lines += [notice, ""]
        if live is None:
            lines += [
                "🟡 <b>Chưa có điều khoản công bố.</b> Khách đang thấy trang /dieukien cũ (chữ cố định).",
            ]
        else:
            lines += [
                f"🟢 Đang công bố: <b>{html.escape(live.version)}</b> từ {_vn(live.effective_from)}",
                f"• Khách đã đồng ý: <b>{accepted}</b>/{users}",
            ]
        lines += [
            "• Bắt buộc đồng ý trước khi tạo link: <b>Tắt</b> (cờ <code>CASHBACK_TERMS_REQUIRED</code>, chờ chủ bot duyệt)",
            "",
            "<b>Phiên bản</b>",
        ]
        lines += [f"• #{item.id} {html.escape(item.version)} · {STATUS_LABELS[item.status]}" for item in items] or ["• Chưa có"]
        lines += [
            "",
            "ⓘ Bản đã công bố không sửa được; đổi nội dung thì tạo phiên bản mới. Công bố không gửi tin cho khách "
            "và không tự ghi ai đã đồng ý.",
        ]
        rows = [((f"👁 #{item.id} {item.version} · {STATUS_LABELS[item.status]}", f"c:tm:v:{item.id}"),) for item in items[:6]]
        if not any(item.version == DRAFT_VERSION for item in items):
            rows.insert(0, ((f"📝 Tạo bản nháp {DRAFT_VERSION} từ mẫu", "c:tm:new"),))
        return BotReply("\n".join(lines), inline_keyboard=(*rows, BACK_MENU))

    def _new_draft(self, admin_id: int, now: datetime) -> BotReply:
        try:
            with self.repo.connect() as conn:
                version_id = terms.create_draft(conn, DRAFT_VERSION, DRAFT_TITLE, DRAFT_SECTIONS, f"admin:{admin_id}", now)
        except terms.TermsError:
            return self._home(now, "⚠️ Đã có phiên bản này.")
        if self.audit:
            self.audit(admin_id, "terms_draft", None, {"id": version_id, "version": DRAFT_VERSION}, now)
        return self._version(version_id, f"📝 Đã tạo bản nháp {DRAFT_VERSION}. Khách chưa thấy bản nháp.")

    def _version(self, version_id: int, notice: str = "") -> BotReply:
        with self.repo.connect() as conn:
            item = terms.get(conn, version_id)
        if item is None:
            return BotReply("Không thấy phiên bản này.", inline_keyboard=(BACK_HOME,))
        lines = [f"⚙️ Quản trị › Điều khoản › <b>{html.escape(item.version)}</b>", ""]
        if notice:
            lines += [notice, ""]
        lines += [
            f"{html.escape(item.title)}",
            f"Trạng thái: {STATUS_LABELS[item.status]}",
            f"Tạo: {_vn(item.created_at)}" + (f" · công bố: {_vn(item.published_at)} bởi {html.escape(item.approved_by or '-')}" if item.published_at else ""),
            f"Mã nội dung: <code>{item.content_hash[:12]}</code>",
            "",
            "Bấm từng mục để đọc đúng chữ khách sẽ thấy.",
        ]
        rows = [((label, f"c:tm:s:{item.id}:{index}"),) for index, (_key, label, _body) in enumerate(item.sections)]
        if item.status == terms.DRAFT:
            rows.append((("🟢 Công bố phiên bản này…", f"c:tm:pub:{item.id}"),))
        return BotReply("\n".join(lines), inline_keyboard=(*rows, BACK_HOME))

    def _section(self, version_id: int, index: int) -> BotReply:
        with self.repo.connect() as conn:
            item = terms.get(conn, version_id)
        if item is None or not 0 <= index < len(item.sections):
            return BotReply("Không thấy mục này.", inline_keyboard=(BACK_HOME,))
        _key, label, body = item.sections[index]
        text = f"<b>{html.escape(label)}</b> · {html.escape(item.version)} ({STATUS_LABELS[item.status]})\n\n{body}"
        return BotReply(text, inline_keyboard=((("◀️ " + item.version, f"c:tm:v:{item.id}"),),))

    def _publish(self, admin_id: int, version_id: int, short_hash: str | None, now: datetime) -> BotReply:
        with self.repo.connect() as conn:
            item = terms.get(conn, version_id)
        if item is None or item.status != terms.DRAFT:
            return self._home(now, "⚠️ Chỉ công bố được bản nháp.")
        if short_hash is None:
            text = (
                f"⚙️ Quản trị › Điều khoản › <b>Công bố {html.escape(item.version)}</b>\n\n"
                f"Mã nội dung: <code>{item.content_hash[:12]}</code>\n\n"
                "• Khách thấy bản này ở /dieukien ngay khi công bố; bản đang công bố (nếu có) thành «Đã thay».\n"
                "• Không gửi tin cho khách, không tự ghi ai đã đồng ý; khách tự bấm đồng ý.\n"
                "• Không bật bắt buộc đồng ý trước khi tạo link.\n"
                "• Sau khi công bố, nội dung không sửa được.\n\n"
                "Chỉ công bố khi chủ bot đã đọc và duyệt toàn bộ nội dung."
            )
            keyboard = (
                (("✅ Tôi đã duyệt, công bố", f"c:tm:pub:{item.id}:{item.content_hash[:12]}:ok"),),
                (("◀️ Chưa, quay lại", f"c:tm:v:{item.id}"),),
            )
            return BotReply(text, inline_keyboard=keyboard)
        if short_hash != item.content_hash[:12]:
            return self._version(version_id, "⚠️ Nội dung đã đổi so với lúc xem. Đọc lại rồi công bố.")
        try:
            with self.repo.connect() as conn:
                published = terms.publish(conn, version_id, item.content_hash, f"admin:{admin_id}", now)
        except terms.TermsError:
            return self._home(now, "⚠️ Không công bố được. Mở lại phiên bản để kiểm tra.")
        if self.audit:
            self.audit(admin_id, "terms_publish", None, {"id": published.id, "version": published.version, "hash": published.content_hash[:12]}, now)
        return self._home(now, f"🟢 Đã công bố {html.escape(published.version)}. Khách thấy ở /dieukien.")
