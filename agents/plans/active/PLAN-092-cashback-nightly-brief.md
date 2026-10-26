# PLAN-092 — 🌙 Bản tin tối cho chủ bot

| | |
|---|---|
| Executor | Claude Code (chủ bot duyệt 2026-10-26: "mỗi tối đi em, triển khai theo từng mục") |
| Trạng thái | ✅ Đã merge vào main 2026-10-26, chờ chủ bot restart |
| Không đổi | Chỉ gửi admin (hàng đợi tin admin), không gửi khách. Đọc số `mode=ro`. Ghi 2 khoá `bot_state`: ngày đã gửi, các mốc G1 đã báo |

## Nội dung

Gửi lúc 21:00 giờ VN mỗi ngày, một lần. Bot tắt lúc 21:00 thì gửi khi bật lại, nếu vẫn còn trong ngày.

- 📍 Giai đoạn G1 / G2+. 🎉 Mốc mới đạt kể từ bản tin trước; bản tin đầu tiên không báo các mốc đã đạt từ trước.
- 📅 Hôm nay (từ 0 giờ VN): khách mới, link, đơn đặt, đơn hoàn thành, HH ròng.
- 🎯 Mục tiêu tháng đã đặt: cùng dòng với màn 🎯 (đã đạt / mục tiêu, trạng thái, dự báo, cần mỗi ngày).
- 🛡 Giới hạn an toàn: "tất cả ổn" hoặc liệt kê mục đỏ.
- 👥 Top 3 khách 7 ngày theo HH ròng.

## Phạm vi file

- `cashback_bot/insights.py`: `day_stats`, `top_since`.
- `cashback_bot/admin_insights.py`: `brief_text`; tách `_goal_line` dùng chung với màn 🎯.
- `cashback_bot/ops_watch.py`: `check_nightly_brief`.
- `cashback_bot/admin_notify.py`: `notify_nightly_brief`.
- `cashback_bot/poller.py`: gọi trong vòng lặp.
- `tests/test_cashback_insights.py`.

## Proof

- `pytest tests/test_cashback_*.py`: 799 passed. `ruff check`: sạch.
- Test mới:
  - `test_ban_tin_toi_moi_ngay_mot_lan_va_moc_moi`: trước 21 giờ không gửi; mỗi ngày một lần; bản đầu không báo mốc cũ; ngày sau báo 🎉 mốc mới.
  - `test_so_lieu_hom_nay_va_top_tuan`.
- Test dời đơn mẫu về `NOW` để không hỏng theo ngày chạy (đơn mẫu cố định 21/10).
- Xem trước trên DB production (`mode=ro`): G1 1/4 mốc; hôm nay 2 khách mới, 6 link; 5 mục tiêu; an toàn tất cả ổn; top 2 khách 7 ngày.
