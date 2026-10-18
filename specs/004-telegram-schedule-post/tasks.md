---

description: "Task list for scheduling a post time from Telegram"
---

# Tasks: Lên lịch đăng bài từ Telegram

**Input**: Design documents from `/specs/004-telegram-schedule-post/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/telegram-schedule.md, quickstart.md

**Tests**: Có. `quickstart.md` yêu cầu ca pytest cho tạo lịch, sửa cùng một bài, giờ sai, hết suất, hủy, và xếp hàng không giờ. Viết ca trước, thấy lỗi, rồi mới nối nút Telegram.

**Organization**: Story 1 là hẹn giờ cho video sẵn sàng. Story 2 là đổi giờ hoặc hủy. Story 3 là từ chối giờ sai. Story 4 là giữ xếp hàng và đăng ngay. Cả bốn cần cửa sổ giờ ở Phase 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Chạy song song được vì khác file và không phụ thuộc việc chưa xong
- **[Story]**: US1, US2, US3 hoặc US4

## Path Conventions

- `app/features/buffer/when.py`
- `app/features/buffer/client.py`
- `app/features/buffer/queue_job.py`
- `app/features/telegram_bot/command_handler.py`
- `app/features/telegram_bot/event_router.py`
- `app/core/notifier/formatting.py`
- `tests/test_telegram_schedule.py`
- `tests/test_buffer_queue.py`

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Khóa phạm vi. Không thêm gói và không thêm bảng.

- [x] T001 Xác nhận không thêm gói và không thêm bảng. Sửa code của feature này chỉ nằm trong `app/features/buffer/when.py`, `app/features/buffer/client.py`, `app/features/buffer/queue_job.py`, `app/features/telegram_bot/command_handler.py`, `app/features/telegram_bot/event_router.py`, `app/core/notifier/formatting.py`, `tests/test_telegram_schedule.py`, theo `specs/004-telegram-schedule-post/plan.md`. Không sửa poller lọc chat và không đổi nghĩa nút đăng ngay

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Đọc được giờ Việt Nam và sửa được giờ của bài đang chờ

**⚠️ CRITICAL**: Chưa có hai việc này thì chưa story nào hẹn giờ mà không biến thành đăng ngay

- [x] T002 [P] Tạo `app/features/buffer/when.py` để đọc giờ Việt Nam và trả mốc giây hoặc một câu từ chối. Múi giờ là giờ Việt Nam. Mốc gửi đi là giờ quốc tế tương ứng. Mẫu gõ là `ngày/tháng giờ:phút` hoặc `ngày/tháng/năm giờ:phút`. Thiếu năm thì lấy năm nay. Giờ đã qua thì từ chối, không cộng thêm một năm. Lịch hợp lệ lớn hơn hiện tại ít nhất 10 phút và không quá 30 ngày. Ba gợi ý là tối nay 20:00, sáng mai 08:00, tối mai 20:00. Gợi ý rơi ngoài cửa sổ thì nút đó từ chối, không tạo lịch. Hàm này không gọi nơi đăng
- [x] T003 [P] Trong `app/features/buffer/client.py`, `edit_post` nhận thêm giờ đến khi chế độ là lịch tùy chọn, và gửi giờ đó cùng nội dung bài đang giữ. Không đổi đường đăng ngay

**Checkpoint**: Giờ sai bị từ chối trước khi gọi nơi đăng. Sửa bài đang chờ gửi được giờ mới

---

## Phase 3: User Story 1 - Chọn giờ đăng cho video sẵn sàng (Priority: P1) 🎯 MVP

**Goal**: Chủ kênh chọn kênh rồi chọn giờ. Chat xác nhận tên kênh và giờ Việt Nam. Bài chưa tới giờ thì chưa đăng

**Independent Test**: Có một video sẵn sàng và một kênh đang nối. Chọn giờ hợp lệ trong tương lai. Chat báo đúng kênh và đúng giờ. Bài không đăng ngay

### Tests for User Story 1

- [x] T004 [US1] Thêm ca thất bại trước trong `tests/test_telegram_schedule.py`, cơ sở dữ liệu nhớ tạm, nơi đăng giả, không gọi mạng. Giờ hợp lệ tạo một job, một bài, câu xác nhận có tên kênh và giờ Việt Nam, chế độ không phải đăng ngay. Lời bài trống thì không tạo lịch và câu trả lời nói còn thiếu lời bài. Kênh không nằm trong danh sách kênh đang nối thì không tạo lịch

### Implementation for User Story 1

- [x] T005 [US1] Trong `app/features/buffer/queue_job.py`, thêm đường hẹn giờ. Lời bài trống thì không tạo lịch. Kênh phải nằm trong danh sách kênh đang nối. Mốc giờ là số giây. Lịch hợp lệ lớn hơn hiện tại ít nhất 10 phút và không quá 30 ngày. Hôm nay hết suất thì không tạo. Tuần hết suất thì không tạo. Gọi cửa sổ giờ của T002 trước khi gửi. Job đã giao kênh giữ trạng thái xong và lưu mã bài bên kênh
- [x] T006 [US1] Trong `app/core/notifier/formatting.py`, thêm nút hẹn giờ trên tin video sẵn sàng. Ba gợi ý là tối nay 20:00, sáng mai 08:00, tối mai 20:00. `callback_data` không vượt 64 byte. Nút xếp hàng không chọn giờ giữ nguyên
- [x] T007 [US1] Trong `app/features/telegram_bot/event_router.py`, bấm kênh rồi bấm một gợi ý thì gọi đường hẹn giờ của T005. Chat xác nhận tên kênh và ngày giờ Việt Nam. Gợi ý rơi ngoài cửa sổ thì nút đó từ chối, không tạo lịch

**Checkpoint**: Hẹn được một bài từ tin video, dù chưa đổi giờ và chưa hủy

---

## Phase 4: User Story 2 - Đổi giờ hoặc hủy lịch trước khi đăng (Priority: P1)

**Goal**: Đổi giờ trên đúng bài đang có. Hủy thì bài không tự đăng. Bài đã đăng thì không đổi và không báo đã hủy

**Independent Test**: Hẹn một bài, đổi giờ, xác nhận giờ mới. Hủy một bài khác, xác nhận bài đó không còn lịch và không đăng

### Tests for User Story 2

- [x] T008 [US2] Thêm ca trong `tests/test_telegram_schedule.py`. Cùng video cùng kênh, lần chọn giờ sau chỉ còn giờ mới, vẫn một job và một mã bài. Hủy bài đang hẹn hoặc bài lỗi chưa đăng thì không còn lịch. Bài đã đăng thì đổi giờ và hủy đều không đổi gì, câu trả lời nói bài đã đăng. Cùng video hai kênh thì hai lịch riêng

### Implementation for User Story 2

- [x] T009 [US2] Trong `app/features/buffer/queue_job.py`, lần hẹn sau cùng video cùng kênh sửa đúng mã bài đang có bằng `edit_post` của T003. Không tạo job thứ hai. Không tự tính lại suất trước. Nơi đăng từ chối thì không báo đã đổi. Trạng thái job đã giao kênh giữ trạng thái xong
- [x] T010 [US2] Trong `app/features/telegram_bot/event_router.py`, thêm hủy lịch tách khỏi nút xóa hiện tại. Bài đang hẹn hoặc lỗi chưa đăng thì xóa bài và chat nói không còn lịch. Bài đã đăng thì từ chối và không nói đã hủy. Nơi đăng từ chối thì không báo thành công
- [x] T011 [US2] Trong `app/features/telegram_bot/command_handler.py`, thêm lệnh gõ giờ kèm mã bài đang chờ và mẫu `ngày/tháng giờ:phút` hoặc `ngày/tháng/năm giờ:phút`. Thiếu mã, thiếu giờ, hoặc không thấy bài thì không gọi nơi đăng và không tạo bài mới. Thêm lệnh này vào `handler_map` và `MENU`

**Checkpoint**: Hẹn nhầm thì sửa hoặc hủy được trong chat

---

## Phase 5: User Story 3 - Từ chối giờ không hợp lệ (Priority: P2)

**Goal**: Giờ đã qua, quá gần, quá xa, hoặc không đọc được thì không tạo lịch và không thành đăng ngay

**Independent Test**: Gửi lần lượt giờ quá khứ, giờ thiếu ngày, và giờ ngoài cửa sổ cho phép. Mỗi lần không có bài mới được hẹn, và câu trả lời nói rõ lý do

### Tests for User Story 3

- [x] T012 [US3] Thêm ca trong `tests/test_telegram_schedule.py`. Giờ đã qua, giờ không đọc được, sớm hơn 10 phút, và xa hơn 30 ngày đều không tạo lịch. Giờ không đọc được thì câu trả lời có mẫu `ngày/tháng giờ:phút`. Sau một lần sai, giờ hợp lệ vẫn tạo lịch như story 1. Không lần nào gọi chế độ đăng ngay

### Implementation for User Story 3

- [x] T013 [US3] Trong `app/features/buffer/queue_job.py` và `app/features/telegram_bot/command_handler.py`, mọi giờ bị T002 từ chối phải dừng trước khi tạo hoặc sửa bài. Câu từ chối là tiếng Việt. Giờ không đọc được thì đưa mẫu `ngày/tháng giờ:phút`. Không ghi mốc đã qua vào job

**Checkpoint**: Giờ sai không làm bài đăng ngay và không vào hàng chờ

---

## Phase 6: User Story 4 - Giữ xếp hàng chờ và đăng ngay (Priority: P2)

**Goal**: Xếp hàng không chọn giờ vẫn vào hàng chờ. Đăng ngay vẫn đăng, không hỏi giờ

**Independent Test**: Với cùng một video sẵn sàng, xếp hàng chờ không chọn giờ vẫn vào hàng chờ. Với một bài đang chờ, đăng ngay vẫn đăng không cần chọn giờ

### Tests for User Story 4

- [x] T014 [P] [US4] Thêm ca trong `tests/test_telegram_schedule.py`. Xếp hàng không chọn giờ thì mốc giờ trên job là 0 và không hỏi giờ. Nút đăng ngay không hỏi giờ. Chạy lại `tests/test_buffer_queue.py` vẫn pass

### Implementation for User Story 4

- [x] T015 [US4] Trong `app/features/buffer/queue_job.py`, lời gọi không có giờ giữ mốc 0, nghĩa là xếp hàng, không phải lịch giờ, và không xét suất mới của feature này. Trong `app/features/telegram_bot/event_router.py`, nút xếp hàng và nút đăng ngay không đi qua cửa sổ giờ của T002

**Checkpoint**: Hai cách đăng cũ dùng được sau khi đã có nút hẹn giờ

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Chạy đúng ca trong quickstart

- [x] T016 Chạy `./venv/bin/python -m pytest tests/test_telegram_schedule.py tests/test_buffer_queue.py -q --tb=short` từ gốc repo và đối chiếu kỳ vọng trong `specs/004-telegram-schedule-post/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Bắt đầu ngay
- **Foundational (Phase 2)**: Sau Phase 1. Chặn mọi story
- **User stories (Phase 3+)**: Sau Phase 2. Làm lần lượt vì cùng sửa `queue_job.py` và `event_router.py`
- **Polish (Phase 7)**: Sau story muốn giao

