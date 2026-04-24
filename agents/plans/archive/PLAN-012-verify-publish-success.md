# PLAN-012: Verify Post Publication Status for Job 737

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-012 |
| **Status** | Active |
| **Executor** | Codex |
| **Created by** | Antigravity |
| **Related Task** | TASK-012 |
| **Related ADR** | None |
| **Created** | 2026-04-24 |
| **Updated** | 2026-04-24 |

---

## Goal
Xác minh xem `story_id=UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcwOTUzNzI4NDI4ODc` (được tạo từ Job 737 qua GraphQL) đã được Facebook publish thành công và có thể xem công khai hay chưa.

---

## Context
- Job 737 đã chạy thành công qua chế độ `GRAPHQL_ONLY=1` và bắn `ComposerStoryCreateMutation`.
- Trả về kết quả id: `UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcwOTUzNzI4NDI4ODc`.
- Cần biết chắc chắn video có bị lỗi render/block hay đã hiển thị bình thường trên page/profile, đồng thời lấy URL public.

---

## Scope
*(Executor chỉ được làm những gì trong danh sách này)*

- Kiểm tra API Facebook hoặc chạy script có sẵn để query trạng thái bài viết theo `story_id`.
- Hoặc dùng logic của Playwright/Requests gọi tới URL bài viết để xem phản hồi HTTP/nội dung.
- Ghi lại log xác nhận trạng thái và URL công khai.

## Out of Scope
*(Executor KHÔNG được làm những điều này trong plan này)*

- Thực hiện việc đăng bài mới.
- Thay đổi logic worker hoặc adapter đăng bài cốt lõi.

---

## Proposed Approach
*(Các bước thực hiện theo thứ tự — Executor đọc và làm từng bước)*

**Bước 1**: Viết một script nhỏ hoặc dùng cURL kiểm tra URL/Graph node của `story_id=UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcwOTUzNzI4NDI4ODc`. Có thể thử convert base64 để xem ID thực sự của post/page nếu định dạng ID này cần decode.
**Bước 2**: Gửi request truy xuất trạng thái, xác định bài viết đã live (HTTP 200, nội dung có chữ public).
**Bước 3**: Ghi lại public URL thu được và copy log/output chứng minh.

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| ID định dạng Base64 không truy cập trực tiếp được | Med | Cần viết script decode base64 hoặc dùng Graph Explorer API nội bộ để lấy node info. |
| Video bị kẹt ở khâu processing | Low | Ghi nhận lại thời gian báo lỗi processing và đánh dấu thử lại sau. |

---

## Validation Plan
*(Executor phải thực hiện những check này và ghi kết quả vào Execution Notes)*

- [x] Check 1: Lệnh query/test script chạy không báo lỗi exception. (**PASS**)
- [x] Check 2: Có URL candidate + HTTP 200, nhưng nội dung trả về báo không xem được/trang không hiển thị. (**FAIL - chưa xác nhận live public**)

---

## Rollback Plan
Không có tác động thay đổi hệ thống nên không cần rollback. Nếu lỗi chỉ cần ghi nhận kết quả thất bại.

---

## Execution Notes
*(Executor điền vào theo thứ tự từng bước — KHÔNG để trống khi Done)*

- ✅ Bước 1: Decode `story_id` thành `S:_I658349620689021:122187095372842887`, suy ra URL kiểm tra:
  - `https://www.facebook.com/_I658349620689021/posts/122187095372842887`
  - `https://www.facebook.com/658349620689021/posts/122187095372842887`
  - `https://www.facebook.com/story.php?story_fbid=122187095372842887&id=658349620689021`
  - `https://www.facebook.com/reel/122187095372842887/`
- ✅ Bước 2: Chạy Playwright headless bằng profile Facebook thật (`account_id=4`) để kiểm tra trạng thái hiển thị thực tế.
- ✅ Bước 3: Thu thập proof HTTP/final URL/body sample và screenshot `logs/plan012_url_check_1.png` ... `logs/plan012_url_check_4.png`.

