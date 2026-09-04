# TASK-053 — Đính ảnh vào comment tự động

## Plan
PLAN-055

## Executor
Claude Code (ngoại lệ theo ADR-010)

## Acceptance
- [x] Cột `comment_image_path` + migration `i7d4e5f6a7b8`
- [x] Ảnh dùng chung cho cả lô bulk, validate trước khi ghi đĩa
- [x] COMMENT job con kế thừa ảnh
- [x] `FacebookAdapter.post_comment()` đính ảnh, hỏng thì vẫn gửi chữ
- [x] Suite 234 passed
- [ ] Live verify (chờ Owner)
