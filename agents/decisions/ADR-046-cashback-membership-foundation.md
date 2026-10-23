# ADR-046: Hạng chỉ trả tỷ lệ, pricing tính tiền

Ngày: 2026-10-23. Trạng thái: trong worktree `cursor/cashback-v12-architecture`. Chưa bật cho khách.

`ranks.py` trả Đồng 6000, Bạc 6500, Vàng 7000 phần vạn và snapshot đã lưu. `pricing.share_cashback` là chỗ duy nhất nhân tỷ lệ đó. `MEMBERSHIP_CUTOVER` đang False nên link mới không nhận 60%.

Link cũ giữ số đã lưu. Thiếu Sub ID, chủ, tỷ lệ, số đã hiển thị hoặc thời điểm thì `needs_owner_review`, không suy ra 70% hay 60%.

Thời hạn quyền lợi báo giá chưa có số ngày. Hiệu lực URL tracking là việc khác và cũng chưa được điền. Không cắt quyền lợi đã cam kết chỉ vì URL còn mở.

Ngưỡng lên hạng vẫn chưa duyệt. Ba bộ dễ, cân bằng, thận trọng chỉ để mô phỏng. Đơn hủy không tính. Thu hồi không được làm quỹ âm. Click và số link không tính.

Migration `003` chỉ thêm cột trên database thử, không sửa số cashback cũ, không được gọi từ `migrate()`.
