# TASK-027: Refactoring Sprint — Chuẩn Hoá Kiến Trúc Theo Tiêu Chuẩn Quốc Tế

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-027 |
| **Status** | Assigned |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex / Claude Code (theo từng Phase) |
| **Related Plan** | PLAN-027 |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Objective
Cấu trúc lại (Refactor) codebase ToolsAuto để tuân thủ các nguyên tắc SOLID, Clean Architecture, DRY — chia thành 4 Phase độc lập.

---

## Pre-Research Notes (Phase 2 — Research)
**Đã đọc `current-status.md` trước khi lập kế hoạch. Phát hiện các việc ĐÃ LÀM XONG, loại khỏi scope:**

| Việc | Trạng thái | Tham chiếu |
|---|---|---|
| Tách `models.py` thành package | ✅ ĐÃ XONG | TASK-022 (archived) |
| Deprecate `gemini_api.py` text path | ✅ ĐÃ XONG | TASK-023/024 (archived) |
| AI Pipeline 2-tier fallback | ✅ ĐÃ XONG | ADR-006 (implemented) |
| Service Test Baseline | ✅ ĐÃ XONG | TASK-021 (archived) |
| Schedule AI Reporter Cron | ✅ ĐÃ XONG | TASK-020 (archived) |

**Còn lại CẦN LÀM (scope thực tế của TASK-027):**

---

## Scope
### Phase 1 — Schema Centralization (P0 — Dễ nhất)
- Dời toàn bộ Pydantic BaseModel từ `routers/` sang `app/schemas/`

### Phase 2 — Thin Controller (P1)
- Tách logic nghiệp vụ ra khỏi `routers/` sang `services/`

### Phase 3 — DRY Error Handling (P2)
- Tạo Playwright Decorator `@playwright_safe_action`
- Apply vào `facebook/adapter.py` và `generic/adapter.py`

### Phase 4 — Enum & Constants (P3)
- Gom Magic Strings vào Enum class

### Opportunistic (không lên lịch, chỉ làm khi có trigger)
- Facebook Adapter Split — khi có bug/feature chạm adapter

## Out of Scope
- ~~Kill Duplicate AI Pathway~~ → ĐÃ XONG (TASK-023/024, ADR-006)
- ~~Tách models.py~~ → ĐÃ XONG (TASK-022)
- ~~Schedule AI Reporter~~ → ĐÃ XONG (TASK-020)
- ~~Service Test Baseline~~ → ĐÃ XONG (TASK-021)
- Database Polling → Message Queue — giai đoạn Scale riêng

---

## Blockers
- Phase 2 phụ thuộc Phase 1 (Schema phải tập trung trước)

---

## Acceptance Criteria
- [ ] **Phase 1**: Không còn class BaseModel nào trong `app/routers/`. Mọi schema nằm trong `app/schemas/`.
- [ ] **Phase 2**: Mọi file router < 500 LOC. Không còn SQL thô hoặc subprocess trong router.
- [ ] **Phase 3**: Không còn khối try-except Playwright lặp > 2 lần. Decorator `@playwright_safe_action` được sử dụng.
- [ ] **Phase 4**: Không còn Magic String `"facebook"`, `"POST"` trong code chính. Tất cả dùng Enum.
- [ ] Mọi phase: `python -c "from app.main import app; print('OK')"` + PM2 status OK.

---

## Execution Notes
*(Executor điền vào trong khi làm)*

- [ ] Phase 1: Schema Centralization
- [ ] Phase 2: Thin Controller
- [ ] Phase 3: DRY Error Handling
- [ ] Phase 4: Enum & Constants

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
| 2026-04-27 | New | Task được tạo bởi Anti sau Architecture Review. Đã research current-status.md, loại bỏ scope trùng lặp. |
| 2026-04-27 | Planned | PLAN-027 được tạo (4 Phase), anh Vu đã approve |
| 2026-04-27 | Assigned | Phase 1 assign cho Antigravity (self-execute), Phase 2-3 cho Codex, Phase 4 cho Claude Code |
