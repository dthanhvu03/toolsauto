# PLAN-137 — Xe Tết: đổ xăng / rửa xe lúc chờ khách

- Status: Code + test xong (02/11), chưa nạp 8810
- Executor: Claude Code (anh 02/11: «khúc đợi khách thêm tính năng đổ xăng rửa xe dc ko»; anh chọn «có ảnh hưởng nhẹ»)

## Luật
- Xe chính chạy: xăng giảm theo km (một bình ~2.500 km), độ bẩn tăng (~3.000 km bẩn hẳn; mưa phùn miền Bắc ×1,8, qua đèo ×1,5).
- Ở bến (đón khách) hoặc trạm dừng: comment «đổ xăng» (+20 % bình), «rửa xe» (−25 % bẩn); mỗi người 10 giây một lần; đang
  chạy thì không có tác dụng. «rùa / rua» trơn không tính.
- Xuất bến: bình ≥ 80 % → chạy nhanh hơn 10 %, xe sạch (bẩn ≤ 20 %) → thêm 5 %. Thiếu xăng / bẩn vẫn chạy bình thường, không
  chặn ai. Thưởng không rút ngắn đoạn đèo / hầm (vẫn đủ PASS_SECONDS cho người xem thấy).
- Màn hình: thanh «⛽ % · 🧽 %» ở thẻ tuyến lúc đón; gợi ý «Gõ ĐỔ XĂNG · RỬA XE»; thông báo gọi tên người làm; lơ xe nói (3 kiểu,
  8 giây / câu); thân xe (sơn riêng, không làm bẩn lây biển hiệu) ngả màu bùn theo độ bẩn; rửa: nước xịt + bọt quanh xe; đổ
  xăng: tia sáng vàng ở nắp bình. AI Gemini biết luật này.

## Proof (02/11)
- pytest 142 (`test_fuel_and_wash_while_waiting_give_small_bonus`: hao theo km, đổ / rửa ở bến, giãn cách 10 giây, đang chạy
  không tác dụng, thưởng / không thưởng, không chặn); đoạn đèo vẫn ≥ PASS_SECONDS khi có thưởng.
- 8811: chuyến TP.HCM → Lào Cai 1.955 km về bến xăng 22 % bẩn 76 %; 3 người rửa → bẩn 1 %, 1 người đổ → 42 %; ảnh thông báo +
  lơ xe «Xe được Bình tắm cho, sạch 49 phần trăm».
