# Data Model: Gộp bài trùng trong báo cáo chỉ số

Không có bảng mới. Nhóm chỉ tồn tại lúc dựng báo cáo.

## Bản đã gửi

Một lần nội dung đã lên một kênh trong tháng đang xem.

| Trường | Quy tắc |
|---|---|
| Mã bản | Có mặt. Không hiện cho chủ kênh. |
| Kênh | Bắt buộc khi gộp. Hai kênh không vào cùng một nhóm. |
| Chữ | So sau khi gộp khoảng trắng. Rỗng vẫn là một giá trị chữ. |
| Ngày gửi | Ngày theo giờ Việt Nam của thời điểm đã gửi. Thiếu thời điểm thì không gộp với bản đã có ngày. |
| Chỉ số | Lượt hiện, cảm xúc, bình luận, chia sẻ, lượt bấm. |
| Link trang | Giữ của bản được chọn để hiện. |

## Nhóm nội dung

Các bản cùng kênh, cùng chữ đã chuẩn hóa, cùng ngày.

| Trường | Quy tắc |
|---|---|
| Kênh | Một nhóm thuộc một kênh. |
| Chữ | Khóa so sánh. |
| Ngày | Khóa so sánh. Hai ngày là hai nhóm. |
| Số bản | Đếm bản trong nhóm. Luôn ít nhất 1. |
| Bản đại diện | Bản có thời điểm gửi muộn nhất trong nhóm. |
| Dòng hiện | Chữ, loại bài, chỉ số và link của bản đại diện, cộng số bản nếu lớn hơn 1. |

## Tóm tắt kênh

| Trường | Quy tắc |
|---|---|
| Số nội dung | Số nhóm trong kênh, trong phần bài báo cáo đang giữ. |
| Số bản | Tổng bản thuộc các nhóm đó. |
| Câu hiện | Nếu số bản bằng số nội dung: `N nội dung`. Nếu lớn hơn: `N nội dung · M bản lịch sử`. |
| Kênh rỗng | Không có bản trong tháng thì không tạo nhóm. Câu hiện là chưa có bài đã đăng. |

## Chuyển trạng thái

Không có. Xem báo cáo không tạo, không sửa, không xóa bản đã gửi.
