# Implementation Plan: Quản lý nguồn khi video đổ về nhiều

**Branch**: `003-manage-source-intake` | **Date**: 2026-09-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-manage-source-intake/spec.md`

## Summary

Chủ kênh thấy từng nguồn còn bao nhiêu video mới đang chờ, tắt một nguồn mà không mất video đã có, và đặt mức xem cùng số video tối đa cho riêng nguồn đó. Mức chung giữ nguyên cho nguồn chưa có số riêng.

Cách làm: gắn video mới với nguồn lúc quét, đếm video trạng thái chờ theo nguồn, chặn quét khi nguồn tắt, và dừng nhận khi đủ số tối đa sau khi đã lọc mức xem.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: Nguồn quét và bot Telegram đang có. Không thêm gói.

**Storage**: Thêm một cột trống được trên video, trỏ về nguồn đã đưa video đó vào. Video cũ để trống. Không xóa dòng.

**Testing**: pytest, cơ sở dữ liệu nhớ tạm. Ca không gọi mạng và không gọi trình tải kênh.

**Target Platform**: Bot Telegram local, cùng tiến trình vòng xử lý nguồn đang chạy.

**Performance Goals**: Đếm chờ là một lần đếm theo nguồn khi mở danh sách. Một lần quét dừng ngay khi đủ số video nhận.

**Constraints**: Nguồn tắt không thêm video. Siết ngưỡng không xóa video đã chờ, đang xử lý, hay đã sẵn sàng. Số riêng của nguồn này không đổi nguồn kia và không đổi mức chung. Số video tối đa nhỏ hơn 1 thì không lưu. Không đổi phụ đề, xếp hàng, hay chọn giờ đăng.

**Scale/Scope**: Một chủ kênh, vài nguồn. Sửa đường quét, câu danh sách nguồn, và một cách đặt số riêng trên lệnh nguồn đang có.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` vẫn là mẫu chưa điền, không có nguyên tắc đã thông qua. Không có cửa nào để vi phạm.

**Trước Phase 0**: PASS

**Sau Phase 1**: PASS. Thiết kế không xóa video đã có, không thêm lệnh mới ngoài cách đặt số trên lệnh nguồn đang dùng, không đụng phụ đề hay đăng bài.

## Project Structure

### Documentation (this feature)

```text
specs/003-manage-source-intake/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── source-card.md
└── tasks.md
```

### Source Code (repository root)

```text
app/core/database/models/viral.py
app/features/viral_intake/sources.py
app/bootstrap_hooks.py
app/features/telegram_bot/command_handler.py
tests/test_viral_sources.py
```

**Structure Decision**: Gắn nguồn lên video trong `sources.py` lúc tạo video mới. Danh sách Telegram đọc số chờ qua bản tóm tắt nguồn đang có. Đặt số riêng đi một hàm chỉ sửa hai số, không đụng trang đích của nguồn.

## Complexity Tracking

Không có vi phạm cần biện minh.
