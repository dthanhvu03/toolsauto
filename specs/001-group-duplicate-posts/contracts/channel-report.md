# Contract: Báo cáo chỉ số kênh

Bề mặt là tin nhắn chủ kênh đọc sau khi mở chỉ số tháng, rồi bấm một kênh. Không thêm lệnh.

## Màn mọi kênh

Một tin tóm tắt, rồi một nút cho mỗi kênh đang có bài trong phần báo cáo.

Mỗi kênh một khối:

- Tên kênh in đậm.
- `N nội dung` khi mỗi nội dung chỉ có một bản.
- `N nội dung · M bản lịch sử` khi M lớn hơn N.
- Dòng chỉ số cộng của các bản đại diện, không cộng trùng năm bản của một video.

Nút mang tên kênh và mở màn một kênh. Không liệt kê từng bản ở màn này.

## Màn một kênh

- Dòng đầu: tên kênh, tháng, và cùng câu `N nội dung` hoặc `N nội dung · M bản lịch sử`.
- Một khối cho mỗi nhóm, bản gửi muộn nhất đứng trước.
- Khối nhóm một bản: loại bài, thời điểm, chữ, chỉ số đủ, link nếu có.
- Khối nhóm nhiều bản: thêm `M bản lịch sử` trên cùng khối đó.
- Không có bản: một câu chưa có bài đã đăng, không có khối trống.

## Ngoài phạm vi

- Không nút xóa bản lịch sử.
- Không đổi nút đăng, đăng lại, chi tiết của một bản đang xếp.
- Tin đã gửi trước đó không tự đổi nội dung.
