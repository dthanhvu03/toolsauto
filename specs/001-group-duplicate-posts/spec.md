# Feature Specification: Gộp bài trùng trong báo cáo chỉ số

**Feature Branch**: `001-group-duplicate-posts`

**Created**: 2026-09-23

**Status**: Draft

**Input**: User description: "Triển khai đề xuất gộp các bài trùng cùng kênh, cùng ngày trong báo cáo chỉ số, để chủ kênh thấy một video thay vì nhiều bản sao lịch sử."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Một video hiện một dòng (Priority: P1)

Chủ kênh mở báo cáo chỉ số của một kênh trong tháng. Cùng một nội dung đã bị đăng nhiều lần trong ngày vẫn chỉ xuất hiện một dòng, kèm số bản lịch sử còn giữ.

**Why this priority**: Năm bản của một video đang khiến báo cáo trông như năm bài khác nhau, dù chủ kênh đã gỡ các bản trên trang.

**Independent Test**: Mở báo cáo một kênh có nhiều bản cùng nội dung trong một ngày và đếm số dòng. Kết quả là một dòng cho nội dung đó, có ghi số bản.

**Acceptance Scenarios**:

1. **Given** một kênh có năm bản đã gửi của cùng một nội dung trong cùng một ngày, **When** chủ kênh xem chỉ số kênh đó, **Then** chủ kênh thấy một dòng cho nội dung đó và thấy rõ còn năm bản trong lịch sử.
2. **Given** một kênh có hai nội dung khác nhau đã gửi trong tháng, **When** chủ kênh xem chỉ số kênh đó, **Then** chủ kênh thấy hai dòng riêng.
3. **Given** cùng một nội dung được gửi ở hai kênh, **When** chủ kênh xem từng kênh, **Then** mỗi kênh có dòng của riêng kênh đó.

---

### User Story 2 - Tóm tắt kênh không đếm nhầm số video (Priority: P2)

Dòng tóm tắt của kênh cho biết số nội dung khác nhau, và nói thêm có bao nhiêu bản lịch sử thừa.

**Why this priority**: Nếu tiêu đề vẫn ghi năm bài, chủ kênh vẫn hiểu nhầm là đã đăng năm video.

**Independent Test**: So số ở dòng tóm tắt với số dòng nội dung bên dưới. Hai số khớp về số nội dung khác nhau.

**Acceptance Scenarios**:

1. **Given** một kênh có năm bản của một nội dung, **When** chủ kênh xem tóm tắt kênh, **Then** tóm tắt nói một nội dung và năm bản lịch sử, không nói năm nội dung khác nhau.
2. **Given** một kênh chưa có bài trong tháng, **When** chủ kênh xem kênh đó, **Then** báo cáo nói chưa có bài, không hiện dòng trống.

---

### Edge Cases

- Hai bài khác nhau nhưng trùng nguyên văn nội dung, cùng kênh, cùng ngày, bị gom thành một dòng và ghi số bản.
- Cùng nội dung đăng ở hai ngày khác nhau vẫn là hai dòng.
- Bản lịch sử không bị xóa. Chủ kênh vẫn thấy số bản còn giữ.
- Kênh không có bài trong tháng vẫn báo chưa có bài.
- Nếu báo cáo chỉ lấy một phần bài mới nhất của tháng, việc gộp chỉ áp dụng trên phần đang hiện.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Khi xem chỉ số một kênh, hệ thống MUST gộp các bản đã gửi cùng nội dung, cùng kênh, cùng ngày thành một dòng.
- **FR-002**: Dòng đã gộp MUST cho biết số bản lịch sử còn giữ.
- **FR-003**: Dòng tóm tắt của kênh MUST đếm số nội dung khác nhau, và MUST nêu số bản lịch sử nếu số bản lớn hơn số nội dung.
- **FR-004**: Hệ thống MUST giữ nguyên các bản trong lịch sử đăng. Việc gộp chỉ đổi cách trình bày.
- **FR-005**: Hai nội dung khác chữ, hoặc khác ngày, hoặc khác kênh, MUST vẫn hiện thành các dòng riêng.
- **FR-006**: Kênh không có bài trong tháng MUST vẫn báo chưa có bài đã đăng.

### Key Entities

- **Bản đã gửi**: Một lần nội dung đã được gửi lên một kênh, có ngày gửi và chỉ số lượt hiện.
- **Nội dung**: Phần chữ của bài. Các bản cùng chữ, cùng kênh, cùng ngày được xem là cùng một nội dung khi trình bày.
- **Kênh**: Trang mà chủ kênh chọn để xem chỉ số riêng.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Với trường hợp năm bản của một nội dung trên một kênh trong một ngày, báo cáo kênh đó hiện đúng một dòng và ghi năm bản.
- **SC-002**: Chủ kênh phân biệt được số nội dung và số bản lịch sử trong một lần xem, không cần đối chiếu từng dòng một.
- **SC-003**: Hai nội dung khác nhau trên cùng kênh vẫn hiện hai dòng trong lần xem đó.
- **SC-004**: Sau khi xem báo cáo, số bản trong lịch sử đăng không giảm.

## Assumptions

- «Cùng nội dung» nghĩa là phần chữ hiển thị của bài giống nhau. Ảnh, chữ và video không tách nhóm nếu chữ giống nhau.
- Ngày tính theo giờ Việt Nam.
- Việc gộp áp dụng khi xem một kênh. Màn tóm tắt mọi kênh chỉ cần số nội dung và số bản, không liệt kê từng bản.
- Không thêm bước xóa lịch sử, vì lịch sử bài đã gửi không xóa được từ công cụ.
- Không đổi cách đăng bài, không đổi nút đăng lại, và không thêm thông báo khi bài lên trang.
