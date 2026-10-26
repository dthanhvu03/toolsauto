"""Dự thảo điều khoản khách (PLAN-077). Admin tạo bản nháp từ mẫu này rồi mới công bố.

V1 công bố 2026-10-24. V2 (PLAN-083): bot có thêm kênh Zalo; chỉ đổi hai câu nói «tài khoản Telegram» thành
«tài khoản Telegram hoặc Zalo». Không đổi quyền lợi, cách tính hay trạng thái chi trả. Nội dung V1, V2 nằm trong DB.
V3 (reports/CASHBACK_TERMS_V3_DRAFT.md, chủ bot duyệt 2026-10-26): mở ví và rút tiền, thu hồi, thời hạn lưu dữ liệu
lấy từ retention.py lúc tạo bản nháp. CHỈ công bố cùng lúc bật ví, sau khi bot đọc được báo cáo thanh toán Shopee
và đã có việc tự xoá dữ liệu hết hạn (điều khoản hứa cả hai).

Viết theo đúng chức năng bot đang chạy (audit PLAN-077 mục 3). Không hứa thời hạn rút, mức rút hay cam kết
chi trả. Khi chức năng đổi (mở ví, hạng thành viên), phải ra phiên bản mới, không sửa bản đã công bố.
Mỗi mục là một tin Telegram, giữ dưới 3.500 ký tự.
"""

from __future__ import annotations

from cashback_bot import retention

DRAFT_VERSION = "V3"
DRAFT_TITLE = "Điều khoản sử dụng chương trình hoàn tiền"

