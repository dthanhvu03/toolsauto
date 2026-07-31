# PLAN-049 — Facebook feed post (bài chữ / bài ảnh)

## Status: Done (đã verify bằng đăng thật)

## Goal

Facebook adapter trước đây **chỉ đăng được Reels** — bắt buộc video. Cần thêm luồng
đăng bài feed (chữ thuần hoặc chữ + ảnh) lên tường cá nhân và Page, vì chương trình
Content Monetization của Meta tính tiền cho cả ảnh và bài viết văn bản.

## Scope

- `JobType.FEED` — tách khỏi `POST` (Reels), không phá hành vi cũ
- Page object composer riêng (không dùng chung với Reels)
- Media tùy chọn; nhận cả ảnh lẫn video
- Form job thủ công cho chọn loại bài

## Out of scope

- Đăng nhiều ảnh một bài (mới hỗ trợ 1 file)
- Story, carousel, bài lên lịch qua composer
- Bulk upload cho FEED (bulk vẫn chỉ tạo Reels)

## Implementation

| Piece | Path |
|-------|------|
| Composer page object | `app/features/facebook/pages/feed_composer.py` |
| Adapter | `FacebookAdapter.publish_feed()` |
| Job type | `app/constants.py` → `JobType.FEED` |
| Validation | `JobService.assert_feed_media()` + `NON_REELS_JOB_TYPES` |
| Routing | `Dispatcher.dispatch()` — nhánh `JobType.FEED` |
| UI | `fragments/manual_job_form.html` — chọn Reels / Bài feed |
| Test | `tests/test_facebook_feed_post.py` (17 test) |

## Verify — đã chạy thật 2026-07-31

| Nhánh | Kết quả |
|---|---|
| Dry-run (mở composer, gõ chữ, tìm nút Đăng) | PASS |
| Đăng thật bài chữ thuần lên Page `kids0810` | `ok=True`, đã thấy trên tường |
| Đăng thật bài chữ + ảnh lên Page `kids0810` | `ok=True`, đã thấy trên tường |
| Kiểm lại sau khi cuộn trang | Cả 2 bài còn trên Page |

Owner đã xác nhận thấy bài trên Facebook.

## Lỗi chỉ lộ khi chạy live (unit test không bắt được)

1. **Composer của Page có bước "Tiếp"** trước "Đăng" — tường cá nhân thì hiện "Đăng"
   ngay. Đã thêm `advance_to_post_button()` nhảy tối đa 3 bước trung gian.
2. **`pre_post_delay()` cần tham số `page`** — gọi thiếu nên văng `TypeError` ngay
   trước lúc bấm Đăng.

## Còn nợ

- **`post_url` chưa lấy được.** Facebook Page không phơi permalink ra DOM (quét 600
  thẻ `<a>` sau khi cuộn → 0 link `/posts/`). Chỉ lấy được qua GraphQL, mà tên mutation
  đoán theo luồng Reels (`ComposerStoryCreateMutation`) không khớp với composer feed.
  Matcher đã nới rộng + log tên mutation thật mỗi lần hụt → lần chạy job thật tiếp theo
  sẽ lộ tên đúng, vá một dòng là xong. Không chặn tính năng: job vẫn DONE.

## Ghi chú vận hành

Không dùng luồng này để đăng hàng loạt lên tài khoản cá nhân đang chờ bật kiếm tiền —
chính sách Meta xếp *nội dung tự động hoàn toàn, sản xuất hàng loạt* vào diện mất quyền
kiếm tiền. Luồng này dành cho Page.
