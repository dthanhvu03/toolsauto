# TASK-012: Kiểm tra kết quả đăng bài Reels từ Job 737

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-012 |
| **Status** | Done |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-012 |
| **Created** | 2026-04-24 |
| **Updated** | 2026-04-24 |

---

## Objective
Kiểm tra xem bài đăng từ Job 737 (story_id=UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcwOTUzNzI4NDI4ODc) đã thực sự hiển thị trên trang Facebook chưa và lấy link công khai.

---

## Scope
- Truy cập vào trang Facebook của account tương ứng (hoặc truy cập qua API/GraphQL nếu có) để tìm video.
- Hoặc chạy thử một script check trạng thái post (nếu có sẵn) với `story_id`.
- Xác nhận trạng thái video (published, processing, hay failed).

## Out of Scope
- Không thực hiện đăng bài mới.
- Không thay đổi mã nguồn logic đăng bài (chỉ viết script test hoặc chạy test thủ công qua code).

---

## Blockers
- Có thể ID được tạo là ID nội bộ của Graph, cần dùng query chuẩn xác để lấy URL thực tế của bài đăng.

---

## Acceptance Criteria
- [x] Xác định được trạng thái hiện tại của `story_id=UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcwOTUzNzI4NDI4ODc` (kết quả: URL mở ra trang unavailable/not viewable).
- [ ] Lấy được URL công khai của video (nếu đã publish thành công). *(Đã có URL candidate nhưng chưa xác nhận public/live)*
- [x] Ghi lại log hoặc bằng chứng hiển thị video.

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [x] Bước 1: Decode `story_id` sang các URL candidate (`/posts`, `story.php`, `/reel`).
- [x] Bước 2: Chạy Playwright headless với profile account Facebook đang active để kiểm tra khả năng truy cập thực tế.

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```
# Decode
DECODED_RAW=S:_I658349620689021:122187095372842887

# Playwright verify (logged-in profile)
ACCOUNT_ID=4
PROFILE_PATH=/home/vu/toolsauto/content/profiles/facebook_4

HTTP=200 | FINAL=https://www.facebook.com/61575286626546/posts/122187095372842887/ | UNAVAILABLE_PATTERN_MATCH=True
HTTP=200 | FINAL=https://www.facebook.com/story.php?story_fbid=122187095372842887&id=658349620689021 | UNAVAILABLE_PATTERN_MATCH=True
HTTP=200 | FINAL=https://www.facebook.com/reel/122187095372842887/ | UNAVAILABLE_PATTERN_MATCH=True

# Screenshots
logs/plan012_url_check_1.png
logs/plan012_url_check_2.png
logs/plan012_url_check_3.png
logs/plan012_url_check_4.png
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-24 | New | Task được tạo bởi Anti |
| 2026-04-24 | Planned | PLAN-012 được tạo |
| 2026-04-24 | Assigned | Assign cho Codex thực thi kiểm tra |
| 2026-04-24 | In Progress | Codex đã chạy verify thực tế; kết quả chưa xác nhận video live/public, cần Anti/Claude tiếp tục handoff |
| 2026-04-24 | Done | Anti APPROVED PLAN-012; Claude Code archived + đổi status Done |
