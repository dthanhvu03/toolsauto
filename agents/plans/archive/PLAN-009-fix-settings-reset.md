# PLAN-009: Fix Settings Reset on Deploy

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-009 |
| **Status** | Active |
| **Executor** | Codex |
| **Created by** | Antigravity |
| **Related Task** | TASK-009 |
| **Related ADR** | DECISION-002 |
| **Created** | 2026-04-19 |
| **Updated** | 2026-04-19 |

---

## Goal
Dời `ai_persona.json` và mọi runtime config file ra khỏi thư mục gốc vào `storage/db/config/`, đảm bảo chúng tồn tại qua mọi lần deploy (`git reset --hard`).

---

## Context
- `deploy.yml` dòng 51 chạy `git reset --hard` → xóa mọi file untracked nằm ngoài `.gitignore`.
- `ai_persona.json` hiện nằm ở root project, không được `.gitignore` bảo vệ → bị xóa mỗi lần deploy.
- Thư mục `storage/` đã có trong `.gitignore` → file nằm trong đó sẽ sống sót.
- Phân tích đầy đủ tại `agents/decisions/DECISION-002-settings-reset-on-deploy.md`.

---

## Scope
*(Executor chỉ được làm những gì trong danh sách này)*

- `app/routers/syspanel.py` — đổi `PERSONA_FILE` từ `os.path.join(APP_DIR, "ai_persona.json")` sang `str(config.STORAGE_DB_DIR / "config" / "ai_persona.json")`
- `.gitignore` — thêm dòng `ai_persona.json`
- `CLAUDE.md` — thêm rule runtime config

## Out of Scope
*(Executor KHÔNG được làm những điều này trong plan này)*

- KHÔNG sửa `deploy.yml`
- KHÔNG sửa logic load/save persona (chỉ đổi path)
- KHÔNG sửa 9router config path (đã nằm trong `data/config/` → an toàn)

---

## Proposed Approach

**Bước 1: Đổi PERSONA_FILE path**
- Mở `app/routers/syspanel.py`.
- Tìm dòng `PERSONA_FILE = os.path.join(APP_DIR, "ai_persona.json")`.
- Thay bằng:
```python
import app.config as config
PERSONA_FILE = str(config.STORAGE_DB_DIR / "config" / "ai_persona.json")
```
- Đảm bảo `os.makedirs(os.path.dirname(PERSONA_FILE), exist_ok=True)` được gọi trước khi ghi file (trong hàm `save_persona`).

**Bước 2: Cập nhật .gitignore**
- Thêm dòng `ai_persona.json` vào section "Generated Data & State" của `.gitignore`.

**Bước 3: Cập nhật CLAUDE.md**
- Thêm rule vào phần conventions/rules:
```
## Runtime Config Rule
Mọi file config runtime (JSON, state files) PHẢI nằm trong `storage/db/config/`.
KHÔNG BAO GIỜ tạo file config ở thư mục gốc project — `git reset --hard` sẽ xóa chúng khi deploy.
```

**Bước 4: Quét codebase**
- Chạy: `grep -rn '\.json' app/routers/syspanel.py | grep -v '__pycache__'`
- Xác nhận không còn file `.json` config nào khác nằm ngoài `storage/` hoặc `data/`.

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| VPS chưa có thư mục `storage/db/config/` | Low | `os.makedirs(..., exist_ok=True)` trong save_persona đã handle |
| File persona cũ trên VPS bị mất sau deploy tiếp theo | Low | Deploy script sẽ copy `data/* → storage/db/` nên nếu file nằm trong data/config/ cũng sẽ được migrate |

---

## Validation Plan

- [x] Check 1: `python -m py_compile app/routers/syspanel.py` → exit 0
- [x] Check 2: `grep 'PERSONA_FILE' app/routers/syspanel.py` → path chứa `storage/db/config`
- [x] Check 3: `grep 'ai_persona' .gitignore` → có kết quả
- [x] Check 4: `grep 'runtime.*config\|storage/db/config' CLAUDE.md` → có rule

---

## Rollback Plan
Nếu execution fail → `git checkout -- app/routers/syspanel.py .gitignore CLAUDE.md`

---

## Execution Notes
*(Executor điền vào theo thứ tự từng bước — KHÔNG để trống khi Done)*

- ✅ Bước 1:
  - Đổi `PERSONA_FILE` sang `str(config.STORAGE_DB_DIR / "config" / "ai_persona.json")` trong `app/routers/syspanel.py`.
  - Bổ sung `os.makedirs(os.path.dirname(PERSONA_FILE), exist_ok=True)` trước khi ghi file trong `save_persona`.
