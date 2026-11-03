# PLAN-146 — Xe Tết: chỉ một xe 24 giường (bỏ xe ôm / taxi / máy bay), «chuyến N», người chờ bên đường đứng phía camera

- Status: Code + test xong (03/11), chưa nạp 8810
- Executor: Claude Code (anh 03/11: «triển khai tiếp 2 phần còn lại chưa ổn … mình làm gì có máy bay đâu, mình chỉ có 1 xe 24 chỗ»)

## Đổi
- Quà: bỏ hẳn RIDES (xe ôm, taxi, 7 / 16 chỗ, xe khách, chuyến bay) và `ride_home`. Quà chỉ giúp người tặng: đang chờ → lên
  đầu hàng (tặng trước rồi mới gõ tỉnh cũng được xếp đầu hàng), có giường → giường vàng; 10 xu pháo hoa, 100 xu băng rôn,
  1000 xu cả xe chúc Tết; Chủ nhà xe / Phó nhà xe giữ nguyên. Bảng quà, FAQ lơ xe, prompt AI nói rõ «chỉ một xe 24 giường».
- «Xe số N» → «chuyến N» (overlay, /control, lơ xe, AI). Số lần về quê của người xem đổi chữ thành «lần về quê thứ N».
- Dừng đón bên đường: người chờ đứng lề phía camera, ngay dưới cửa trước, biển điểm đón bên phải nhóm; xe chạy lại mà máy
  chậm chưa kịp bước thì gỡ (coi như đã lên) — không còn người đứng lại khi xe đi.

## Proof (03/11)
- pytest 165 (thay test xe ôm/taxi bằng `test_big_gift_sends_no_other_vehicle_only_one_bus`).
- 8811: ảnh bảng quà mới, dừng đón Phú Yên thấy rõ 3 người + biển, xe chạy lại không còn ai đứng lề; 0 lỗi JS.
