# Feature Specification: Lên lịch đăng bài từ Telegram

**Feature Branch**: `004-telegram-schedule-post`

**Created**: 2026-09-24

**Status**: Draft

**Input**: User description: "Kiểm tra đã có chức năng lên lịch đăng bài từ Telegram chưa. Hiện chưa có: từ Telegram chỉ xếp vào hàng chờ (giờ do hàng chờ tính) hoặc đăng ngay. Cần cho chủ kênh chọn ngày giờ đăng cụ thể ngay trong Telegram."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Chọn giờ đăng cho video sẵn sàng (Priority: P1)

Chủ kênh nhận tin video đã xử lý xong trên Telegram, chọn kênh đăng, rồi chọn một ngày giờ cụ thể. Bài được hẹn đăng đúng giờ đó. Chat xác nhận lại kênh và giờ theo giờ Việt Nam.

**Why this priority**: Đây là việc chủ kênh đang thiếu. Hôm nay bấm kênh chỉ đưa bài vào hàng chờ, không chọn được giờ.

**Independent Test**: Có một video sẵn sàng và một kênh đang nối. Chọn giờ hợp lệ trong tương lai. Chat báo đúng kênh và đúng giờ. Bài không đăng ngay.

**Acceptance Scenarios**:

1. **Given** video đã sẵn sàng và kênh đang nối, **When** chủ kênh chọn kênh rồi chọn một giờ hợp lệ trong tương lai, **Then** bài được hẹn đăng vào giờ đó và chat xác nhận tên kênh cùng ngày giờ Việt Nam.
2. **Given** chủ kênh vừa hẹn giờ, **When** chưa tới giờ đã chọn, **Then** bài chưa xuất hiện công khai trên kênh.
3. **Given** video chưa có lời bài, **When** chủ kênh cố hẹn giờ, **Then** không tạo lịch và chat nói rõ còn thiếu lời bài.

---

### User Story 2 - Đổi giờ hoặc hủy lịch trước khi đăng (Priority: P1)

Chủ kênh xem bài đã hẹn, đổi sang giờ khác, hoặc hủy lịch. Chat báo trạng thái mới. Bài đã hủy không tự đăng.

**Why this priority**: Hẹn nhầm giờ mà không sửa được thì lịch thành gánh nợ vận hành.

**Independent Test**: Hẹn một bài, đổi giờ, xác nhận giờ mới. Hủy một bài khác, xác nhận bài đó không còn lịch và không đăng.

**Acceptance Scenarios**:

1. **Given** một bài đã có giờ hẹn, **When** chủ kênh chọn giờ hợp lệ khác, **Then** chỉ còn giờ mới và chat xác nhận giờ mới.
2. **Given** một bài đã có giờ hẹn, **When** chủ kênh hủy lịch, **Then** bài không còn giờ hẹn và không tự đăng.
3. **Given** một bài đã đăng xong, **When** chủ kênh cố đổi giờ hoặc hủy, **Then** không đổi gì và chat nói bài đã đăng.

---

### User Story 3 - Từ chối giờ không hợp lệ (Priority: P2)

Chủ kênh gõ hoặc chọn giờ ở quá khứ, quá gần, quá xa, hoặc không đọc được. Không tạo lịch. Chat nói vì sao và nhắc cách nhập lại.

**Why this priority**: Giờ sai không được âm thầm thành "đăng ngay" hay thành slot hàng chờ.

**Independent Test**: Gửi lần lượt giờ quá khứ, giờ thiếu ngày, và giờ ngoài cửa sổ cho phép. Mỗi lần không có bài mới được hẹn, và câu trả lời nói rõ lý do.

**Acceptance Scenarios**:

1. **Given** video sẵn sàng, **When** chủ kênh chọn giờ đã qua, **Then** không tạo lịch và chat nói giờ phải ở tương lai.
2. **Given** video sẵn sàng, **When** chủ kênh nhập giờ không đọc được, **Then** không tạo lịch và chat đưa một mẫu ngày giờ đúng.
3. **Given** một lần nhập sai, **When** chủ kênh nhập lại giờ hợp lệ, **Then** lịch được tạo như chuyện 1.

---

### User Story 4 - Giữ xếp hàng chờ và đăng ngay (Priority: P2)

Chủ kênh vẫn xếp bài vào hàng chờ mà không chọn giờ, và vẫn bấm đăng ngay trên bài đang chờ. Hai cách cũ không bị lịch mới chặn.

**Why this priority**: Lên lịch là thêm một cách đăng, không thay thế cách đang dùng mỗi ngày.

**Independent Test**: Với cùng một video sẵn sàng, xếp hàng chờ không chọn giờ vẫn vào hàng chờ. Với một bài đang chờ, đăng ngay vẫn đăng không cần chọn giờ.

**Acceptance Scenarios**:

1. **Given** video sẵn sàng, **When** chủ kênh xếp vào kênh mà không chọn giờ, **Then** bài vào hàng chờ như hiện tại và chat không bắt buộc chọn giờ.
2. **Given** bài đang trong hàng chờ, **When** chủ kênh bấm đăng ngay, **Then** bài được đưa đi đăng mà không hỏi giờ.

