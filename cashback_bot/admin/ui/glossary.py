"""Từ điển thuật ngữ và bảng nhãn / mã cố định của /admin."""

from __future__ import annotations



# Một định nghĩa cho mọi màn (PLAN-076; thuật ngữ chung từ rà soát 2026-10-26, xem GLOSSARY).
ADMIN_KEEP_NOTE = (
    "«Biên» = HH ròng − phần khách − dự phòng phí − dự phòng thuế. "
    "Là số ước tính, chưa trừ phí và thuế thực tế theo chứng từ."
)

# Tên gọi tiền dùng chung cho mọi màn (2026-11-03, money_flow.py). Đổi chữ ở đây, không viết lại ở từng màn.
MONEY_HOME = "Tiền & ví"
WAIT_SHOPEE = "Chờ Shopee trả"
WAIT_HOLD = "Chờ đủ ngày giữ"
IN_WALLET = "Trong ví"
OWED_BACK = "Đang trừ lại"
RESERVED = "Đang chờ chuyển"
PAID_OUT = "Đã chuyển"
FUND_LEFT = "Quỹ chi trả còn"
OWNER_REAL = "Thực nhận"
OWNER_SOON = "Sắp về"

# Bảng thuật ngữ dùng chung cho mọi màn admin, Telegram và web (⚙️ Cài đặt → 📖 Thuật ngữ).
GLOSSARY = (
    "⚙️ Quản trị › Cài đặt › <b>📖 Thuật ngữ</b>\n\n"
    "<b>Tiền theo chứng từ</b> (💰 Tiền &amp; ví)\n"
    "• <b>Kỳ thanh toán</b>: một lần Shopee chuyển tiền, gom hoa hồng các đơn đã duyệt.\n"
    "• <b>Kỳ khớp</b>: báo cáo Shopee, phép tính và tiền về tài khoản khớp nhau.\n"
    "• <b>Thực nhận</b> = tiền về tài khoản − tiền hoàn của khách (các kỳ khớp). Phí, thuế Shopee giữ trừ vào phần anh.\n"
    "• <b>Sắp về</b>: kỳ Shopee đã báo nhưng tiền chưa về, chưa tính vào thực nhận.\n"
    "• <b>Quỹ chi trả</b>: phần đơn qua bot của các kỳ khớp, sau phí và thuế, trừ tiền đang chờ chuyển và đã chuyển. "
    "Là trần chi cho khách.\n\n"
    "<b>Tiền hoàn của khách</b>\n"
    f"• {WAIT_SHOPEE} → {IN_WALLET} → {RESERVED} → {PAID_OUT}. «{WAIT_HOLD}»: đơn đã trong kỳ khớp, còn trong số "
    "ngày giữ. «Đang trừ lại»: Shopee giảm hoa hồng sau khi tiền đã vào ví, ví khách âm.\n"
    "• <b>Hoàn dự kiến → hoàn tạm tính → tiền hoàn</b>: số khách thấy lúc tạo link → khi đã có đơn → khi đã vào ví.\n\n"
    "<b>Ước tính</b> (💹 Dòng tiền, 💰 % hoàn, 🧪 Mô phỏng)\n"
    "• <b>HH ròng</b>: hoa hồng sàn trả, sau phí MCN.\n"
    "• <b>Phần khách</b>: tiền hoàn chia cho khách, theo % hoàn lưu kèm từng link.\n"
    "• <b>Dự phòng</b>: phí và thuế bot tự trừ khi ước tính, chưa phải tiền Shopee giữ thật.\n"
    "• <b>Biên</b> = HH ròng − phần khách − dự phòng: phần anh giữ, ước tính.\n"
    "• <b>Lãi</b> = biên − chi phí vận hành / hạ tầng.\n"
    "• <b>Tạm tính</b>: mọi đơn chưa huỷ, sàn chưa trả tiền.\n"
    "• <b>Đơn hoàn thành</b>: người mua đã nhận hàng; hoa hồng vẫn chờ sàn duyệt và thanh toán."
)


STATS_PERIODS = (("today", "Hôm nay"), ("7d", "7 ngày"), ("30d", "30 ngày"), ("all", "Tất cả"))


