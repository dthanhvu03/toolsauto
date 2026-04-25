# TASK-011: Xác minh luồng "Direct Fire" qua GraphQL cho Reels

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-011 |
| **Status** | Completed |
| **Priority** | P0 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-011 |
| **Created** | 2026-04-22 |
| **Updated** | 2026-04-22 |

---

## Objective
Chạy thành công job 737 ở chế độ GRAPHQL_ONLY và thu thập post_id.

---

## Scope
- Chạy script `scripts/graphql_publish_job.py 737`.
- Monitor network mutations.
- Ghi log kết quả.

## Acceptance Criteria
- [x] Chạy job 737 ở chế độ GRAPHQL_ONLY thành công.
- [x] Log bắt được `useCometVideoEditorCopyrightCheckMutation` (gate event).
- [x] Trích xuất được `story_id` hợp lệ: `UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcwOTUzNzI4NDI4ODc`.

---

## Execution Notes
- Đã phát hiện lỗi "Không thấy file input" trong lần chạy đầu tiên. Đã cập nhật script với retry logic và screenshot chẩn đoán.

---

## Verification Proof
```
[2026-04-24T01:49:04] 🚀 Direct GraphQL publish: fire ComposerStoryCreateMutation ...
[2026-04-24T01:49:05] ✅ Direct GraphQL id hint: story_id=UzpfSTY1ODM0OTYyMDY4OTAyMToxMjIxODcwOTUzNzI4NDI4ODc
[2026-04-24T01:49:05] Direct GraphQL retry result: True
[2026-04-24T01:49:05] ? Job 737 status -> DONE
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-22 | New | Task được tạo bởi Anti |
| 2026-04-22 | In Progress | Bắt đầu chạy job xác minh (Corrected Path) |
