"""Màn /admin → 👛 Ví khách (PLAN-066): bật ví, cài đặt, thành viên, duyệt yêu cầu rút."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from cashback_bot.admin_ui import (
    WALLET_ADMIN_BACK,
    WALLET_ENABLE_CONFIRM,
    WALLET_ENABLE_KEYBOARD,
    PAYOUT_STATUS,
    STEP_CODES,
    payout_keyboard,
    payout_step_text,
    payout_text,
    wallet_admin_keyboard,
    wallet_admin_text,
    wallet_member_text,
    wallet_members_keyboard,
    wallet_members_text,
    wallet_settings_keyboard,
    wallet_settings_text,
)
from cashback_bot import payout_readiness, payouts
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply, payout_notice
from cashback_bot.money import format_vnd
from cashback_bot.payout_gate import PayoutBlocked
from cashback_bot.vietqr import VietQRError, build_payload, qr_png
from cashback_bot.wallet import BANKS, HOLD_DAY_CHOICES, KEY_ENABLED, MIN_WITHDRAW_CHOICES, Wallet

_PAYOUT = re.compile(r"^c:wl:rq:(\d{1,9})$")
_STEP = re.compile(r"^c:wl:mv:(\d{1,9}):(\d{1,6}):(rv|ap|pr|se|pd|rj|ca|fl|nr|rt)(:ok)?$")
_VERIFY = re.compile(r"^c:wl:vb:(\d{1,9})$")
WAIT_TTL = timedelta(minutes=10)
# Bước cần admin gõ thêm: (mô tả ô nhập, cần lý do, cần chứng từ).
_TEXT_STEPS = {
    "rejected": "lý do từ chối (khách sẽ thấy)",
    "cancelled": "lý do huỷ (khách sẽ thấy)",
    "needs_review": "lý do cần xử lý",
    "failed": "lý do kèm mã/tham chiếu ngân hàng xác nhận lệnh không thực hiện",
    "paid_confirmed": "mã giao dịch ngân hàng trên biên nhận / sao kê",
    "returned": "lý do kèm chứng từ ngân hàng hoàn tiền",
}
_ERRORS = {
    "stale": "Nút đã cũ (yêu cầu vừa đổi trạng thái). Mở lại chi tiết.",
    "transition": "Không chuyển được từ trạng thái hiện tại.",
    "reason": "Cần lý do.",
    "evidence": "Cần chứng từ (mã giao dịch / tham chiếu ngân hàng, ít nhất 4 ký tự).",
    "money_may_have_left": "Đã từng gửi lệnh chuyển: không từ chối / huỷ được. Dùng «Chuyển thất bại» kèm chứng từ, "
                           "hoặc xác nhận đã trả.",
    "locked": "Còn khoá tài chính.",
    "terms": "Khách chưa đồng ý điều khoản chi trả.",
    "bank_verified": "Tài khoản người nhận chưa xác minh.",
    "fund": "Quỹ có chứng từ không đủ.",
    "limits": "Vượt hạn mức hoặc hạn mức chưa duyệt.",
    "not_found": "Không tìm thấy yêu cầu này.",
}
_MEMBER = re.compile(r"^c:wl:u:(\d+)$")
_HOLD = re.compile(r"^c:wl:hold:(\d+)$")
_MIN = re.compile(r"^c:wl:min:(\d+)$")
_LIMIT = re.compile(r"^c:wl:lim:(req|day|month):(\d+)$")
_LIMIT_FIELDS = {"req": "max_per_request_vnd", "day": "daily_total_vnd", "month": "monthly_total_vnd"}

# (admin, action, trước, sau, lúc): ghi vào admin_change_audit để màn 📊 Lịch sử thấy.
AuditFn = Callable[[int, str, dict | None, dict | None, datetime], None]


class WalletAdmin:
    def __init__(self, repo: TrackingRepository, audit: AuditFn | None = None, waiting: dict | None = None):
        self.repo = repo
        self.wallet = Wallet(repo)
        self.audit = audit
        # admin_id → (việc, payout_id, version, đích, hạn). Chờ admin gõ lý do / chứng từ, trong RAM.
        self.waiting = {} if waiting is None else waiting

    def _log(self, admin_id: int, action: str, before: dict | None, after: dict | None, now: datetime) -> None:
        if self.audit is not None and before != after:
            self.audit(admin_id, action, before, after, now)

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == "c:menu:wallet":
            return self.screen()
        if data in ("c:wl:on", "c:wl:on:ok") and self.wallet.settings().locked_reasons:
            # Khoá tài chính (hardening V1): nút cũ hay callback gõ tay đều không bật được.
            return self.screen("🔒 Chưa bật được ví: còn khoá tài chính (xem lý do bên dưới).")
        if data == "c:wl:on":
            return BotReply(WALLET_ENABLE_CONFIRM, inline_keyboard=WALLET_ENABLE_KEYBOARD)
        if data == "c:wl:on:ok":
            try:
                self.wallet.set_enabled(True)
            except PayoutBlocked:
                return self.screen("🔒 Chưa bật được ví: còn khoá tài chính (xem lý do bên dưới).")
            self._log(admin_id, "wallet_enabled", {"on": False}, {"on": True}, now)
            return self.screen("🟢 Đã bật ví. Khách thấy nút 👛 Ví của tôi từ tin kế tiếp.")
        if data == "c:wl:off":
            before = self.repo.get_state(KEY_ENABLED) == "1"  # công tắc đã lưu, không phải trạng thái hiệu lực
            self._log(admin_id, "wallet_enabled", {"on": before}, {"on": False}, now)
            self.wallet.set_enabled(False)
            return self.screen("⏸️ Đã tắt ví. Yêu cầu rút đang chờ vẫn xử lý được ở đây.")
        if data == "c:wl:cfg":
            return self._settings()
        hold = _HOLD.fullmatch(data)
        if hold and int(hold.group(1)) in HOLD_DAY_CHOICES:
            days = int(hold.group(1))
            self._log(admin_id, "wallet_hold_days", {"days": self.wallet.settings().hold_days}, {"days": days}, now)
            self.wallet.set_hold_days(days)
            return self._settings()
        low = _MIN.fullmatch(data)
        if low and int(low.group(1)) in MIN_WITHDRAW_CHOICES:
            amount = int(low.group(1))
            before = {"vnd": self.wallet.settings().min_withdraw_vnd}
            self._log(admin_id, "wallet_min_withdraw", before, {"vnd": amount}, now)
            self.wallet.set_min_withdraw(amount)
            # Một con số tối thiểu: bảng hạn mức đang dùng theo «Rút tối thiểu» (ADR-059).
            return self._settings(self._change_limits(admin_id, now, min_vnd=amount))
        if (limit := _LIMIT.fullmatch(data)) is not None and int(limit.group(2)) in payouts.LIMIT_CHOICES[limit.group(1)]:
            return self._settings(self._change_limits(admin_id, now, **{_LIMIT_FIELDS[limit.group(1)]: int(limit.group(2))}))
        if data == "c:wl:members":
            members = self.wallet.members()
            return BotReply(wallet_members_text(members), inline_keyboard=wallet_members_keyboard(members))
        member = _MEMBER.fullmatch(data)
        if member:
            return self._member(int(member.group(1)))
        if (payout := _PAYOUT.fullmatch(data)) is not None:
            row = self.wallet.payout(int(payout.group(1)))
            return self.screen("Không tìm thấy yêu cầu này.") if row is None else self._payout_detail(row)
        if (step := _STEP.fullmatch(data)) is not None:
            return self._step(admin_id, int(step.group(1)), int(step.group(2)), STEP_CODES[step.group(3)],
                              bool(step.group(4)), now)
        if (verify := _VERIFY.fullmatch(data)) is not None:
            return self._ask_verify(admin_id, int(verify.group(1)), now)
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=(WALLET_ADMIN_BACK,))

    def screen(self, notice: str = "") -> BotReply:
        settings = self.wallet.settings()
        requests = self.wallet.open_requests()
        with self.repo.connect() as conn:
            fund = payouts.fund_position(conn)
            problems = payouts.invariants(conn)
            groups = {
                PAYOUT_STATUS.get(status, status): int(count)
                for status, count in conn.execute("SELECT status, COUNT(*) FROM cashback_payouts GROUP BY status")
            }
        return BotReply(
            wallet_admin_text(settings, self.wallet.totals(), requests, notice, fund=fund, groups=groups, problems=problems),
            inline_keyboard=wallet_admin_keyboard(settings, requests),
        )

    def _change_limits(self, admin_id: int, now: datetime, **changes: int) -> str:
        """Thêm dòng hạn mức mới nếu có đổi. Trả thông báo cho admin ('' nếu không có gì để báo)."""
        with self.repo.connect() as conn:
            current = payouts.active_limits(conn)
            if current is None:
                return "" if "min_vnd" in changes else "Chưa có bảng hạn mức đã duyệt."
            if all(getattr(current, key) == value for key, value in changes.items()):
                return ""
            try:
                after = payouts.set_limits(conn, current, admin_id=admin_id, now=now, **changes)
            except ValueError:
                return "⚠️ Không đổi: cần tối thiểu ≤ mỗi lần ≤ mỗi ngày ≤ mỗi tháng."
        self._log(admin_id, "wallet_limits", _limits_dict(current), _limits_dict(after), now)
        return ""

    def _settings(self, notice: str = "") -> BotReply:
        settings = self.wallet.settings()
        with self.repo.connect() as conn:
            limits = payouts.active_limits(conn)
        return BotReply(
            wallet_settings_text(settings, limits, notice),
            inline_keyboard=wallet_settings_keyboard(
                settings, HOLD_DAY_CHOICES, MIN_WITHDRAW_CHOICES, limits, payouts.LIMIT_CHOICES
            ),
        )

    def _member(self, user_id: int) -> BotReply:
        user = self.repo.get_user(user_id)
        text = wallet_member_text(
            user_id,
            None if user is None else user["username"],
            self.wallet.balance(user_id),
            self.wallet.entries(user_id, limit=10),
            self.wallet.bank(user_id),
        )
        return BotReply(text, inline_keyboard=((("◀️ Thành viên", "c:wl:members"),), WALLET_ADMIN_BACK))

    # --- Yêu cầu rút (PLAN-078) -------------------------------------------------------------

    def _step(self, admin_id: int, payout_id: int, version: int, target: str, confirmed: bool, now: datetime) -> BotReply:
        """Bước 1: hỏi lại. Bước 2 (:ok): bước cần lý do / chứng từ thì chờ admin gõ; còn lại ghi ngay."""
        row = self.wallet.payout(payout_id)
        if row is None:
            return self.screen("Không tìm thấy yêu cầu này.")
        if int(row["version"] or 1) != version:
            return self._payout_detail(row, f"⚠️ {_ERRORS['stale']}")
        if target not in payouts.TRANSITIONS.get(row["status"], {}):
            return self._payout_detail(row, f"⚠️ {_ERRORS['transition']}")
        needs = _TEXT_STEPS.get(target)
        if not confirmed:
            code = next(k for k, v in STEP_CODES.items() if v == target)
            keyboard = (
                (("✅ Xác nhận", f"c:wl:mv:{payout_id}:{version}:{code}:ok"),),
                (("◀️ Quay lại", f"c:wl:rq:{payout_id}"),),
            )
            return BotReply(payout_step_text(row, target, needs), inline_keyboard=keyboard)
        if needs:
            self.waiting[admin_id] = ("step", payout_id, version, target, now + WAIT_TTL)
            return BotReply(f"✍️ Gõ {needs}.", inline_keyboard=((("✖️ Hủy", f"c:wl:rq:{payout_id}"),),))
        return self._apply(admin_id, payout_id, version, target, None, now)

    def _apply(self, admin_id: int, payout_id: int, version: int, target: str, text: str | None, now: datetime) -> BotReply:
        rule = payouts.TRANSITIONS.get((self.wallet.payout(payout_id) or {"status": ""})["status"], {}).get(target)
        note = text if rule is None or rule.needs_reason else None
        evidence = text if rule is not None and rule.needs_evidence else None
        row, code = self.wallet.advance(
            payout_id, target, admin_id, version, now, note=note, evidence=evidence,
            idempotency_key=f"admin:{admin_id}:{payout_id}:{version}:{target}",
        )
        if row is None:
            return self.screen(_ERRORS.get(code, code))
        if code not in ("ok", "duplicate"):
            return self._payout_detail(row, f"⚠️ {_ERRORS.get(code, code)}")
        if code == "ok":
            self._notify_customer(row, target, text)
        return self._payout_detail(row, f"✅ Đã chuyển sang: {PAYOUT_STATUS.get(target, target)}.")

    def _notify_customer(self, row, target: str, text: str | None) -> None:
        """Chỉ báo khách khi có kết luận: đã trả (có chứng từ), tiền trở lại ví, hoặc cần kiểm tra tài khoản."""
        if target == payouts.PAID:
            body = payout_notice(row, True)
        elif target in (payouts.REJECTED, payouts.CANCELLED, payouts.FAILED, payouts.RETURNED):
            body = payout_notice(row, False) + (f"\n\nLý do: {text}" if text else "")
        elif target == payouts.NEEDS_REVIEW:
            body = (
                "⚠️ <b>Yêu cầu rút cần kiểm tra thêm</b>\n\n"
                f"Mã: <code>{row['transfer_note']}</code>. Tiền vẫn được giữ cho yêu cầu này. "
                "Bot sẽ báo khi có kết quả; bạn có thể gửi thông tin qua /hotro."
            )
        else:
            return
        self.repo.enqueue_admin_event(
            event_key=f"payout:{row['id']}:{row['version']}:{target}",
            event_type="PAYOUT_DECIDED",
            chat_id=int(row["telegram_user_id"]),
            message_html=body,
        )

    def _ask_verify(self, admin_id: int, payout_id: int, now: datetime) -> BotReply:
        row = self.wallet.payout(payout_id)
        if row is None:
            return self.screen("Không tìm thấy yêu cầu này.")
        self.waiting[admin_id] = ("verify", payout_id, int(row["version"] or 1), "", now + WAIT_TTL)
        return BotReply(
            "✅ <b>Xác minh tài khoản người nhận</b>\n\n"
            f"Tài khoản ••••{row['account_no'][-4:]} · {row['account_name']}.\n"
            "Gõ bằng chứng xác minh (ví dụ: «chuyển thử 1.000đ, app hiện đúng tên, mã GD …» hoặc «khách xác nhận "
            "qua /hotro #…»). Tạo được mã QR <b>không</b> phải là xác minh.",
            inline_keyboard=((("✖️ Hủy", f"c:wl:rq:{payout_id}"),),),
        )

    def consume_text(self, admin_id: int, text: str, now: datetime) -> BotReply | None:
        job = self.waiting.get(admin_id)
        if job is None:
            return None
        kind, payout_id, version, target, deadline = job
        stripped = (text or "").strip()
        self.waiting.pop(admin_id, None)
        if deadline <= now or not stripped or stripped.startswith("/"):
            return None
        if kind == "verify":
            row = self.wallet.payout(payout_id)
            if row is None:
                return self.screen("Không tìm thấy yêu cầu này.")
            try:
                with self.repo.connect() as conn:
                    payouts.verify_bank(conn, int(row["telegram_user_id"]), row["account_sha"] or "", admin_id,
                                        "manual", stripped, now)
            except payouts.PayoutError:
                return self._payout_detail(row, f"⚠️ {_ERRORS['evidence']}")
            self._log(admin_id, "bank_verified", None, {"payout": payout_id, "last4": row["account_no"][-4:]}, now)
            return self._payout_detail(row, "✅ Đã ghi xác minh tài khoản (gắn với đúng số tài khoản này).")
        return self._apply(admin_id, payout_id, version, target, stripped, now)

    def _payout_detail(self, row, notice: str = "") -> BotReply:
        user = self.repo.get_user(int(row["telegram_user_id"]))
        locked = bool(self.wallet.settings().locked_reasons)
        now = datetime.now(timezone.utc)
        with self.repo.connect() as conn:
            conditions = (
                [payout_readiness.Condition("system", "Khoá tài chính đã mở", not locked, "system")]
                + payout_readiness.user_conditions(conn, int(row["telegram_user_id"]))
                + payout_readiness.payout_conditions(conn, row, now)
            )
            parts = payouts.allocations(conn, int(row["id"]))
            history = payouts.events(conn, int(row["id"]))
            state = payouts.bank_status(conn, int(row["telegram_user_id"]), row["account_sha"])
            shared = payouts.shared_account_users(conn, row["account_sha"]) if row["account_sha"] else 0
            fund = payouts.fund_position(conn)
        show_account = row["status"] == payouts.PROCESSING and not locked
        photo = qr_problem = None
        if show_account:
            photo, qr_problem = self._qr(row)
        text = payout_text(
            row, None if user is None else user["username"], BANKS.get(row["bank_code"], ("", row["bank_code"]))[1],
            allocations=parts, conditions=conditions, events=history, bank_state=state, shared_users=shared,
            fund=fund, notice=notice, show_account=show_account, qr_problem=qr_problem, qr_sent=photo is not None,
        )
        targets = list(payouts.TRANSITIONS.get(row["status"], {}))
        return BotReply(text, inline_keyboard=payout_keyboard(row, targets, locked), photo=photo)

    def _qr(self, row) -> tuple[tuple[str, bytes, str] | None, str | None]:
        """Ảnh QR tự tạo (không gửi thông tin khách ra ngoài). Lỗi thì trả lý do để admin chuyển tay."""
        bank = BANKS.get(row["bank_code"])
        if bank is None:
            return None, f"Ngân hàng {row['bank_code']} không còn trong danh sách hỗ trợ."
        try:
            payload = build_payload(bank[0], row["account_no"], int(row["amount_vnd"]), row["transfer_note"] or "")
        except VietQRError as exc:
            return None, f"Không tạo được mã QR: {exc}."
        image = qr_png(payload)
        if image is None:
            return None, "Máy chủ chưa vẽ được ảnh QR."
        caption = f"{row['transfer_note']} · {format_vnd(int(row['amount_vnd']))} · {bank[1]} ••••{row['account_no'][-4:]}"
        return (f"qr-{row['transfer_note'] or row['id']}.png".replace(" ", "-"), image, caption), None


def _limits_dict(limits: payouts.LimitPolicy) -> dict:
    return {
        "min": limits.min_vnd,
        "req": limits.max_per_request_vnd,
        "day": limits.daily_total_vnd,
        "month": limits.monthly_total_vnd,
    }
