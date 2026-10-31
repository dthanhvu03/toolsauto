"""Từ điển thuật ngữ và bảng nhãn / mã cố định của /admin."""

from __future__ import annotations



# Một định nghĩa cho mọi màn (PLAN-076; thuật ngữ chung từ rà soát 2026-10-26, xem GLOSSARY).
ADMIN_KEEP_NOTE = (
    "«Biên» = HH ròng − phần khách − dự phòng phí − dự phòng thuế. "
    "Là số ước tính, chưa trừ phí và thuế thực tế theo chứng từ."
)
# Bảng thuật ngữ dùng chung cho mọi màn admin, Telegram và web (⚙️ Cài đặt → 📖 Thuật ngữ).
GLOSSARY = (
    "⚙️ Quản trị › Cài đặt › <b>📖 Thuật ngữ</b>\n\n"
    "• <b>HH ròng</b>: hoa hồng sàn trả cho chương trình, sau phí MCN.\n"
    "• <b>Phần khách</b>: tiền hoàn chia cho khách, theo % hoàn lưu kèm từng link.\n"
    "• <b>Dự phòng</b>: dự phòng phí và thuế bot tự đặt, chưa phải tiền đã nộp.\n"
    "• <b>Biên</b> = HH ròng − phần khách − dự phòng: phần anh giữ.\n"
    "• <b>Lãi</b> = biên − chi phí vận hành / hạ tầng (anh nhập ở 💹 Dòng tiền).\n"
    "• <b>Tạm tính</b>: tính trên mọi đơn chưa huỷ; sàn chưa trả tiền.\n"
    "• <b>Thực</b>: chỉ đơn sàn đã trả tiền và đối soát khớp.\n"
    "• <b>Đơn hoàn thành</b>: người mua đã nhận hàng; hoa hồng vẫn chờ sàn duyệt và thanh toán.\n"
    "• <b>Hoàn dự kiến → hoàn tạm tính → tiền hoàn</b>: số khách thấy lúc tạo link → khi đã có đơn → khi đã vào ví."
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


_ENTRY_ADMIN = {"pending": "đang xử lý", "holding": "chờ duyệt", "available": "đã vào ví", "cancelled": "huỷ"}


PAYOUT_STATUS = {
    "requested": "🆕 Mới gửi",
    "under_review": "🔎 Đang kiểm tra",
    "approved_for_payment": "🟢 Đã duyệt, chờ chuyển",
    "processing": "🏦 Đang chuyển",
    "sent_unconfirmed": "⏳ Đã gửi, chờ xác nhận ngân hàng",
    "paid_confirmed": "✅ Đã trả (có chứng từ)",
    "paid": "✅ Đã trả (bản cũ)",
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