### User Story Dependencies

- **User Story 1 (P1)**: Sau Phase 2. Không cần story khác
- **User Story 2 (P1)**: Sau Phase 2. Ca máy tự tạo bài đang chờ, không cần bấm nút của story 1
- **User Story 3 (P2)**: Sau Phase 2. Dùng cửa sổ giờ của T002
- **User Story 4 (P2)**: Sau Phase 2. Chỉ khóa đường cũ, không cần lịch của story 1

### Within Each User Story

- Ca test viết trước và phải lỗi trước khi sửa code
- Cửa sổ giờ trước đường tạo lịch
- Đường tạo lịch trước nút Telegram
- Xong một story rồi mới sang story kế

### Parallel Opportunities

- T002 và T003 khác file, chạy song song sau T001
- T014 khác đường sửa của T013 nên chạy song song với ca test story 3 khi file test không còn đang được sửa
- Story 1 đến story 4 không song song vì cùng `queue_job.py` và `event_router.py`

---

## Parallel Example: Foundational

```bash
Task: "Tạo app/features/buffer/when.py để đọc giờ Việt Nam"
Task: "Sửa edit_post trong app/features/buffer/client.py để gửi giờ đến"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Xong Phase 1
2. Xong Phase 2
3. Xong Phase 3
4. Dừng và kiểm tra độc lập story 1
5. Chủ kênh hẹn được một giờ từ tin video

### Incremental Delivery

1. Setup + Foundational
2. Story 1 → hẹn giờ được
3. Story 2 → sửa và hủy được
4. Story 3 → giờ sai không đăng ngay
5. Story 4 → xếp hàng và đăng ngay vẫn như cũ
6. Phase 7 chạy quickstart

### Parallel Team Strategy

Một người làm lần lượt. Hai người chỉ chia T002 và T003. Không chia story vì đụng cùng file.

---

## Notes

- [P] chỉ khi khác file và không phụ thuộc việc chưa xong
- Story 2 cũng là P1. Sau MVP nên làm tiếp story 2 trước khi dùng thật, vì hẹn nhầm mà chưa hủy được
- Không thêm bảng, không thêm gói, không đổi poller lọc chat
