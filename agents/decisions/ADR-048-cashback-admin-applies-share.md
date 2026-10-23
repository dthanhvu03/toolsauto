# ADR-048: Admin đổi tỷ lệ chia trong Telegram

Ngày: 2026-10-23. Trạng thái: chủ bot duyệt. Mở rộng ADR-047 (trước đó tỷ lệ chia chỉ đổi qua `.env`).

Admin được đổi **tỷ lệ chia** của báo giá V1.2 trong `/admin` → Chính sách: số nguyên 0–70% (trần V1 `MAX_SHARE_BPS`), ngày hiệu lực, xem trước rồi áp dụng.

Tỷ lệ nằm ở bảng riêng `share_policies`, chỉ thêm dòng, tách khỏi `reserve_policies`. Mỗi báo giá lấy dòng mới nhất đã tới hiệu lực của từng bảng, nên lịch đổi tỷ lệ và lịch đổi dự phòng không đè nhau. Chưa có dòng nào thì dùng `CASHBACK_RATE_PERCENT`.

Link mới ghi `cashback_rate_percent` là tỷ lệ đã dùng và mã `+s{id}` trong `estimate_policy`. Link cũ giữ số cũ. V1.1 không đọc bảng này. Hạng thành viên vẫn không bật được từ Telegram.
