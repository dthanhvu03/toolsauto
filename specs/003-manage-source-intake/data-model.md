# Data Model: Quản lý nguồn khi video đổ về nhiều

Không thêm bảng. Thêm một liên kết trống được từ video về nguồn.

## Nguồn

Một kênh đang được theo dõi.

| Trường | Quy tắc |
|---|---|
| Mã nguồn | Có mặt. Dùng khi đặt số riêng. |
| Bật | Bật thì được quét. Tắt thì lần quét không thêm video. |
| Mức xem riêng | Số nguyên không âm, hoặc trống. Trống nghĩa là dùng mức chung. |
| Số video tối đa riêng | Số nguyên từ 1 đến trần một lần quét đang có, hoặc trống. Trống nghĩa là dùng mức chung. Nhỏ hơn 1 thì không lưu. |
| Lần quét gần nhất | Thời điểm, số video mới thêm được, và lỗi nếu có. Giữ như hiện tại. |
| Trang đích | Không đổi khi chỉ sửa hai số ngưỡng. |

## Video

| Trường | Quy tắc |
|---|---|
| Nguồn | Trống được. Video tạo từ một lần quét sau quy tắc này trỏ về đúng nguồn đó. Video cũ và video dán tay để trống. |
| Trạng thái chờ | Trạng thái «mới, chưa xử lý». Chỉ những dòng này được đếm là video chờ của nguồn. |
| Xóa | Không xóa khi tắt nguồn hoặc đổi ngưỡng. |

## Số đang có hiệu lực

Dùng lúc quét một nguồn đang bật.

| Trường | Quy tắc |
|---|---|
| Mức xem | Số riêng nếu có, không thì mức chung. |
| Số video tối đa | Số riêng nếu có, không thì mức chung. Lần quét dừng khi số video vừa thêm đạt số này. |
| Cửa sổ đọc | Bằng số lớn hơn giữa số video tối đa đang có hiệu lực và mức chung, và không vượt trần một lần quét. |

## Đếm chờ

Số video có nguồn trùng mã nguồn và đang ở trạng thái chờ. Video không gắn nguồn không cộng vào nguồn nào.
