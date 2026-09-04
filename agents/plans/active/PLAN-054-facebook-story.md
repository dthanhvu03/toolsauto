# PLAN-054 — Đăng Story Facebook + gắn link affiliate

## Status: Code done — chờ verify live (2026-08-21)

## Goal

`JobType.STORY` mới chỉ là một hằng số trong `app/constants.py`: không adapter, không
nhánh dispatcher, không UI. Đây là món đắt nhất còn thiếu của combo Page Master (5tr).

## Scope

- `FacebookStoryComposer` — page object riêng cho luồng tin
- `FacebookAdapter.publish_story()` — ảnh hoặc video, đăng dưới danh nghĩa Page
- Nhánh `JobType.STORY` trong dispatcher + cổng media không đòi video như Reels
- Chèn link affiliate (`tracking_url` → `affiliate_url`) làm chữ trên tin
- Form job thủ công thêm lựa chọn "Tin (Story)"

## Out of scope

- Sticker link bấm được (link sticker) — xem §Rủi ro, cần khảo sát live trước khi hứa
- Story dạng chữ thuần (không media) — tin phải có ảnh/video
- Story cho Instagram / Threads

## Quyết định thiết kế

**Vào từ bề mặt Page, không vào thẳng `/stories/create`.** Danh tính người đăng lấy
theo bề mặt đang đứng — đúng cách `publish_feed` đang làm. Vào thẳng URL tạo tin dễ
đăng nhầm dưới tài khoản cá nhân, mà đăng nhầm chỗ là sự cố nặng nhất của hệ này
(`publish` Reels phải abort vì lý do đó).

**Kiểm danh tính trước khi bấm Chia sẻ.** Đọc chip tác giả trong hộp thoại tin:
- Đọc được và **khác** tên Page → dừng, không đăng (`is_fatal=False`, cho retry)
- Không đọc được → vẫn đăng nhưng ghi cảnh báo (DOM tin đổi thường xuyên; chặn cứng
  ở đây sẽ khoá luôn tính năng khi Facebook đổi layout)

**Story không sinh COMMENT job** — đã chốt ở PLAN-053, tin không có bình luận công khai.

## Implementation

| Piece | Path |
|-------|------|
| Page object | `app/features/facebook/pages/story_composer.py` |
| Adapter | `FacebookAdapter.publish_story()` |
| Routing | `Dispatcher.dispatch()` — nhánh `JobType.STORY` |
| Cổng media | `JobService.assert_story_media()` + `NON_REELS_JOB_TYPES` |
| Link aff | `FacebookAdapter.story_overlay_text()` |
| UI | `fragments/manual_job_form.html` — 3 lựa chọn Reels / Bài feed / Tin |
| Test | `tests/test_facebook_story_post.py` |

## Rủi ro đã biết

1. **Link trong tin có bấm được không** — chưa kiểm chứng được nếu không chạy live.
   Bản này chèn link dạng **chữ trên tin**. Nếu Page có link sticker thì phải làm thêm
   một vòng nữa. **Không hứa với khách "link aff bấm được trong story" trước khi test live.**
2. Selector hộp thoại tin chưa từng chạy thật → phải verify live như PLAN-049 đã dạy
   (hai lỗi của luồng feed chỉ lộ khi đăng thật).

## Lệch so với kế hoạch (ghi để khỏi quên)

- `story_overlay_text` đặt ở `FacebookAdapter` chứ không phải `JobService`: nó chỉ
  phục vụ luồng tin của Facebook, đưa xuống tầng queue là kéo thêm phụ thuộc vô ích.
- `_resolve_target_page_name` lặp lại ~10 dòng tra tên Page vốn nằm inline trong
  `publish()`. **Cố ý không sửa `publish()`** — Reels là luồng chạy production nhiều
  nhất, đổi nó nằm ngoài scope plan này. Gộp lại khi nào có plan chạm vào Reels.

## Verify — 2026-08-21

| Hạng mục | Kết quả |
|---|---|
| Cổng media: tin thiếu media / file lạ đều bị chặn, nhận cả ảnh lẫn video | PASS |
| Tin không media bị chặn **ngay lúc tạo job**, không chờ tới lúc đăng | PASS |
| Dispatcher rẽ nhánh STORY, trả lại `media_path` gốc trong `finally` | PASS |
| Cổng video-only của Reels bỏ qua STORY (`NON_REELS_JOB_TYPES`) | PASS |
| Chữ phủ tin: `tracking_url` → `affiliate_url` → caption → rỗng | PASS |
| Chặn đăng nhầm danh nghĩa; không đọc được tên thì không chặn | PASS |
| Bắt link tin `/stories/` mà không nhặt nhầm link `/posts/` | PASS |
| Nhãn có đủ tiếng Việt lẫn tiếng Anh; không bấm nhầm "Chia sẻ lên bảng feed" | PASS |
| UI có lựa chọn Tin, `accept` + `required` đổi theo | PASS |

`tests/test_facebook_story_post.py` — 23 test. Full suite **222 passed**.

Một lỗi thật do test lộ ra: `_normalize_fb_text` chỉ NFD nên vẫn còn dấu tổ hợp; tên
Page lệch dấu so với nhãn Facebook sẽ bị coi là "người khác" và **chặn oan cả job**.
Đã thêm `_identity_key` (bỏ dấu + gộp khoảng trắng) cho riêng phép so danh tính.

## Còn nợ — BẮT BUỘC làm trước khi giao khách

- [ ] **Live**: đăng tin ảnh + tin video lên Page nháp. Selector hộp tạo tin chưa
      từng chạy thật lần nào. PLAN-049 có hai lỗi chỉ lộ khi đăng live — luồng tin
      không có lý do gì khá hơn.
- [ ] **Live**: kiểm chữ phủ lên tin có bấm được thành link không. Nếu không, phải
      làm link sticker hoặc đổi cách bán mô tả tính năng này.
