# PLAN-122 — Xe Tết: tuyến xe thật (bến đi, làn theo hướng, km thật, đường quanh co)

- Status: Done (chờ anh duyệt ảnh + quyết commit)
- Executor: Claude Code (anh duyệt 31/10: bến đi mặc định Miền Đông mới, phương án B bến nhiều làn, cho gọi OSRM)
- BRD: `xe_tet/docs/BRD-tuyen-xe.md`

## Scope

- **R1 dữ liệu:** `server/game/geo.py` (toạ độ tỉnh lỵ, 5 bến đi, 20 đèo), `tools/build_routes.py` (OSRM một lần → km,
  độ quanh co / 10 km, đèo đi qua, gom làn theo ngả đường 150 km đầu) → `server/game/data/routes.json`.
- **R2 luật chơi:** `network.py`; engine: hàng chờ theo làn, chọn làn xuất bến BR-4 (đếm bỏ qua lúc xuất bến, bỏ qua 2
  chuyến → bắt buộc chạy), xe trống quay đầu theo khách đầu tiên, đặt / đổi vé theo làn (BR-2), dừng theo km thật (BR-3),
  chặng tỉ lệ km (3 km/s, cao điểm 5 km/s), trạm nghỉ giữa quãng (> 900 km: 2 trạm), tỉnh trùng bến đi (BR-5),
  đổi bến đi chỉ khi bến trống (BR-8). Server: thiết lập `departure`, lệnh admin `departure`.
- **R3 màn hình:** HUD km thật, làn ở bến, vé có tuyến + km, thả khách có km + giờ xe, đèo; LED đầu xe «TP.HCM → HÀ NỘI»;
  biển bến thật + bảng từng làn; cột cây số km thật; `/control` chọn bến đi.
- **R4 đường:** `overlay/src/bend.ts` — uốn thế giới trong shader (cua / dốc) theo độ quanh co OSRM, đèo, vùng; xe chúi theo
  dốc, nghiêng khi vào cua.

## Ngoài scope

Đoàn nhiều xe chạy cùng lúc; tên bến xe đến cho đủ 63 tỉnh (hiện ghi tên tỉnh); độ cao thật (OSRM không có).

## Proof (31/10)

- Dữ liệu: `venv/bin/python -m xe_tet.tools.build_routes` → `routes.json` 179 KB, 5 bến × 62 tỉnh, 0 tuyến ra nước ngoài
  (79 tuyến dẫn lại qua QL1 — BRD mục 9). OSRM tổng ≈ 700 lượt ≤ 1 lượt / giây, 0 lần thử lại; cache gzip 6,8 MB gitignore.
- `pytest xe_tet/tests` 66 passed; `test_real_route_table`: TP.HCM → Hà Nội 1.600–1.800 km qua Hải Vân + Ngang,
  Nghệ An chung làn Hà Nội, Cà Mau khác làn Hà Nội (TP.HCM và Đà Lạt), 2–5 làn mỗi bến, độ quanh co < 300 °/km.
- Fuzz (scratchpad `fuzz_routes.py`): 2 giờ live × 5 bến, ~125 chuyến — khách trên xe luôn đúng làn, vé chờ không trùng,
  không vừa chờ vừa ngồi, chặng tăng dần theo km, thả khách có km + giờ > 0. Lỗi tìm ra + sửa: 12 km → «0 giờ xe»
  (engine gửi giờ 1 số lẻ, HUD đổi sang phút).
- E2E Chromium: `ux_scenarios` 11 tình huống 0 lỗi; `control_panel` 28/28.
- Ảnh: Đà Lạt đang đón ⬆ Hà Nội 3/24 + «Út Cà Mau» giữ chỗ ⬇ TP.HCM ⏳1 (biển «HƯỚNG TP.HCM · 1 CHỜ»); đèo Tây Nguyên;
  QL1A đồng bằng thẳng. Lỗi tìm ra + sửa: đường uốn nhấc cả mặt đất che xe (mặt phẳng dài 2 đỉnh) → `strip()`;
  dòng trạng thái bị cắt «chạy sau …» → «Đi Hà Nội · chạy sau m:ss», chỉ liệt kê làn có người chờ.
- Còn: cua trên khung dọc nhìn nhẹ (biên độ giữ thấp để bóng đổ không lệch); tên bến xe đến 63 tỉnh.
