"""Màn /admin → ⚖️ Sẵn sàng chi trả (PLAN-077). Chỉ đọc.

Gom những gì còn thiếu trước khi mở ví: lý do khoá tài chính (đọc trực tiếp từ payout_gate), link chưa chứng
minh được chính sách, thuế, xử lý hoa hồng bị thu hồi, điều khoản, hỗ trợ. Mọi chính sách ở đây là
PENDING_REVIEW: màn này không có nút duyệt, không tạo bảng hay dòng nào làm mất cảnh báo khoá.
"""

from __future__ import annotations

from datetime import datetime

from cashback_bot import payout_readiness, payouts, policy_snapshot, support, terms
from cashback_bot.db import TrackingRepository
from cashback_bot.messages import BotReply
from cashback_bot.payout_gate import FinancialGate

HOME = "c:rd:home"
BACK_MENU = (("◀️ Tổng quan", "c:menu:home"),)
BACK_HOME = (("◀️ Sẵn sàng chi trả", HOME),)

TAX_TEXT = (
    "⚙️ Quản trị › Sẵn sàng chi trả › <b>Thuế</b>\n\n"
    "Trạng thái: <b>PENDING_REVIEW</b>, chưa có quyết định nào được duyệt.\n\n"
    "<b>Sáu khoản khác nhau, không gộp:</b>\n"
    "1. Thuế của chủ bot trên hoa hồng affiliate: theo chứng từ Shopee/cơ quan thuế.\n"
    "2. Thuế Shopee đã khấu trừ: chỉ lấy từ báo cáo thanh toán (🧾 Đối soát), không đoán.\n"
    "3. Phí Shopee: theo chứng từ.\n"
    "4. VAT trên phí: theo chứng từ, không trừ hai lần.\n"
    "5. Dự phòng 0,98% / 10% của công thức V1.2: chỉ để <b>ước tính</b> số hoàn, không phải thuế của ai.\n"
    "6. Nghĩa vụ thuế khi chi cho người nhận: <b>chưa xác định</b>, chờ kế toán.\n\n"
    "<b>Cần kế toán trả lời</b> (danh sách đầy đủ trong báo cáo PLAN-077, mục 10):\n"
    "• Bản chất khoản hoàn cho người mua (giảm giá, khuyến mại, tiền công giới thiệu…).\n"
    "• Người trả là cá nhân chưa đăng ký kinh doanh có phải khấu trừ không; ngưỡng mỗi lần chi.\n"
    "• Khoản hoàn có được trừ khỏi doanh thu chịu thuế của chủ bot không.\n"
    "• Chứng từ cần lưu cho mỗi lần chuyển.\n\n"
    "ⓘ Các mốc pháp lý 2026 trong báo cáo mới được xác nhận qua nguồn thứ cấp, phải đối chiếu văn bản gốc."
)
CLAWBACK_TEXT = (
    "⚙️ Quản trị › Sẵn sàng chi trả › <b>Hoa hồng bị thu hồi</b>\n\n"
    "Trạng thái: <b>PENDING_REVIEW</b>. Bot chỉ ghi nhận, không trừ hay thu tiền của khách.\n\n"
    "<b>Đang làm (đã có trong code):</b>\n"
    "• Trước khi Shopee duyệt: khoản dự kiến cập nhật theo hoa hồng mới, ghi lịch sử thay đổi.\n"
    "• Gian lận / từ chối: khoản chuyển «không được hoàn», không tạo khoản phải trả.\n"
    "• Sau khi kỳ đã đối soát khớp: mỗi lần Shopee giảm/thu hồi tạo một dòng điều chỉnh OPEN (🧾 Đối soát).\n\n"
    "<b>Chờ chủ bot quyết định:</b>\n"
    "• Shopee đã thanh toán, chưa chi khách: chi theo số ròng sau điều chỉnh? (đề xuất: có)\n"
    "• Đã chi khách rồi mới bị thu hồi: chủ bot chịu / trừ vào khoản hoàn sau (cần khách đồng ý trong "
    "điều khoản) / xử lý tranh chấp từng ca.\n"
    "• Ngưỡng nhỏ bỏ qua, thời hạn giữ tiền trước khi chi.\n\n"
    "ⓘ Không chọn phương án nào thay chủ bot. Bảng quyết định đầy đủ trong báo cáo PLAN-077, mục 11."
)


class ReadinessAdmin:
    def __init__(self, repo: TrackingRepository):
        self.repo = repo

    def route(self, admin_id: int, data: str, now: datetime) -> BotReply:
        if data == HOME:
            return self._home(now)
        if data == "c:rd:tax":
            return BotReply(TAX_TEXT, inline_keyboard=(BACK_HOME,))
        if data == "c:rd:claw":
            return BotReply(CLAWBACK_TEXT, inline_keyboard=(BACK_HOME,))
        return BotReply("Nút này không còn hiệu lực.", inline_keyboard=(BACK_HOME,))

    def _home(self, now: datetime) -> BotReply:
        gate = FinancialGate(self.repo)
        with self.repo.connect() as conn:
            readiness = gate.readiness(conn)
            coverage = policy_snapshot.coverage(conn)
            live = terms.current(conn, now)
            counts = support.counts(conn)
            conditions = payout_readiness.system_conditions(conn)
            fund = payouts.fund_position(conn)
            problems = payouts.invariants(conn)
        unresolved = coverage[policy_snapshot.UNRESOLVED] + coverage["missing"]
        open_tickets = sum(count for status, count in counts.items() if status not in support.FINAL)
        lines = [
            "⚙️ Quản trị › <b>Sẵn sàng chi trả</b>",
            "",
            f"🔒 Ví và chi trả: <b>{'KHOÁ' if not readiness.ok else 'đủ điều kiện hệ thống'}</b>",
        ]
        # Điều kiện PLAN-078 hiện ở ma trận bên dưới; ở đây chỉ hai lý do khoá gốc.
        lines += [f"• {reason}" for reason in readiness.reasons if not reason.startswith("Chưa đạt:")]
        lines += [
            "",
            f"🧾 Link chứng minh được chính sách: <b>{coverage[policy_snapshot.CAPTURED] + coverage[policy_snapshot.BACKFILLED]}</b>"
            f" · chưa xác định: <b>{unresolved}</b> (không bao giờ vào ví)",
            f"📋 Điều khoản: <b>{'chưa công bố' if live is None else live.version}</b>",
            f"📩 Yêu cầu hỗ trợ đang mở: <b>{open_tickets}</b>",
            "",
            "⏱ Thời hạn xử lý hỗ trợ (SLA): <b>chưa duyệt</b>",
            "",
            "🧩 <b>Điều kiện chi trả (PLAN-078)</b>",
            *[f"{'✅' if item.ok else '❌'} {item.label}" for item in conditions],
            (f"🏦 Quỹ có chứng từ: còn <b>{fund.headroom_vnd:,}đ</b>".replace(",", ".") if fund.verified
             else "🏦 Quỹ có chứng từ: <b>Chưa xác minh</b>"),
            f"🧮 Kiểm tra sổ: <b>{'ổn' if not problems else f'{len(problems)} cảnh báo'}</b>",
            "",
            "ⓘ Màn này chỉ để xem. Không có nút duyệt hay mở ví. Đạt hết vẫn cần khoá cũ mở và chủ bot duyệt riêng.",
        ]
        keyboard = (
            (("⚖️ Thuế", "c:rd:tax"), ("↩️ Thu hồi hoa hồng", "c:rd:claw")),
            BACK_MENU,
        )
        return BotReply("\n".join(lines), inline_keyboard=keyboard)
