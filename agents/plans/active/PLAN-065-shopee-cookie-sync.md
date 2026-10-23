# PLAN-065 — Đồng bộ Shopee Affiliate qua Cookie (J2TEAM / Header String)

| | |
|---|---|
| Trạng thái | **APPROVED (user, 2026-10-23)** — Code & Tests hoàn thành 100% |
| Executor | Antigravity |
| Bối cảnh | Tài khoản Shopee Affiliate cá nhân không có quyền Shopee Open API (GraphQL trả lỗi 10020/10035). Thay vì mở Chrome trên Windows, bot tự đồng bộ trực tiếp trên server qua cookie xác thực của trang `affiliate.shopee.vn`. |
| Phạm vi | `cashback_bot/` (`shopee_client.py`, `shopee_cookie.py`, `shopee_sync.py`, `admin_ui.py`, `admin_policy.py`, `admin_stats.py`, `admin_notify.py`, `db.py`, `telegram_api.py`, `poller.py`, `service.py`), `storage/db/config/`, unit tests. |

---

## ⚠️ Rủi ro & Nguyên tắc an toàn (Đã báo và được user duyệt)

1. **Bảo mật Cookie nhạy cảm**:
   - Cookie Shopee Affiliate mở được toàn bộ tài khoản (kể cả xem hoa hồng, thông tin thanh toán).
   - Lưu trữ riêng trong file `storage/db/config/shopee_affiliate_cookies.json` với phân quyền `0o600` (chỉ tài khoản sở hữu file đọc/ghi).
   - Tuyệt đối **không** ghi cookie vào log, **không** commit vào git (`storage/` đã nằm trong `.gitignore`).
   - Khuyến nghị user dùng tài khoản affiliate riêng, không dùng chung với tài khoản mua hàng Shopee.
2. **Xoá tin nhắn chứa Cookie trên Telegram**:
   - Ngay khi admin dán JSON / chuỗi cookie vào chat, bot phân tích kiểm tra và gọi `deleteMessage` của Telegram để xoá ngay tin nhắn khỏi lịch sử chat, giảm thiểu rủi ro lưu vết.
3. **Độ ổn định API nội bộ**:
   - Đây là API nội bộ của trang web (`affiliate.shopee.vn/api/v3/...`), không phải Open API chính thức.
   - Giữ tần suất đồng bộ thấp (mỗi 3–6 giờ một lần) để tránh rate limit hoặc bị Shopee quét bất thường.

---

## 🎯 Chi tiết triển khai

### 1. Phân tích & Lưu trữ Cookie (`shopee_cookie.py`)
- Hỗ trợ đa định dạng đầu vào:
  - Xuất file/text JSON từ extension **J2TEAM Cookies** (hoặc Cookie-Editor): mảng `[{"name": "...", "value": "..."}, ...]`.
  - JSON dictionary dạng `{ "name": "value", ... }` hoặc `{ "cookies": [...] }`.
  - Chuỗi raw header HTTP: `name1=value1; name2=value2; ...`.
- Lọc và lưu cookie quan trọng (`SPC_EC`, `SPC_F`, `SPC_SI`, `SPC_U`, `shopee_token`, ...).
- Hàm lưu an toàn với `os.chmod(0o600)` và hàm nạp cookie an toàn.

### 2. Shopee Affiliate Web Client (`shopee_client.py`)
- `check_status()`: Gọi `GET https://affiliate.shopee.vn/api/v3/user/status`.
  - Kiểm tra `code == 0` và `data.allow_to_login == True`.
  - Trả về `ok: bool`, thông tin tài khoản (username, program_type) hoặc báo lỗi hết hạn.
- `fetch_clicks(start_time, end_time, page_no, page_size)`: Gọi `GET https://affiliate.shopee.vn/api/v1/click_report/list`.
- `fetch_conversions(start_time, end_time, page_no, page_size)`: Gọi `GET https://affiliate.shopee.vn/api/v3/report/list`.

### 3. Database Schema & Migration (`cashback_bot/db.py`)
- Mở rộng bảng trong SQLite:
  - `shopee_cookies`: Trạng thái kết nối (`status`, `account_name`, `last_sync_at`, `last_error`, `updated_at`).
  - `shopee_clicks`: `click_id` (PRIMARY KEY), `sub_id`, `click_time`, `raw_json`, `created_at`.
  - `shopee_conversions`: `conversion_id` (PRIMARY KEY), `sub_id`, `order_sn`, `order_status`, `conversion_status`, `purchase_time`, `gross_commission_vnd`, `net_commission_vnd`, `telegram_user_id`, `matched_link_id`, `raw_json`, `created_at`, `updated_at`.
  - `shopee_sync_runs`: `id`, `trigger_type` (manual/auto), `status`, `clicks_synced`, `conversions_synced`, `new_orders_count`, `error_message`, `started_at`, `completed_at`.

### 4. Đồng bộ & Khớp Sub ID (`shopee_sync.py`)
- Đối soát `conversion.sub_id` với `link_requests.sub_id`:
  - Khớp chính xác 100% case-sensitive.
  - Gán `telegram_user_id` và `matched_link_id`.
