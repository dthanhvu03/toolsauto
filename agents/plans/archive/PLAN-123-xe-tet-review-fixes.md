# PLAN-123 — Xe Tết: sửa sau rà soát 01/11 (lỗi → chuyên môn → tâm lý người xem)

- Status: Done — anh duyệt 01/11, commit `01d3bed` (nhánh `feat/xe-tet`, PR vào `main`)
- Executor: Claude Code (anh duyệt 01/11: «vá hết theo thứ tự ưu tiên, vừa vá vừa research»)
- Nguồn: rà soát 01/11 (2 reviewer độc lập server + overlay, đo trên routes.json thật) — tóm tắt trong current-status.md

## Đợt 1 — lỗi chắc chắn

Server (`server/game/engine.py`, `app.py`, `network.py`, `settings.py`):
1. `trip_km` đứng 0 cả chuyến sau SPECIAL lúc đón khách (`resume` không reset).
2. Khách đang ngồi đổi sang tỉnh khác làn → giường trống không kéo người chờ lên.
3. Xe trống hết giờ đón không đổi sang làn có người chờ; vé ma (rời phòng) làm sai chọn làn / cao điểm / số chờ.
4. Comment tỉnh bến đi khi đang ngồi / đang chờ → vẫn giữ giường, bảng tỉnh đếm 2 lần.
5. Chuyến ngắn vẫn có trạm nghỉ (12 km → nghỉ ở km 6).
6. Cao điểm tính tổng mọi làn → xe làn vắng cũng chạy nhanh, bớt nghỉ.
7. Giờ chờ dự kiến: thiếu thời gian đón thật, FINISH / SPECIAL.
8. `+30 s` lúc SPECIAL kéo dài cảnh quà thay vì pha sau.
9. Spam «không về» / tỉnh bến đi không giới hạn.
10. Dữ liệu sự kiện sai kiểu (`name: 5`) → 500; tim của sự kiện bị loại vẫn cộng.
11. Bến đi kiểm theo bảng code, không theo `routes.json`.
12. Đổi tỉnh cùng làn khi đang chờ → bị đẩy xuống cuối hàng.

Overlay (`overlay/src/*`):
13. Đổi vùng rò bộ nhớ GPU (không dispose), biển miền Trung nằm lại mãi; ba lô người đi bộ tạo hình mới mỗi người;
    hoa đào cổng làng không dispose.
14. Vệt pháo hoa không vẽ (buffer 1 đỉnh).
15. Biển bến 3 bảng làn trong khi bến 4–5 làn; biển vẽ lại 5 lần / giây.
16. Xe chúi 2 lần khi lên dốc (shader + setLean); mặt phẳng ở bến / ruộng / cát / mái che ít đỉnh → lún khi uốn.
17. HUD: thanh nghỉ sai khi cao điểm, toast quà nhân đôi, dòng trạng thái cắt mất km / giờ, tên dài tràn, bong bóng
    chat chồng chất, `JSON.parse` không bọc lỗi, chữ trên canvas vẽ trước khi font tải.

## Đợt 2 — đúng chuyên môn

18. Hầm hay đèo: tuyến đi hầm (Hải Vân, Đèo Cả, Cổ Mã, Cù Mông, Đèo Ngang, Phước Tượng, Phú Gia, Tam Điệp…) ghi «Hầm …»,
    không làm dốc đèo; đèo thật giữ nguyên. Phân loại bằng độ quanh co đo được + danh sách hầm có thật.
19. Vùng cảnh theo từng km (tỉnh lỵ gần nhất của mỗi đoạn 10 km), trạm nghỉ lấy đặc sản theo nơi nghỉ thật.
20. Làn trộn 2 ngả đường: làn theo hành lang; tỉnh rẽ nhánh tính km xe chạy theo điểm rẽ (không còn chặng 34 km
    Lạng Sơn → Sơn La).

## Đợt 3 — tâm lý người xem

21. Rút thời lượng chuyến (km vẫn thật, nén thời gian theo độ dài chuyến) → tăng số người được lên xe / giờ.
22. Chọn làn theo «số người chở được mỗi phút + thời gian đã chờ»; công khai «Xe kế tiếp: Hướng …».
23. Người đang chờ luôn thấy tên mình trên màn hình (bảng «Chờ xe sau» + thứ tự).
→ đo lại bằng mô phỏng chờ (trước: phòng vắng chờ trung vị 10–15′, phòng đông 7–22 % người hướng Hà Nội được lên xe).

## Dọn (chỉ trong file đang sửa)

Số giường 24 → một hằng; hằng lặp (10_000, ZoneInfo, 3 s thả khách, 180/90); bảng món ăn gộp 1 bảng; export / trường
không dùng; tên sai nghĩa (`roundtrip`); `REVIEW.md` §3 mô tả mô hình cũ.

## Ngoài scope

Nhiều xe chạy cùng lúc; quà «vé ưu tiên / xe tăng cường» (chờ anh quyết); tên bến xe đến 63 tỉnh.

## Proof (01/11)

- `pytest xe_tet/tests`: 82 passed (thêm 16 test hồi quy: km sau quà lớn, đổi làn kéo người chờ, xe trống đổi làn,
  tỉnh bến đi bỏ vé, giữ thứ tự chờ, chuyến ngắn không trạm, trạm theo nơi thật + đặc sản, nén chuyến dài, cao điểm theo
  hướng, +30 s lúc chúc Tết, chống spam, hàng chờ trên màn hình, ETA lúc về bến, ai chờ trước đi trước, km rẽ nhánh, test
  dữ liệu thật hầm Hải Vân / Cù Mông + đèo Pha Đin). `ruff` + `tsc` sạch, `npm run build` qua.
- Fuzz 2 giờ × 5 bến (~130 chuyến): 0 vi phạm bất biến (khách đúng làn, vé không trùng, km tăng dần, odometer khớp).
- E2E Chromium: `control_panel` 28/28; `ux_scenarios` lần cuối 0 lỗi, 0 ghi chú (lần trước: «bảng góc phải bị che 20 %» do bảng chờ 2 dòng /
  người → sửa còn 1 dòng, 5 người).
- Ảnh: Đà Lạt «⏳ Chờ xe sau: ⬇ Út Cà Mau #1 …», «⛰ Đèo Mimosa», «Nghỉ ở Phú Yên», «🚇 Hầm Cù Mông» (km 572, Bình Định).
- Dữ liệu (`build_routes` chạy lại từ cache, 0 lượt OSRM): làn theo hành lang (Giáp Bát 6 làn: TP.HCM / Tây Bắc / Lạng Sơn /
  Cao Bằng / Quảng Ninh / Bình Thuận), hầm đo được 0–34 °/km, đèo 61–240.
- Mô phỏng chờ 4 giờ (TP.HCM): người được lên xe trong 30 phút — 1 comment / 20 s: ~67 % → 82 %; 1 / 45 s: ~82 % → 94 %;
  làn thiệt nhất 78–88 %. So 5 luật chọn làn, chọn «ai chờ trước đi trước».
- Còn lại (ghi nhận, không sửa): một xe 24 giường chở tối đa ~110–220 khách / giờ — phòng rất đông (1 comment / 6 s) chỉ
  ~40 % lên xe trong 30 phút, cần nhiều xe / quà «xe tăng cường» (chờ anh quyết); bóng đổ chưa uốn theo đường (lệch < 1,4 đơn
  vị ở mép); TikTok nối lại có thể gửi trùng sự kiện (chưa kiểm chứng, chưa lọc theo msg_id).
