# TASK-027: Refactoring Sprint — Chuẩn Hoá Kiến Trúc Theo Tiêu Chuẩn Quốc Tế

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-027 |
| **Status** | Planned |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex / Claude Code (theo từng Phase) |
| **Related Plan** | PLAN-027 |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Objective
Cấu trúc lại (Refactor) toàn bộ codebase ToolsAuto để tuân thủ các nguyên tắc thiết kế phần mềm tiêu chuẩn quốc tế: SOLID, Clean Architecture, DRY, theo 6 Phase độc lập.

---

## Scope
Refactor được chia thành **6 Phase** độc lập, mỗi Phase có thể triển khai và verify riêng:

### Phase 1 — Schema Centralization (P0 — Dễ nhất, làm đầu tiên)
- Dời toàn bộ Pydantic BaseModel từ các file `routers/` sang `app/schemas/`
- Tạo các file schema theo domain

### Phase 2 — Thin Controller (P1 — Sau Phase 1)
- Tách logic nghiệp vụ (SQL thô, subprocess) ra khỏi `routers/`
- Tạo Service layer tương ứng cho từng Router béo

### Phase 3 — Kill Duplicate AI Pathway (P1)
- Deprecate `gemini_api.py`, migrate 8 caller sang `ai_pipeline.py`
- Giải quyết fallback strategy cho `content_orchestrator.py`

### Phase 4 — DRY Error Handling (P2)
- Tạo Playwright Decorator `@playwright_safe_action`
- Apply vào `facebook/adapter.py` và `generic/adapter.py`

### Phase 5 — Facebook Adapter Split (P2 — Opportunistic)
- Tách God Object 2373 LOC thành facade + module con
- Chỉ thực hiện khi có bug/feature chạm adapter

### Phase 6 — Enum & Constants (P3)
- Gom tất cả Magic Strings vào các Enum class
- Apply xuyên suốt dự án

## Out of Scope
- Chuyển đổi Database Polling sang Message Queue (Redis/RabbitMQ) — đây là Phase riêng cho giai đoạn Scale
- Tách `models.py` thành package — đã có TASK-022 riêng
- Viết Unit Test — đã có TASK-021 riêng

---

## Blockers
- Phase 2 phụ thuộc Phase 1 (Schema phải tập trung trước khi Router được dọn)
- Phase 5 là Opportunistic (chỉ thực hiện khi có lý do chạm adapter)

---

## Acceptance Criteria
- [ ] **Phase 1**: Không còn bất kỳ class BaseModel nào bên trong thư mục `app/routers/`. Mọi schema nằm trong `app/schemas/`.
- [ ] **Phase 2**: Mọi file router < 500 LOC. Không còn câu SQL thô hoặc subprocess trong router.
- [ ] **Phase 3**: `gemini_api.py` được đánh dấu `@deprecated`. Mọi caller chính thức đi qua `ai_pipeline.py`.
- [ ] **Phase 4**: Không còn khối try-except Playwright bị lặp lại > 2 lần. Decorator `@playwright_safe_action` được sử dụng.
- [ ] **Phase 5**: Class `FacebookAdapter` < 500 LOC (facade). Logic nằm trong module con.
- [ ] **Phase 6**: Không còn Magic String `"facebook"`, `"POST"`, `"DONE"` trong code chính. Tất cả dùng Enum.
- [ ] Mọi phase: Hệ thống chạy ổn định sau refactor (PM2 status OK, no crash trong 1h).

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [ ] Phase 1: Schema Centralization
- [ ] Phase 2: Thin Controller
- [ ] Phase 3: Kill Duplicate AI Pathway
- [ ] Phase 4: DRY Error Handling
- [ ] Phase 5: Facebook Adapter Split
- [ ] Phase 6: Enum & Constants

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```
# Mỗi Phase phải có:
# 1. grep proof (không còn vi phạm)
# 2. python import smoke test
# 3. pm2 status all OK
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-27 | New | Task được tạo bởi Anti sau Architecture Review |
| 2026-04-27 | Planned | PLAN-027 được tạo, chia 6 Phase |
