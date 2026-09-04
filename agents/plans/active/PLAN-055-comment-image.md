# PLAN-055 — Đính ảnh vào comment tự động

## Status: Code done — chờ verify live (2026-08-21)

## Goal

`post_comment()` hiện chỉ gõ chữ rồi Enter — không có `set_input_files` ở đâu cả.
Combo Page Master bán kèm "gắn cmt vào video: link aff, **hình ảnh**, tiêu đề dạng
link nhóm". Phần chữ và link đã chạy; phần ảnh chưa từng có.

## Scope

- Cột `comment_image_path` trên `jobs` + migration
- Ảnh comment dùng chung cho cả lô khi bulk upload
- COMMENT job tự sinh kế thừa ảnh từ job cha
- `FacebookAdapter.post_comment()` đính ảnh trước khi Enter
- Bốn adapter cùng nhận `image_path` để dispatcher không phải dò chữ ký hàm

## Out of scope

- Nhiều ảnh trong một comment (Facebook chỉ cho 1 ảnh mỗi bình luận)
- Ảnh comment riêng cho từng job trong lô (dùng chung 1 ảnh cho cả lô)
- Instagram / TikTok / Threads đính ảnh — chỉ nhận tham số rồi ghi log bỏ qua

## Implementation

| Piece | Path |
|-------|------|
| Migration | `alembic/versions/i7d4e5f6a7b8_job_comment_image.py` |
| Cột + resolve | `app/core/database/models/jobs.py` |
| Lưu file + gán cho lô | `JobService.bulk_create_jobs_from_uploads()` |
| Kế thừa sang COMMENT job | `JobService.mark_done()` |
| Đính ảnh | `FacebookAdapter.post_comment(..., image_path=...)` |
| Truyền xuống | `Dispatcher.dispatch()` |
| UI | `fragments/create_job_form.html` |
| Test | `tests/test_comment_image.py` |

## Verify — 2026-08-21

| Hạng mục | Kết quả |
|---|---|
| Migration `i7d4e5f6a7b8` chạy thật trên Postgres dev, cột nullable, có downgrade | PASS |
| Ảnh comment: nhận .jpg/.jpeg/.png, chặn video và file lạ | PASS |
| Ảnh bị từ chối không để lại file rác trên đĩa | PASS |
| COMMENT job con kế thừa `comment_image_path` từ job cha (DB thật) | PASS |
| Đính ảnh hỏng vẫn gửi comment chữ — không mất cả bình luận | PASS |
| Cả 4 adapter cùng nhận `image_path` (kiểm bằng `inspect.signature`) | PASS |
| Form bulk có ô ảnh comment, gửi kèm `comment_image` | PASS |

`tests/test_comment_image.py` — 12 test. Full suite **234 passed**.

## Ghi chú

`config_service.py` chứa **template sinh code** adapter mới (f-string), nên chữ ký ở
đó cũng phải đổi theo, dùng `{class_name}` chứ không phải tên cứng.

## Còn nợ

- [ ] **Live**: comment kèm ảnh dưới một Reels thật. Selector khay đính kèm của ô
      bình luận chưa chạy thật lần nào.
