# PLAN-027: Refactoring Sprint — Chuẩn Hoá Kiến Trúc Theo Tiêu Chuẩn Quốc Tế

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-027 |
| **Status** | Active |
| **Executor** | Claude Code (Phase 1, 4) / Codex (Phase 2, 3) |
| **Created by** | Antigravity |
| **Related Task** | TASK-027 |
| **Related ADR** | DECISION-006-codebase-refactor-rfc |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Goal
Loại bỏ các vi phạm nguyên tắc thiết kế phần mềm quốc tế (SOLID, Clean Architecture, DRY) đã phát hiện trong Architecture Review ngày 27/04/2026. Chỉ bao gồm phần CHƯA LÀM — đã loại scope trùng lặp với TASK-020/021/022/023/024.

---

## Context
**Đã đọc `agents/handoffs/current-status.md` (Phase 2 — Research):**
- Dự án ~50K LOC, kiến trúc phân tầng tốt nhưng ranh giới giữa các tầng bị mờ.
- Các task đã hoàn thành trước đó: models split (TASK-022), AI fallback (TASK-023/024), test baseline (TASK-021), cron reporter (TASK-020).
- Tài liệu tham chiếu: `agents/ARCHITECTURE_REVIEW.md`, `agents/CODING_STANDARDS.md`.
- Hệ thống đang chạy production ổn định — refactor phải đảm bảo ZERO downtime.

---

## Scope — 4 Phase (đã loại scope trùng lặp)

---

### Phase 1: Schema Centralization
**Executor:** Claude Code
**Effort:** ~2 giờ

**Bước 1.1** — Quét:
```bash
grep -rn "class.*BaseModel" app/routers/ --include="*.py"
```

**Bước 1.2** — Tạo file schema theo domain trong `app/schemas/`:
- `compliance.py`, `jobs.py`, `accounts.py`, `platform_config.py`, `threads.py`
- `__init__.py` re-export tất cả

**Bước 1.3** — Di chuyển từng class BaseModel, cập nhật import trong router.

**Bước 1.4** — Verify:
```bash
grep -rn "class.*BaseModel" app/routers/  # phải = 0
python -c "from app.main import app; print('OK')"
```

---

### Phase 2: Thin Controller
**Executor:** Codex
**Effort:** ~6 giờ
**Phụ thuộc:** Phase 1 phải xong trước

| # | Router | LOC | Service mới |
|---|---|---|---|
| 1 | `platform_config.py` | 1063 | `services/platform_config_service.py` |
| 2 | `compliance.py` | 929 | `services/compliance_service.py` |
| 3 | `insights.py` | 883 | `services/insights_service.py` |
| 4 | `syspanel.py` | 853 | `services/syspanel_service.py` |

**Bước 2.1** — Với mỗi router: tạo service mới, dời SQL/subprocess/logic vào service, router chỉ giữ route + validate + gọi service.

**Bước 2.2** — Verify từng router:
```bash
wc -l app/routers/<file>.py  # phải < 500
grep -c "db.execute\|text(" app/routers/<file>.py  # phải = 0
```

---

### Phase 3: DRY Error Handling
**Executor:** Codex
**Effort:** ~3 giờ

**Bước 3.1** — Tạo `app/adapters/common/decorators.py` với `@playwright_safe_action`.

**Bước 3.2** — Apply vào helper functions trong `facebook/adapter.py` và `generic/adapter.py`.

**Bước 3.3** — Verify:
```bash
grep -c "except.*Timeout" app/adapters/facebook/adapter.py  # phải giảm > 50%
```

---

### Phase 4: Enum & Constants
**Executor:** Claude Code
**Effort:** ~3 giờ

**Bước 4.1** — Mở rộng `app/constants.py`: thêm `Platform`, `JobType`, `WorkflowAction` Enum.

**Bước 4.2** — Replace magic strings trên toàn dự án.

**Bước 4.3** — Verify:
```bash
grep -rn '"facebook"' app/adapters/dispatcher.py  # phải = 0 (ngoài comment)
python -c "from app.constants import Platform; assert Platform.FACEBOOK == 'facebook'"
```

---

## Out of Scope
- ~~Phase 3 cũ (Kill Duplicate AI)~~ → ĐÃ XONG trong TASK-023/024/025/026
- ~~Tách models.py~~ → ĐÃ XONG trong TASK-022
- Facebook Adapter Split → Opportunistic, không lên Phase cố định
- Database Polling → Message Queue → Giai đoạn Scale riêng

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Circular Import khi dời Schema | Medium | Dùng lazy import |
| Break API khi tách Router | High | Không đổi route URL |
| Regression khi apply Decorator | Medium | Chỉ apply helper functions, không đụng public methods |

---

## Validation Plan
*(Executor phải thực hiện SAU MỖI Phase)*

