# PLAN-125 — Xe Tết: xe tăng cường (chạy ngầm, tự động + bằng quà)

- Status: Done — anh duyệt 01/11, commit `01d3bed` (nhánh `feat/xe-tet`, PR vào `main`)
- Executor: Claude Code (anh chốt 01/11: «Tự động + bằng quà», mốc «100 xu, gộp bậc băng rôn»; thêm giữa chừng:
  «Admin control được tất cả các chuyến xe, góc cam chuyến xe»)

## Vấn đề

Một xe 24 giường chở tối đa ~110–220 khách / giờ. Phòng rất đông (1 comment / 6 s) chỉ ~40 % người được lên xe trong
30 phút (mô phỏng 4 giờ, PLAN-123).

## Thiết kế

- Xe chính vẫn là xe duy nhất vẽ 3D. Xe tăng cường chạy «ngầm» theo tuyến + km thật (`Network.plan`), không trạm nghỉ,
  không cảnh chúc Tết; góc màn hình có dải «🚌 Xe tăng cường ⬇ Cà Mau · còn 120 km».
- Xuất bến:
  - **Tự động:** làn có ≥ 24 người chờ (sau khi bỏ vé ma) → một xe tăng cường chở 24 người đầu hàng.
  - **Bằng quà:** người đang giữ chỗ cộng dồn đạt bậc băng rôn (100 xu) → xe tăng cường chạy ngay làn của họ, họ lên trước,
    xe mang tên «Xe tăng cường của …»; lời thoại nhấn «bao cả xe cho bà con …» (lợi cho cả làn, không phải chen hàng).
  - Tối đa 4 xe tăng cường cùng lúc (quà được vượt tới 6) — giữ màn hình đọc được.
- Lên xe tăng cường: thẻ gộp tên «🎫 Út, Bé Na, Dì Năm +21 lên xe tăng cường!». Tới nơi: băng rôn đọc tên từng người như
  xe chính (băng rôn xếp hàng, không đè nhau); cảnh 3D không đổi (xe chính vẫn chạy).
- Đổi bến đi bị khoá khi còn xe tăng cường đang chạy (tuyến của xe tính theo bến cũ).
- Xe tăng cường qua đèo / hầm cũng chậm lại như xe chính (dùng chung `_pace`).
- **Admin điều khiển mọi chuyến (anh thêm 01/11):** `/control` → «🚌 Các chuyến xe»: xe chính + từng xe tăng cường (làn, số
  khách, điểm kế, km còn, ai bao xe); «📺 Chiếu» = màn hình live theo xe đó (cảnh 3D, đèo / hầm, HUD, tên trên xe), góc máy
  dùng chung phần Camera; «⏭ Tới điểm kế»; gọi thêm xe tăng cường cho làn có người chờ; công tắc tự gọi. Xe đang chiếu tới
  bến cuối → màn hình tự về xe chính. Trạng thái xe chính cho admin ở trường `main`.

## Kiểm

Test: tự xuất bến khi đủ 24, quà 100 xu khi đang chờ, người tặng lên trước, thả khách đủ tên + thống kê, giới hạn số xe,
khoá đổi bến; fuzz bất biến (không ai vừa ở xe chính vừa ở xe tăng cường / hàng chờ). Mô phỏng chờ: mục tiêu phòng rất
đông ≥ 80 % lên xe trong 30 phút. Ảnh: dải xe tăng cường, thẻ lên xe, băng rôn thả khách. E2E.

## Proof (01/11)

- `pytest`: 91 passed — thêm: tự xuất bến khi đủ 24, thả khách đủ tên + thống kê, quà 100 xu người tặng lên trước + tên trên
  xe tăng cường (không dán xe chính), giới hạn số xe + khoá đổi bến, một người chỉ ở một chỗ, chiếu xe tăng cường rồi tự về
  xe chính, API admin (gọi xe / chiếu / tới điểm kế / tắt tự gọi / lỗi 400).
- Fuzz 2 giờ × 5 bến (có quà ngẫu nhiên + đổi xe chiếu): 0 vi phạm (không ai ở hai chỗ, khách xe tăng cường đúng làn, ≤ 6 xe).
- Mô phỏng chờ 4 giờ, tỉ lệ được lên xe trong 30 phút — 1 comment / 6 s: ~40 % → 98 % (trong 5 phút: ~1 % → 76 %);
  1 / 3 s: 99 %; 1 / 20 s: 82 % → 98 %; bến Giáp Bát 1 / 6 s: 98 %.
- Ảnh: thẻ «Khách miền Tây 1, 2 +21 người lên xe tăng cường!», quà «Út Gia Lai bao nguyên xe tăng cường» (Út + Chị Hai
  lên, Út trước), chiếu xe số 3 (3D chạy qua Tây Nguyên, «Xe Tết của Út Gia Lai», «Trên xe số 3»), băng rôn gom «Xe tăng
  cường về tới quê!», bảng admin «Các chuyến xe» trên điện thoại; huy hiệu «🚌+2» không làm card tuyến cao thêm.
- E2E Chromium trên bản cuối: `ux_scenarios` 0 lỗi, 0 ghi chú; `control_panel` 28/28.
