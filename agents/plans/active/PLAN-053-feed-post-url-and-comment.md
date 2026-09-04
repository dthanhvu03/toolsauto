# PLAN-053 — Lấy post_url bài feed + mở khoá auto-comment cho bài feed

## Status: Code done — chờ verify live (2026-08-21)

## Goal

Hai lỗ hổng nối nhau, cùng chặn đúng thứ khách Combo 2 mua ("gắn cmt vào bài"):

1. **`post_url` bài feed chưa lấy được** (nợ ghi trong PLAN-049). Listener chỉ đọc
   phản hồi GraphQL nào có request chứa một trong 4 token đoán trước
   (`StoryCreate` / `Composer` / `FeedPost` / `CometComposer`). Composer feed đổi tên
   mutation ⇒ hụt hết ⇒ `post_url = None`.
2. **Auto-comment chỉ chạy cho Reels.** `mark_done` tạo COMMENT job khi
   `job.job_type == JobType.POST`. Bài feed (ảnh / video dài) không bao giờ được
   gắn comment, dù form có ô nhập.

## Scope

- Bỏ lọc theo tên mutation: đọc **mọi** phản hồi `/api/graphql/` trong lúc đăng,
  lọc bằng *nội dung* (link bài) thay vì đoán tên
- Fallback thứ hai: nhặt `post_id` / `story_fbid` trong payload rồi ghép thành permalink
- Tách phần suy ra link thành hàm thuần để test được không cần trình duyệt
- `mark_done` tạo COMMENT job cho cả `FEED`

## Out of scope

- STORY (làm ở PLAN-054) — story Facebook không có luồng bình luận như bài viết
- Ảnh trong comment (PLAN-055)

## Implementation

| Piece | Path |
|-------|------|
| Nhặt link/id từ payload GraphQL | `FacebookAdapter._walk_for_post_ids()`, `_post_url_from_payload()` |
| Ghép permalink từ id | `FacebookAdapter._compose_post_url()` |
| Listener bỏ lọc tên mutation | `FacebookAdapter.publish_feed()` |
| Auto-comment cho FEED | `JobService.mark_done()` |
| Test | `tests/test_feed_post_url.py` |

## Rủi ro tự tạo ra rồi tự vá (ghi để nhớ)

Bỏ lọc tên mutation xong thì phản hồi của **truy vấn feed lúc cuộn trang** cũng chứa
link bài — của người khác. Nếu cứ tin cái đến trước thì `post_url` sẽ trỏ sang bài
người khác, và COMMENT job sẽ đi bình luận nhầm chỗ. Đã vá hai lớp:

1. Listener chỉ gắn **sát lúc bấm Đăng**, không nghe suốt lúc cuộn feed
2. Link từ phản hồi có `Mutation` trong request được ưu tiên; link từ truy vấn thường
   chỉ dùng khi không còn gì khác

## Verify — 2026-08-21

| Hạng mục | Kết quả |
|---|---|
| Suy ra link khi payload có sẵn URL (cắt query thừa) | PASS |
| Ghép permalink từ `post_id` / `story_fbid` lồng nhiều tầng | PASS |
| Không có Page thì về host gốc | PASS |
| Payload không liên quan → **không bịa link** | PASS |
| id quá ngắn / không phải số → bỏ qua | PASS |
| Listener gắn sau bước cuộn feed (kiểm bằng thứ tự trong source) | PASS |
| Bài FEED có comment + link → sinh COMMENT job đúng `parent_job_id` | PASS |
| Bài FEED không có link → **không** sinh COMMENT job mồ côi | PASS |
| Reels vẫn sinh COMMENT như cũ; STORY không sinh | PASS |

`tests/test_feed_post_url.py` — 14 test. Full suite lúc đó: **198 passed**.

## Còn nợ

- [ ] **Live**: đăng một bài feed thật rồi xem log có bắt được `post_url` không.
      Đây là thứ duy nhất chứng minh được matcher mới ăn khớp với composer thật.
