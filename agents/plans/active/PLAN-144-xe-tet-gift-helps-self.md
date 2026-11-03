# PLAN-144 — Xe Tết: quà tặng có lợi cho chính người tặng

- Status: Bước 1 xong (03/11), chưa nạp 8810; bước 2 (bảng quà theo mốc xu kiểu «dụng cụ») chờ anh duyệt
- Executor: Claude Code (anh 02/11: «chức năng tặng quà chưa hiệu quả»; live 02/11 chỉ 6 lượt × 1 xu / 3 người / 153 người xem;
  anh chọn «quà giúp chính mình»; 03/11 gửi ảnh game khác: bảng quà theo mốc xu, mỗi mốc một việc cụ thể, vinh danh người tặng
  nhiều nhất — «mình toàn free thôi»)

## Bước 1 — quà giúp chính mình (xong)
- Đang giữ chỗ chuyến sau mà tặng quà bất kỳ → lên đầu hàng làn mình (sau người tặng trước), một lần tới khi lên xe; cũng ưu
  tiên khi xe làn khác chạy ngang quê. Đã có giường mà tặng → giường vàng + tên viền vàng.
- Báo đúng lúc: thẻ vé giữ chỗ ghi «🎁 tặng quà để lên đầu hàng»; bảng quà dòng đầu «⚡ Đang chờ xe → lên đầu hàng»; lơ xe
  «X tặng quà, lên đầu hàng xe Cà Mau, thứ 1» (8 giây / câu); câu hỏi «quà được gì» + AI biết luật.
- Proof: pytest 163 (`test_waiting_gifter_jumps_to_front_once_until_boarding`).
