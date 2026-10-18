# Research: Lên lịch đăng bài từ Telegram

## Decision: Dùng mốc giờ trên job, không thêm bảng lịch

**Rationale**: Job đăng kênh đã có mốc giờ. Mốc bằng 0 thì vào hàng chờ. Mốc trong tương lai thì nơi đăng nhận lịch theo giờ đó. Mốc đã qua thì đường hiện tại coi là đăng ngay, nên Telegram không được gửi mốc đã qua. Xác nhận giờ lấy từ giờ nơi đăng trả về, đổi sang giờ Việt Nam bằng cách đang dùng ở hạn đăng.

**Alternatives considered**: Bảng lịch riêng rồi worker đăng sau. Thêm một nơi chờ nữa trong khi job và bài trên kênh đã là lịch. Lưu giờ chỉ trong chữ Telegram. Đổi máy là mất lịch.

## Decision: Lần chọn giờ thứ hai sửa bài đang có

**Rationale**: Cùng video cùng kênh, job đã xong và đã có mã bài thì lần xếp nữa đang trả «đã xếp» và dừng. Spec cấm lịch thứ hai. Khi có giờ mới, sửa bài đó sang giờ mới và ghi lại mốc trên cùng job. Sửa bài hôm nay không gửi giờ, nên phải gửi kèm giờ, nếu không bài bị coi là rỗng hoặc mất giờ đã chọn.

**Alternatives considered**: Xóa bài cũ rồi tạo bài mới. Dễ nhân đôi nếu lần xóa xong mà lần tạo lỗi. Tạo thêm job. Chủ kênh thấy hai lịch.

## Decision: Ba nút giờ gần, giờ khác thì gõ lệnh

**Rationale**: Bot không nhớ cuộc nói đang chờ giờ. Tin thường không phải lệnh chỉ được đọc nếu có link. Nút «Tối nay 20:00», «Sáng mai 08:00», «Tối mai 20:00» đủ cho việc hằng ngày và nằm trong 64 byte cùng kiểu nút bài đang có. Giờ khác dùng một lệnh có mã bài và mẫu `ngày/tháng giờ:phút`. Lệnh sai thì không gọi nơi đăng.

**Alternatives considered**: Nhớ trong bộ nhớ «tin tới là giờ». Poller khởi động lại thì quên, và tin link bị hiểu nhầm là giờ. Nhét cả ngày giờ vào nút bấm. Dễ vượt 64 byte.

## Decision: Hết suất chỉ chặn lúc tạo lịch có giờ

**Rationale**: Hạn trong ngày mà lệnh hạn đăng đang đọc chỉ là hôm nay. Mục tiêu tuần là cả kỳ. Lịch mới trong hôm nay bị chặn khi hôm nay hết suất. Mọi lịch mới bị chặn khi tuần hết suất. Ngày khác trong cửa sổ 30 ngày không có trần từng ngày để đọc, nên chỗ đó để nơi đăng từ chối và chat nói lỗi, không báo đã hẹn. Đổi giờ không tự trừ suất lần nữa trước khi sửa. Xếp hàng không chọn giờ không đi qua cửa này.

**Alternatives considered**: Chặn mọi ngày trong 30 ngày bằng trần hôm nay. Ngày mai bị cấm oan khi hôm nay đã đủ bài. Chặn cả xếp hàng không giờ. Đổi hành vi đang dùng.

## Decision: Hủy lịch là xóa bài chưa đăng, không đụng đăng ngay

**Rationale**: Xóa bài đang chờ đã có, nhưng đang không nhìn trạng thái đã đăng. Hủy lịch phải từ chối khi bài đã đăng và không nói hủy thành công. Nút đăng ngay và nút xếp hàng trên tin video giữ nguyên.

**Alternatives considered**: Chỉ chuyển nháp. Bài còn trên kênh, chủ kênh tưởng đã hủy. Đổi nút xóa hiện tại thành hủy có kiểm tra. Làm đổi nghĩa nút xóa đang dùng.
