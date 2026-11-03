# PLAN-132 — Xe Tết: tối ưu hiệu suất, bộ nhớ, cách tải giao diện (theo /code-review)

- Status: Done (đã nạp 8810)
- Executor: Claude Code (anh yêu cầu 01/11: «senior tối ưu lại toàn bộ game, hiệu suất, ram, cách load ui ux» + /code-review)

## Sửa (theo thứ tự nặng nhẹ khi live)
1. Màn hình live «đứng hình»: server bỏ kết nối chậm khỏi danh sách nhưng không đóng → overlay không biết rớt, không tự nối
   lại. Giờ đóng hẳn (`_close_quietly`) → overlay tự nối lại sau 1,5 giây.
2. Game khựng mỗi phút: vòng game chờ VieNeu `/health` (tới 3 giây khi VieNeu đang đọc). Giờ hỏi danh sách giọng ở tác vụ
   nền riêng (`Announcer.watch_voices`).
3. Thêm / tải bài nhạc: `ffprobe` (tới 20 giây / file) chạy trong vòng game. Giờ đo ở luồng riêng, tạm tính 3 phút.
4. Biển chữ 3D lẫn font: chỉ tải bộ chữ latin (Ế Ầ Ừ vẽ font dự phòng suốt buổi). Giờ tải đủ bộ tiếng Việt (chữ mẫu có dấu)
   cho Be Vietnam Pro + Baloo 2 trước khi dựng cảnh.
5. Rò bộ nhớ âm thanh: mỗi câu lơ xe / mỗi bài nhạc file giữ lại một nút Web Audio + file đã giải mã. Giờ nhả sau khi phát.
6. /control vẽ lại cả danh sách xe mỗi giây (đồng hồ «còn m:ss») → nút dưới tay bị thay, bấm trượt. Giờ mỗi xe một khung cố
   định, chỉ ghi phần chữ đổi.
7. Thanh chặng dựng lại 5 lần / giây → chỉ dời chiếc xe (trượt mượt bằng CSS); `setHTML` thôi đọc innerHTML mỗi lần.
8. Nhãn chữ 3D tính lại ma trận cả cây cảnh lần hai mỗi khung → dùng ma trận WebGL vừa tính. Vùng không hiện gỡ khỏi cảnh
   (không duyệt hàng nghìn vật ẩn); cảnh tĩnh không tính lại ma trận.
9. Cảnh trong xe vẫn vẽ bóng đổ ngoài trời → tắt bóng khi ở trong xe.
10. Người chibi 13–15 khối / người → gộp phần đứng yên thành 1 khối tô màu theo đỉnh (dùng chung theo kiểu người, có trần),
    còn tay chân riêng: ~23 → ~11 lần vẽ / người (kể cả bóng).
11. Dựng vùng mới giữa đường (khựng hình) → dựng sẵn từng vùng lúc xe đang đón khách ở bến, cách nhau 3 giây.
12. e2e: kiểm «đang live» đúng máy chủ sắp bấm, 8810 tắt không văng lỗi; import đầu file; đóng trình duyệt trong `finally`.
- Giữ nguyên: `tiktok.py` nạp TikTokLive khi bấm kết nối (cố ý — server chạy được cả khi không cài thư viện).

## Proof (01/11, máy thử 8811)
- pytest 115 passed (thêm: tracks() không chạy ffprobe trên luồng chính). tsc + build sạch.
- Lần vẽ (Cao): bến 516 → 440; đường 316; bến 14 người 600; thả 14 khách 554. Bộ nhớ JS 23 → 28 MB sau 90 giây giả lập
  phòng đông (không tăng mãi), 0 lỗi trang. Ảnh: người chibi đủ màu, «BẾN XE MIỀN ĐÔNG MỚI» đúng font.
- e2e control_panel trên 8811: PASS 28, FAIL 0, JS errors [].
