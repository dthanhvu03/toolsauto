---

description: "Task list for skipping burned subtitles on music-led videos"
---

# Tasks: Bỏ phụ đề khi video đã có nhạc

**Input**: Design documents from `/specs/002-skip-sub-with-music/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/subtitle-decision.md, quickstart.md

**Tests**: Có. `quickstart.md` yêu cầu ca pytest cho đoạn nhạc, đoạn lặp chữ, đoạn thiếu điểm, và video vừa có lời nói vừa có nhạc. Viết ca trước, thấy lỗi, rồi mới nối hàm lọc vào đường nghe.

**Organization**: Story 1 là video chỉ có nhạc thì không cháy phụ đề. Story 2 là video có câu nói vẫn giữ phụ đề. Cả hai dùng chung hàm lọc ở Phase 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được vì khác file và không phụ thuộc việc chưa xong
- **[Story]**: US1 hoặc US2

## Path Conventions

- `app/features/viral_intake/subtitle_layer.py`
- `tests/test_subtitle_layer.py`
- Không sửa `app/features/viral_intake/reup_processor.py` trừ khi rà soát thấy nó tự cháy phụ đề sau khi lớp phụ đề trả không áp dụng.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Khóa phạm vi. Không tạo module mới.

- [x] T001 Xác nhận không thêm gói, bảng, hay lệnh. Mọi sửa code của feature này chỉ nằm trong `app/features/viral_intake/subtitle_layer.py` và `tests/test_subtitle_layer.py`, theo `specs/002-skip-sub-with-music/plan.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Hàm lọc đoạn dùng cho cả hai story

**⚠️ CRITICAL**: Chưa xong phase này thì chưa nối vào đường nghe

- [x] T002 Thêm hàm lọc đoạn trong `app/features/viral_intake/subtitle_layer.py`. Đoạn có điểm không phải lời nói từ 0,6 trở lên thì bỏ. Đoạn có tỷ lệ lặp chữ trên 2,4 thì bỏ. Thiếu điểm nào thì không dùng điểm đó để bỏ. Chữ rỗng thì bỏ. Kết thúc không sau bắt đầu thì bỏ. Hàm chưa được gọi từ đường nghe

**Checkpoint**: Gọi hàm lọc với đoạn giả ra đúng danh sách giữ, chưa cần video

---

## Phase 3: User Story 1 - Video nhạc không bị cháy phụ đề (Priority: P1) 🎯 MVP

**Goal**: Video mà mọi đoạn đều rõ là nhạc thì không có chữ phụ đề trên hình

**Independent Test**: Đưa toàn đoạn điểm không-phải-lời-nói từ 0,6 hoặc tỷ lệ lặp trên 2,4. Không tạo file hình có phụ đề

### Tests for User Story 1

- [x] T003 [US1] Thêm ca thất bại trước trong `tests/test_subtitle_layer.py`: đoạn điểm không phải lời nói 0,6 bị bỏ; đoạn tỷ lệ lặp chữ 2,5 bị bỏ; đoạn không có hai điểm số được giữ; danh sách chỉ còn đoạn nhạc thì đường áp phụ đề không tạo file hình

### Implementation for User Story 1

- [x] T004 [US1] Gọi hàm lọc ở cuối đường nghe trong `app/features/viral_intake/subtitle_layer.py` trước khi trả danh sách. Hết đoạn thì đi lối không cháy đang có, không tạo file phụ đề

**Checkpoint**: Story 1 xong với video chỉ có nhạc, dù ca trộn lời nói chưa có

---

## Phase 4: User Story 2 - Video có lời nói vẫn có phụ đề (Priority: P2)

**Goal**: Còn một đoạn lời nói thì đoạn đó vẫn được cháy, đoạn nhạc cạnh nó bị bỏ

**Independent Test**: Một đoạn điểm 0,2 đứng cạnh một đoạn điểm 0,9. Chỉ đoạn 0,2 còn lại

### Tests for User Story 2

- [x] T005 [US2] Thêm ca trong `tests/test_subtitle_layer.py`: đoạn lời nói điểm không phải lời nói 0,2 được giữ khi cạnh đoạn nhạc điểm 0,9; kết quả không phải danh sách rỗng

### Implementation for User Story 2

- [x] T006 [US2] Giữ vòng lọc từng đoạn trong `app/features/viral_intake/subtitle_layer.py`. Còn một đoạn dưới cả hai mốc thì vẫn trả đoạn đó. Không thêm nhánh bỏ cả video chỉ vì có một đoạn nhạc

**Checkpoint**: Video nói chuyện có nhạc nền vẫn có phụ đề cho câu nói

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Khớp quickstart, không đụng thuyết minh và video đã xong

- [x] T007 Chạy `./venv/bin/python -m pytest tests/test_subtitle_layer.py -q --tb=short` từ gốc repo và đối chiếu `specs/002-skip-sub-with-music/quickstart.md`
- [x] T008 Rà `app/features/viral_intake/subtitle_layer.py` và `app/features/viral_intake/reup_processor.py` để không đổi cờ thuyết minh và không có đường làm lại video đã xử lý xong

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Bắt đầu được ngay
- **Foundational (Phase 2)**: Sau Setup. Chặn mọi story
- **User Story 1 (Phase 3)**: Sau Foundational
- **User Story 2 (Phase 4)**: Sau Foundational. Dùng cùng hàm lọc với Story 1, nên làm sau Story 1 để khỏi sửa cùng một file song song
- **Polish (Phase 5)**: Sau story muốn giao

### User Story Dependencies

- **User Story 1 (P1)**: Không cần Story 2
- **User Story 2 (P2)**: Cần hàm lọc của Phase 2. Ca trộn tự kiểm được khi hàm đã lọc từng đoạn

### Within Each User Story

- Viết ca trước, chạy thấy lỗi, rồi mới sửa đường nghe
- Story 1 xong rồi mới sang Story 2

### Parallel Opportunities

- Không có task [P]. Cả hai story sửa cùng `subtitle_layer.py` và `tests/test_subtitle_layer.py`

---

## Parallel Example: User Story 1

Không chạy song song. T003 xong và thấy lỗi rồi mới làm T004.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Xong Phase 1 và Phase 2
2. Xong Phase 3
3. Dừng và kiểm video chỉ có nhạc không có chữ trên hình
4. Chưa cần Story 2 để giao phần nhạc

### Incremental Delivery

1. Setup + hàm lọc
2. Story 1: video nhạc không cháy phụ đề
3. Story 2: câu nói còn phụ đề khi cạnh nhạc
4. Chạy pytest cả file phụ đề

---

## Notes

- Không có task song song vì cùng file
- Ca máy dùng đoạn giả, không gọi bộ nghe thật
- Đoạn thiếu điểm số phải được giữ, để ca dựng kiểu chữ cũ không đổi nghĩa