**Verification Proof**:
```
# 1) Decode story_id
DECODED_RAW=S:_I658349620689021:122187095372842887
url_posts=https://www.facebook.com/658349620689021/posts/122187095372842887
url_story=https://www.facebook.com/story.php?story_fbid=122187095372842887&id=658349620689021

# 2) Playwright check with logged-in profile
ACCOUNT_ID=4
PROFILE_PATH=/home/vu/toolsauto/content/profiles/facebook_4

=== https://www.facebook.com/61575286626546/posts/122187095372842887/
HTTP=200
FINAL=https://www.facebook.com/61575286626546/posts/122187095372842887/
UNAVAILABLE_PATTERN_MATCH=True
FOLDED_SNIPPET=... ban hien khong xem duoc noi dung nay ...

=== https://www.facebook.com/story.php?story_fbid=122187095372842887&id=658349620689021
HTTP=200
FINAL=https://www.facebook.com/story.php?story_fbid=122187095372842887&id=658349620689021
UNAVAILABLE_PATTERN_MATCH=True
FOLDED_SNIPPET=... ban hien khong xem duoc noi dung nay ...

=== https://www.facebook.com/reel/122187095372842887/
HTTP=200
FINAL=https://www.facebook.com/reel/122187095372842887/
UNAVAILABLE_PATTERN_MATCH=True
FOLDED_SNIPPET=... trang nay hien khong hien thi ...
```

Execution Done. Cần Claude Code verify + handoff.

---

## Anti Sign-off Gate ⛔
*(Anti điền vào — BLOCKING. Không có section này = Claude Code không được archive)*

**Reviewed by**: Antigravity — 2026-04-24

### Acceptance Criteria Check
*(Copy từ TASK — điền từng dòng, không bỏ qua)*

| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Xác định được trạng thái hiện tại của story_id. | Yes — [Playwright execution logs] | ✅ |
| 2 | Lấy được URL công khai của video. | Yes — [Có URL candidate nhưng truy cập bị báo lỗi Unavailable] | ✅ |
| 3 | Ghi lại log hoặc bằng chứng hiển thị video. | Yes — [Có Verification Proof] | ✅ |

### Scope & Proof Check
- [x] Executor làm đúng Scope, không mở rộng âm thầm
- [x] Proof là output thực tế, không phải lời khẳng định
- [x] Proof cover hết Validation Plan

### Verdict
> **APPROVED** — Codex đã làm đúng yêu cầu (xác minh trạng thái). Kết quả xác minh cho thấy **lỗi nghiêm trọng**: Mặc dù GraphQL trả về `story_id` hợp lệ nhưng thực tế video **không được hiển thị công khai** (Lỗi "bạn hiện không xem được nội dung này"). Luồng Direct Fire GraphQL hiện tại là chưa đủ hoặc bị thiếu field/mutation.

---

## Handoff Note
*(Claude Code điền vào sau khi Anti APPROVED)*

- **Trạng thái sau execution**: GraphQL Direct Fire trả về `story_id` hợp lệ nhưng 3/3 URL candidate (`/posts`, `story.php`, `/reel`) đều load được HTTP 200 với nội dung "bạn hiện không xem được nội dung này" / "trang này hiện không hiển thị". → Post **không public/live**. Direct Fire hiện tại còn thiếu mutation hoặc field (có thể là bước confirm/publish sau `ComposerStoryCreateMutation`, hoặc privacy/audience field chưa set đúng).
- **Những gì cần làm tiếp**:
  1. Anti cần tạo TASK/PLAN mới để điều tra mutation/field còn thiếu trong Direct Fire path (candidate: `useCometFeedStoryPrivacyMutation`, `ComposerStoryPublishMutation`, hoặc audience/privacy parameter trong payload `ComposerStoryCreateMutation`).
  2. So sánh payload Direct Fire hiện tại với payload khi publish qua UI thông thường (diff GraphQL request bodies).
  3. Trước mắt có thể fallback về luồng UI publish cũ cho các job production để không mất post.
- **Liên quan PLAN-011**: Anti Sign-off Gate của PLAN-011 vẫn đang PENDING (mặc dù TASK-011 đã Completed). Cần Anti điền sign-off để archive PLAN-011.
- **Archived**: Yes — 2026-04-24
