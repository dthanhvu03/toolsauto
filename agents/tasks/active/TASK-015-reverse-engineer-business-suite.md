# TASK-015: Giải mã hệ API GraphQL của Business Suite

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-015 |
| **Status** | Assigned |
| **Priority** | P0 |
| **Owner** | Antigravity |
| **Executor** | Codex (Anti kiêm nhiệm) |
| **Related Plan** | PLAN-015 |
| **Created** | 2026-04-24 |
| **Updated** | 2026-04-24 |

---

## Objective
Reverse-engineer 2 mutation cốt lõi của Business Suite (`CPXComposerCopyrightPrecheckMutationQuery` và `BusinessComposerStoryCreationMutation`) để hỗ trợ việc đăng tự động cực nhanh (Direct Publish) cho các Page mà không cần thao tác UI.

---

## Scope
- Sử dụng log JSON đã dump ở quá trình trước (hoặc dump lại nếu cần) để trích xuất cấu trúc chuẩn của 2 mutation trên.
- Xác định biến nào là động (dynamic như video_id, page_id) và biến nào là tĩnh (static).
- Viết thử nghiệm giả lập (PoC) bắn thẳng 2 mutation này để kiểm tra xem Facebook có accept và bài đăng có thực sự live không.

## Out of Scope
- Tích hợp code giả lập vào `scripts/graphql_publish_job.py`. Task này chỉ dừng ở mức Research & Proof of Concept (PoC).

---

## Blockers
- Cấu trúc payload của Business Suite thường lớn và phức tạp, chứa nhiều tham số anti-spam.

---

## Acceptance Criteria
- [ ] Lấy được payload JSON đầy đủ của `CPXComposerCopyrightPrecheckMutationQuery`.
- [ ] Lấy được payload JSON đầy đủ của `BusinessComposerStoryCreationMutation`.
- [ ] Chạy thành công script PoC bắn 2 mutation này (thu được HTTP 200 và URL live).

---

## Execution Notes
- [ ] Bước 1:
- [ ] Bước 2:

---

## Verification Proof
```
# [Kết quả PoC và bằng chứng URL]
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-24 | New | Task được tạo bởi Anti |
| 2026-04-24 | Planned | PLAN-015 được tạo |
| 2026-04-24 | Assigned | Giao cho Executor (Anti kiêm nhiệm do Codex hết token) |
