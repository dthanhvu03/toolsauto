# ADR-010: Ngoại lệ — Claude Code được execute backend cho đợt Combo 2

## Status
Accepted — Owner duyệt trực tiếp 2026-08-21.

## Context

`CLAUDE.md` quy định Claude Code đóng vai **UX, Refactor & Quality**, mục "Không được
làm" ghi rõ: *viết adapter, worker, core business logic, database migration*. Quy trình
chuẩn là Antigravity ra PLAN → Codex/Cursor execute backend → Claude Code verify UI.

Đợt này Owner muốn phát triển toàn bộ tính năng còn thiếu của hai combo đang bán
(Auto Page 3tr5 / Page Master 5tr). Khảo sát ngày 2026-08-21 cho thấy phần thiếu **nằm
gần như trọn trong backend**: Playwright adapter, page object, job type, hàng đợi, migration.
Nếu giữ nguyên phân vai, Claude Code chỉ ra được tài liệu và phải chờ executor khác.

Owner đã được thông báo giới hạn này và vẫn chọn "em code luôn cả backend".

## Decision

Cho phép Claude Code execute cả backend **trong phạm vi PLAN-052 → PLAN-056**, với ba
ràng buộc giữ nguyên:

1. **Vẫn viết PLAN trước khi code.** Không có PLAN thì không đụng file.
2. **Minimal diff.** Đúng scope trong PLAN; không refactor "tiện thể".
3. **Không migration phá huỷ.** Thêm cột thì nullable + có default; không DROP/DELETE
   dữ liệu production khi chưa hỏi lại Owner.

## Scope hết hiệu lực

Ngoại lệ này áp cho đúng 5 plan nói trên. Đợt sau quay lại phân vai gốc trong `CLAUDE.md`,
trừ khi Owner mở lại bằng một ADR mới.

## Consequences

- Được: đi thẳng từ khảo sát → code → verify trong một phiên, không mất vòng bàn giao.
- Mất: không còn cặp mắt thứ hai giữa PLAN và code. Bù lại bằng test cho từng plan và
  verify chạy thật trên Page nháp trước khi giao khách.
- Rủi ro đã biết: các luồng Playwright (story, giỏ hàng) chỉ lộ lỗi khi chạy live —
  unit test không thay thế được, đúng như bài học PLAN-049 §"Lỗi chỉ lộ khi chạy live".
