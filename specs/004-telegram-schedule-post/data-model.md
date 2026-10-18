# Data Model: Lên lịch đăng bài từ Telegram

Không thêm bảng. Một lịch là một job đăng kênh đã có mã bài và một mốc giờ trong tương lai.

## Job đăng kênh

| Trường | Quy tắc |
|---|---|
| Video | Bắt buộc khi hẹn từ video sẵn sàng. |
| Kênh | Phải nằm trong danh sách kênh đang nối. |
| Lời bài | Trống thì không tạo lịch. |
| Mốc giờ | Số giây. 0 nghĩa là xếp hàng, không phải lịch giờ. Lịch hợp lệ lớn hơn hiện tại ít nhất 10 phút và không quá 30 ngày. |
| Mã bài bên kênh | Có sau lần tạo hoặc lần sửa thành công. Lần hẹn sau cùng video cùng kênh sửa đúng mã này. |
| Trạng thái job | Job đã giao kênh giữ trạng thái xong. Không tạo job thứ hai cho cùng video cùng kênh. |

## Giờ chủ kênh chọn

| Trường | Quy tắc |
|---|---|
| Múi giờ | Giờ Việt Nam. Mốc gửi đi là giờ quốc tế tương ứng. |
| Mẫu gõ | `ngày/tháng giờ:phút` hoặc `ngày/tháng/năm giờ:phút`. Thiếu năm thì lấy năm nay. Giờ đã qua thì từ chối, không cộng thêm một năm. |
| Gợi ý | Tối nay 20:00, sáng mai 08:00, tối mai 20:00. Gợi ý rơi ngoài cửa sổ thì nút đó từ chối, không tạo lịch. |

## Bài trên kênh

| Trạng thái | Đổi giờ | Hủy lịch |
|---|---|---|
| Đang hẹn | Sửa giờ. Vẫn một bài. | Xóa bài. Không tự đăng. |
| Lỗi, chưa đăng | Được sửa hoặc hủy. | Xóa bài. |
| Đã đăng | Từ chối. | Từ chối. Không nói đã hủy. |
| Đang được đưa đi đăng | Nơi đăng từ chối thì chat nói không đổi được. Không báo thành công. | Cùng luật. |

## Suất

| Việc | Quy tắc |
|---|---|
| Tạo lịch trong hôm nay | Hôm nay hết suất thì không tạo. |
| Tạo lịch bất kỳ | Tuần hết suất thì không tạo. |
| Đổi giờ | Không tự tính lại suất trước. Nơi đăng từ chối thì không báo đã đổi. |
| Xếp hàng không giờ | Không xét suất mới của feature này. |