- Phát hiện đơn mới: nếu conversion chưa từng xuất hiện trong hệ thống và có `sub_id` thuộc bot, đánh dấu là đơn mới.
- Thông báo admin qua `AdminNotifier`:
  - Khi có đơn mới qua link bot: Báo mã đơn, Sub ID, người tạo link, hoa hồng Shopee ghi nhận.
  - Khi cookie hết hạn: Báo admin kèm hướng dẫn dán lại cookie mới.

### 5. Giao diện `/admin` (`admin_ui.py` & `admin_policy.py`)
- Màn hình `🔗 Kết nối Shopee`:
  - Hiển thị trạng thái: 🟢 Đã kết nối (Tài khoản, Lần đồng bộ gần nhất, số click, số đơn) hoặc 🔴 Chưa kết nối / Hết hạn.
  - Nút bấm:
    - `[ 🔑 Cập nhật Cookie ]`: Chuyển sang chờ nhận tin nhắn chứa cookie.
    - `[ 🔄 Đồng bộ ngay ]`: Kích hoạt đồng bộ thủ công ngay lập tức.
    - `[ ◀️ Tổng quan ]`: Quay lại menu chính.
- Xử lý nhận cookie:
  - Admin dán cookie -> Bot kiểm tra `check_status()`.
  - Bot gọi `delete_message` để xoá ngay tin nhắn chứa cookie.
  - Nếu hợp lệ: Lưu cookie -> Báo "✅ Đã kết nối Shopee Affiliate thành công!".
  - Nếu không hợp lệ: Báo lỗi và giữ an toàn.

### 6. Thống kê nâng cao (`admin_stats.py` & `admin_ui.py`)
- Trong màn `📈 Thống kê`, bổ sung phần:
  - 🖱️ **Click thật (Shopee)**: Tổng click, click có Sub ID bot.
  - 📦 **Đơn hàng đối soát**: Chờ duyệt / Hoàn thành / Đã huỷ, số đơn khớp bot.
  - 💵 **Hoa hồng thật**: Hoa hồng Shopee ghi nhận vs Hoa hồng ước tính đã báo khách.
  - 📊 **Tỷ lệ chuyển đổi (CR)**: Đơn / Click.

### 7. Tự động đồng bộ định kỳ (`poller.py`)
- Thiết lập chu kỳ đồng bộ nền mỗi 4 giờ (`_check_shopee_auto_sync`).
- Khi gặp lỗi cookie hết hạn, tự động chuyển trạng thái sang `expired` và gửi thông báo cảnh báo cho admin.

---

## ✅ Tiêu chí hoàn thành (Definition of Done)
- [x] Cookie parser hỗ trợ cả J2TEAM JSON và chuỗi name=value, lưu quyền 0600, không lộ log.
- [x] `TelegramApi.delete_message` xoá tin nhắn cookie thành công.
- [x] Admin kết nối Shopee và kiểm tra được `user/status`.
- [x] Đồng bộ đơn hàng & click, lưu vào SQLite an toàn, đối soát đúng Sub ID sang `telegram_user_id`.
- [x] Thông báo admin khi có đơn mới và khi cookie hết hạn.
- [x] Màn hình Thống kê mở rộng hiển thị số liệu đơn, click, hoa hồng thật.
- [x] 100% unit tests passed (không phụ thuộc mạng internet trong tests bằng mock/fixtures).

---

## 🔬 Proof / Log thực thi

### Antigravity — 2026-10-23
- Viết `cashback_bot/shopee_cookie.py`: Hỗ trợ J2TEAM JSON list, JSON dict, header string `name=value;`. Lưu quyền `0o600`.
- Viết `cashback_bot/shopee_client.py`: Gọi `/api/v3/user/status`, `/api/v1/click_report/list`, `/api/v3/report/list`.
- Viết `cashback_bot/shopee_sync.py`: Khớp Sub ID với `link_requests`, quy đổi scale 100.000 về VND, lưu bảng đối soát, phát hiện đơn mới.
- Mở rộng `cashback_bot/db.py`: Bổ sung bảng `shopee_cookies`, `shopee_clicks`, `shopee_conversions`, `shopee_sync_runs` và các hàm repository tương ứng.
- Cập nhật `cashback_bot/telegram_api.py`, `cashback_bot/messages.py`, `cashback_bot/poller.py`: Triển khai `delete_message` tự động xoá tin nhắn chứa cookie.
- Cập nhật `cashback_bot/admin_ui.py` & `cashback_bot/admin_policy.py`: Thêm màn hình `🔗 Shopee Affiliate`, nút cập nhật cookie và đồng bộ.
- Cập nhật `cashback_bot/admin_stats.py`: Bổ sung số liệu click thật, đơn thật, tỷ lệ chuyển đổi và hoa hồng thật vào màn Thống kê.
- Test `tests/test_cashback_shopee_sync.py` (17 tests).
- Toàn bộ test suite: **188 passed** in 18.21s. Ruff check sạch 0 errors.