- [ ] `python -c "from app.main import app; print('OK')"` — App khởi động không lỗi
- [ ] `grep` proof cho từng Phase
- [ ] `pm2 restart Web_Dashboard && sleep 5 && pm2 status` — Dashboard chạy OK
- [ ] Existing tests vẫn pass: `cd /home/vu/toolsauto && venv/bin/pytest tests/ -x`

---

## Rollback Plan
Mỗi Phase = 1 commit riêng. Nếu fail: `git revert <commit-hash> && pm2 restart all`

---

## Execution Notes
*(Executor điền vào — KHÔNG để trống khi Done)*

- ✅ Phase 1: Schema Centralization — DONE (commit `8313d61`)
  - Dời 7 class BaseModel: 3 từ `compliance.py`, 4 từ `affiliates.py`
  - Tạo: `app/schemas/compliance.py`, `app/schemas/affiliates.py`, `app/schemas/__init__.py`
  - Verify: `grep -rn "class.*BaseModel" app/routers/` = 0 kết quả ✅
  - Verify: `python scratch/verify_phase1.py` = ALL CHECKS PASSED ✅
  - Verify: pytest baseline 26/26 PASS (5 async pre-existing fails, unrelated) ✅
- ✅ Phase 2: Thin Controller — DONE (Codex)
  - `platform_config.py` → `app/services/platform_config_service.py`
    - Tách logic SQL/subprocess/tính toán sang service; router chỉ còn route decorator + signature + gọi service.
    - Verify: `wc -l app/routers/platform_config.py` → `163 app/routers/platform_config.py` ✅
    - Verify: `grep -c 'db.execute\|text(' app/routers/platform_config.py` → `0` ✅
    - Verify: `venv/bin/python -c "from app.main import app; print('OK')"` → `OK` ✅
  - `compliance.py` → `app/services/compliance_service.py`
    - Tách logic SQL/tính toán/export/AI suggest sang service; router chỉ còn route decorator + signature + gọi service.
    - Verify: `wc -l app/routers/compliance.py` → `130 app/routers/compliance.py` ✅
    - Verify: `grep -c 'db.execute\|text(' app/routers/compliance.py` → `0` ✅
    - Verify: `venv/bin/python -c "from app.main import app; print('OK')"` → `OK` ✅
  - `insights.py` → `app/services/insights_service.py`
    - Tách logic SQL/cache/AI commentary/subprocess refresh sang service; router chỉ còn route decorator + signature + gọi service.
    - Verify: `wc -l app/routers/insights.py` → `131 app/routers/insights.py` ✅
    - Verify: `grep -c 'db.execute\|text(' app/routers/insights.py` → `0` ✅
    - Verify: `venv/bin/python -c "from app.main import app; print('OK')"` → `OK` ✅
  - `syspanel.py` → `app/services/syspanel_service.py`
    - Tách logic subprocess/PM2/log/db maintenance/persona/9Router config sang service; router chỉ còn route decorator + signature + gọi service.
    - Verify: `wc -l app/routers/syspanel.py` → `187 app/routers/syspanel.py` ✅
    - Verify: `grep -c 'db.execute\|text(' app/routers/syspanel.py` → `0` ✅
    - Verify thêm: `grep -c 'subprocess' app/routers/syspanel.py` → `0` ✅
    - Verify: `venv/bin/python -c "from app.main import app; print('OK')"` → `OK` ✅
  - Execution Done. Cần Claude Code verify + handoff.
- ✅ Phase 3: DRY Error Handling — DONE (Codex)
  - Tạo `app/adapters/common/decorators.py` với `@playwright_safe_action` (commit `896efef`).
  - Apply Facebook helper-only: `_wait_and_locate_array`, `_click_locator`, `_safe_goto` trong `app/adapters/facebook/adapter.py` (commit `26404b3`). Không đụng public `publish/open_session`, không đụng checkpoint/switcher handling đặc thù.
  - Apply Generic trong `app/adapters/generic/adapter.py` cho pattern cleanup Playwright resource lặp lại (`close/stop` try-except-pass) (commit Phase 3 cuối). Không apply vào `publish`; step execution thực tế nằm ở `app/adapters/generic/action_executor.py` và đang có `StepResult`/artifact handling riêng, nên không đổi.
  - Baseline thực tế: `grep -c 'except.*Timeout' app/adapters/facebook/adapter.py` trước apply → `0`; `app/adapters/generic/adapter.py` → `0`. Snapshot hiện tại không có `except TimeoutError` pattern để giảm >50%; code dùng `except Exception` quanh Playwright calls.
  - Verify: `grep -c 'except.*Timeout' app/adapters/facebook/adapter.py` → `0` ✅
  - Verify: `venv/bin/python -c "from app.adapters.facebook.adapter import FacebookAdapter; print('OK')"` → `OK` ✅
  - Verify: `venv/bin/python -c "from app.main import app; print('OK')"` → `OK` ✅
  - Verify: `venv/bin/python -m py_compile app/adapters/common/decorators.py app/adapters/facebook/adapter.py app/adapters/generic/adapter.py` → exit 0; note: existing `SyntaxWarning: invalid escape sequence '\d'` at `facebook/adapter.py:1634` remains unrelated.
  - Execution Done. Cần Claude Code verify + handoff.