WALLET_ENABLE_CONFIRM = (
    "🟢 <b>Bật ví cho khách?</b>\n\n"
    "Sau khi bật:\n"
    "• Trang chủ có nút <b>👛 Ví của tôi</b>, lệnh /vi dùng được.\n"
    "• Câu \"chưa theo dõi đơn và chưa chi trả\" đổi thành lời hứa chi trả.\n"
    "• Khách nhận tin khi có đơn, đơn hoàn thành, tiền vào ví, đơn huỷ.\n"
    "• Khách khai ngân hàng và bấm Rút; anh chuyển khoản tay rồi bấm ✅.\n\n"
    "ⓘ Mô tả bot (màn trước khi bấm Start) và menu lệnh chỉ đổi sau lần restart kế tiếp."
)


_ENTRY_ADMIN = {"pending": "đang xử lý", "holding": "chờ Shopee trả", "available": "đã vào ví", "cancelled": "huỷ"}


PAYOUT_STATUS = {
    "requested": "🆕 Mới gửi",
    "under_review": "🔎 Đang kiểm tra",
    "approved_for_payment": "🟢 Đã duyệt, chờ chuyển",
    "processing": "🏦 Đang chuyển",
    "sent_unconfirmed": "⏳ Đã gửi, chờ xác nhận ngân hàng",
    "paid_confirmed": "✅ Đã chuyển (có chứng từ)",
    "paid": "✅ Đã chuyển (bản cũ)",
    "rejected": "✖️ Từ chối",
    "cancelled": "↩️ Đã huỷ",
    "failed": "❌ Chuyển thất bại",
    "needs_review": "⚠️ Cần xử lý",
    "returned": "↩️ Ngân hàng hoàn lại",
}
# Mã ngắn trong callback c:wl:mv:<id>:<version>:<mã>.
STEP_CODES = {
    "rv": "under_review", "ap": "approved_for_payment", "pr": "processing", "se": "sent_unconfirmed",
    "pd": "paid_confirmed", "rj": "rejected", "ca": "cancelled", "fl": "failed", "nr": "needs_review",
    "rt": "returned",
}
STEP_LABELS = {
    "under_review": "🔎 Bắt đầu kiểm tra",
    "approved_for_payment": "🟢 Duyệt chi",
    "processing": "🏦 Bắt đầu chuyển khoản",
    "sent_unconfirmed": "📤 Đã gửi lệnh, chờ biên nhận",
    "paid_confirmed": "✅ Xác nhận đã trả (nhập chứng từ)",
    "rejected": "✖️ Từ chối",
    "cancelled": "↩️ Huỷ",
    "failed": "❌ Chuyển thất bại (nhập chứng từ)",
    "needs_review": "⚠️ Cần xử lý",
    "returned": "↩️ Ngân hàng hoàn lại (nhập chứng từ)",
}
STEP_HELP = {
    "under_review": "Chỉ ghi là đang kiểm tra, chưa giữ thêm hay chi tiền.",
    "approved_for_payment": "Kiểm lại khoá tài chính, điều khoản, tài khoản đã xác minh, quỹ và hạn mức. Chưa chuyển tiền.",
    "processing": "Bot hiện số tài khoản đầy đủ và mã QR để chuyển tay. Bấm khi bắt đầu thao tác trên app ngân hàng.",
    "sent_unconfirmed": "Bấm ngay sau khi gửi lệnh trên app ngân hàng, kể cả khi app treo. Từ đây không huỷ hay từ chối được nữa.",
    "paid_confirmed": "Chỉ bấm khi đã có biên nhận / sao kê: nhập mã giao dịch ngân hàng. Bot báo khách đã chuyển.",
    "rejected": "Tiền trở lại ví khách, khách được báo lý do.",
    "cancelled": "Huỷ trước khi chuyển, tiền trở lại ví khách.",
    "failed": "Chỉ khi ngân hàng xác nhận lệnh không thực hiện: nhập lý do kèm mã/tham chiếu. Tiền trở lại ví khách.",
    "needs_review": "Tạm dừng để kiểm tra (sai tài khoản, chưa rõ kết quả, khách đổi tài khoản…). Không giải phóng tiền.",
    "returned": "Ngân hàng hoàn khoản đã trả: nhập chứng từ. Lịch sử «đã trả» giữ nguyên, tiền trở lại ví khách.",
}
_BANK_STATE = {"VERIFIED": "✅ đã xác minh", "REJECTED": "❌ xác minh không đạt"}


PAYOUT_TEXT_MAX = 4000
