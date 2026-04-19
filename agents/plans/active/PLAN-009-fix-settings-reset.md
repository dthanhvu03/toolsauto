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

- [ ] Check 1: `python -m py_compile app/routers/syspanel.py` → exit 0
- [ ] Check 2: `grep 'PERSONA_FILE' app/routers/syspanel.py` → path chứa `storage/db/config`
- [ ] Check 3: `grep 'ai_persona' .gitignore` → có kết quả
- [ ] Check 4: `grep 'runtime.*config\|storage/db/config' CLAUDE.md` → có rule

---

## Rollback Plan
Nếu execution fail → `git checkout -- app/routers/syspanel.py .gitignore CLAUDE.md`

---

## Execution Notes
*(Executor điền vào theo thứ tự từng bước — KHÔNG để trống khi Done)*

- ⏳ Bước 1: 
- ⏳ Bước 2: 
- ⏳ Bước 3: 
- ⏳ Bước 4: 

**Verification Proof**:
```
```

---

## Anti Sign-off Gate ⛔
*(Anti điền vào — BLOCKING. Không có section này = Claude Code không được archive)*

**Reviewed by**: Antigravity — [TBD]

### Acceptance Criteria Check
| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | ai_persona.json không ở root | TBD | ⏳ |
| 2 | PERSONA_FILE trỏ storage/db/config | TBD | ⏳ |
| 3 | Fallback DEFAULT_PERSONA khi file chưa tồn tại | TBD | ⏳ |
| 4 | .gitignore có ai_persona.json | TBD | ⏳ |
| 5 | CLAUDE.md có runtime config rule | TBD | ⏳ |

### Scope & Proof Check
- [ ] Executor làm đúng Scope, không mở rộng âm thầm
- [ ] Proof là output thực tế, không phải lời khẳng định
- [ ] Proof cover hết Validation Plan

### Verdict
> **TBD**

---

## Handoff Note
*(Claude Code điền vào sau khi Anti APPROVED)*

- Trạng thái sau execution: ...
- Những gì cần làm tiếp (nếu có): ...
- Archived: Yes / No — [date]
