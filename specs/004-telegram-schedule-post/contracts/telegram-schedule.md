# Contract: Hẹn giờ trong Telegram

Bề mặt là nút dưới tin video, nút trên bài đang chờ, và một lệnh gõ giờ. Chat trả lời tiếng Việt. Giờ trong câu trả lời là giờ Việt Nam, dạng giờ và ngày.

## Hẹn từ video sẵn sàng

Chủ kênh bấm hẹn giờ, chọn kênh, rồi chọn một giờ gợi ý hoặc gõ lệnh.

- Đủ lời bài, kênh có trong danh sách, giờ trong cửa sổ, còn suất: tạo một lịch. Chat nói tên kênh và giờ đã chọn. Trước giờ đó bài chưa đăng.
- Thiếu lời bài, kênh lạ, giờ đã qua, giờ không đọc được, sớm hơn 10 phút, xa hơn 30 ngày, hoặc hết suất: không tạo lịch, nói lý do. Có mẫu gõ khi giờ không đọc được.
- Đã có lịch cùng video cùng kênh: sửa giờ, không tạo lịch thứ hai.

Xếp vào kênh mà không bấm hẹn giờ vẫn vào hàng chờ như hiện tại và không hỏi giờ.

## Trên bài đang chờ

- Ba giờ gợi ý và lệnh gõ giờ sửa đúng bài đó.
- Hủy lịch khi bài chưa đăng: bài biến mất khỏi hàng và không tự đăng.
- Bài đã đăng: đổi giờ hoặc hủy không đổi gì, chat nói bài đã đăng.
- Đăng ngay vẫn đăng mà không hỏi giờ.

## Lệnh gõ giờ

Một lệnh, kèm mã bài đang chờ, rồi ngày và giờ.

- Đủ và hợp lệ: sửa lịch, chat xác nhận giờ mới.
- Thiếu mã, thiếu giờ, hoặc giờ không hợp lệ: không gọi nơi đăng.
- Mã không thấy: không tạo bài mới.

## Ai được bấm

Chỉ cuộc chat chủ kênh đã nối. Chat khác không tới được các nút và lệnh này.
