# TASK-009: Fix Settings Reset on Deploy

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-009 |
| **Status** | New |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-009 |
| **Created** | 2026-04-19 |
| **Updated** | 2026-04-19 |

---

## Objective
Dời toàn bộ file config runtime ra khỏi thư mục gốc project vào `storage/db/config/` để `git reset --hard` trong deploy.yml không còn xóa mất settings đã cấu hình trên System Panel.

---

## Scope
- Dời `ai_persona.json` từ root → `storage/db/config/ai_persona.json`
- Sửa constant `PERSONA_FILE` trong `app/routers/syspanel.py` trỏ sang path mới
- Thêm `ai_persona.json` vào `.gitignore` (phòng thủ lớp 2)
- Quét codebase kiểm tra còn file config runtime nào khác nằm ngoài `storage/`
- Cập nhật `CLAUDE.md` với rule: runtime config → `storage/db/config/`

## Out of Scope
- KHÔNG thay đổi logic `git reset --hard` trong `deploy.yml`
- KHÔNG sửa cấu trúc DB hay migration

---

## Blockers
- Không có

---

## Acceptance Criteria
- [ ] `ai_persona.json` không còn tồn tại ở thư mục gốc project
- [ ] `PERSONA_FILE` trong `syspanel.py` trỏ đến `storage/db/config/ai_persona.json`
- [ ] Code load persona fallback về DEFAULT_PERSONA khi file chưa tồn tại (không crash)
- [ ] `ai_persona.json` có mặt trong `.gitignore`
- [ ] `CLAUDE.md` có rule ghi rõ: mọi runtime config phải nằm trong `storage/db/config/`
- [ ] Không còn file `.json` config runtime nào khác nằm ngoài `storage/` hoặc `data/`

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [ ] Bước 1: 
- [ ] Bước 2: 
- [ ] Bước 3: 

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```
# Lệnh đã chạy + output thực tế
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-19 | New | Task được tạo bởi Anti dựa trên DECISION-002 |
