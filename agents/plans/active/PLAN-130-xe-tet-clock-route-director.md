# PLAN-130 — Xe Tết: giờ chạy xe khớp lời nói, bảng chặng đường, tự chiếu xe, font + bố cục, trộn tiếng

- Status: Done (chờ anh cho khởi động lại 8810 để nạp)
- Executor: Claude Code (anh chốt 01/11: font «cả hai» màn hình; tự chiếu «cả hai kiểu, chọn trên /control»; bảng chặng
  «overlay + /control»; thời gian: «giờ nói không khớp, xa gần như nhau, chạy nhanh quá»)
- Server đổi → cần khởi động lại 8810 (hỏi anh trước). Thử trên 8811.

## 1. Thời gian chạy xe (engine)
- Trước: phần chạy đường nén ≤ 4 phút, tối thiểu 3 km/giây → 325 km ≈ 1:50, 1.700 km ≈ 4:00 (xa gần chênh ít), lơ xe nói
  «chừng 26 tiếng» mà màn hình không có giờ nào khớp.
- Sau: giây chạy = dài nhất × (km / 1.750)^0,75, tối thiểu 45 giây; «dài nhất» = thiết lập `trip_minutes` (mặc định 8 phút,
  chỉnh 3–15 trên /control). Cao điểm × 0,6. Xe tăng cường cùng công thức.
- Đồng hồ trên xe: giờ VN lúc xuất bến + km / 52 km/h (+ 30 phút mỗi trạm dừng) → lơ xe nói 26 tiếng thì đồng hồ trên xe
  chạy đủ 26 tiếng; mỗi điểm dừng có giờ tới dự kiến. Trời (sáng / chiều / đêm) theo đồng hồ trên xe, chuyển mượt.

## 2. Bảng chặng đường
- Server: `route` (xe đang chiếu: các điểm dừng, km, giờ tới theo đồng hồ xe, còn bao nhiêu giây thật) + `fleet` (mọi xe:
  đang ở đâu, điểm kế, còn bao lâu).
- Overlay: dải chặng trong thẻ tuyến (chấm điểm dừng, xe đang ở đâu, giờ tới). /control: bảng đủ các xe + từng điểm dừng.

## 3. Tự chiếu xe
- Thiết lập `auto_feature`: tắt / «theo chuyện hay» / «xoay vòng» (+ `rotate_seconds`). Theo chuyện hay: xe tăng cường
  sắp thả khách thì chiếu xe đó, xong quay về xe chính; xe chính có cảnh (xuất bến, trạm, thả khách) thì về xe chính; mỗi
  lần chiếu tối thiểu ~40 giây. Admin bấm tay → tạm ngưng tự chuyển 2 phút.

## 4. Font + bố cục
- Tự chứa font (không phụ thuộc Google Fonts khi LIVE Studio mở): Be Vietnam Pro + Baloo 2 cho tiêu đề / băng rôn.
- Overlay giữ ngoài vùng TikTok che; /control gọn trên điện thoại.

## 5. Trộn tiếng
- Nén chung (compressor) cho nhạc + giọng + tiếng xe; tiếng đường (lốp, gió) theo tốc độ; lơ xe nói thì nhạc + tiếng xe
  nhỏ lại; chế độ trộn chọn trên /control (cân bằng / nhạc nổi / lơ xe nổi).

## Verify
- pytest; tsc + build; ảnh trên 8811.

## Proof (01/11, máy thử 8811)
- pytest 113 passed (thêm: xa / gần + chỉnh phút, đồng hồ chạy đủ số giờ của chuyến + giờ tới từng điểm, danh sách xe,
  tự chiếu theo chuyện hay — chỉ chiếu xe tăng cường lúc xe chính đang chạy, xong về xe chính; bấm tay nhường 2 phút;
  xoay vòng; thiết lập kẹp giá trị).
- Ảnh: thanh cả chuyến có chấm ☕ / 📍 + 🚌, «🕐 19:19 · ☕ Trạm Quảng Nam 09:34 (còn 3:25) → 📍 Nghệ An…»; chiếu xe tăng
  cường ban đêm 19:41 (trời tối theo đồng hồ xe); /control điện thoại: từng xe đủ điểm dừng, giờ tới (ngày 2, 3); máy
  tính: hai cột.
- Tự chiếu (events): đổi xe ở giây 0 → 42 (xe tăng cường số 2) → 76 (về xe chính) → 112 → 137.
- Lần vẽ không đổi so với PLAN-129 (chỉ thêm DOM). Font tự chứa 300 KB.
