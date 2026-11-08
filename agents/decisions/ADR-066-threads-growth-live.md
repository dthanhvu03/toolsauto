# ADR-066: Threads Kéo khách — quét bằng trình duyệt, tự đăng theo ngưỡng, dừng khi checkpoint

## Status
Accepted 06/11/2026 (chủ bot duyệt trực tiếp, PLAN-158).

## Context
Cần kéo khách từ Threads về Cashbot (@zt_shopee_bot) và AI Pass Store (@aipass_shop_bot), đo A/B bằng mã `?start=`.
Chưa có Threads API (keyword search / reply cần app review Meta); hệ thống đã có `ThreadsAdapter` (Playwright, profile bền).

## Decision
1. **Quét + đăng bằng Playwright** qua `ThreadsAdapter` (dùng lại mở phiên / nhận checkpoint / selector soạn thảo).
   Bài lấy từ **JSON trang tìm kiếm** (bền hơn DOM); DOM chỉ dự phòng.
2. **Tài khoản riêng** `accounts.name=threads_growth`, profile `instagram_5`, `is_active=False` — worker Threads cũ
   (`Threads_AutoReply`, `Threads_Publisher`) lọc `is_active` nên không đụng tài khoản này.
3. **Dữ liệu ở SQLite riêng** `data/threads_growth.sqlite` (gitignore), cột thêm bằng ALTER tại chỗ — không migration Postgres.
4. **Tự đăng theo ngưỡng** `growth.auto_post_min_relevance`; dưới ngưỡng → chờ duyệt (web + Telegram). Reply là câu mẫu
   (AI lỗi) không bao giờ tự đăng. Mọi lần đăng qua `posting_quota()` (giờ / ngày / giãn cách) + chờ ngẫu nhiên.
5. **Checkpoint / mất đăng nhập** → tự tắt `growth.enabled`, đánh `login_status=INVALID`, báo Telegram; không thử vượt.
6. **Lọc**: chỉ tiếng Việt (đếm chữ có dấu — Threads hầu như không trả `detected_language`), chỉ bài gốc, bài ≤ N giờ,
   không reply lại cùng tác giả trong N ngày, bỏ bài khoá reply / đã reply.
7. **Cấu hình trên web** (`growth.*`); giữ cố định trong code: handle bot, mã `?start=`, tên biến thể.
8. Telegram gọi growth qua `feature_hooks` (`growth.callback`, `growth.summary`) — giữ contract features độc lập.

## Consequences
- Được: chạy không cần sửa code; dừng an toàn khi Threads nghi ngờ; đo A/B theo bài.
- Rủi ro / nợ: phụ thuộc cấu trúc JSON / DOM Threads (đổi là phải sửa `browser.py`); AI không phải lúc nào cũng chèn link
  `?start=` → một phần reply không đo được; đăng nhập lại cần màn hình (WSLg `DISPLAY=:0`).