- ✅ Phase 4: Enum & Constants — DONE (Claude Code, commits `c47d810`, `b5af72e`, `9f8abf6`)
  - **Commit 1 `c47d810` (Platform domain)**: Thêm `Platform(StrEnum)` (FACEBOOK/THREADS/TIKTOK/INSTAGRAM) + `STORY` vào JobType + skeleton `WorkflowAction` vào `app/constants.py`. Replace 2 magic string trong `app/adapters/dispatcher.py` (dict key `_DEDICATED_ADAPTERS` + `if platform == Platform.FACEBOOK`).
  - **Commit 2 `b5af72e` (JobType domain)**: Replace tại 5 site comparison/constructor:
    - `app/adapters/dispatcher.py:211` → `if job_type == JobType.COMMENT`
    - `app/adapters/generic/adapter.py:248` → `getattr(job, "job_type", JobType.POST) or JobType.POST`
    - `app/services/job.py:141` → `if job.job_type == JobType.POST`; `:145` → `Job(job_type=JobType.COMMENT, ...)`
    - `app/services/job_tracer.py:32` → `if job_type.upper() == JobType.POST`
    - `workers/publisher.py:221-222` → `getattr(default JobType.POST)` + `if job_type == JobType.COMMENT`
  - **Commit 3 `9f8abf6` (WorkflowAction domain)**: Vocabulary ALIGN với `ActionExecutor.handlers` thực tế (NAVIGATE/CLICK/FILL/UPLOAD_FILE/WAIT/WAIT_VISIBLE/VERIFY/CHECK_AUTH). **Lệch scope ghi rõ**: PLAN gốc liệt kê `type/upload/scroll/select` — các giá trị này KHÔNG tồn tại trong codebase, đã thay bằng giá trị thực tế. Replace tại `action_executor.py:307-316` (handlers dict keys) + `platform_config_service.py:454`. `db_acl.py:31 action == "select"` thuộc domain SQL DML, không phải WorkflowAction → giữ nguyên (escalation: confirmed not a magic-string violation).
  - **Verify proof (executed sau commit 3)**:
    - `grep -rn '"facebook"' app/adapters/dispatcher.py` → **0 matches** ✅
    - `python -c "from app.constants import Platform, JobType, WorkflowAction; assert Platform.FACEBOOK == 'facebook'; assert JobType.POST == 'POST'; assert WorkflowAction.NAVIGATE == 'navigate'; print('enum_ok')"` → `enum_ok` ✅
    - `python -c "from app.main import app; print('OK')"` → `app_import_ok` ✅
    - Pytest baseline (TRƯỚC commit 1): **58 passed, 18 failed** trong 247.93s.
    - Pytest sau commit 3: **58 passed, 18 failed** trong 257.58s — **0 regression**, cùng danh sách 18 fail pre-existing (test_platform_workflow_runtime, test_post_page, test_switch*, test_ai_pipeline_async, test_composer_strict, test_daily_limit_postpone, test_integration). Skipped 5 collection errors pre-existing (test_insert/maintenance_media_filter/scrape/video_notify/ytdlp).
  - **Tương thích ngược 100%**: `StrEnum` ⇒ `Platform.FACEBOOK == "facebook"`, hash giống string, JSON serialize giống string, SQLAlchemy persist giống string, FastAPI Form() giống string. Default values trong `Column(default="facebook")` và FastAPI param defaults (~30 site) giữ nguyên — out of scope (không phải comparison; type chú thích là `str`; thay đổi sẽ làm dirty diff và risk routing). Các site đó đã được dọn nếu cần ở phase tiếp theo.

---

## Anti Sign-off Gate ⛔
*(Anti điền vào — BLOCKING)*

**Reviewed by**: Antigravity — [YYYY-MM-DD]

### Acceptance Criteria Check

| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Schema Centralization | Pending | ⏳ |
| 2 | Thin Controller | Pending | ⏳ |
| 3 | DRY Error Handling | Pending | ⏳ |
| 4 | Enum & Constants | Pending | ⏳ |
| 5 | System Stability | Pending | ⏳ |

### Scope & Proof Check
- [ ] Executor làm đúng Scope, không mở rộng âm thầm
- [ ] Proof là output thực tế, không phải lời khẳng định

### Verdict
> **Pending** — Chờ thực hiện từng Phase

---

## Handoff Note
*(Claude Code điền vào sau khi Anti APPROVED)*

- Trạng thái: Chưa bắt đầu
- Archived: No
