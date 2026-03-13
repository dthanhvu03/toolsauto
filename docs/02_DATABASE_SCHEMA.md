# Database Schema (SQLite via SQLAlchemy)

## Các Bảng Chính (Tables)

### 1. `accounts`

Lưu trữ thông tin cấu hình tài khoản MXH.

- `id` (PK)
- `name` (TEXT, unique): Tên gợi nhớ
- `platform` (TEXT): Nền tảng (mới hỗ trợ `facebook`)
- `is_active` (BOOL): Trạng thái (để bật/tắt tự động hóa)
- `profile_path` (TEXT, unique): Đường dẫn tới thư mục browser profile
- **Login Lifecycle Machine**:
  - `login_status` (TEXT): `NEW`, `LOGGING_IN`, `ACTIVE`, `INVALID`
  - `login_started_at`, `login_process_pid`, `last_login_check`, `login_error`
- **Limits & Breakers**:
  - `daily_limit` (INT): Số bài đăng tối đa/ngày
  - `cooldown_seconds` (INT): Khoảng cách tối thiểu giữa 2 bài
  - `last_post_ts` (INT): Lần cuối đăng bài
  - `consecutive_fatal_failures` (INT): Đếm lỗi liên tiếp để ngắt auto
- Timestamps: `created_at`, `updated_at`

### 2. `jobs`

Trung tâm lưu trữ các tác vụ đăng bài, AI sinh caption và tracking.

- `id` (PK)
- `platform` (TEXT)
- `account_id` (FK -> accounts.id)
- `media_path` (TEXT): Đường dẫn file media gốc
- `caption` (TEXT): Nội dung text
- `schedule_ts` (INT): Thời gian lên lịch
- **State Tracking**:
  - `status` (TEXT): Lưu trạng thái luồng (`DRAFT`, `PENDING`, `RUNNING`, `DONE`, `FAILED`, `CANCELLED`)
  - `is_approved` (BOOL): Đã được duyệt chưa (đối với AI DRAFT)
  - `tries` / `max_tries` (INT): System retry limit.
  - `last_error`, `error_type` (`RETRYABLE` / `FATAL`)
- **Idempotency & Processing**:
  - `external_post_id` (TEXT): ID của post trả về từ Facebook
  - `dedupe_key` (TEXT): Hash chống upload trùng trong bulk
  - `batch_id` (TEXT): UUID gom nhóm upload
  - `processed_media_path` (TEXT): Đường dẫn sau khi xử lý (vd encode FFmpeg)
- **Post-Publish Metrics**:
  - `post_url` (TEXT): Link đến post
  - `view_24h` (INT): Số lượt view cập nhật sau 24h
  - `metrics_checked` (BOOL), `last_metrics_check_ts` (INT)
- **Link Tracking (Affiliate)**:
  - `tracking_code` (TEXT): Mã rút gọn (ví dụ uuid[:8])
  - `tracking_url` (TEXT): Link trỏ qua local domain `/r/code`
  - `affiliate_url` (TEXT): Link gốc tới Shopee/Lazada...
  - `click_count` (INT): Đếm số lượt nhấp
- `auto_comment_text` (TEXT): Mẫu bình luận chèn link sau khi đăng.
- Timestamps: `locked_at`, `last_heartbeat_at`, `started_at`, `finished_at`, `created_at`

### 3. `system_state`

Trạng thái global của Worker để điều khiển từ Dashboard.

- `id` (PK) = 1 (Luôn chỉ có 1 row)
- `worker_status` (TEXT): `RUNNING` hoặc `PAUSED`
- `heartbeat_at` (INT): Worker báo danh sống sót (Unix TS)
- `current_job_id` (INT): ID job đang xử lý
- `safe_mode` (BOOL): Chế độ an toàn (chạy chậm, giả lập human hơn)
- `pending_command` (TEXT): `REQUEST_EXIT`, `RESTART_REQUESTED`
- `worker_started_at` (INT): Thu thập Uptime

### 4. `job_events`

Lưu log dạng timeline của từng job.

- `id` (PK)
- `job_id` (FK -> jobs.id)
- `ts` (INT)
- `level` (TEXT): INFO, WARN, ERROR
- `message` (TEXT)
- `meta_json` (TEXT)

## Indexes & Constraints

Hệ thống sử dụng các 복 hợp Index để tối ưu Polling trên bảng `jobs`:

- `idx_jobs_status_schedule` (status, schedule_ts): Để tìm Job đến giờ chạy nhanh nhất.
- `idx_jobs_account_status` (account_id, status): Kiểm tra limit daily account.
- `idx_jobs_metrics` (status, metrics_checked, finished_at): Để query job cần rescanning metrics.
- `idx_jobs_dedupe_unique`, `idx_jobs_tracking_unique`: Unique Partial index.
