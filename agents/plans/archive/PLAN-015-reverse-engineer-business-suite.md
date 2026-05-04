# PLAN-015: Reverse-engineer GraphQL Mutations của Business Suite

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-015 |
| **Status** | Active |
| **Executor** | Codex (Anti kiêm nhiệm) |
| **Created by** | Antigravity |
| **Related Task** | TASK-015 |
| **Related ADR** | None |
| **Created** | 2026-04-24 |
| **Updated** | 2026-04-24 |

---

## Goal
Phân tích và mô phỏng lại luồng gọi API nội bộ của trang Business Suite để xây dựng tính năng Direct Publish cho Page, thay thế cho luồng UI chậm chạp.

---

## Context
- `ComposerStoryCreateMutation` cũ đã bị vô hiệu hóa hoặc ẩn nội dung đối với các Page bị ép sang giao diện Business Suite.
- Luồng Business Suite sử dụng `CPXComposerCopyrightPrecheckMutationQuery` (chặn gate bản quyền) và `BusinessComposerStoryCreationMutation` (để publish).
- Đã có sẵn file dump log JSON từ Playwright UI ở PLAN-013. Cần tận dụng để phân tích.

---

## Scope
- Đọc file JSON đã dump ở PLAN-013 (vd: `logs/investigate_graphql_20260424_043924.json`) hoặc chạy lại `scripts/investigate_graphql.py` nếu cần.
- Bóc tách `doc_id` và `variables.input` của 2 mutation mục tiêu.
- Xây dựng một script Proof of Concept (`scripts/poc_business_suite_publish.py`) nhận tham số `video_id` và `page_id`, tạo payload chuẩn, gửi lên `facebook.com/api/graphql/` bằng request HTTP bình thường (dùng token/cookie lấy từ Playwright context).
- Xác minh bài đăng live thành công bằng luồng này.

## Out of Scope
- Không sửa trực tiếp file worker chính `graphql_publish_job.py`.

---

## Proposed Approach
**Bước 1**: Đọc và bóc tách cấu trúc payload: Mở file log dump, tìm `friendlyName="BusinessComposerStoryCreationMutation"` và `CPXComposerCopyrightPrecheckMutationQuery`. Phân tích schema.
**Bước 2**: Viết script PoC: Import Playwright để lấy context (cookies, fb_dtsg, lsd), gọi API `vupload` để tải một video test nhỏ, thu về `video_id`.
**Bước 3**: Gọi trực tiếp `CPXComposerCopyrightPrecheckMutationQuery` và đợi kết quả trả về.
**Bước 4**: Chèn `video_id` vào payload `BusinessComposerStoryCreationMutation` và gọi HTTP POST. Kiểm tra `story_id` trả về.
**Bước 5**: Kiểm tra URL public.

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Business Suite kiểm tra Referer chặt chẽ | Med | Cần set header `Referer` chuẩn: `business.facebook.com/latest/reels_composer`. |

---

## Validation Plan
- [ ] Check 1: Lấy được payload JSON thô của 2 mutation.
- [ ] Check 2: Script PoC chạy đến cuối không báo lỗi `missing_required_variable_value` hoặc permission denied.
- [ ] Check 3: Bằng chứng URL live.

---

## Execution Notes
- ⏳ Bước 1: 
- ⏳ Bước 2: 
- ⏳ Bước 3: 
- ⏳ Bước 4: 
- ⏳ Bước 5: 

**Verification Proof**:
```
# [Log kết quả chạy script PoC]
```

---

## Anti Sign-off Gate ⛔
**Reviewed by**: Antigravity — [YYYY-MM-DD]

### Acceptance Criteria Check
| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Lấy được payload JSON đầy đủ của CPX... | Yes/No — [ref] | ✅ / ❌ |
| 2 | Lấy được payload JSON đầy đủ của Business... | Yes/No — [ref] | ✅ / ❌ |
| 3 | Chạy thành công script PoC | Yes/No — [ref] | ✅ / ❌ |

### Scope & Proof Check
- [ ] Executor làm đúng Scope
- [ ] Proof là output thực tế
- [ ] Proof cover hết Validation Plan

### Verdict
> **PENDING**
