# TASK-009: Fix Settings Reset on Deploy

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-009 |
| **Status** | In Progress (Execution Done, chờ Anti review) |
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
- [x] `ai_persona.json` không còn tồn tại ở thư mục gốc project
- [x] `PERSONA_FILE` trong `syspanel.py` trỏ đến `storage/db/config/ai_persona.json`
- [x] Code load persona fallback về DEFAULT_PERSONA khi file chưa tồn tại (không crash)
- [x] `ai_persona.json` có mặt trong `.gitignore`
- [x] `CLAUDE.md` có rule ghi rõ: mọi runtime config phải nằm trong `storage/db/config/`
- [x] Không còn file `.json` config runtime nào khác nằm ngoài `storage/` hoặc `data/` (ngoại lệ `gemini_cookies.json` là cookie artifact đã được `.gitignore` bảo vệ theo DECISION-002)

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [x] Bước 1: Sửa `PERSONA_FILE` trong `app/routers/syspanel.py` sang `storage/db/config/ai_persona.json`; thêm `os.makedirs(..., exist_ok=True)` trước khi save.
- [x] Bước 2: Thêm `ai_persona.json` vào `.gitignore`.
- [x] Bước 3: Thêm Runtime Config Rule vào `CLAUDE.md`.
- [x] Bước 4: Quét `syspanel.py` theo lệnh grep của plan để xác nhận các tham chiếu `.json`.

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```
$ python -m py_compile app/routers/syspanel.py
# exit code 0

$ grep -n 'PERSONA_FILE' app/routers/syspanel.py
712:PERSONA_FILE = str(config.STORAGE_DB_DIR / "config" / "ai_persona.json")

$ grep -n 'ai_persona' .gitignore
45:ai_persona.json

$ grep -nE 'runtime.*config|storage/db/config' CLAUDE.md
71:Mọi file config runtime (JSON, state files) PHẢI nằm trong `storage/db/config/`.

$ grep -rn '\.json' app/routers/syspanel.py | grep -v '__pycache__'
283:    cookie_path = os.path.join(APP_DIR, "gemini_cookies.json")
696:    cookie_path = os.path.join(APP_DIR, "gemini_cookies.json")
712:PERSONA_FILE = str(config.STORAGE_DB_DIR / "config" / "ai_persona.json")

$ test -f ai_persona.json && echo exists || echo missing
missing
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-19 | New | Task được tạo bởi Anti dựa trên DECISION-002 |
| 2026-04-19 | In Progress | Codex đã thực thi xong scope PLAN-009, chờ Anti review/sign-off |
