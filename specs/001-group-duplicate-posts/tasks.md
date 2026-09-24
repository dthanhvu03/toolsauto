---

description: "Task list for grouping duplicate sent posts in the channel stats report"
---

# Tasks: Gộp bài trùng trong báo cáo chỉ số

**Input**: Design documents from `/specs/001-group-duplicate-posts/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/channel-report.md, quickstart.md

**Tests**: Có. `quickstart.md` yêu cầu ca pytest cho năm bản, hai chữ, hai ngày, và câu tóm tắt. Viết ca trước, thấy lỗi, rồi mới sửa hàm dựng chữ.

**Organization**: Story 1 là danh sách một kênh. Story 2 là câu đếm ở tóm tắt. Cả hai dùng chung hàm gộp ở Phase 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được vì khác file và không phụ thuộc việc chưa xong
- **[Story]**: US1 hoặc US2

## Path Conventions

- `app/features/buffer/client.py`
- `tests/test_buffer_api.py`
- Bot giữ `/so` và nút kênh. Không thêm lệnh.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Khóa phạm vi. Không tạo module mới.

- [x] T001 Xác nhận không thêm gói, bảng, hay lệnh. Mọi sửa code của feature này chỉ nằm trong `app/features/buffer/client.py` và `tests/test_buffer_api.py`, theo `specs/001-group-duplicate-posts/plan.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Hàm gộp dùng cho cả hai story

**⚠️ CRITICAL**: Chưa xong phase này thì chưa sửa câu hiện của kênh

- [x] T002 Thêm hàm chuẩn hóa chữ và lấy ngày giờ Việt Nam trong `app/features/buffer/client.py`. Chữ so sánh là cả đoạn sau khi gộp khoảng trắng và xuống dòng thành một dấu cách, không cắt 80 ký tự. Ngày là ngày của thời điểm đã gửi theo giờ Việt Nam. Bản thiếu thời điểm gửi không gộp với bản đã có ngày
- [x] T003 Thêm hàm gộp trong `app/features/buffer/client.py`. Một nhóm là các bản cùng kênh, cùng chữ đã chuẩn hóa, cùng ngày. Số bản ít nhất là 1. Bản đại diện là bản có thời điểm gửi muộn nhất trong nhóm. Hàm không gọi xóa bản

**Checkpoint**: Gọi hàm gộp với dữ liệu giả ra đúng nhóm, chưa cần đổi tin Telegram

---

## Phase 3: User Story 1 - Một video hiện một dòng (Priority: P1) 🎯 MVP

**Goal**: Xem một kênh thì cùng nội dung trong một ngày chỉ còn một khối, có ghi số bản lịch sử

**Independent Test**: Năm bản cùng chữ, cùng kênh, cùng ngày thành một khối ghi 5 bản. Hai chữ khác nhau thành hai khối. Cùng chữ hai ngày thành hai khối

### Tests for User Story 1

- [x] T004 [US1] Thêm ca thất bại trước trong `tests/test_buffer_api.py`: năm bản cùng chữ cùng kênh cùng ngày ra một nhóm với số bản 5. Hai chữ khác nhau ra hai nhóm. Cùng chữ ở hai ngày ra hai nhóm. Ca không gọi xóa bản

### Implementation for User Story 1

- [x] T005 [US1] Đổi `insights_channel` trong `app/features/buffer/client.py` để mỗi nhóm một khối `describe_post` của bản đại diện. Nếu số bản lớn hơn 1 thì khối đó có chữ `M bản lịch sử`. Thứ tự nhóm theo bản đại diện, muộn nhất trước. Kênh không có bản vẫn một câu chưa có bài đã đăng, không khối trống

**Checkpoint**: Story 1 xem một kênh được, dù dòng tóm tắt mọi kênh chưa đổi

---

## Phase 4: User Story 2 - Tóm tắt kênh không đếm nhầm số video (Priority: P2)

**Goal**: Dòng đầu kênh đếm số nội dung, và nêu số bản khi số bản lớn hơn số nội dung

**Independent Test**: Năm bản một nội dung cho câu một nội dung và năm bản lịch sử, không câu năm nội dung

### Tests for User Story 2

- [x] T006 [US2] Thêm ca trong `tests/test_buffer_api.py`: tóm tắt của năm bản cùng nội dung chứa `1 nội dung` và `5 bản lịch sử`, và không mô tả đó là năm nội dung khác nhau

### Implementation for User Story 2

- [x] T007 [US2] Đổi câu từng kênh trong `_insights_text` của `app/features/buffer/client.py`. Nếu số bản bằng số nội dung thì `N nội dung`. Nếu số bản lớn hơn thì `N nội dung · M bản lịch sử`. Chỉ số cộng ở dòng dưới chỉ lấy bản đại diện của mỗi nhóm, không cộng năm bản của một video
- [x] T008 [US2] Đổi dòng đầu của `insights_channel` trong `app/features/buffer/client.py` sang cùng câu đếm với T007, gồm tên kênh và tháng

**Checkpoint**: Màn mọi kênh và màn một kênh cùng một cách đếm

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Khớp quickstart, không đụng luồng đăng

- [x] T009 Chạy `./venv/bin/python -m pytest tests/test_buffer_api.py -q --tb=short` từ gốc repo và đối chiếu `specs/001-group-duplicate-posts/quickstart.md`
- [x] T010 Rà `app/features/buffer/client.py` để đường dựng báo cáo không gọi xóa bản đã gửi

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Bắt đầu ngay
- **Foundational (Phase 2)**: Sau T001. Chặn mọi story
- **User Story 1 (Phase 3)**: Sau T003
- **User Story 2 (Phase 4)**: Sau T003. Nên sau T005 vì cùng sửa `insights_channel`
- **Polish (Phase 5)**: Sau story muốn giao

### User Story Dependencies

- **User Story 1 (P1)**: Không cần story 2. Danh sách một kênh tự đủ
- **User Story 2 (P2)**: Dùng hàm gộp của Phase 2. Câu đếm kiểm tra được dù story 1 chưa gắn vào tin kênh, nhưng T008 đụng cùng hàm với T005 nên làm sau T005

### Within Each User Story

- Ca test viết trước và phải đỏ trước khi sửa hàm hiện
- Hàm gộp xong rồi mới đổi câu tin

### Parallel Opportunities

- Không có task [P]. T004 và T006 cùng file test. T005, T007, T008 cùng `client.py`

---

## Parallel Example: User Story 1

Không tách song song. Một người làm T004 rồi T005 trong hai file theo thứ tự đó.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Xong Phase 1 và Phase 2
2. Xong Phase 3
3. Dừng. Mở một kênh có năm bản cùng video và thấy một khối ghi 5 bản
4. Story 2 làm tiếp để dòng tóm tắt hết ghi nhầm năm nội dung

### Incremental Delivery

1. Hàm gộp xong là nền
2. Story 1 giao danh sách một kênh
3. Story 2 giao câu đếm cho cả màn mọi kênh và dòng đầu một kênh

---

## Notes

- Không thêm file module mới
- Không sửa `app/features/telegram_bot/command_handler.py` trừ khi câu chữ trả về làm vỡ ca `/so` hiện có
- Tin `/so` đã gửi không tự đổi. Chủ kênh gõ lại lệnh
