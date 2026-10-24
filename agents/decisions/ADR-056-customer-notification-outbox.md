# ADR-056 — Thông báo đơn hàng cho khách qua hàng đợi chung, sinh trong transaction ghi đơn

| | |
|---|---|
| Trạng thái | Accepted (PLAN-079), chưa triển khai production |
| Ngày | 2026-10-24 |
| Liên quan | ADR-051 (trạng thái hoa hồng), ADR-053 (snapshot), ADR-054 (hỗ trợ), ADR-055 (chi trả) |

## Bối cảnh
- Tin cho khách (ví, chi trả, hỗ trợ) và tin cho admin đi chung bảng `admin_notifications`.
- Bảng này chỉ được xả khi thông báo admin bật. Khi gửi lỗi, bot thử lại ngay mỗi vòng, không đọc `retry_after`, không phân biệt khách chặn bot, không lưu mã tin.
- Chưa có thông báo đơn hàng chủ động. Khách không tự xem được đơn của mình.

## Quyết định
1. **Một hàng đợi, một bộ gửi:**
   - giữ `admin_notifications`, thêm cột `audience` (admin / customer), `category` (order_new, order_update, support, wallet), `next_retry_at`, `telegram_message_id`, `reply_markup_json`, `source_ref`;
   - trạng thái: pending, sending, sent, retry, failed, suppressed, unknown;
   - `notify_dispatch.Dispatcher` thay cho `flush_pending` cũ, dùng cho cả tin admin và tin khách.
2. **Sinh sự kiện trong transaction ghi đơn:**
   - `TrackingRepository.conversion_hooks` được gọi trong `record_conversion_snapshot`, sau khi ghi lịch sử thay đổi, bọc SAVEPOINT;
   - dữ liệu đơn rollback thì không có tin; hook lỗi thì không làm hỏng việc ghi đơn.
3. **Khoá chống trùng theo sự kiện nghiệp vụ:** `conversion:<id>:first_matched` cho đơn mới, `conversion:<id>:changes:<id thay đổi lớn nhất>` cho cập nhật. Không khoá theo mã đơn, vì một đơn có nhiều thay đổi hợp lệ.
4. **Người nhận và nội dung:**
   - người nhận là người tạo link có Sub ID được ghi nhận; có xung đột gán thì không gửi;
   - tiền hoàn tính theo snapshot của link;
   - thay đổi hoa hồng dưới ngưỡng (< 500đ và < 10%) không báo; về 0 thì luôn báo;
   - mỗi lần đồng bộ, mỗi đơn tối đa một tin.
5. **Cờ và tuỳ chọn:**
   - `CUSTOMER_NOTIFICATIONS_ENABLED` (mặc định tắt) chỉ quyết định thông báo đơn hàng;
   - tin trả lời hỗ trợ và tin chi trả vẫn gửi như trước, theo tuỳ chọn của khách;
   - sự kiện phát sinh khi cờ tắt, khách đã tắt loại tin, khách đã chặn bot, hoặc khách chưa bắt đầu bot: ghi trạng thái `suppressed` kèm lý do, không bao giờ gửi. Nhờ vậy bật cờ không gửi dồn tin cũ;
   - lúc gửi kiểm tra lại cờ, tuỳ chọn và tin quá cũ (> 72 giờ).
6. **Không gửi dồn đơn lịch sử:**
   - `customer_notify_baseline_at` được đặt lần đầu bot khởi động khi cờ đã bật;
   - đơn mua trước mốc không được báo "đơn mới", vẫn xem được ở `/donhang`;
   - thay đổi thật xảy ra sau mốc vẫn được xét gửi.
7. **Gửi và thử lại:**
   - 429: thử lại sau `retry_after`; 5xx: giãn cách 30 giây × 2ⁿ, tối đa 5 lần;
   - 4xx: `failed`, nếu là 400/403 thì đánh dấu khách đã chặn bot; khách nhắn lại thì bỏ đánh dấu;
   - hết giờ hoặc mất kết nối với tin khách: `unknown`, không tự gửi lại;
   - bot dừng giữa lúc gửi (dòng kẹt ở `sending`): lúc khởi động chuyển `unknown`;
   - admin gửi lại tay ở 🔔. Chọn tối đa một lần cho tin khách, không hứa đúng một lần.

## Hệ quả
- Gate A không gửi thêm tin nào cho khách (cờ tắt).
- Tin hỗ trợ giờ không còn phụ thuộc cờ thông báo admin.
- Muốn có tin gần thời gian thực cần tự đồng bộ Shopee định kỳ: tách thành PLAN riêng.
