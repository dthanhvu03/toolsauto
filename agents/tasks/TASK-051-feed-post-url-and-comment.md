# TASK-051 — post_url bài feed + auto-comment cho bài feed

## Plan
PLAN-053

## Executor
Claude Code (ngoại lệ theo ADR-010)

## Acceptance
- [x] Không còn lọc phản hồi GraphQL theo tên mutation đoán trước
- [x] Có fallback ghép permalink từ post_id
- [x] COMMENT job sinh ra cho bài FEED
- [x] Suite 198 passed (lúc đó); hiện 243
