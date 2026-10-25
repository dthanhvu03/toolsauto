# PLAN-084 — Gộp tin "Lỗi bot" khi rớt mạng

| | |
|---|---|
| Executor | Claude Code (chủ bot đồng ý lên plan sau sự cố 2026-10-24 17:22Z) |
| Trạng thái | Chủ bot duyệt 2026-10-25 ("anh duyệt nhé"); đã lên main, chờ restart Telegram |

## Sự cố gốc
- 2026-10-24, 17:22–17:27Z: máy mất mạng khoảng 4–5 phút. Bot Telegram và bot Zalo cùng báo `ConnectionError`, rồi tự chạy lại; không cần restart.
- Admin nhận 3 tin giống nhau "⚠️ Lỗi bot · `telegram_poll_failed` · POLL_ERROR". Cả 3 chỉ tới sau khi mạng có lại.
- Khối chi tiết có `Update -` / `User -`: hai dòng không mang thông tin gì.
- 2026-10-25 01:11:45–01:12:26Z: Telegram trả 502 rồi quá giờ, khoảng 1 phút (bot Zalo không lỗi) → 1 tin "Lỗi bot". PLAN-084 không báo loại này.
- Trước đó còn 2 lần rớt mạng ngắn (2026-10-23 01:13, 2026-10-24 01:11–01:12). Mỗi lần chỉ hỏng 1–2 lượt nhận tin, nhưng lần nào cũng báo admin.

## Hiện tại
- `poller._loop`: mỗi lần `requests.RequestException` → `notify_request_failed("telegram_poll_failed")`. Chặn trùng 60 giây, nên rớt mạng 5 phút ra khoảng 3–5 tin.
- `zalo_bot._loop`: chỉ ghi log. Zalo im quá 10 phút đã có cảnh báo riêng (PLAN-083).

## Làm
| Việc | Cách làm | File |
|---|---|---|
| N1 | Lỗi mạng khi nhận tin Telegram thì không báo ngay: ghi `net_down_since` (bot_state) ở lần lỗi đầu, đếm số lần lỗi | `poller.py` |
| N2 | Nhận tin thành công lại: nếu mất kết nối ≥ 60 giây thì gửi **1 tin** "📡 Bot mất kết nối mạng HH:MM–HH:MM (N phút), đã tự kết nối lại. Tin khách Zalo gửi trong lúc này có thể bị mất." Ngắn hơn 60 giây thì chỉ ghi log. Xoá `net_down_since` | `poller.py`, `admin_notify.py` |
| N3 | Lỗi kéo dài ≥ 5 phút mà vẫn gửi được tin (ví dụ chỉ `getUpdates` bị lỗi, các lệnh khác vẫn chạy) → báo "đang mất kết nối" một lần, rồi chờ tin N2 | `poller.py`, `admin_notify.py` |
| N4 | Tin "Lỗi bot" bỏ khối chi tiết khi không có cả mã update lẫn mã người dùng | `admin_notify.py` |

**Không đổi:**
- `poll_loop_failed` (lỗi code, không phải lỗi mạng): vẫn báo như cũ.
- Lỗi xử lý từng tin khách, cảnh báo Zalo im 10 phút, backup.
- Tiền, ví, chính sách, luồng khách.

## Kiểm thử
- 1 lần lỗi rồi nhận tin được → 0 tin admin.
- Lỗi liên tục 4 phút rồi có mạng lại → đúng 1 tin, có giờ bắt đầu, giờ kết thúc, số phút.
- Lỗi 6 phút → 1 tin "đang mất", rồi 1 tin "đã kết nối lại"; không lặp lại.
- Bot khởi động lại giữa lúc mất mạng → vẫn đọc `net_down_since`, báo đúng 1 lần.
- `notify_request_failed` không có update / user → không có khối chi tiết.
- Toàn bộ test cũ đạt, ruff sạch.

## Triển khai
1. Backup. Làm trên nhánh, merge `--ff-only`, chạy test, push.
2. Chủ bot restart riêng bot Telegram. Bot Zalo không cần.
3. Kiểm tra log khởi động, chạy `gate_b_check`.

## Đã làm (2026-10-25)
- **Backup:** `cashback-20261025T013601Z.sqlite` (47 bảng, 40 link).
- `poller.py`:
  - `_net_failed` / `_net_recovered`, hằng `NET_DOWN_KEY`, `NET_ALERT_AFTER_SEC = 60`, `NET_STILL_DOWN_SEC = 300`;
  - lỗi mạng khi nhận tin không còn gọi `notify_request_failed("telegram_poll_failed")`.
- `admin_notify.py`:
  - `notify_connection(since, until=None)`: tin `NET_DOWN` / `NET_UP`;
  - "Lỗi bot" bỏ khối chi tiết khi không có update / user.
- `tests/test_cashback_net_outage.py`: 5 test theo mục Kiểm thử.
- **Kết quả:** 703 passed, ruff sạch.
