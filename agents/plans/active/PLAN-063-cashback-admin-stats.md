# PLAN-063 — Thống kê trong /admin

| | |
|---|---|
| Trạng thái | **APPROVED (user, 2026-10-23)** — code xong, chờ restart |
| Executor | Claude Code (user trực tiếp giao) |
| Phạm vi | `cashback_bot/` + test cashback. Chỉ đọc, không đổi schema |
| Ngoài phạm vi | Số đơn, doanh thu thật, chuyển đổi (cần Conversion Sync, chưa có) |

## Màn `/admin` → 📈 Thống kê

Kỳ: Hôm nay / 7 ngày / 30 ngày / Tất cả, tính theo ngày giờ Việt Nam.

- 👥 Người dùng: tổng, mới trong kỳ, có gửi link trong kỳ.
- 🔗 Link: số gửi, tạo được (tỷ lệ), lỗi theo lý do.
- 💰 Số dự kiến: hoa hồng ước tính, đã báo khách, chênh lệch trước phí và thuế. Ghi rõ "chưa phải doanh thu".
- 📅 7 ngày gần nhất: link tạo được mỗi ngày, cột chữ.
- 🏆 Người gửi nhiều nhất, 🛍️ món được hỏi nhiều nhất (top 5).
- 🩺 Tin gửi lỗi chưa xong, lỗi hệ thống trong kỳ.

## Tiêu chí xong
- [x] Nút 📈 Thống kê ở Tổng quan, đổi kỳ bằng edit tin.
- [x] Mốc kỳ đúng 00:00 giờ VN.
- [x] Không có dữ liệu thì hiện trạng thái trống, không lỗi.
- [x] Không ghi DB. pytest cashback xanh.

## Proof / Log thực thi

### Claude Code — 2026-10-23

- `admin_stats.py`: `collect(conn, period, now)` chỉ SELECT; mốc kỳ 00:00 giờ VN; lỗi gom nhãn (link sai, không thấy sản phẩm, lỗi tạo link, còn lại "dữ liệu sản phẩm chưa sẵn"); xu hướng 7 ngày theo `date(created_at, '+7 hours')`; top 5 người gửi, top 5 món theo `item_id`.
- `admin_ui.py`: nút 📈 Thống kê đầu Tổng quan (mặc định 7 ngày), `stats_text`, `stats_keyboard` đánh dấu kỳ đang xem; username escape HTML.
- `admin_policy.py`: callback `c:st:(today|7d|30d|all)`; DB thiếu bảng → thông báo, không vỡ.
- Thử trên bản sao `data/backups/cashback-20261023T103218Z.sqlite`: 7 ngày = 5 người dùng, 27 link, hoa hồng ước tính 754.603đ, đã báo khách 528.221đ; màn 1.148 ký tự.
- Test `tests/test_cashback_stats.py` (7 test, có mốc 23:59/00:00 giờ VN và kết nối chỉ đọc). Proof: **165 passed**.
