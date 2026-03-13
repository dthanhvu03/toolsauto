# Luồng Hoạt Động Của Worker 24/7 (Workflow)

Worker (`worker.py`) là trái tim của việc tự động hóa, chạy ngầm liên tục qua vòng lặp. Cấu hình độ trễ (tick) mỗi vòng lặp dựa trên biến `WORKER_TICK_SECONDS` và xử lý từng job một, cùng với các task tự động dọn dẹp hệ thống.

## Vòng Lặp Chính (Main Loop)

Mỗi **tick** của vòng lặp thực hiện theo trình tự an toàn sau, và nếu gặp lỗi Crash sẽ tự động recover ở lần chạy lại.

### 1) Đồng bộ State & Heartbeat 🫀

- Lấy `system_state` từ DB. Cập nhật `heartbeat_at` và `current_job_id` để UI biết worker vẫn sống.
- Kiểm tra các Lệnh điều khiển (Pending Commands) như `REQUEST_EXIT` hoặc xem UI có bấm lệnh `PAUSED` tạm dừng không.

### 2) Tìm và Xử Lý Job Công Khai Đã Đến Hạn (PENDING) 🚀

Worker ưu tiên tìm các bài viết thực tế cần đăng trước:

- Lấy job: `SELECT WHERE status=PENDING AND schedule_ts <= now` + các Rule check về Limit, Cooldown của account.
- Xử lý màng lọc an toàn (Safe guard): Không đăng nếu caption chứa thẻ `[AI_GENERATE]`.
- Ném sang `Dispatcher.dispatch(job)` để gọi Adapter (VD: `FacebookAdapter.publish()`).
- Truy xuất `publish_result`:
  - **OK**: Lưu link, đổi status thành `DONE`, gửi Telegram Notification thành công.
  - **FAIL**: Retry (chuyển về `PENDING` thay đổi giờ theo Backoff strategy) hoặc max try -> đổi thành `FAILED`, gửi cảnh báo lỗi qua Telegram và log Error. Nếu Adapter báo Account bị vô hiệu hóa -> đổi Account sang `INVALID`.

### 3) Tìm và Xử Lý DRAFT Job (AI Generation) 🤖

Nếu không có Job nào cần đăng, nó kiểm tra các bài DRAFT cần chạy Sinh nội dung AI:

- Gửi yêu cầu qua `ContentOrchestrator` => Tương tác RPA Gemini.
- Nếu thành công: Build caption có chứa HashTags + Tracking Salt Code. Báo Notifier `DRAFT_READY` qua Telegram (tích hợp nút bấm Inline Button `Duyệt nhanh`). Trạng thái vẫn giữ là `DRAFT` chờ User confirm.
- Nếu thất bại: Lỗi sẽ bị ghi vào `last_error`, bỏ qua chu kỳ này, retry thẳng vòng tick sau mà không limit retry.

### 4) Dọn Dẹp (`CleanupService`) 🧹

Xóa các file tạm (`*.tmp`) đã cũ hoặc xóa file Media (video/văn bản) đã qua xử lý nếu `Job` mang cờ trạng thái bị `CANCELLED`, `DONE` sau khi publish thành công để tránh tốn dung lượng ổ đĩa.

### 5) Quét Lại Views Kênh (`MetricsChecker`) 📊

Quét 1 `DONE` job cần đo lường lại Traffic sau khi đăng khoảng >24 tiếng. Quá trình kiểm tra views này sử dụng cùng Browser session, đi đếm lượt Click/lượt Views từ URL gốc. Tránh việc quét lại liên tục, bảng `jobs` bật cờ `metrics_checked = True` khi xong.

### 6) Gửi Tổng Hợp Ngày (`Daily Summary`) 📝

Vào 23:00 hằng ngày, tổng kiểm kê số bài Đăng thành công/thất bại, lượng Views thay đổi tổng ra sao, lượt Click Affiliate đạt mức nào -> Bắn báo cáo tới Telegram. Kênh báo giúp User bám sát kết quả.

## Cơ Chế Backoff & Crash Recovery

- **Stale Heartbeat check**: Chạy lúc bắt đầu bật worker script. Quét `RUNNING` jobs có `heartbeat_at` cũ, gỡ khóa về `PENDING`.
- **Lỗi Retryable**: Thử lại job sau `+5m` (lần 1), `+15m` (lần 2).
- **Lỗi Fatal**: Ngưng try và lập tức bắn Failed, gửi Telegram. Nếu Session / Cookie Adapter gặp vấn đề -> đánh dấu Account Invalid. Đẩy về dashboard yêu cầu User Verify Login thủ công lại.
