# Implementation Plan: Bỏ phụ đề khi video đã có nhạc

**Branch**: `002-skip-sub-with-music` | **Date**: 2026-09-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-skip-sub-with-music/spec.md`

## Summary

Video mà phần nghe chính là nhạc thì không cháy phụ đề lên hình. Video có người nói thành câu vẫn có phụ đề, kể cả khi có nhạc nền. Không phân biệt được thì giữ cách viết phụ đề hiện tại. Không đụng chữ đăng bài, không làm lại video đã xong, không bật thuyết minh.

Cách làm: sau khi nhận các đoạn nghe, bỏ đoạn nào rõ là không phải lời nói. Hết đoạn thì không cháy phụ đề. Đoạn thiếu điểm số thì giữ.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: Lớp phụ đề hiện có. Bộ nhận lời nói hiện có đã trả điểm «không phải lời nói» và tỷ lệ lặp chữ trên từng đoạn. Không thêm gói.

**Storage**: Không ghi thêm. Quyết định chỉ sống trong lần xử lý video đó.

**Testing**: pytest. Ca dùng đoạn giả, không gọi bộ nhận lời nói thật và không gọi bộ mã hóa hình.

**Target Platform**: Máy local đang chạy vòng xử lý video nguồn.

**Performance Goals**: Thêm một lượt lọc trên các đoạn đã có. Không thêm lượt nghe lại cả video.

**Constraints**: Không cháy phụ đề khi mọi đoạn đều rõ là nhạc. Giữ phụ đề khi còn đoạn lời nói. Thiếu điểm số thì không bỏ đoạn. Không đổi chữ đăng bài. Không làm lại video đã xong. Không bật thuyết minh.

**Scale/Scope**: Một chủ kênh. Một hàm lọc và chỗ gọi nó trong lớp phụ đề. Ca kiểm tra nằm ở file test phụ đề đang có.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` vẫn là mẫu chưa điền, không có nguyên tắc đã thông qua. Không có cửa nào để vi phạm.

**Trước Phase 0**: PASS

**Sau Phase 1**: PASS. Thiết kế không thêm kho, không thêm lệnh, không làm lại video đã xong, không bật thuyết minh.

## Project Structure

### Documentation (this feature)

```text
specs/002-skip-sub-with-music/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── subtitle-decision.md
└── tasks.md
```

### Source Code (repository root)

```text
app/features/viral_intake/subtitle_layer.py
tests/test_subtitle_layer.py
```

**Structure Decision**: Lọc đoạn trong `subtitle_layer.py` trước khi dựng phụ đề. `ReupProcessor` giữ nguyên: lớp phụ đề trả không áp dụng thì video giữ bản chưa cháy chữ. Ca kiểm tra thêm vào `tests/test_subtitle_layer.py`.

## Complexity Tracking

Không có vi phạm cần biện minh.
