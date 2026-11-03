# PLAN-144 — Xe Tết: quà tặng có lợi cho chính người tặng

- Status: Bước 1 + 2 xong (03/11), chưa nạp 8810
- Executor: Claude Code (anh 02/11: «chức năng tặng quà chưa hiệu quả»; live 02/11 chỉ 6 lượt × 1 xu / 3 người / 153 người xem;
  anh chọn «quà giúp chính mình»; 03/11 gửi ảnh game khác: bảng quà theo mốc xu, mỗi mốc một việc cụ thể, vinh danh người tặng
  nhiều nhất — «mình toàn free thôi»)

## Bước 1 — quà giúp chính mình (xong)
- Đang giữ chỗ chuyến sau mà tặng quà bất kỳ → lên đầu hàng làn mình (sau người tặng trước), một lần tới khi lên xe; cũng ưu
  tiên khi xe làn khác chạy ngang quê. Đã có giường mà tặng → giường vàng + tên viền vàng.
- Báo đúng lúc: thẻ vé giữ chỗ ghi «🎁 tặng quà để lên đầu hàng»; bảng quà dòng đầu «⚡ Đang chờ xe → lên đầu hàng»; lơ xe
  «X tặng quà, lên đầu hàng xe Cà Mau, thứ 1» (8 giây / câu); câu hỏi «quà được gì» + AI biết luật.
- Proof: pytest 163 (`test_waiting_gifter_jumps_to_front_once_until_boarding`).

## Bước 2 — bảng quà theo mốc xu, bỏ xe tăng cường, Chủ nhà xe (anh chọn 03/11)
- Anh: «không cần xe tăng cường nữa, nhiều xe quá anh không cover được» → tắt xe tăng cường tự gọi + gọi bằng quà (`RELIEF_AUTO`
  = False; máy giữ cho admin gọi tay). Trên màn hình chỉ một xe.
- Quà = xe đưa người đang chờ về quê ngay (xu cộng dồn từng người): 10 xu xe ôm 1 người · 20 taxi 2 · 30 xe 7 chỗ 4 · 50 xe 16
  chỗ 8 · 100 xe khách 20 · 500+ chuyến bay cả bến. Người tặng đang chờ về trước, rồi người chờ lâu nhất; được tính «về tới quê»
  (số chuyến, hồ sơ khách quen, báo cáo). Không ai chờ thì xu giữ lại (thẻ quà ghi rõ). Dưới 10 xu: lên đầu hàng / giường vàng.
- «👑 Chủ nhà xe» / «Phó nhà xe»: hai người tặng nhiều xu nhất buổi, ở chân bảng quà; đổi chủ thì lơ xe + thông báo.
- Bảng quà lớn cố định trong thẻ phía trên (anh chọn): «🎁 TẶNG QUÀ = ĐƯA NGƯỜI ĐANG CHỜ VỀ QUÊ NGAY» + 7 ô có hình + chân
  «⏳ N người đang chờ · 👑 Chủ nhà xe … · từ 18 tuổi»; thẻ quà gợi ý mốc xe kế tiếp («thêm 10 xu → 🚐 7 chỗ đưa 4 người»).
- Proof: pytest 164 (`test_gift_rides_send_waiting_people_home_giver_first`, `test_top_gifters_are_owner_and_deputy`; 4 test máy
  xe tăng cường bật lại cờ trong phạm vi test); ảnh 8811 bảng quà + Chủ nhà xe + «Xe 16 chỗ của Chúa Tết đưa 4 người về quê»,
  0 lỗi JS; e2e control_panel 28/28.
