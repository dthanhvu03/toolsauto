# PLAN-150 — Xe Tết: đua tỉnh + bảng quảng cáo bên đường chiếu video (xe dừng xem rồi chạy tiếp)

- Status: Code + test xong (03/11), chưa nạp 8810
- Executor: Claude Code (anh 03/11: «có em, triển khai đi» (đua tỉnh); «làm cái bảng hiệu quảng cáo … chiếu các video nổi bật …
  anh sẽ up video lên, xe đang chạy dừng lại xem rồi chạy tiếp»)

## Đua tỉnh
- Điểm cho tỉnh quê (vé đang có, không thì quê lần trước): bình luận 1 điểm / 15 giây / người, 20 tim = 1 điểm, 1 xu = 5 điểm —
  trộn hành động miễn phí (không thành «chấm điểm chỉ bằng quà»).
- Chuyến mới: sau luật «chờ quá 10 phút đi trước», tỉnh nhiều điểm nhất CÓ người đang chờ quyết hướng xe; báo «⚔️ X thắng đua
  tỉnh», vòng mới mỗi chuyến. Lơ xe: race_lead (≥ 30 giây / câu), race_win.
- Màn hình: bảng góc phải «⚔️ Đua tỉnh · thắng đi trước» (🥇🥈🥉 + điểm), dòng gợi ý trong khung kêu gọi.

## Bảng quảng cáo
- /control «📺 Bảng quảng cáo»: tải video mp4 / webm (≤ 500 MB, thư mục `storage/media/xe_tet/videos/`, 8811 dùng
  XE_TET_VIDEO_DIR), danh sách + «▶ Chiếu ngay» / 🗑, «Chiếu video kế tiếp», «Dừng video»; công tắc tự chiếu (mặc định bật,
  mỗi 10 phút, xoay vòng), tối đa 120 giây / video, công tắc tiếng video.
- Chỉ chiếu lúc xe đang chạy đường, giữa chặng (15–80 %), không lúc dừng đón / bị chặn. Xe đứng yên tới hết video (tạm dừng
  game thì giờ chiếu dừng theo), rồi chạy tiếp. Trạm thu phí / công an không chen lúc đang chiếu.
- Cảnh: bảng LED lớn lề bên kia đường (co theo tỉ lệ video dọc / ngang), máy quay ngước lên bảng; ẩn khung kêu gọi / lơ xe /
  thông báo trong lúc chiếu; dòng tuyến «📺 tên video · còn 0:53». Màn mở giữa chừng vẫn khớp chỗ đang chiếu.
- Tiếng video đi qua bộ trộn (màn không phát tiếng thì im), nhạc trong xe nhỏ lại; trình duyệt chặn tự phát tiếng thì chiếu câm.

## Proof (03/11)
- pytest 174 (`test_province_race_decides_next_trip_and_resets_each_trip`, `test_billboard_video_stops_bus_then_continues`);
  fuzz 15 × 30 phút 0 lỗi.
- 8811: tải video 9:16 60 giây qua /api/video → «Chiếu ngay» → xe dừng, bảng chiếu video to giữa khung, dòng tuyến «Xem video ·
  còn 0:53», hết video xe chạy lại; bảng đua tỉnh Kiên Giang 11 / Cà Mau 2 / Hà Nội 1; 0 lỗi JS. Ảnh scratchpad p142/v_show.png,
  v_ctrl.png.
