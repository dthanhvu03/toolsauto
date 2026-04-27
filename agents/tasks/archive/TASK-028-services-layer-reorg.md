# TASK-028: Services Layer Reorganization

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-028 |
| **Status** | Verified |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-028 |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Objective
Tái cấu trúc (reorganize) thư mục `app/services/` từ cấu trúc phẳng sang cấu trúc thư mục chuẩn Domain (ai, jobs, telegram...) mà không gây vỡ import của bất kỳ caller nào thông qua Re-export Pattern.

---

## Scope
- Khởi tạo `app/services/__init__.py` cho mục đích Re-export.
- Di chuyển ~60 file logic của Services vào các thư mục con theo Domain.
- Đổi tên một số file cho ngắn gọn (ví dụ `ai_pipeline.py` -> `ai/pipeline.py`).

## Out of Scope
- KHÔNG thay đổi logic nghiệp vụ bên trong các file được di chuyển.
- KHÔNG sửa đổi các Router hay Worker (`from app.services...` phải được giữ nguyên).

---

## Blockers
- Không có

---

## Acceptance Criteria
- [x] Tất cả file service đã được đưa vào đúng Domain folder tương ứng.
- [x] `app/services/__init__.py` re-export đầy đủ và mapping chuẩn xác các symbol cũ.
- [x] Không có file Caller nào (`routers/`, `workers/`, etc.) bị chỉnh sửa.
- [x] Khởi động ứng dụng (app boot) thành công, không dính `ImportError`.

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [x] Bước 1: Foundation (Re-export pattern set up)
- [x] Bước 2: Migrate AI Domain
- [x] Bước 3: Migrate Telegram Domain
- [x] Bước 4: Migrate Observability Domain
- [x] Bước 5: Migrate Jobs Domain
- [x] Bước 6: Migrate Content Domain
- [x] Bước 7: Migrate Viral Domain
- [x] Bước 8: Migrate Compliance Domain
- [x] Bước 9: Migrate Dashboard Domain
- [x] Bước 10: Migrate Platform & DB Domain

Execution Done. Can Claude Code verify + handoff.

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```
$ wsl -d Ubuntu -- bash -lc 'cd /home/vu/toolsauto && git mv ... && scan source/destination'
MOVE_COUNT=62
SOURCE_LEFT=0
DEST_MISSING=0

$ wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'
from app.services import ai_native_fallback
import app.services.ai.native_fallback as target
print('ALIAS_IDENTITY_OK', ai_native_fallback is target)
PY"
ALIAS_IDENTITY_OK True

$ wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'
modules = [
    'app.services.ai_pipeline',
    'app.services.ai_native_fallback',
    'app.services.ai_runtime',
    'app.services.notifier_service',
    'app.services.notifiers',
    'app.services.job_queue',
    'app.services.content_orchestrator',
    'app.services.platform_config_service',
    'app.services.compliance_service',
]
for module_name in modules:
    __import__(module_name)
print('LEGACY_IMPORT_MATRIX_OK', len(modules))
PY"
LEGACY_IMPORT_MATRIX_OK 9

$ wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && git ls-files 'app/services/*.py' 'app/services/**/*.py' | xargs venv/bin/python -m py_compile && echo PY_COMPILE_SERVICES_OK"
PY_COMPILE_SERVICES_OK

$ wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && venv/bin/python - <<'PY'
from app.main import app
print('APP_IMPORT_OK', len(app.routes), 'routes')
PY"
APP_IMPORT_OK 207 routes

$ wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && venv/bin/pytest -q tests/test_ai_pipeline.py tests/test_ai_native_fallback.py tests/test_ai_reporter.py tests/test_incident_logger.py"
..........................                                               [100%]
26 passed in 1.23s

$ wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && find app/services -maxdepth 1 -type f -printf '%f\n' | sort && echo ROOT_FILE_SCAN_DONE"
__init__.py
ROOT_FILE_SCAN_DONE

$ wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && git diff --name-only -- . ':(exclude)app/services/**'"
# no output
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-27 | New | Task được tạo bởi Anti |
| 2026-04-27 | Planned | PLAN-028 được tạo và approve. Đã cập nhật theo template chuẩn. |
| 2026-04-27 | Assigned | Assign cho Codex thực thi logic backend |
| 2026-04-27 | In Progress | Codex bắt đầu di chuyển file |
| 2026-04-27 | Verified | Anti sign-off APPROVED — 207 routes boot OK, 9/9 caller imports PASS, 26/26 pytest PASS |
| 2026-04-27 | Execution Done | Codex moved services into domain packages, preserved legacy imports with lazy aliases, and recorded proof. Pending Claude verify + handoff. |
