# Implementation Plan: Gộp bài trùng trong báo cáo chỉ số

**Branch**: `001-group-duplicate-posts` | **Date**: 2026-09-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-group-duplicate-posts/spec.md`

## Summary

Khi chủ kênh xem chỉ số một kênh, các bản đã gửi cùng chữ, cùng kênh, cùng ngày hiện thành một dòng và ghi số bản lịch sử. Tóm tắt kênh đếm số nội dung, không đếm mỗi bản thành một video. Không xóa lịch sử và không thêm lệnh.

Cách làm: thêm bước gộp trên danh sách bài tháng đang có, rồi dùng nhóm đó trong câu tóm tắt và trong danh sách một kênh.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: Client Buffer hiện có, bot Telegram hiện có

**Storage**: Không ghi thêm. Đọc danh sách bài đã gửi trong tháng rồi gộp trong bộ nhớ.

**Testing**: pytest, ca thuần trên hàm gộp, không gọi mạng

**Target Platform**: Bot Telegram local, cùng tiến trình poller đang chạy

**Performance Goals**: Gộp dưới 50 bài của một lần xem, xong trong lần dựng tin

**Constraints**: Không xóa bản đã gửi. Không đổi đăng bài. Tin `/so` cũ không tự sửa. Ngày theo giờ Việt Nam. So cả đoạn chữ sau khi gộp khoảng trắng.

**Scale/Scope**: Một chủ kênh, vài kênh, tối đa 50 bài trong một lần báo cáo tháng

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` vẫn là mẫu chưa điền, không có nguyên tắc đã thông qua. Không có cửa nào để vi phạm.

**Trước Phase 0**: PASS

**Sau Phase 1**: PASS. Thiết kế không thêm kho, không thêm lệnh, không xóa dữ liệu đã gửi.

## Project Structure

### Documentation (this feature)

```text
specs/001-group-duplicate-posts/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── channel-report.md
└── tasks.md             # /speckit-tasks, chưa tạo ở bước này
```

### Source Code (repository root)

```text
app/features/buffer/client.py
app/features/telegram_bot/command_handler.py
app/features/telegram_bot/event_router.py
tests/test_buffer_api.py
```

**Structure Decision**: Sửa hàm dựng báo cáo trong `client.py`. `command_handler.py` và `event_router.py` giữ lệnh `/so` và nút kênh, chỉ nhận câu chữ mới. Ca kiểm tra nằm ở `tests/test_buffer_api.py`.

## Complexity Tracking

Không có vi phạm cần biện minh.
