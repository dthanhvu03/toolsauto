# Implementation Plan: Lên lịch đăng bài từ Telegram

**Branch**: `004-telegram-schedule-post` | **Date**: 2026-09-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-telegram-schedule-post/spec.md`

## Summary

Chủ kênh chọn một ngày giờ Việt Nam cho video sẵn sàng hoặc cho bài đang chờ, ngay trong Telegram. Bài chưa tới giờ thì chưa đăng. Đổi giờ sửa đúng lịch đang có. Hủy thì bài không tự đăng. Xếp hàng không chọn giờ và đăng ngay giữ như hiện tại.

Cách làm: lần tạo có giờ thì ghi mốc giờ lên job rồi gửi lịch tùy chọn đã có. Lần chọn giờ sau, cùng video cùng kênh, sửa bài đang chờ thay vì tạo bài thứ hai. Giờ sai bị chặn trước khi gọi nơi đăng.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: Bot Telegram và hàng đăng kênh đang có. Không thêm gói.

**Storage**: Dùng mốc giờ trên job đăng kênh đang có. Không thêm bảng. Không xóa job.

**Testing**: pytest, cơ sở dữ liệu nhớ tạm, nơi đăng giả. Không gọi mạng.

**Target Platform**: Bot Telegram local, cùng tiến trình đang nhận nút bấm.

**Performance Goals**: Tin xác nhận đi ngay sau khi nơi đăng nhận giờ. Ca máy không chờ mạng.

**Constraints**: Giờ Việt Nam, từ 10 phút tới 30 ngày. Giờ sai không tạo lịch và không biến thành đăng ngay. Cùng video cùng kênh chỉ một lịch. Chat lạ đã bị poller chặn. Nút bấm không vượt 64 byte. Xếp hàng không giờ và đăng ngay không đổi.

**Scale/Scope**: Một chủ kênh, vài kênh. Thêm nút hẹn giờ, ba giờ gợi ý, một lệnh gõ giờ, và đường sửa giờ trên bài đang chờ.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` vẫn là mẫu chưa điền, không có nguyên tắc đã thông qua. Không có cửa nào để vi phạm.

**Trước Phase 0**: PASS

**Sau Phase 1**: PASS. Không thêm bảng, không đổi xếp hàng không giờ, không đổi đăng ngay, không mở chat lạ.

## Project Structure

### Documentation (this feature)

```text
specs/004-telegram-schedule-post/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── telegram-schedule.md
└── tasks.md
```

### Source Code (repository root)

```text
app/features/buffer/queue_job.py
app/features/buffer/client.py
app/features/buffer/when.py
app/features/telegram_bot/command_handler.py
app/features/telegram_bot/event_router.py
app/core/notifier/formatting.py
tests/test_telegram_schedule.py
```

**Structure Decision**: Chọn giờ nằm ở `when.py`. Tạo hoặc sửa lịch đi qua `queue_job.py`, vì đó là chỗ Telegram đã xếp bài. `client.py` chỉ thêm giờ khi sửa bài đang chờ. Nút và lệnh Telegram gọi hai chỗ đó, không tự tính cửa sổ giờ.

## Complexity Tracking

Không có vi phạm cần biện minh.
