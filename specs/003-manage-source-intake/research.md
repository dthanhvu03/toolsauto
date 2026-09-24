# Research: Quản lý nguồn khi video đổ về nhiều

## Decision: Gắn nguồn lên video lúc quét, không đoán lại từ chữ kênh

**Rationale**: Video mới hiện không lưu nguồn nào đã tạo ra nó. Đếm «còn chờ» theo tên kênh sẽ gộp nhầm hai nguồn cùng nền tảng, và không gắn được video dán tay. Cột trống được, chỉ điền cho video tạo từ một lần quét sau quy tắc này. Video cũ để trống nên không bị đếm nhầm và không bị xóa.

**Alternatives considered**: Đếm `last_found` của lần quét trước và gọi đó là số đang chờ. Số đó không giảm khi video đã được xử lý, nên chủ kênh vẫn thấy nguồn «đầy» sau khi hàng đã tiêu. Suy ra nguồn từ đường dẫn video. Hai nguồn có thể trỏ cùng một kênh theo hai dạng địa chỉ.

## Decision: Quét nguồn tắt thì dừng trước khi đọc kênh

**Rationale**: Nút quét một nguồn hiện vẫn đọc kênh dù nguồn đang tắt. Vòng quét tất cả thì đã bỏ nguồn tắt. Spec bắt mọi lần quét của nguồn tắt đều không thêm video. Chặn ở một chỗ, trước khi gọi trình đọc kênh, thì cả nút bấm lẫn vòng tự động cùng một luật.

**Alternatives considered**: Chỉ ẩn nút quét. Chủ kênh vẫn có thể gọi quét. Chỉ chặn vòng tự động. Nút bấm vẫn đổ video.

## Decision: Số tối đa là số video được nhận, không phải số dòng đọc được

**Rationale**: Lọc mức xem đang loại video ít xem trước, rồi nhận mọi video còn lại trong cửa sổ đọc. Vì vậy một nguồn «tối đa 3» vẫn có thể nhận nhiều hơn 3 nếu cửa sổ đọc rộng. Dừng khi số video vừa thêm đạt mức tối đa đang có hiệu lực. Cửa sổ đọc lấy bằng mức tối đa đang có hiệu lực, và không nhỏ hơn mức chung, để vẫn thấy đủ video qua mức xem rồi mới dừng. Trần cửa sổ giữ nguyên trần đang có của một lần quét.

**Alternatives considered**: Cắt cửa sổ đọc đúng bằng số tối đa riêng. Ba video mới nhất có thể đều dưới mức xem, trong khi video đủ mức xem đứng ngay sau đó, và nguồn nhận 0 dù kênh còn video đủ điều kiện trong cùng lần đọc rộng hơn.

## Decision: Đặt số riêng bằng lệnh nguồn đang có, không thêm lệnh

**Rationale**: Mức chung đã có một lệnh. Danh sách nguồn đã có nút bật, tắt và quét. Thêm số riêng vào cùng lệnh danh sách: có mã nguồn kèm hai số thì lưu riêng; có mã nguồn kèm lời xóa thì đưa về mức chung. Hàm sửa nguồn hiện tại còn ghi đè trang đích khi thiếu danh sách trang. Đường Telegram chỉ được sửa hai số ngưỡng.

**Alternatives considered**: Màn hình mới để gõ số. Thêm một lệnh nữa cho cùng việc. Gọi hàm sửa nguồn cũ từ chat và vô tình xóa trang đích.

## Decision: Không dọn hàng chờ khi siết hoặc tắt

**Rationale**: Spec cấm xóa video đã chờ, đang xử lý, hay đã sẵn sàng. Ngưỡng mới chỉ chặn lần nhận sau.

**Alternatives considered**: Xóa video chờ của nguồn vừa tắt để hàng sạch ngay. Mất video chủ kênh có thể vẫn muốn xử lý.
