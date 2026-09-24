# Data Model: Bỏ phụ đề khi video đã có nhạc

Không có bảng mới. Quyết định chỉ tồn tại trong lần xử lý một video.

## Đoạn nghe

Một khúc thời gian mà bộ nghe trả về, trước khi cháy lên hình.

| Trường | Quy tắc |
|---|---|
| Bắt đầu, kết thúc | Giây. Kết thúc phải sau bắt đầu. Đoạn không hợp lệ bị bỏ như hiện tại. |
| Chữ | Sau khi gom khoảng trắng. Rỗng thì bỏ như hiện tại. |
| Điểm không phải lời nói | Số từ 0 đến 1. Từ 0,6 trở lên thì bỏ đoạn. Thiếu thì không dùng điểm này để bỏ. |
| Tỷ lệ lặp chữ | Số dương. Trên 2,4 thì bỏ đoạn. Thiếu thì không dùng điểm này để bỏ. |

## Quyết định phụ đề

Kết quả sau khi lọc mọi đoạn của một video.

| Trường | Quy tắc |
|---|---|
| Các đoạn giữ lại | Đoạn còn chữ, còn thời lượng hợp lệ, và không dính một trong hai mốc bỏ. |
| Có cháy phụ đề | Còn ít nhất một đoạn giữ lại. |
| Không cháy | Không còn đoạn. Hình giữ bản chưa có phụ đề. |
| Chữ đăng bài | Không phải trường của quyết định này. Không đổi. |

## Video đã xong

Video đã xử lý xong trước quy tắc này không đi qua quyết định này lần nữa.
