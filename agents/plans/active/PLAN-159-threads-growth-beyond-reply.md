# PLAN-159 — Kéo khách Threads ngoài reply: bài riêng, trả lời lại, chiến dịch 11/11, đo theo kênh

- **Executor:** Claude Code · **Duyệt:** chủ bot trực tiếp (06/11: «oke em triển khai em hoàn thiện cho anh đi em»)
- **Tiếp nối:** PLAN-158 (reply A/B tự động), ADR-066

## Bối cảnh (số liệu 06/11)
35 reply → 2 khách /start Cashbot → 0 khách gửi link. Xem công khai: mỗi reply 3–24 lượt xem — nút thắt là độ phủ.
Tài khoản @us28qt có 2.101 người theo dõi nhưng chưa từng được dùng để đăng nội dung săn sale.

## Scope
1. **Bài riêng trên tài khoản** (`growth/content.py`, `worker.post_own`): theo khung giờ `growth.own_post_times`
   (mặc định 11:45, 20:15 VN; lệch cố định 0–25 phút), mỗi khung ≤ 1 bài. Nội dung AI viết từ dữ liệu THẬT:
   - dịp sale lớn trong 5 ngày tới (`cashback_bot.sale_calendar`, bỏ mini) → 1 bài nhắc / ngày;
   - còn lại: tối đa 3 món trong kho deal Cashbot (`bot_state.deals_pool`, chỉ đọc, giá thấp nhất 30 ngày, thấy lại < 6h),
     không lặp món trong 3 ngày.
   AI lỗi → thử lại mỗi 15 phút trong khung, không bao giờ đăng câu mẫu. Đăng qua hộp «New thread» (`GrowthBrowser.create_post`).
2. **Trả lời người hỏi lại** (`worker.followups`): mỗi 20 phút mở ≤ 6 reply của mình (đăng trong `followup_lookback_hours`,
   mỗi reply kiểm lại ≥ 3 giờ / lần), lấy reply có `reply_to_author` = mình; AI trả lời câu hỏi hoặc SKIP (cảm ơn / chê / spam /
   bán cạnh tranh). Hạn mức riêng `growth.followup_max_per_day` (15). AI lỗi hoặc hết suất → không đánh dấu đã kiểm.
3. **Chiến dịch 11/11**: thêm từ khóa «săn sale 11/11, sale 11.11 shopee, giỏ hàng 11/11» (DB cài đặt, xoá được trong ⚙️);
   bài nhắc sale đếm ngược tự động theo lịch.
4. **Đo theo kênh**: mã `?start=` riêng — `threads_{cb|ai}_post` (bài riêng), `_conv` (trả lời lại), `_bio` (anh đặt ở bio).
   `conversions.report()` thêm `channel` + `by_channel`; web + Telegram hiện «theo kênh».
5. **AI viết lại câu mẫu**: bài chờ duyệt vì AI lỗi → mỗi 30 phút thử AI viết lại (≤ 5 bài); được và đủ điểm → «Chờ đăng».
6. Web: khung «Bài riêng trên tài khoản» + «Người hỏi lại»; ⚙️ Kéo khách thêm 2 nhóm cài đặt. Telegram: báo cáo vòng có bài riêng,
   trả lời lại, số bài viết lại, khách theo kênh.

## Ngoài scope
Sửa profile @us28qt (tên, bio, ghim bài) — chủ bot làm tay. Tin bot tự nhắn khách chưa gửi link (cần chủ bot duyệt luật riêng).

## Proof
- Test: `tests/test_threads_growth.py` 53 pass (+12: kho deal, lịch sale, bài riêng sale/deal/không lặp/AI lỗi, khung giờ, parser
  `replies_to_me`, trả lời lại + hạn mức + AI lỗi, viết lại câu mẫu, mã kênh + `by_channel`, tin Telegram). ruff sạch,
  lint-imports không thêm vi phạm (2 contract BROKEN có từ trước).
- Thử khô trên Threads thật (không đăng): nút cũ của adapter KHÔNG còn («Start a thread»), giao diện mới là `[aria-label="New thread"]`
  → hộp thoại, nút «Post» khớp chính xác; gõ 3 dòng vào ô soạn đúng, Cancel → «Save to drafts?» (đóng không lưu).
- Đăng thật 1 bài (06/11 ~15:50 VN, bài nhắc 11.11): https://www.threads.com/@us28qt/post/DfZLfuUid-g — link bắt được.
- Watchdog (06/11): worker treo 16 phút ngay sau khi mở Chromium (Playwright driver kẹt) → `watchdog_sleep` +
  SIGALRM: 20 phút không qua `sleep` nào thì thoát để PM2 restart. Test 54 pass.
- Vòng thật đầu tiên: quét 323 bài, +22 chờ đăng, kiểm trả lời lại 6 reply (chưa ai hỏi).
- AI: 9Router «no active credentials» (chủ bot đăng nhập lại ở http://localhost:20128); Gemini chạy lại sau quota.
