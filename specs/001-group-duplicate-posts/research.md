# Research: Gộp bài trùng trong báo cáo chỉ số

## Decision: Gộp khi trình bày, không xóa lịch sử

**Rationale**: Năm bản cùng video vẫn nằm trong lịch sử đăng vì bài đã gửi không xóa được từ công cụ. Spec cấm giảm số bản sau khi xem báo cáo.

**Alternatives considered**: Gọi lệnh xóa từng bản. Đã thử trên năm bản đã gửi và bị từ chối. Đánh dấu ẩn trong kho riêng. Thêm chỗ lưu mới cho một việc chỉ đổi cách đọc.

## Decision: Khóa gộp là chữ đã chuẩn hóa, kênh, và ngày theo giờ Việt Nam

**Rationale**: Spec định nghĩa cùng nội dung bằng phần chữ, cùng kênh, cùng ngày. Chuẩn hóa là gộp khoảng trắng và xuống dòng thành một dấu cách, rồi so cả đoạn chữ, không cắt 80 ký tự đầu. Cắt ngắn sẽ gộp hai bài dài khác nhau chỉ vì mở đầu giống nhau.

**Alternatives considered**: So 80 ký tự đầu như dòng caption đang cắt khi hiện. Loại vì hai bài khác nhau có thể trùng mở đầu. So cả link trang. Loại vì các bản trùng không dùng chung một link.

## Decision: Dòng đã gộp lấy chỉ số của bản gửi muộn nhất, và ghi số bản

**Rationale**: Cộng lượt hiện của năm bản sẽ đếm trùng một video. Bản muộn nhất là bản chủ kênh nhìn thấy sau cùng. Số bản ghi rõ lịch sử còn giữ.

**Alternatives considered**: Cộng mọi chỉ số. Lấy bản có lượt hiện cao nhất. Cộng làm số to hơn số người thật đã xem một video. Lấy bản cao nhất có thể là bản đã gỡ trên trang và số không còn nghĩa.

## Decision: Tóm tắt kênh đếm nội dung, rồi nêu số bản nếu lớn hơn

**Rationale**: Dòng `5 bài` đang là lý do chủ kênh hiểu nhầm. Màn mọi kênh và màn một kênh dùng cùng câu đếm.

**Alternatives considered**: Giữ `5 bài` ở tóm tắt và chỉ gộp danh sách bên dưới. Không đạt story 2.

## Decision: Sửa chỗ dựng chữ báo cáo, không thêm lệnh mới

**Rationale**: `/so` đã có tóm tắt từng kênh và nút mở một kênh. Việc còn lại là đổi cách đếm và cách liệt kê trong hai hàm dựng chữ đó.

**Alternatives considered**: Lệnh mới `/so gop`. Thêm bước cho việc spec muốn xảy ra ngay khi xem kênh.
