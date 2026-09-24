---

description: "Task list for managing source intake when videos flood in"
---

# Tasks: Quản lý nguồn khi video đổ về nhiều

**Input**: Design documents from `/specs/003-manage-source-intake/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/source-card.md, quickstart.md

**Tests**: Có. `quickstart.md` yêu cầu ca pytest cho đếm chờ từng nguồn, quét nguồn tắt, trần 3 video, và số riêng không làm đổi nguồn khác. Viết ca trước, thấy lỗi, rồi mới sửa đường quét.

**Organization**: Story 1 là thấy nguồn nào đang đổ. Story 2 là tắt nguồn mà không mất video đã có. Story 3 là đặt ngưỡng riêng. Cả ba cần cột gắn nguồn ở Phase 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được vì khác file và không phụ thuộc việc chưa xong
- **[Story]**: US1, US2 hoặc US3

## Path Conventions

- `app/core/database/models/viral.py`
- `alembic/versions/`
- `app/features/viral_intake/sources.py`
- `app/bootstrap_hooks.py`
- `app/features/telegram_bot/command_handler.py`
- `tests/test_viral_sources.py`
- `tests/test_telegram_video_controls.py`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Khóa phạm vi. Không tạo bảng mới và không thêm gói.

- [x] T001 Xác nhận không thêm gói và không thêm bảng. Sửa code của feature này chỉ nằm trong `app/core/database/models/viral.py`, một migration mới trong `alembic/versions/`, `app/features/viral_intake/sources.py`, `app/bootstrap_hooks.py`, `app/features/telegram_bot/command_handler.py`, `tests/test_viral_sources.py` và `tests/test_telegram_video_controls.py`, theo `specs/003-manage-source-intake/plan.md`. Không sửa phụ đề, xếp hàng, hay chọn giờ đăng

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Video mới có chỗ để nhớ nguồn đã đưa nó vào

**⚠️ CRITICAL**: Chưa có cột này thì chưa đếm được video chờ theo nguồn

- [x] T002 [P] Thêm cột `source_id` trên `ViralMaterial` trong `app/core/database/models/viral.py`. Cột là số nguyên, trống được, có chỉ mục, khóa ngoại tới `viral_sources.id`. Video cũ và video dán tay để trống. Không điền lại hàng cũ. Không xóa dòng
- [x] T003 [P] Thêm migration trong `alembic/versions/` nối sau revision `s6a3b4c5d6e7`. `upgrade` thêm cột `source_id` kiểu số nguyên, trống được, có chỉ mục, khóa ngoại tới `viral_sources.id` trên bảng `viral_materials`. `downgrade` chỉ bỏ cột đó

**Checkpoint**: Tạo video mới gắn được nguồn, video cũ vẫn trống

---

## Phase 3: User Story 1 - Thấy nguồn nào đang đổ video (Priority: P1) 🎯 MVP

**Goal**: Danh sách nguồn hiện bật hay tắt, ngưỡng đang dùng, số video mới còn chờ của đúng nguồn đó, và kết quả lần quét gần nhất

**Independent Test**: Hai nguồn. Nguồn thứ nhất có 20 video trạng thái `NEW` gắn đúng nguồn đó. Nguồn thứ hai có 0. Danh sách hiện 20 và 0. Video không gắn nguồn không bị cộng vào nguồn nào

### Tests for User Story 1

- [x] T004 [P] [US1] Thêm ca thất bại trước trong `tests/test_viral_sources.py`: 20 video trạng thái `NEW` gắn nguồn A được đếm cho A; nguồn B đếm 0; video không có `source_id` không cộng vào A hay B
- [x] T005 [P] [US1] Thêm ca trong `tests/test_telegram_video_controls.py`: bản tóm tắt có `waiting_count` 20 thì tin `/nguon` hiện số 20, vẫn hiện tên nguồn, ngưỡng, dòng lần quét, và vẫn còn nút `scan:{id}` với `tgsrc:{id}`. Ca `/nguon` đang có phải chạy tiếp khi thiếu `waiting_count`

### Implementation for User Story 1

- [x] T006 [US1] Trong `app/features/viral_intake/sources.py`, khi `_ingest_lines` tạo `ViralMaterial` thì gán `source_id` bằng mã nguồn vừa quét. Thêm hàm đếm video trạng thái `NEW` theo đúng `source_id`. Video không gắn nguồn không đếm
- [x] T007 [US1] Trong `app/bootstrap_hooks.py`, `viral_sources_summary` thêm `waiting_count` từ hàm đếm của T006. Giữ `enabled`, `min_views`, `max_videos`, `last_scanned_at`, `last_found`, `last_error`
- [x] T008 [US1] Trong `app/features/telegram_bot/command_handler.py`, thẻ `/nguon` hiện số video còn chờ, trạng thái bật hoặc tắt, ngưỡng đang dùng (hai số riêng nếu có, không thì nói mức chung), và dòng lần quét gần nhất đang có. Không thêm nút mới

**Checkpoint**: Mở danh sách là biết nguồn nào đang đầy hàng, dù chưa tắt nguồn và chưa đặt số riêng

---

## Phase 4: User Story 2 - Tạm dừng một nguồn mà không mất video đã có (Priority: P1)

**Goal**: Tắt một nguồn thì lần quét không thêm video. Video đã chờ, đang xử lý, hay đã sẵn sàng vẫn còn

**Independent Test**: Tắt nguồn đang có video chờ, rồi quét nguồn đó. Số video mới thêm là 0. Số video đã chờ không giảm. Bật lại thì quét được theo ngưỡng đang có hiệu lực

### Tests for User Story 2

- [x] T009 [US2] Thêm ca thất bại trước trong `tests/test_viral_sources.py`: nguồn `enabled` sai thì `scan_source` trả 0 video mới, không gọi trình đọc kênh, và không xóa video trạng thái `NEW`, `PROCESSING`, hay `READY`. `viral_scan_source` trong `app/bootstrap_hooks.py` trả câu nói nguồn đang tắt. Bật lại thì lần quét sau được gọi trình đọc kênh

### Implementation for User Story 2

- [x] T010 [US2] Trong `app/features/viral_intake/sources.py`, `scan_source` dừng trước khi đọc kênh khi nguồn đang tắt. Không thêm video và không xóa video đã có
- [x] T011 [US2] Trong `app/bootstrap_hooks.py`, `viral_scan_source` thấy nguồn tắt thì trả câu nguồn đang tắt và không gọi `scan_source`. Nguồn bật vẫn trả câu số video mới và số bỏ qua như hiện tại

**Checkpoint**: Tắt đúng nguồn đang ồn thì vòi dừng, hàng đã nhận không mất

---

## Phase 5: User Story 3 - Đặt ngưỡng riêng cho một nguồn (Priority: P2)

**Goal**: Một nguồn có mức xem tối thiểu và số video tối đa riêng. Lần quét chỉ nhận video đủ mức xem và dừng khi đủ số tối đa. Nguồn khác và mức chung không đổi

**Independent Test**: Nguồn A tối đa 3, một lần quét có từ 3 video trở lên đủ mức xem thì chỉ thêm đúng 3. Nguồn B và hai số chung không đổi. Xóa số riêng thì A dùng lại mức chung. Số video tối đa nhỏ hơn 1 thì không lưu

### Tests for User Story 3

- [x] T012 [P] [US3] Thêm ca thất bại trước trong `tests/test_viral_sources.py`: mười video đủ mức xem và số tối đa riêng là 3 thì chỉ thêm 3, cả ba gắn đúng nguồn, theo thứ tự đọc. Đặt số riêng của A không đổi số của B, không đổi `viral.min_views` và `viral.max_videos_per_channel`, và không đổi `target_pages`. Xóa số riêng thì lần quét dùng mức chung. Mức xem âm, số không phải số nguyên, hoặc số video tối đa nhỏ hơn 1 thì không ghi gì. Ca `test_scan_source_tiktok_creates_new_materials_and_dedups` đang khóa `--playlist-end` bằng số tối đa riêng: sửa kỳ vọng đó cho khớp cửa sổ đọc mới, không đổi số video được nhận của ca đó
- [x] T013 [P] [US3] Thêm ca trong `tests/test_telegram_video_controls.py`: `/nguon` kèm mã nguồn và hai số nguyên gọi hook đặt số riêng; `/nguon` kèm mã nguồn và chữ `xoa` gọi hook xóa số riêng; giá trị sai thì tin báo lý do và không gọi hook ghi

### Implementation for User Story 3

- [x] T014 [US3] Trong `app/features/viral_intake/sources.py`, thêm hàm chỉ sửa `min_views` và `max_videos`. Trống nghĩa là ghi NULL để dùng mức chung. `min_views` là số nguyên không âm hoặc trống. `max_videos` là số nguyên từ 1 đến `MAX_VIDEOS_CAP` hoặc trống. Nhỏ hơn 1 thì không lưu. Không gọi `update_source` vì hàm đó ghi đè trang đích. Trong `_ingest_lines`, dừng khi số video vừa thêm đạt số tối đa đang có hiệu lực. Số đang có hiệu lực là số riêng nếu có, không thì mức chung. `--playlist-end` bằng số lớn hơn giữa số tối đa đang có hiệu lực và mức chung, và không vượt `MAX_VIDEOS_CAP`
- [x] T015 [US3] Trong `app/bootstrap_hooks.py`, thêm hook đặt và xóa hai số riêng, gọi hàm của T014. Không nhận trang đích
- [x] T016 [US3] Trong `app/features/telegram_bot/command_handler.py`, cùng lệnh `/nguon`: không tham số thì liệt kê như T008; kèm mã nguồn và hai số thì gọi hook T015; kèm mã nguồn và `xoa` thì đưa hai số về trống; sai thì báo lý do và không ghi. Không thêm lệnh mới

**Checkpoint**: Siết một nguồn đang ồn, các nguồn còn lại vẫn theo mức chung

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Khớp quickstart và không tràn sang việc khác

- [x] T017 Chạy `./venv/bin/python -m pytest tests/test_viral_sources.py tests/test_telegram_video_controls.py -q --tb=short` từ gốc repo và đối chiếu `specs/003-manage-source-intake/quickstart.md`
- [x] T018 Rà diff để không sửa `app/features/viral_intake/subtitle_layer.py`, đường xếp hàng Buffer, và đường chọn giờ đăng

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Bắt đầu được ngay
- **Foundational (Phase 2)**: Sau Setup. Chặn mọi story
- **User Story 1 (Phase 3)**: Sau Foundational
- **User Story 2 (Phase 4)**: Sau Story 1, vì cùng sửa `sources.py` và `bootstrap_hooks.py`
- **User Story 3 (Phase 5)**: Sau Story 2, vì cùng sửa `sources.py`, `bootstrap_hooks.py` và `command_handler.py`
- **Polish (Phase 6)**: Sau story muốn giao

### User Story Dependencies

- **User Story 1 (P1)**: Cần cột `source_id`. Không cần tắt nguồn hay số riêng
- **User Story 2 (P1)**: Cần đếm chờ của Story 1 để chứng minh số chờ không giảm
- **User Story 3 (P2)**: Cần video đã gắn nguồn từ Story 1. Không cần Story 2 để đặt số, nhưng làm sau để khỏi sửa cùng file

### Within Each User Story

- Viết ca trước, chạy thấy lỗi, rồi mới sửa đường quét và thẻ nguồn
- Story 1 xong rồi mới sang Story 2, rồi Story 3

### Parallel Opportunities

- T002 và T003 khác file
- T004 và T005 khác file
- T012 và T013 khác file
- Ba story không chạy song song vì cùng `sources.py`

---

## Parallel Example: User Story 1

```text
T004: ca đếm trong tests/test_viral_sources.py
T005: ca thẻ nguồn trong tests/test_telegram_video_controls.py
```

Hai ca viết song song. T006 xong rồi mới T007, rồi T008.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Xong Phase 1 và Phase 2
2. Xong Phase 3
3. Dừng và kiểm danh sách hiện đúng số chờ của từng nguồn
4. Chưa cần tắt nguồn hay số riêng để biết nguồn nào đang đổ

### Incremental Delivery

1. Cột gắn nguồn
2. Story 1: nhìn thấy nguồn nào đầy
3. Story 2: tắt nguồn, video đã có vẫn còn
4. Story 3: siết mức xem và số video tối đa của một nguồn
5. Chạy pytest hai file nguồn và thẻ Telegram

---

## Notes

- Không có task story chạy song song với nhau
- Ca máy dùng cơ sở dữ liệu nhớ tạm và trình đọc kênh giả, không gọi mạng
- Video cũ không gắn nguồn thì không bị đếm và không bị xóa
