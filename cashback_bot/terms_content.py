"""Dự thảo điều khoản khách (PLAN-077). Admin tạo bản nháp từ mẫu này rồi mới công bố.

V1 công bố 2026-10-24. V2 (PLAN-083): bot có thêm kênh Zalo; chỉ đổi hai câu nói «tài khoản Telegram» thành
«tài khoản Telegram hoặc Zalo». Không đổi quyền lợi, cách tính hay trạng thái chi trả.

Viết theo đúng chức năng bot đang chạy (audit PLAN-077 mục 3). Không hứa thời hạn rút, mức rút hay cam kết
chi trả. Khi chức năng đổi (mở ví, hạng thành viên), phải ra phiên bản mới, không sửa bản đã công bố.
Mỗi mục là một tin Telegram, giữ dưới 3.500 ký tự.
"""

from __future__ import annotations

DRAFT_VERSION = "V2"
DRAFT_TITLE = "Điều khoản sử dụng chương trình hoàn tiền"

# (mã, tiêu đề nút, nội dung HTML Telegram)
DRAFT_SECTIONS: tuple[tuple[str, str, str], ...] = (
    (
        "chung",
        "📋 Điều khoản chung",
        "<b>1. Chương trình là gì</b>\n"
        "Bot giúp bạn tạo link mua hàng Shopee có gắn mã theo dõi của chương trình Shopee Affiliate do người "
        "vận hành bot tham gia. Khi đơn đủ điều kiện, Shopee trả hoa hồng cho người vận hành; bot dự kiến chia "
        "lại một phần cho người tạo link.\n\n"
        "• Bot <b>không phải</b> dịch vụ của Shopee và không đại diện Shopee.\n"
        "• Bot không thu phí. Bạn mua và thanh toán trực tiếp trên Shopee; giá, khuyến mãi, giao hàng, đổi trả "
        "do Shopee và người bán quyết định.\n\n"
        "<b>2. Trạng thái chi trả hiện tại</b>\n"
        "• <b>Ví hoàn tiền và chi trả chưa mở.</b> Bot chưa chuyển tiền cho ai và chưa nhận yêu cầu rút.\n"
        "• Khi mở, điều kiện nhận, thời điểm, mức rút và cách chuyển tiền sẽ được công bố trong một phiên bản "
        "điều khoản mới. Trước đó, số tiền bot hiển thị chỉ là dự kiến.\n\n"
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
        "• Mỗi link bot tạo có một mã theo dõi (Sub ID) riêng, gắn với tài khoản Telegram hoặc Zalo đã gửi link cho bot.\n"
        "• Đơn mua qua link đó được ghi nhận cho <b>người đã tạo link</b>, kể cả khi người khác bấm link và "
        "đặt hàng. Chia sẻ link không chuyển quyền nhận hoàn tiền sang người mua.\n"
        "• Muốn tự nhận hoàn tiền, mỗi người tự gửi link sản phẩm cho bot để có link riêng.\n"
        "• Bot chỉ biết đơn khi Shopee báo về trong báo cáo Affiliate có đúng Sub ID của link.\n\n"
        "<b>2. Số hoàn dự kiến</b>\n"
        "• Số hiện khi tạo link là <b>ước tính</b> theo giá tham khảo và mức hoa hồng Shopee công bố lúc đó, "
        "không phải số chắc chắn nhận.\n"
        "• Số thật có thể thấp hơn, cao hơn hoặc bằng 0 vì: số tiền bạn thực trả (voucher, xu, giảm giá), huỷ "
        "hoặc trả hàng, chính sách và điều chỉnh hoa hồng của Shopee, Shopee từ chối hoặc gắn gian lận.\n"
        "• Cách tính hiện hành trừ trước các khoản dự phòng phí và thuế do bot tự đặt để ước tính, rồi chia "
        "một phần cho bạn. Khoản dự phòng <b>không phải</b> số thuế bạn phải nộp.\n\n"
        "<b>3. Cách tính của từng link</b>\n"
        "• Mỗi link lưu lại cách tính lúc tạo. Bot đổi cách tính thì link cũ vẫn giữ cách tính cũ.\n"
        "• Giữ cách tính không có nghĩa là giữ số tiền: số tiền vẫn theo hoa hồng Shopee thực tế của đơn.\n\n"
        "<b>4. Các bước của một đơn</b>\n"
        "1) Shopee ghi nhận đơn → 2) hoa hồng chờ Shopee xác minh → 3) Shopee duyệt hoa hồng → "
        "4) Shopee thanh toán hoa hồng cho người vận hành → 5) khoản hoàn tiền mới có thể được chi.\n"
        "Hiện bot chưa có nguồn xác nhận bước 3–4 và chưa mở bước 5.",
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
        "kiểm tra lại qua /hotro.\n"
        "• Nếu Shopee giảm hay thu hồi hoa hồng sau khi đã ghi nhận, khoản dự kiến giảm theo. Cách xử lý khoản "
        "đã chi (nếu sau này có chi trả) sẽ được quy định trước khi mở ví.",
    ),
    (
        "du_lieu",
        "🛡 Dữ liệu cá nhân",
        "<b>Bot lưu những gì</b>\n"
        "• Mã tài khoản Telegram hoặc Zalo, tên người dùng hoặc tên hiển thị, thời điểm dùng bot.\n"
        "• Link Shopee bạn gửi, thông tin sản phẩm, link bot tạo và mã theo dõi (Sub ID).\n"
        "• Thông tin đơn qua link từ báo cáo Shopee Affiliate: mã đơn, tên sản phẩm, trạng thái, hoa hồng.\n"
        "• Nội dung bạn gửi trong yêu cầu hỗ trợ.\n"
        "• Tin nhắn không phải link sản phẩm không được lưu nội dung.\n"
        "• Bot không hỏi mật khẩu, OTP, cookie Shopee hay thông tin thẻ. Đừng gửi những thông tin này.\n\n"
        "<b>Dùng để làm gì</b>\n"
        "Tạo link, ghi nhận đơn cho đúng người, tính số hoàn dự kiến, đối soát với Shopee, trả lời hỗ trợ và "
        "chống lạm dụng.\n\n"
        "<b>Ai xem được</b>\n"
        "Chỉ người vận hành bot. Khách khác không xem được dữ liệu hay yêu cầu hỗ trợ của bạn. Bot không bán "
        "dữ liệu.\n\n"
        "<b>Bảo vệ và lưu giữ</b>\n"
        "• Dữ liệu nằm trên máy chủ của người vận hành, bản sao lưu được giới hạn quyền đọc, nhật ký hệ thống "
        "che mã bí mật.\n"
        "• Dữ liệu về đơn và tiền được giữ để đối soát và đáp ứng nghĩa vụ pháp luật; thời gian lưu cụ thể sẽ "
        "được công bố khi chốt chính sách lưu trữ.\n\n"
        "<b>Quyền của bạn</b>\n"
        "Bạn có thể yêu cầu xem, sửa hoặc xoá dữ liệu của mình qua /hotro → 🛡 Dữ liệu cá nhân. Dữ liệu tài "
        "chính cần giữ theo luật hoặc để giải quyết tranh chấp có thể chưa xoá được ngay; bot sẽ giải thích lý do.",
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
