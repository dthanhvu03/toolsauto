# Feature Specification: Bỏ phụ đề khi video đã có nhạc

**Feature Branch**: `002-skip-sub-with-music`

**Created**: 2026-09-24

**Status**: Draft

**Input**: User description: "Với những video mà có nhạc thì không cần viết sub."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Video nhạc không bị cháy phụ đề (Priority: P1)

Chủ kênh nhận một video sẵn sàng để đăng. Nếu phần nghe chính của video là nhạc, hình không có dòng phụ đề.

**Why this priority**: Phụ đề trên video nhạc che hình và không đúng việc chủ kênh cần. Đây là thay đổi duy nhất anh yêu cầu.

**Independent Test**: Đưa một video chỉ có nhạc, không có người nói thành câu. Video trả về không có chữ phụ đề trên hình.

**Acceptance Scenarios**:

1. **Given** một video mà phần nghe chính là bài hát hoặc nhạc không lời, **When** video được xử lý xong, **Then** hình không có phụ đề.
2. **Given** video nhạc đã xử lý xong, **When** chủ kênh xem video sẵn sàng, **Then** chủ kênh vẫn nhận được video và phần chữ đăng bài như hiện tại.

---

### User Story 2 - Video có lời nói vẫn có phụ đề (Priority: P2)

Video có người nói thành câu vẫn được viết phụ đề, kể cả khi phía dưới có nhạc nền nhỏ.

**Why this priority**: Nếu mọi video có chút nhạc đều mất phụ đề, các video kể chuyện sẽ mất chữ mà chủ kênh đang dùng.

**Independent Test**: Đưa một video có người nói thành câu, kèm nhạc nền. Video trả về vẫn có phụ đề cho lời nói.

**Acceptance Scenarios**:

1. **Given** một video có người nói thành câu, **When** video được xử lý xong, **Then** hình có phụ đề cho lời nói đó.
2. **Given** video nói chuyện có nhạc nền nhỏ, **When** video được xử lý xong, **Then** phụ đề vẫn được viết.

---

### Edge Cases

- Không phân biệt được video có nhạc hay có lời nói: vẫn viết phụ đề như hiện tại.
- Video không có tiếng: vẫn xử lý như hiện tại, không thêm phụ đề mới chỉ vì quy tắc này.
- Video đã xử lý xong trước khi có quy tắc này: không làm lại.
- Phần chữ dùng để đăng bài không đổi vì video có nhạc.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Khi phần nghe chính của video là nhạc, hệ thống MUST bỏ bước viết phụ đề lên hình.
- **FR-002**: Khi video có người nói thành câu, hệ thống MUST vẫn viết phụ đề, kể cả khi có nhạc nền.
- **FR-003**: Khi không xác định được phần nghe chính là nhạc hay lời nói, hệ thống MUST giữ cách viết phụ đề hiện tại.
- **FR-004**: Bỏ phụ đề MUST không bỏ video, không bỏ phần chữ đăng bài, và không đổi video đã xử lý xong trước đó.

### Key Entities

- **Video sẵn sàng**: Bản video chủ kênh nhận để đăng.
- **Phụ đề trên hình**: Chữ cháy trên video cho lời nói. Không phải phần chữ đăng bài.
- **Phần nghe chính**: Nhạc khi người xem nghe thấy bài hát hoặc nhạc không lời là chính. Lời nói khi nghe rõ người nói thành câu.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Trong một lượt thử với một video chỉ có nhạc, video sẵn sàng không có chữ phụ đề trên hình.
- **SC-002**: Trong một lượt thử với một video có người nói thành câu, video sẵn sàng có phụ đề cho lời nói đó.
- **SC-003**: Cùng một video nhạc, phần chữ đăng bài trước và sau quy tắc này giống nhau.
- **SC-004**: Một video đã xử lý xong trước quy tắc này không bị làm lại chỉ vì quy tắc này.

## Assumptions

- «Viết sub» nghĩa là phụ đề cháy trên hình, không phải phần chữ dùng để đăng bài.
- «Có nhạc» nghĩa là phần nghe chính là nhạc. Nhạc nền dưới lời nói không tính là video nhạc.
- Không bật thuyết minh cho mọi video. Cách thuyết minh hiện tại giữ nguyên.
- Không đổi cách xếp hàng, cách chọn giờ đăng, hay cách quét nguồn.
