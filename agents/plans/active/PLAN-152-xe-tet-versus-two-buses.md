# PLAN-152 — Xe Tết: đối kháng hai xe ở bến

- Status: Code + test xong (04/11), chưa nạp 8810
- Executor: Claude Code (anh 04/11: «đối kháng phải làm 2 xe khách chuẩn bị xuất bến, xe nào win thì xe đó chạy trước»)
- Nền: PLAN-151 (quà quyết trận, giờ vàng, MVP lên băng rôn). Hiện trận đấu lúc xe đang chạy, bên thắng giành chuyến sau.

## Anh đã chốt (04/11)
1. Trận đấu ở bến, trong lúc đón khách (không còn đấu lúc xe chạy).
2. Xe thua giữ khách, chạy chuyến ngay sau.

## Phạm vi
### Máy chủ (engine)
- Vào bến đón khách mà đối kháng bật + có ≥2 hướng người chờ (anh không chọn tay, không có xe thua đang chờ chạy)
  → mở trận: chốt hai hướng đầu hàng chờ, lơ xe hô, giờ đón trọn `board_seconds` (3 phút).
- Trong trận chưa xếp ai lên giường; người gõ quê vào hàng chờ hướng mình (là khách của xe hướng đó).
- Xe đứng đầu bến (xe chính) là hướng đang dẫn điểm; lật kèo thì đổi.
- Giờ vàng = `versus_golden_s` giây cuối giờ đón (tạm dừng / chen cảnh thì đồng hồ đứng).
- Hết giờ: hướng thắng mở cửa, khách lên (lơ xe đọc tên như thường), xuất bến; MVP lên băng rôn.
  Hướng thua thành chuyến kế tiếp (lượt đó không đấu).
- Một bên hết người chờ giữa trận (xe tăng cường chở đi / bỏ vé) → huỷ trận, đón khách như thường.
- Lúc xe chạy không còn thanh PK.

### Màn hình (overlay)
- Ở bến có trận: xe thứ hai đậu làn bên cạnh, bảng LED hướng của nó; xe dẫn điểm đứng làn trước, lật kèo thì hai xe đổi làn.
- Thanh PK + thẻ kết quả giữ như PLAN-151, chữ đổi sang «xe nào thắng xuất bến trước».

## Không làm
- Không đổi hệ số điểm / giờ vàng / quà chung.

## Kiểm tra
- Test engine: mở trận lúc vào bến, chưa ai lên giường, giờ vàng theo giờ đón, hết giờ hướng thắng lên xe + chạy, chuyến
  sau là hướng thua (không đấu), huỷ trận khi một bên hết người.
- 8811: chụp hai xe ở bến, lúc lật kèo, lúc thắng; 0 lỗi JS. Không nạp 8810 khi anh chưa bảo.

## Proof (04/11)
- pytest 216 (`test_versus_two_buses_at_station_winner_departs_loser_next`: trận mở lúc vào bến, chưa ai lên giường, lật kèo
  thì xe đổi làn đầu, quê hướng khác không cộng, xe thắng nhận khách + chạy, chuyến sau là xe thua không đấu;
  `test_versus_gifts_decide_golden_minute_mvp_and_cancel`: quà / tiếp sức bên thua / giờ vàng theo giờ đón / MVP băng rôn /
  tắt giữa trận thì huỷ + xếp giường), ruff sạch, engine_audit 15 lượt không lỗi.
- 8811: xe thứ hai đậu làn sau (x 0, z −5,5 — thử thêm làn trước thì che xe chính); biển phe trên nóc «👑 ⬆ Đà Nẵng · 60» /
  «⬇ Cà Mau · 0»; tặng quà lật kèo → hai xe đổi làn; hết trận «🏁 XUẤT BẾN» / «⏳ CHUYẾN SAU», băng rôn MVP; 0 lỗi JS.
  Ảnh scratchpad duel_grid.png.
- Lần chụp đầu, quà 1 xu của người thử cũ (uid c1, có sẵn trong DB thử) không ra điểm; thử lại người mới qua /api/event thì
  đúng 20 điểm. Chưa tìm ra nguyên nhân với uid cũ.
