# PLAN-124 — Xe Tết: đường đèo thật (cua, dốc nhìn thấy được, bóng đổ uốn theo)

- Status: Done (chờ anh xem ảnh)
- Executor: Claude Code (anh duyệt 01/11 sau khi em báo cua / dốc hiện tại gần như không thấy)

## Vấn đề (đo 01/11)

1 đơn vị ≈ 1 m (xe dài 12). Khung dọc 9:16 chỉ thấy ~26 m đường quanh xe.
- Cua gắt nhất bán kính ~200 m → mép đường lệch < 0,5 m / đường rộng 8 m: không thấy. Đèo thật 15–60 m, cao tốc ≥ ~650 m.
- Dốc đèo 3,5 % (thật 7–10 %), lượn lên xuống đều theo sin — không có lên trước đỉnh / xuống sau đỉnh.
- Xe nghiêng khi vào cua ~1,4°.
- Biên độ bị giữ thấp vì bóng đổ (shadow map) vẽ trên hình chưa uốn → uốn mạnh thì bóng lệch khỏi vật.

## Scope

1. `bend.ts`: uốn cả lượt vẽ bóng đổ (vật liệu độ sâu dùng chung, cùng khối shader uốn) → mở khoá biên độ.
2. Hình đường theo độ quanh co đo được (bán kính cua liên tục): ≤ 18 °/km thẳng; 18 → 140 °/km bán kính 600 m → 40 m.
3. Dốc: đèo 8 % lên trước đỉnh, xuống sau đỉnh (server báo chiều theo km đèo + chiều xe chạy); đồi theo vùng ≤ 4 %;
   đồng bằng / cao tốc ≤ 1,5 %; hầm phẳng.
4. Xe: nghiêng theo gia tốc ngang (v² / R), tối đa ~6°; leo đèo thì cảnh trôi chậm lại + khói ống xả dày hơn.
5. Kiểm: ảnh ngày + đêm (đồng bằng, đồi, đèo lên / xuống, hầm), số khung / giây, e2e, test server.

## Ngoài scope

Độ cao thật (OSRM không có); đường cua ngoặt chữ U (một parabol trong khung 26 m không vẽ được chữ U).

## Proof (01/11)

- Bán kính cua theo độ quanh co: đồng bằng (11 °/km) thẳng; Bảo Lộc (67) ~170 m; Pha Đin (158) 40 m. Dốc đèo 8 % lên trước
  đỉnh / xuống sau đỉnh (server `terrain.climb`, test `test_pass_climbs_before_summit_then_descends`); hầm thẳng, phẳng.
- Bóng đổ uốn cùng (vật liệu độ sâu dùng chung trong `bend.ts`) → mở được biên độ.
- Đèo / hầm chạy chậm cho kịp thấy: đèo ≥ 16 giây, hầm ≥ 8 giây (`test_pass_lasts_long_enough_to_see`).
- Hầm (`tunnel.ts`): vách bê tông đốt 6 m + gạch men chân vách, đèn vàng trôi, đá núi phủ hai bên, trời tối lại, xe bật đèn.
- Ảnh (ban ngày `?hour=10`, chụp lúc tạm dừng vì trình duyệt không GPU ~1 khung / giây): đồng bằng thẳng; Pha Đin lên dốc /
  đổ dốc đường cong rõ hai chiều ngược nhau; Bảo Lộc; Hầm Cổ Mã.
- Rò bộ nhớ: 2 vòng đổi đủ 4 vùng, số hình / ảnh GPU đứng yên 261 → 263 / 42 → 45 (trước PLAN-123: tăng mãi 162 → 271).
- `pytest` 89 passed, `tsc` + `ruff` sạch, build qua.
- Còn: FPS phải đo trên Chrome Windows có GPU (`/?fps=1`); máy chủ chỉ có trình duyệt phần mềm.
