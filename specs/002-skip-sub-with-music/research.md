# Research: Bỏ phụ đề khi video đã có nhạc

## Decision: Lọc đoạn đã nghe, không thêm bộ phân loại nhạc

**Rationale**: Lớp phụ đề đã nghe video và nhận từng đoạn kèm điểm «không phải lời nói» và tỷ lệ lặp chữ. Nhạc và chữ bịa trên nhạc thường có điểm không-phải-lời-nói cao hoặc chữ lặp bất thường. Lọc trên điểm đó đủ để bỏ phụ đề mà không nghe lại video.

**Alternatives considered**: Bộ tách nhạc và lời nói riêng. Thêm gói và một lượt xử lý nữa cho một quy tắc chỉ cần bỏ chữ bịa. Hỏi chủ kênh từng video. Spec muốn việc này xảy ra lúc xử lý, không thêm bước bấm.

## Decision: Ngưỡng lấy đúng mức bộ nghe đang dùng làm mặc định

**Rationale**: Đoạn có điểm không-phải-lời-nói từ 0,6 trở lên bị bỏ. Đoạn có tỷ lệ lặp chữ trên 2,4 bị bỏ. Hai mốc này là ngưỡng sẵn của bộ nghe để loại im lặng và chữ lặp. Lời nói thật, kể cả khi có nhạc nền nhỏ, thường nằm dưới mốc không-phải-lời-nói nên vẫn được giữ.

**Alternatives considered**: Bỏ cả video ngay khi có một đoạn nhạc. Sai story 2: video nói chuyện có nhạc nền vẫn phải có phụ đề cho câu nói. Hạ ngưỡng xuống 0,3. Dễ bỏ nhầm lời nói nhỏ.

## Decision: Thiếu điểm số thì giữ đoạn

**Rationale**: Spec bắt khi không xác định được thì viết phụ đề như hiện tại. Đoạn giả trong ca kiểm tra cũ không có hai điểm này. Giữ chúng để các ca đang xanh không đổi nghĩa.

**Alternatives considered**: Coi đoạn thiếu điểm là nhạc và bỏ. Làm video nói chuyện bị mất phụ đề khi bộ nghe không trả điểm.

## Decision: Hết đoạn thì đi đúng lối «không cháy» đang có

**Rationale**: Khi không còn đoạn nào, lớp phụ đề đã trả không áp dụng và không tạo hình có chữ. Không cần đường tắt mới. Video không có tiếng cũng đã trả danh sách rỗng.

**Alternatives considered**: Xóa file phụ đề sau khi đã cháy. Muộn và tốn một lần mã hóa hình.

## Decision: Không làm lại video đã xong, không đụng chữ đăng bài, không bật thuyết minh

**Rationale**: Spec giới hạn quy tắc này cho lần xử lý từ nay. Chữ đăng bài và thuyết minh là việc khác.

**Alternatives considered**: Quét kho video sẵn sàng và làm lại. Đụng file đã giao cho chủ kênh mà spec cấm.