# (mã, tiêu đề nút, nội dung HTML Telegram)
def draft_sections(keep: dict[str, int]) -> tuple[tuple[str, str, str], ...]:
    """Các mục V3. `keep`: thời hạn lưu (retention.load) ghi vào mục 🛡 Dữ liệu cá nhân."""
    period = {key: retention.period(key, value) for key, value in keep.items()}
    return (
        (
            "chung",
            "📋 Điều khoản chung",
            "<b>1. Chương trình là gì</b>\n"
            "Bot giúp bạn tạo link mua hàng Shopee có gắn mã theo dõi của chương trình Shopee Affiliate do người "
            "vận hành bot tham gia. Khi đơn đủ điều kiện, Shopee trả hoa hồng cho người vận hành; bot chia "
            "lại một phần cho người tạo link.\n\n"
            "• Bot <b>không phải</b> dịch vụ của Shopee và không đại diện Shopee.\n"
            "• Bot không thu phí. Bạn mua và thanh toán trực tiếp trên Shopee; giá, khuyến mãi, giao hàng, đổi trả "
            "do Shopee và người bán quyết định.\n\n"
            "<b>2. Ví hoàn tiền</b>\n"
            "• Khoản hoàn đủ điều kiện được ghi vào ví của bạn trong bot. Bạn rút về tài khoản ngân hàng theo mục "
            "👛 Ví và rút tiền.\n"
            "• Ví chỉ hoạt động khi người vận hành bật. Khi ví tạm tắt, khoản đã ghi nhận vẫn được giữ và yêu cầu "
            "rút đang chờ vẫn được xử lý.\n\n"
            "<b>3. Thay đổi điều khoản</b>\n"
            "• Mỗi lần thay đổi là một phiên bản mới, có số phiên bản và ngày hiệu lực, xem ở /dieukien.\n"
            "• Phiên bản đã công bố không bị sửa lại.\n"
            "• Thay đổi cách tính chỉ áp dụng cho link tạo sau ngày hiệu lực; link đã tạo giữ cách tính lúc tạo.\n"
            "• Khoản đã được xác nhận đủ điều kiện không bị huỷ chỉ vì đổi điều khoản; nếu có tranh chấp, xử lý "
            "theo mục Hỗ trợ và khiếu nại.",
        ),
        (
            "ghi_nhan",
            "💰 Ghi nhận và cách tính",
            "<b>1. Đơn được ghi nhận cho ai</b>\n"
            "• Mỗi link bot tạo có một mã theo dõi (Sub ID) riêng, gắn với tài khoản Telegram hoặc Zalo đã gửi link "
            "cho bot.\n"
            "• Đơn mua qua link đó được ghi nhận cho <b>người đã tạo link</b>, kể cả khi người khác bấm link và "
            "đặt hàng. Chia sẻ link không chuyển quyền nhận hoàn tiền sang người mua.\n"
            "• Muốn tự nhận hoàn tiền, mỗi người tự gửi link sản phẩm cho bot để có link riêng.\n"
            "• Bot chỉ biết đơn khi Shopee báo về trong báo cáo Affiliate có đúng Sub ID của link.\n\n"
            "<b>2. Số hoàn dự kiến</b>\n"
            "• Số hiện khi tạo link là <b>ước tính</b> theo giá tham khảo và mức hoa hồng Shopee công bố lúc đó, "
            "không phải số chắc chắn nhận.\n"
            "• Số thật có thể thấp hơn, cao hơn hoặc bằng 0 vì: số tiền bạn thực trả (voucher, xu, giảm giá), huỷ "
            "hoặc trả hàng, chính sách và điều chỉnh hoa hồng của Shopee, Shopee từ chối hoặc gắn gian lận.\n"
            "• Cách tính hiện hành trừ trước các khoản dự phòng phí và thuế của người vận hành, rồi chia một phần "
            "cho bạn. Khoản dự phòng <b>không phải</b> số thuế bạn phải nộp. Khi chuyển tiền cho bạn, bot không "
            "trừ thêm thuế hay phí.\n\n"
            "<b>3. Cách tính của từng link</b>\n"
            "• Mỗi link lưu lại cách tính lúc tạo. Bot đổi cách tính thì link cũ vẫn giữ cách tính cũ.\n"
            "• Giữ cách tính không có nghĩa là giữ số tiền: số tiền vẫn theo hoa hồng Shopee thực tế của đơn.\n\n"
            "<b>4. Các bước của một đơn</b>\n"
            "1) Shopee ghi nhận đơn → 2) hoa hồng chờ Shopee xác minh → 3) Shopee duyệt hoa hồng → "
            "4) Shopee thanh toán cho người vận hành, và người vận hành đối soát khớp với tiền thực nhận → "
            "5) khoản vào ví.\n"
            "Khoản vào ví khi đủ <b>cả ba</b>:\n"
            "• Shopee đã duyệt hoa hồng của đơn.\n"
            "• Shopee đã thanh toán và đối soát khớp.\n"
            "• Đã qua số ngày giữ tiền tính từ khi đơn hoàn thành (xem trong 👛 Ví).\n"
            "Thường mất vài tuần đến vài tháng sau khi đặt hàng, tuỳ lịch duyệt và thanh toán của Shopee.",
        ),
        (
            "khong_hop_le",
            "🚫 Đơn không được hoàn",
            "Đơn hoặc khoản hoàn <b>không được tính</b> khi:\n"
            "• Đơn bị huỷ, trả hàng hoặc hoàn tiền, hoặc Shopee không trả hoa hồng cho đơn.\n"
            "• Shopee từ chối hoa hồng hoặc gắn cờ gian lận cho đơn.\n"
            "• Không xác định được Sub ID, đơn không đi qua link của bot, hoặc không có dữ liệu Shopee để đối chiếu.\n"
            "• Có bằng chứng thao tác bất thường (bấm link hay đặt hàng lặp lại để trục lợi).\n\n"
            "Lưu ý:\n"
            "• Shopee không ghi nhận đơn <b>không có nghĩa</b> là bạn gian lận. Nhiều đơn mất ghi nhận vì giỏ hàng "
            "có sẵn, bấm sang link khác hoặc quy định của Shopee.\n"
            "• Bot chỉ coi là gian lận khi có dữ liệu từ Shopee hoặc bằng chứng cụ thể, và bạn có quyền yêu cầu "
            "kiểm tra lại qua /hotro.\n\n"
            "<b>Khi Shopee giảm hoặc thu hồi hoa hồng</b>\n"
            "• Khoản chưa vào ví giảm theo.\n"
            "• Khoản đã chi được <b>trừ vào các khoản hoàn sau</b> của bạn. Khi còn khoản phải trừ, bạn tạm chưa "
            "rút được cho tới khi trừ đủ. Bot không yêu cầu bạn chuyển trả tiền.\n"
            "• Đơn Shopee gắn cờ gian lận không được vào ví.",
        ),
        (
            "vi",
            "👛 Ví và rút tiền",
            "<b>1. Điều kiện rút</b>\n"
            "• Bạn đã đồng ý phiên bản điều khoản này trong bot.\n"
            "• Số dư rút được từ mức tối thiểu trở lên (xem trong 👛 Ví).\n"
            "• Mỗi lần một yêu cầu: yêu cầu trước xong mới tạo được yêu cầu mới.\n"
            "• Mỗi yêu cầu, và tổng rút của bạn mỗi ngày, mỗi tháng, không vượt hạn mức đang hiện trong 👛 Ví. "
            "Chạm hạn mức ngày hoặc tháng thì bạn rút tiếp vào ngày hoặc tháng sau.\n\n"
            "<b>2. Tài khoản nhận tiền</b>\n"
            "• Tài khoản ngân hàng phải đứng tên bạn, và tên chủ tài khoản phải trùng tên bạn khai.\n"
            "• Người vận hành kiểm tra tên người nhận trước khi chuyển. Tên không khớp thì yêu cầu bị từ chối và "
            "tiền trở lại ví.\n"
            "• <b>Đổi tài khoản:</b> sau khi đổi, bạn chờ 7 ngày mới rút về tài khoản mới. Người vận hành có thể "
            "xác minh và cho rút sớm hơn. Yêu cầu đang chờ mang tài khoản cũ sẽ được kiểm tra lại.\n\n"
            "<b>3. Chuyển tiền</b>\n"
            "• Người vận hành chuyển khoản thủ công trong <b>3–7 ngày làm việc</b> kể từ khi bạn gửi yêu cầu.\n"
            "• Nội dung chuyển khoản: <code>Hoan tien</code> kèm mã yêu cầu.\n"
            "• Bạn nhận đúng số tiền trong yêu cầu, không bị trừ phí hay thuế.\n"
            "• Chuyển xong, bot báo bạn kèm mã giao dịch ngân hàng. Chuyển lỗi hoặc ngân hàng hoàn lại thì tiền "
            "trở lại ví.\n\n"
            "<b>4. Thay đổi mức</b>\n"
            "• Mức tối thiểu, hạn mức rút và số ngày giữ tiền có thể thay đổi. Mức đang áp dụng luôn hiện trong 👛 Ví.\n"
            "• Mức mới áp dụng cho yêu cầu tạo sau khi đổi. Số ngày giữ mới áp dụng cho đơn chưa vào ví; khoản đã "
            "vào ví giữ nguyên.",
        ),
        (
            "du_lieu",
            "🛡 Dữ liệu cá nhân",
            "<b>Bot lưu những gì</b>\n"
            "• Mã tài khoản Telegram hoặc Zalo, tên người dùng hoặc tên hiển thị, thời điểm dùng bot.\n"
            "• Link Shopee bạn gửi, thông tin sản phẩm, link bot tạo và mã theo dõi (Sub ID).\n"
            "• Thông tin đơn qua link từ báo cáo Shopee Affiliate: mã đơn, tên sản phẩm, trạng thái, hoa hồng.\n"
            "• Khi dùng ví: ngân hàng, số tài khoản và tên chủ tài khoản bạn khai; lịch sử yêu cầu rút và chứng từ "
            "chuyển khoản (mã giao dịch).\n"
            "• Nội dung bạn gửi trong yêu cầu hỗ trợ.\n"
            "• Tin nhắn không phải link sản phẩm không được lưu nội dung.\n"
            "• Bot không hỏi mật khẩu, OTP, cookie Shopee hay thông tin thẻ. Đừng gửi những thông tin này.\n\n"
            "<b>Dùng để làm gì</b>\n"
            "Tạo link, ghi nhận đơn cho đúng người, tính và chi tiền hoàn, đối soát với Shopee, trả lời hỗ trợ và "
            "chống lạm dụng.\n\n"
            "<b>Ai xem được</b>\n"
            "Chỉ người vận hành bot. Khách khác không xem được dữ liệu hay yêu cầu hỗ trợ của bạn. Bot không bán "
            "dữ liệu.\n\n"
            "<b>Bảo vệ và lưu giữ</b>\n"
            "• Dữ liệu nằm trên máy chủ của người vận hành, bản sao lưu được giới hạn quyền đọc, nhật ký hệ thống "
            "che mã bí mật. Màn quản trị chỉ hiện 4 số cuối tài khoản ngân hàng.\n"
            f"• Sổ ví, yêu cầu rút và chứng từ chuyển khoản (gồm tài khoản đã nhận tiền): <b>{period['finance_years']}</b>, "
            "để đối soát và kê khai thuế khi cần.\n"
            f"• Tài khoản ngân hàng chưa từng nhận tiền: xoá khi bạn yêu cầu, hoặc sau <b>{period['bank_idle_months']}</b> "
            "bạn không dùng bot.\n"
            f"• Link, click và đơn không phát sinh tiền: <b>{period['activity_months']}</b>.\n"
            f"• Nội dung yêu cầu hỗ trợ: <b>{period['ticket_months']}</b> sau khi đóng.\n"
            "• Hết hạn, dữ liệu được xoá hoặc ẩn danh.\n\n"
            "<b>Quyền của bạn</b>\n"
            "Bạn có thể yêu cầu xem, sửa hoặc xoá dữ liệu của mình qua /hotro → 🛡 Dữ liệu cá nhân. Sổ ví và chứng "
            "từ chi trả cần giữ tới hạn trên nên chưa xoá được ngay; phần còn lại được xoá hoặc ẩn danh, bot sẽ báo "
            "lại cho bạn.",
        ),
        (
            "ho_tro",
            "📩 Hỗ trợ và khiếu nại",
            "Bạn có thể gửi yêu cầu kiểm tra qua /hotro khi:\n"
            "• Không thấy đơn đã mua qua link của bot.\n"
            "• Số hoàn dự kiến có vẻ sai.\n"
            "• Đơn bị ghi nhận cho người khác hoặc sai link.\n"
            "• Đơn chờ xác minh lâu bất thường.\n"
            "• Câu hỏi về dữ liệu cá nhân hoặc vấn đề khác.\n\n"
            "<b>Cách xử lý</b>\n"
            "• Mỗi yêu cầu có mã số và trạng thái, bạn xem lại được trong /hotro.\n"
            "• Người vận hành kiểm tra bằng dữ liệu link, mã theo dõi và báo cáo Shopee, rồi trả lời qua bot.\n"
            "• Việc phụ thuộc Shopee sẽ ở trạng thái «Chờ Shopee»; bot không tự kết luận bạn sai khi Shopee chưa "
            "có kết quả.\n"
            "• Bot không bảo đảm Shopee chấp nhận mọi khiếu nại và chưa cam kết thời hạn xử lý cụ thể.\n"
            "• Khi kết luận, bot ghi lý do và báo cho bạn.",
        ),
    )


DRAFT_SECTIONS = draft_sections(retention.DEFAULTS)
