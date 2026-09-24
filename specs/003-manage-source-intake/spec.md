# Feature Specification: Quản lý nguồn khi video đổ về nhiều

**Feature Branch**: `003-manage-source-intake`

**Created**: 2026-09-24

**Status**: Draft

**Input**: User description: "Hiện video đổ về nhiều quá. Các nguồn thì nghiệp vụ quản lý như nào?"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Thấy nguồn nào đang đổ video (Priority: P1)

Chủ kênh mở danh sách nguồn và biết từng nguồn đang bật hay tắt, ngưỡng của nguồn đó, và còn bao nhiêu video mới của nguồn đó đang chờ xử lý.

**Why this priority**: Khi video đổ nhiều, việc đầu tiên là biết nguồn nào gây đầy hàng, trước khi tắt hay siết ngưỡng.

**Independent Test**: Có hai nguồn, một nguồn vừa đưa 20 video mới vào hàng chờ, nguồn kia không có video chờ. Danh sách hiện đúng 20 ở nguồn thứ nhất và 0 ở nguồn thứ hai.

**Acceptance Scenarios**:

1. **Given** một nguồn vừa quét và đưa video mới vào hàng chờ, **When** chủ kênh mở danh sách nguồn, **Then** nguồn đó hiện số video mới còn chờ và kết quả lần quét gần nhất.
2. **Given** hai nguồn, **When** chủ kênh xem danh sách, **Then** số video chờ của nguồn này không cộng vào nguồn kia.

---

### User Story 2 - Tạm dừng một nguồn mà không mất video đã có (Priority: P1)

Chủ kênh tắt một nguồn đang đổ quá nhiều. Nguồn đó không được quét thêm. Video đã nằm trong hàng chờ vẫn còn.

**Why this priority**: Tắt nguồn là cách dừng vòi nước ngay, không cần xóa việc đã nhận.

**Independent Test**: Tắt một nguồn đang có video chờ, rồi bấm quét nguồn đó. Không có video mới. Số video đang chờ không giảm.

**Acceptance Scenarios**:

1. **Given** một nguồn đang bật và còn video chờ, **When** chủ kênh tắt nguồn đó rồi quét, **Then** không thêm video mới và video đang chờ vẫn còn.
2. **Given** một nguồn đang tắt, **When** chủ kênh bật lại rồi quét, **Then** nguồn được quét trở lại theo ngưỡng đang có hiệu lực.

---

### User Story 3 - Đặt ngưỡng riêng cho một nguồn (Priority: P2)

Chủ kênh đặt cho riêng một nguồn mức xem tối thiểu và số video mới tối đa mỗi lần quét. Nguồn khác và mức chung không đổi. Lần quét sau chỉ nhận video đủ mức xem, và dừng khi đủ số tối đa.

**Why this priority**: Tắt hẳn thì mất nguồn. Siết riêng một nguồn đang ồn để các nguồn khác vẫn chảy bình thường.

**Independent Test**: Nguồn A đặt tối thiểu 1.000 lượt xem và tối đa 3 video. Lần quét có 10 video trên 1.000 lượt xem thì chỉ thêm 3. Nguồn B vẫn dùng mức chung.

**Acceptance Scenarios**:

1. **Given** một nguồn chưa có số riêng, **When** chủ kênh đặt mức xem tối thiểu và số video tối đa cho nguồn đó, **Then** lần quét sau của nguồn đó dùng hai số này.
2. **Given** nguồn A đã có số riêng, **When** chủ kênh xem nguồn B, **Then** nguồn B vẫn dùng mức chung.
3. **Given** chủ kênh xóa số riêng của một nguồn, **When** quét nguồn đó, **Then** nguồn dùng lại mức chung.

---

### Edge Cases

- Số riêng không phải số nguyên, hoặc số video tối đa nhỏ hơn 1: không lưu, và báo cho chủ kênh biết vì sao.
- Siết ngưỡng hoặc tắt nguồn không xóa video đã chờ, video đang xử lý, hay video đã sẵn sàng.
- Nguồn không có số riêng dùng mức chung. Mức chung đổi thì chỉ các nguồn chưa có số riêng đổi theo.
- Quét một nguồn đang tắt không thêm video và nói rõ nguồn đang tắt.
- Một lần quét gặp nhiều video cùng đủ mức xem: lấy đủ số tối đa của nguồn đó rồi dừng, không lấy thêm trong lần đó.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Danh sách nguồn MUST cho mỗi nguồn biết trạng thái bật hoặc tắt, ngưỡng đang dùng, số video mới còn chờ của đúng nguồn đó, và kết quả lần quét gần nhất.
- **FR-002**: Chủ kênh MUST tắt hoặc bật được từng nguồn. Nguồn tắt MUST không được thêm video mới khi quét.
- **FR-003**: Chủ kênh MUST đặt được, cho riêng một nguồn, mức xem tối thiểu và số video mới tối đa mỗi lần quét. Bỏ hai số đó MUST đưa nguồn về mức chung.
- **FR-004**: Một lần quét MUST chỉ thêm video đạt mức xem đang có hiệu lực, và MUST dừng khi đủ số video tối đa đang có hiệu lực của nguồn đó.
- **FR-005**: Tắt nguồn hoặc siết ngưỡng MUST không xóa video đã chờ, video đang xử lý, hay video đã sẵn sàng.

### Key Entities

- **Nguồn**: Một kênh được theo dõi. Có trạng thái bật hoặc tắt, có thể có mức xem tối thiểu riêng và số video tối đa riêng.
- **Mức chung**: Mức xem tối thiểu và số video tối đa dùng cho mọi nguồn chưa đặt số riêng.
- **Video mới còn chờ**: Video đã nhận từ một nguồn và chưa được xử lý xong. Gắn với đúng nguồn đã đưa nó vào.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Với hai nguồn, chủ kênh chỉ trong một lần xem danh sách chỉ đúng số video chờ của từng nguồn, không cộng chéo.
- **SC-002**: Sau khi tắt một nguồn và quét nguồn đó, số video mới thêm vào là 0, và số video đã chờ trước đó không giảm.
- **SC-003**: Một nguồn đặt tối đa 3 video, trong một lần quét có từ 3 video trở lên đủ mức xem, chỉ thêm đúng 3 video.
- **SC-004**: Đổi số riêng của một nguồn không đổi số riêng của nguồn khác và không đổi mức chung.

## Assumptions

- «Đổ về nhiều» nghĩa là hàng video mới chờ xử lý đầy vì một hoặc vài nguồn, không phải lỗi tải một video.
- Cách dừng ngay là tắt đúng nguồn đó. Cách chảy chậm là đặt mức xem và số video tối đa cho riêng nguồn đó.
- Video đã nhận không bị xóa khi đổi cách quản lý. Chỉ lần nhận sau mới theo ngưỡng mới.
- Mức chung hiện có vẫn là mức mặc định. Spec này thêm lớp số riêng và việc nhìn thấy nguồn nào đang đổ.
- Không đổi cách viết phụ đề, cách xếp hàng, hay cách chọn giờ đăng.
