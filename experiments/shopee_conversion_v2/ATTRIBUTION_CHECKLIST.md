# Attribution verification — checklist T+24h / T+48h

Chưa đến mốc kiểm tra. Không tạo click mới. Không mở debugger trong lúc chờ.

Mẫu: `sub_id=G3lkg1JK`

- T0 mở link thật: `2026-10-22T01:37:36.843939Z`
- T+24h: `2026-10-23 08:37:36` giờ Việt Nam
- T+48h: `2026-10-24 08:37:36` giờ Việt Nam

Baseline tại thời điểm lập checklist:

- Click 30 ngày: 3 dòng cũ, `sub_id="----"`
- Click sau T0: 0
- Filter `sub_id=G3lkg1JK`: 0
- Conversion sau T0: 0

## Khi đến từng mốc

1. Mở profile POC `C:\Users\Admin\chrome-profiles\shopee-affiliate-poc` bằng tay, đăng nhập sẵn. Không thêm cờ debug nếu chỉ xem UI.
2. Vào Click Report, timezone `Asia/Saigon`.
3. Đếm tổng click toàn tài khoản trước, so với baseline 3.
4. Lọc khoảng thời gian từ T0 đến hiện tại.
5. Lọc đúng `sub_id=G3lkg1JK`. Không dùng filter `utm_content`.
6. Kiểm tra phân trang. Ghi số trang và số dòng.
7. Vào Conversion Report, tìm conversion có `utm_content` hoặc sub id đúng `G3lkg1JK` sau T0.
8. Đóng trình duyệt. Không để cổng 9222 mở.

## Cách đọc kết quả

- Có click mới và sub id khớp: GO Click Attribution.
- Có click mới nhưng sub id trống hoặc `----`: điều tra cách Shopee lưu tracking, chưa sửa link bot.
- Không có click mới: chưa kết luận link sai. Ghi nhận độ trễ, self-click và điều kiện ghi nhận.
- Conversion Report có sub id khớp chính xác: GO Conversion Attribution cho mẫu đó, dù Click Report chưa khớp.
- Sau 48 giờ vẫn không có dữ liệu: làm một phép thử đối chứng bằng Custom Link chính thức, một lượt, không click hàng loạt.
