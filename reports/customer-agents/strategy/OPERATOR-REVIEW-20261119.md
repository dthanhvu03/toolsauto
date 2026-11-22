# Chiến lược thử48h và nhiệm vụ đầu tiên — 19/11/2026

Đây là kết quả rà soát nội bộ sau hai lượt gọi AI của khung18h. Chưa đăng/gửi các nháp này. RawAI trong 2026-11-19-18.json được giữ nguyên để đối chiếu.

## Kết luận review
Đầu ra SQL sẵn sàng. Bản nháp AI cần sửa: quá chung chung, không trả lời một vấn đề cụ thể; có câu gọi Cashbot là công cụ tạo link thanh toán/giao dịch, sai nghiệp vụ. Không chuyển các nháp raw vào sender/queue. Chỉ bản đã biên tập dưới đây được chuẩn bị cho chủ vận hành xem.

Không đồng nhất tiến độ chiến lược mới0 với kết quả cả bot: mốc bắt đầu mới là23:03:51 ngày19/11VN. Cửa sổ24h/7ngày là dữ liệu nền; nguồn first-touch không đo perpost/quan hệ nhân quả. Tỷ lệ có đơn trong cohort không tự thành conversion24h.

## Thử nghiệm1 — CapCut: giúp đúng lỗi, mở hội thoại
- Đối tượng: bài mới của người dùng hỏi cụ thể về xuất/lưu video hoặc thông báo tài nguyên Pro; loại seller/tuyển dụng/crack/dispute.
- Hành động đang triển khai: lane help_first trong worker; không gắn link hay lời bán, không giả kinh nghiệm cá nhân. Trả lời lại nếu khách chủ động hỏi tiếp. DMAnLinh vẫn tắt.
- Giả thuyết cần kiểm: hỏi làm rõ lỗi và thiết bị có tạo phản hồi hai chiều hữu ích hơn cách chỉ tìm người hỏi mua không.
- KPI mục tiêu48h:3cuộc hỏi đáp có phản hồi; chưa phải kết quả có sẵn và chưa chứng minh thành lead/đơn.
- Giữ/bỏ: sau48h xem số câu trả lời thực và mức phù hợp; không có hội thoại thì rà lại query/ngữ cảnh, không tăng quota hoặc spam cùng người.

Nháp trợ giúp, chỉ dùng khi đúng câu hỏi:
> Bạn thấy thông báo gì khi CapCut dừng xuất video? Bạn gửi nguyên văn lỗi và cho biết đang dùng điện thoại hay máy tính nhé; đừng gửi thông tin đăng nhập.

Chỉ đưa thông tin sản phẩm sau khi người hỏi thể hiện nhu cầu mua phù hợp; kiểm lại giá/mô tả trong bot. Không suy “không xuất được” thành “phải mua Pro”.

## Thử nghiệm2 — Cashbot: giải thích bước dùng thật
- Đối tượng: người đang hỏi cách tiết kiệm/mã giảm giá cho món Shopee cụ thể.
- Hành động: ưu tiên query có nhu cầu rõ, trả lời gắn với món/vấn đề; giải thích linkmua+sốhoàndựkiến, không gọi đó là link thanh toán.
- Giả thuyết cần kiểm: chỉ rõ bước dán link sản phẩm và kỳ vọng số hoàn có giúp khách vào dùng thay vì chỉ xem lời giới thiệu không.
- KPI mục tiêu48h:2cuộc hỏi đáp có phản hồi; mục tiêu chung cả nhóm2khách mới dùng thật. Tách khách vào/dùng/đơn, không tính reply thành khách.
- Giữ/bỏ: chỉ giữ cách giải thích nếu có khách dùng thật hoặc phản hồi hữu ích; không có tín hiệu thì đổi vấn đề/nội dung sau khi xem dữ liệu, không bịa số hoàn.

Nháp trả lời, cần đúng account/link đã hỗ trợ khi xuất bản:
> Bạn đang cần mã cho món nào? Nếu muốn so thêm số hoàn dự kiến, bạn có thể dán link sản phẩm Shopee vào bot để xem trước khi mua. Số hoàn cuối cùng còn phụ thuộc đơn hợp lệ và đối soát.

## Nhiệm vụ vận hành
1. Tìm cơ hội: buyer và help_first, tối đa6lượt tìm/tài khoản/lượtquét, xoay query, giữ hạn mức cũ.
2. Tương tác: xử lý câu hỏi mới, chuyển ca tiền/đơn/bảo hành; không tự nhắn người lạ.
3. Đo kết quả: SQL24h/7ngày và từ lúc bắt đầu đến mốc48h, loại admin/test đã cấu hình, tách hai bot/nguồn.
4. Chuyển đổi: mỗi6giờ chọn tối đa2việc/thử nghiệm dựa số liệu, nêu điều kiện giữ/bỏ. Đề xuất chưa tự sửa vận hành.
5. Nội dung: mỗi6giờ2nháp cụ thể, qua kiểm chất lượng và duyệt nội bộ; nháp không phải bài đã gửi.

Mục tiêu5hội thoại và2kháchdùngthật là mục tiêu thử nghiệm. Cùng một người có thể xuất hiện ở nhiều cuộc hoặc hai bot; hiện chưa khử trùng xuyên kênh và chưa có đủ nhãn đánh giá chất lượng hội thoại.
