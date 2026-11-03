# PLAN-148 — Xe Tết: trạm thu phí / công an chặn xe, người xem tặng quà góp đủ thì đi tiếp

- Status: Code + test xong (03/11), chưa nạp 8810
- Executor: Claude Code (anh 03/11: «qua trạm thu phí, kêu gọi mn góp để qua trạm, đang đi bị công an kiểm tra giấy tờ, đóng
  phạt, quá tốc độ, tặng quà góp để đi tiếp»; chọn: CHỈ QUÀ mới tính, chờ tới khi góp đủ, phòng ít quà thì Anh Tư báo bù lỗ —
  admin control được)

## Luật
- Mỗi chuyến từ 120 km: trạm thu phí cứ ~350 km một trạm (tối đa 2); chuyến từ 150 km: 60 % gặp công an một lần. Không đặt sát
  điểm thả khách / trạm nghỉ (12 km), hai điểm chặn cách nhau ≥ 40 km.
- Xe đứng yên tới khi tổng xu quà góp ≥ phí (mặc định trạm 20 xu, phạt 10 xu). Tim / bình luận không tính.
- Công an gặp lúc xe đang chạy nhanh (quà tăng tốc còn giây / tốc độ ≥ x2) → «quá tốc độ», phạt gấp 3, hết tăng tốc.
- «💸 Anh Tư bù lỗ» trên /control: xe đi ngay, lơ xe nói bù phần thiếu. Tự bù lỗ sau N giây (mặc định 0 = chờ tới khi đủ).
- /control: bật/tắt, «Trạm thu phí ngay», «Công an ngay», phí / phạt (xu), tự bù lỗ, dòng trạng thái góp bao nhiêu / chờ bao lâu.
- Engine trần (test) tắt chặn xe; server bật theo cài đặt `blocks_on` (mặc định bật).

## Màn hình
- Thẻ kêu gọi: thay «Gõ tên tỉnh» bằng «🚧 TRẠM THU PHÍ ĐỒNG NAI» / «👮 QUÁ TỐC ĐỘ · CÔNG AN PHẠT» + thanh «8 / 20 xu · 🎁 tặng
  quà góp để xe đi tiếp»; chân bảng «🙏 Cảm ơn …». Thanh tuyến: pill «Trạm thu phí» / «Công an», «góp 8/20 xu».
- Cảnh đường: chòi thu phí + barie (góp đủ thì barie nhấc lên), chú CSGT + nón giao thông, biển ở lề phía camera; bảng góc
  phải ẩn khi bị chặn để không che.
- Lơ xe: toll / police / speeding / block_remind (25 giây) / block_paid / block_cover, 3 kiểu nói.

## Proof (03/11)
- pytest 169 (`test_toll_stops_bus_until_gifts_cover_fee_only_gifts_count`, `test_police_speeding_fine_and_anh_tu_covers_the_loss`,
  `test_blocks_planned_on_long_trips_away_from_stops`).
- 8811: trạm thu phí Đồng Nai góp 8/20 rồi đủ 20 → barie mở, xe đi; công an Khánh Hòa sau quà tăng tốc → «chạy quá tốc độ» 30 xu;
  bấm bù lỗ → xe đi; 0 lỗi JS. Ảnh: scratchpad p142/k_toll.png, k_police.png.

## Rà soát ngoại lệ + tỉ lệ (03/11, anh: «check lại các trường hợp ngoại lệ, tỉ lệ thuật toán, research thêm»)
- Số liệu thật (storage/db/xe_tet.db, chỉ đọc): buổi 02/11 20 phút, TB 46 người xem (max 153), 108 bình luận, 2.162 tim,
  6 quà = 6 xu (≈ 0,3 xu / phút). 1 xu ≈ 200 đ khi nạp, người live nhận ≈ 100 đ. QL1 cũ Lạng Sơn → Bạc Liêu ~29 trạm.
- Giả lập 60 phút × 8 lần / cấu hình (scratchpad sim/rates2.py), quà gần buổi thật (hầu hết 1 xu), không ai bấm bù lỗ:
  | Phòng | Phí cố định 20/10 | Phí theo phòng + ít chặn |
  |---|---|---|
  | 0,3 quà / phút | đứng chờ 47 phút / giờ, về quê 23, kẹt 34 phút | 12 phút / giờ, về quê 89, kẹt 7 phút |
  | 1 quà / phút | 31 phút / giờ, về quê 57 | 11 phút / giờ, về quê 93 |
  | 3 quà / phút | 20 phút / giờ, về quê 70 | 15 phút / giờ, về quê 82 |
  Thêm tự bù lỗ 120 giây ở phòng 0,3: 6 phút / giờ, về quê 100, không kẹt quá 3 phút.
- Fuzz 40 × 30 phút (sim/fuzz.py: khách ngẫu nhiên + admin bấm bỏ qua / tạm dừng / chặn / bù lỗ / tắt bật): 0 lỗi bất biến
  (không trùng giường / hàng chờ, không vừa ngồi vừa chờ, không vừa chặn vừa dừng đón, snapshot không lỗi).
- Sửa: phí theo phòng (`fee_auto`, mặc định bật); phòng ít quà ít bị chặn; trạm 600 km / trạm (từ 300 km), công an 40 %;
  quá tốc độ chỉ khi đang chạy x2 nhờ quà (tim không tính) và không mất giây chạy nhanh; tắt tính năng giữa lúc bị chặn → xe
  đi luôn; tạm dừng không tính vào giờ tự bù lỗ; tặng quà lúc chưa có vé chỉ lên đầu hàng MỘT lần (trước: cả buổi); quà lúc
  đang chen cảnh chúc Tết vẫn tính vào góp; xe đầy vì cả hàng chờ lên cùng lúc giữ tới 35 giây cho lơ xe đọc hết tên (trước
  10 giây); overlay chờ tên tới 32 giây.
- Còn để ý: giờ hẹn «~N giây xe tới» của người bắt xe dọc đường và «lên xe sau ~N phút» trên vé không cộng giờ đang bị chặn
  (giờ chạy trung bình đo thật nên dần tự đúng).