---

### Edge Cases

- Giờ đúng cửa sổ nhưng kênh đã hết suất đăng trong ngày hoặc trong tuần: không tạo lịch, chat nói hết suất.
- Cùng một video, cùng một kênh, đã có lịch: lần chọn giờ sau là đổi giờ, không tạo lịch thứ hai.
- Cùng một video hẹn hai kênh khác nhau: mỗi kênh một lịch riêng.
- Hủy lịch khi bài đang được đưa đi đăng: chat nói không hủy được nữa, không báo hủy thành công.
- Chat không phải của chủ kênh: không tạo, không đổi, không hủy lịch.
- Chủ kênh chọn giờ rồi mất kết nối trước khi nhận xác nhận: khi nhắn lại, trạng thái lịch khớp với lần chọn đã ghi nhận, không nhân đôi lịch.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Chủ kênh MUST hẹn được một ngày giờ đăng cụ thể cho video sẵn sàng, trên một kênh đang nối, ngay trong Telegram.
- **FR-002**: Hệ thống MUST xác nhận lại trong cùng cuộc chat: tên kênh và ngày giờ theo giờ Việt Nam, trong vòng 10 giây sau khi nhận giờ hợp lệ.
- **FR-003**: Bài đã hẹn MUST chưa đăng công khai trước giờ đã chọn.
- **FR-004**: Chủ kênh MUST xem được bài nào đang hẹn, kênh nào, và giờ nào, ngay trong Telegram.
- **FR-005**: Chủ kênh MUST đổi được giờ của một bài chưa đăng.
- **FR-006**: Chủ kênh MUST hủy được lịch của một bài chưa đăng. Bài đã hủy MUST không tự đăng.
- **FR-007**: Hệ thống MUST từ chối giờ đã qua, giờ không đọc được, giờ sớm hơn 10 phút, và giờ xa hơn 30 ngày. Mỗi lần từ chối MUST nói lý do bằng tiếng Việt và MUST không tạo lịch.
- **FR-008**: Khi thiếu lời bài, kênh không có trong danh sách, hoặc kênh hết suất, hệ thống MUST không tạo lịch và MUST nói rõ thiếu gì.
- **FR-009**: Xếp vào hàng chờ mà không chọn giờ, và đăng ngay bài đang chờ, MUST vẫn làm được như hiện tại.
- **FR-010**: Chỉ cuộc chat của chủ kênh MUST được hẹn, đổi, hoặc hủy lịch.
- **FR-011**: Chọn giờ lần hai cho cùng video và cùng kênh MUST đổi lịch đang có, không tạo thêm một lịch nữa.

### Key Entities

- **Lịch đăng**: Một lần hẹn của một video lên một kênh, gồm giờ đăng theo giờ Việt Nam và trạng thái đang hẹn, đã hủy, hoặc đã đăng.
- **Video sẵn sàng**: Video đã xử lý xong, có lời bài, đang chờ chủ kênh quyết định đăng.
- **Kênh đăng**: Kênh chủ kênh đã nối và đang thấy trong Telegram khi chọn nơi đăng.
- **Hàng chờ**: Tập bài đã giao cho kênh nhưng chưa chọn giờ cụ thể, hoặc đang chờ tới lượt theo hàng chờ.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Chủ kênh hẹn xong một bài, từ tin video đến tin xác nhận giờ, trong dưới 1 phút, không cần mở màn hình quản trị.
- **SC-002**: 100% lần chọn giờ đã qua, không đọc được, sớm hơn 10 phút, hoặc xa hơn 30 ngày bị từ chối và không sinh lịch.
- **SC-003**: Trong lần dùng thử 10 bài hẹn giờ hợp lệ, cả 10 tin xác nhận đúng kênh và đúng giờ Việt Nam đã chọn.
- **SC-004**: Đổi giờ hoặc hủy lịch xong, tin trả lời trong dưới 10 giây và đúng trạng thái mới.
- **SC-005**: Trên 10 lần xếp hàng chờ không chọn giờ và 10 lần đăng ngay, cả 20 lần vẫn xong mà không bị hỏi giờ.

## Assumptions

- Người dùng là một chủ kênh, thao tác trong đúng cuộc chat Telegram đang nối với tool.
- Giờ hiển thị và giờ chủ kênh nhập là giờ Việt Nam (UTC+7).
- Cửa sổ giờ hợp lệ là từ 10 phút tới 30 ngày kể từ lúc chọn. Ngoài cửa sổ đó thì từ chối.
- Cách nhập mặc định: chọn từ gợi ý giờ gần (ví dụ tối nay, sáng mai) hoặc gõ một mẫu ngày giờ được nhắc trong chat khi nhập sai.
- Lên lịch áp dụng cho kênh chủ kênh đã thấy khi bấm đăng từ Telegram. Không thêm kênh mới trong phạm vi này.
- Xếp hàng chờ không chọn giờ và nút đăng ngay giữ nguyên hành vi hiện tại.
- Không gồm lịch lặp lại hàng ngày, không gồm gợi ý giờ đẹp bằng máy, không gồm sửa lời bài trong lúc hẹn giờ.