- ✅ Bước 2:
  - Thêm `ai_persona.json` vào `.gitignore` (section Generated Data & State).
- ✅ Bước 3:
  - Thêm section `Runtime Config Rule` vào `CLAUDE.md`.
- ✅ Bước 4:
  - Quét `syspanel.py` theo lệnh grep yêu cầu.
  - Kết quả: persona đã trỏ storage path; các tham chiếu `.json` còn lại tại root là `gemini_cookies.json` (đã được ignore từ trước, không thuộc scope runtime config migration của plan này).

**Verification Proof**:
```
$ python -m py_compile app/routers/syspanel.py
# exit code 0

$ grep -n 'PERSONA_FILE' app/routers/syspanel.py
712:PERSONA_FILE = str(config.STORAGE_DB_DIR / "config" / "ai_persona.json")
742:        os.makedirs(os.path.dirname(PERSONA_FILE), exist_ok=True)

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

## Claude Code Verify — 2026-04-19

### Acceptance Criteria Check
| # | Criterion | Proof thực tế | Pass? |
|---|---|---|---|
| 1 | `ai_persona.json` không ở root | `test -f ai_persona.json` → `missing` ✅ | ✅ |
| 2 | `PERSONA_FILE` trỏ `storage/db/config` | `syspanel.py:712` = `str(config.STORAGE_DB_DIR / "config" / "ai_persona.json")` ✅ | ✅ |
| 3 | Fallback `DEFAULT_PERSONA` khi file chưa tồn tại | `_load_persona()` line 720-727: `if os.path.exists(PERSONA_FILE)` → else `return DEFAULT_PERSONA`. Không crash ✅ | ✅ |
| 4 | `.gitignore` có `ai_persona.json` | `.gitignore:45` = `ai_persona.json` ✅ | ✅ |
| 5 | `CLAUDE.md` có runtime config rule | `CLAUDE.md:70-71` = `## Runtime Config Rule` + rule text ✅ | ✅ |
| 6 | `os.makedirs` trước khi save | `syspanel.py:742` = `os.makedirs(os.path.dirname(PERSONA_FILE), exist_ok=True)` ✅ | ✅ |
| Compile | `py_compile syspanel.py` | exit 0 ✅ | ✅ |

### Scope Check
- ✅ Executor làm đúng Scope: chỉ sửa `PERSONA_FILE` path + `.gitignore` + `CLAUDE.md`
- ✅ Không đụng `deploy.yml`, không sửa logic load/save persona ngoài path
- ✅ Proof là output lệnh thực tế (grep + test -f + py_compile)

**Ghi chú**: Migration auto (`shutil.move` từ root sang storage) không nằm trong scope PLAN-009 — đã được Anti quyết định bỏ qua. File root hiện tại đã `missing`, không có dữ liệu sống cần migrate.

**Status: DONE — Tất cả AC pass. Chờ Anti final sign-off để archive.**

---

## Anti Sign-off Gate ⛔

**Reviewed by**: Antigravity — 2026-04-19

### Acceptance Criteria Check
| # | Criterion | Proof | Pass? |
|---|---|---|---|
| 1 | `ai_persona.json` không ở root | `test -f` → `missing` | ✅ |
| 2 | `PERSONA_FILE` trỏ `storage/db/config` | `syspanel.py:712` | ✅ |
| 3 | Fallback DEFAULT_PERSONA | `_load_persona()` L720-727 | ✅ |
| 4 | `.gitignore` có `ai_persona.json` | `.gitignore:45` | ✅ |
| 5 | `CLAUDE.md` có runtime rule | `CLAUDE.md:70-71` | ✅ |
| 6 | `os.makedirs` trước save | `syspanel.py:742` | ✅ |

### Scope & Proof Check
- [x] Executor làm đúng Scope
- [x] Proof là output thực tế
- [x] Proof cover hết Validation Plan

### Verdict
> **APPROVED** — Diff sạch, đúng scope, proof đầy đủ.

---

## Handoff Note
*(Claude Code — 2026-04-19)*

- **Trạng thái sau execution**: Tất cả 6 AC pass. Hệ thống sẵn sàng — persona config sẽ sống sót mọi lần deploy.
- **Những gì cần làm tiếp**: Anti sign-off → Claude Code archive PLAN-009 + TASK-009 → commit tổng thể TASK-007 + TASK-008 + TASK-009.
- **Archived**: No — chờ Anti sign-off.
