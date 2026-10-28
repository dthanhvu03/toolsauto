# Cashback bot: timeout và chống trùng (2026-10-28)

Rà soát theo yêu cầu chủ bot. Mô tả cơ chế đang chạy, hai chỗ hở đã vá, và khung tối thiểu để mang sang bot khác.

## 1. Timeout

Mọi lời gọi mạng đều có giới hạn chờ:

| Gọi tới | Giới hạn chờ |
|---|---|
| Telegram (nhận / gửi tin) | 35 giây |
| Zalo (nhận / gửi tin) | 45 giây |
| AddLiveTag sản phẩm | 20 giây, các lệnh cách nhau ít nhất 0,35 giây |
| AddLiveTag deal / lịch sử giá | 20–30 giây, tối đa 500 món / phút |
| RioHub, Shopee | 20 giây |
| sendChatAction | 10 giây, lỗi thì bỏ qua |

Lỗi gửi tin chia 5 loại (`telegram_api.classify_delivery_error`; Zalo dùng chung các loại này):

| Loại | Nghĩa | Xử lý |
|---|---|---|
| `offline` | Chưa kết nối được (DNS, mất mạng) | Tin chắc chắn chưa đi: gửi lại, không tính lượt thử |
| `ambiguous` | Hết giờ hoặc đứt kết nối giữa chừng | Bên kia có thể đã nhận: xem mục 3 |
| `rate_limited` | HTTP 429 | Chờ đúng `Retry-After`, dừng cả vòng gửi |
| `permanent` | HTTP 4xx | Không thử lại. Riêng 403 thì đánh dấu khách đã chặn bot |
| `transient` | HTTP 5xx | Thử lại giãn cách 30, 60, 120… giây, tối đa 5 lần |

Không giữ transaction SQLite trong lúc gọi mạng. Lời gọi chậm (RioHub, soạn deal) chạy ở luồng nền, kết quả đi qua hàng đợi.

## 2. Chống trùng

| Nguy cơ | Cách chặn |
|---|---|
| Telegram gửi lại cùng một update | Offset chỉ tiến lên sau khi xử lý xong. Lỗi nhiều lần thì cách ly (`failed_updates`) rồi mới tiến |
| Xử lý lại sau restart | Câu trả lời lưu vào `outbound_messages` theo `update_id` trước khi gửi; gặp lại thì gửi câu đã lưu |
| Một tin tạo hai link | `link_requests.telegram_update_id UNIQUE`; gặp lại thì `_render_existing` trả link cũ |
| Zalo gửi lại cùng một tin | `zalo_inbox.message_id UNIQUE` (INSERT OR IGNORE); tin đã qua trạng thái `received` thì bỏ qua |
| Thông báo gửi hai lần | `admin_notifications.event_key UNIQUE`, ví dụ `deals:<ngày>:trua:<khách>`, `tiktok_link:<sub_id>` |
| Hai vòng gửi cùng lấy một tin | `UPDATE … SET status='sending' WHERE status IN ('pending','retry')`, chỉ gửi khi đúng 1 dòng bị sửa |
| Bấm rút tiền hai lần | `idempotency_key = cb:<khách>:<query_id>` UNIQUE, mỗi khách chỉ một yêu cầu rút đang mở |
| Hai lượt đồng bộ Shopee chạy cùng lúc | Khoá có hạn (lease) trong `shopee_sync_state`; lượt mất khoá không ghi kết quả |
| Hai tiến trình bot cùng chạy | `flock` trên `/tmp/cashback_bot.lock`, `/tmp/cashback_zalo.lock` |
| Việc định kỳ chạy hai lần | Trạng thái theo ngày trong `bot_state` (`deals:<ngày>`: building → draft → sent) cộng `event_key` của từng khách |

## 3. Không rõ tin đã đi hay chưa (`ambiguous`)

| Loại tin | Chọn | Lý do |
|---|---|---|
| Trả lời khách vừa nhắn (thẻ link…) | Gửi lại, ít nhất một lần | Trùng thẻ link thì vô hại; mất thì khách không có link |
| Thông báo bot tự gửi khách | Không gửi lại (tối đa một lần), ghi `unknown` để admin xem | Hai tin «có đơn mới» làm khách hoang mang |
| Tin admin | Gửi lại | Chấp nhận được |
| Tin đang `sending` lúc bot dừng | Khởi động: `recover_sending` chuyển `unknown`, không tự gửi lại | |
| Một câu trả lời Zalo nhiều tin | Lưu phần chưa gửi; lần sau chỉ gửi tiếp phần còn lại | |

## 4. Chỗ hở đã vá (2026-10-28)

1. **Việc tạo link TikTok mất khi restart.** Việc chỉ nằm trong ThreadPoolExecutor (RAM).
   - Nay ghi `bot_state.tiktok_job:<sub_id>` trước khi chạy và xoá sau khi thẻ vào hàng đợi.
   - Khởi động (`service.resume_tiktok_jobs`), mỗi bot chỉ lấy khách kênh mình:
     - thẻ đã vào hàng đợi: chỉ dọn job;
     - link đã lưu: gửi thẻ có sẵn, không gọi RioHub lần hai;
     - job quá 30 phút: bỏ, vì tin «đang tạo» đã dặn khách gửi lại sau 1 phút;
     - còn lại: làm tiếp.
2. **Zalo kẹt ở `received` khi tiến trình bị tắt ngang.** Zalo không gửi lại tin cũ. Khởi động (`ZaloChannel.recover_inbox`):
   - đã có câu trả lời lưu sẵn: chuyển `retry` để gửi nốt;
   - chưa có câu trả lời (nội dung tin không được lưu): nhắn khách gửi lại, nếu tin chưa quá 6 giờ;
   - cũ hơn 6 giờ: bỏ.

Còn lại, chấp nhận được:
- Nút chỉ trả toast thì không vào outbox. Bot chết đúng giữa lúc xử lý và tiến offset thì nút bật/tắt có thể đảo hai lần.
- Trả lời Zalo bị `ambiguous` thì gửi lại, khách có thể thấy hai thẻ giống nhau.

## 5. Khung tối thiểu cho bot khác

1. Mỗi tin vào có mã duy nhất trong DB (UNIQUE / INSERT OR IGNORE).
2. Lưu kết quả trước khi gửi; gặp lại mã thì gửi lại kết quả đã lưu.
3. Mỗi việc phụ có khoá chống trùng (`event_key`, `idempotency_key`).
4. Giữ chỗ bằng `UPDATE … WHERE status = …` và kiểm tra đúng 1 dòng bị sửa.
5. Phân loại lỗi: offline / ambiguous / permanent / rate_limited / transient.
6. Việc dính tiền (giao hàng, trừ kho, chi trả) không bao giờ tự làm lại khi `ambiguous`: đánh dấu chờ người kiểm.
7. Việc chạy nền ghi vào DB trước khi chạy, khởi động thì làm tiếp hoặc dọn.
