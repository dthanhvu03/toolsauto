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
