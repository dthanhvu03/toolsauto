# PLAN-037 — Refactor sang feature-based architecture

**Status**: Phase 3 Step 24 facebook_publisher done. Phase 3 COMPLETED. Ready for Phase 5 (Lint Guard).
**ADR**: [ADR-007-module-boundary](../../decisions/ADR-007-module-boundary.md)
**Owner**: Antigravity (architectural decision) — Codex execute — Claude Code verify
**Related task**: [TASK-037](../../tasks/active/TASK-037-feature-based-module-refactor.md)

> **Gate**: KHÔNG execute trước khi Status = Approved (Anti sign-off). Vi phạm process này sẽ bị reject post-hoc.

## Problem

Codebase hiện tổ chức theo **technical layer** (`adapters/` × platform, `services/` × concern, `routers/` × URL prefix, `workers/` × process). Mỗi feature bị xé ra rải vào 4-5 layer khác nhau.

**Ví dụ Threads pipeline cần đụng 7 file ở 5 thư mục**:
- `app/adapters/threads/adapter.py`
- `app/services/content/threads_news.py` + `topic_key.py` + `article_scorer.py`
- `app/services/dashboard/threads_service.py`
- `app/routers/threads.py`
- `workers/threads_publisher.py` + `threads_news_worker.py` + `threads_auto_reply.py` + `threads_verifier.py`

**Hậu quả**:
- Onboarding chậm: muốn hiểu 1 feature phải nhảy 4-5 thư mục.
- Khó delete cả feature (phải xoá rải rác, dễ sót).
- Cross-feature coupling ngầm (vd `services/content/orchestrator.py` 651 dòng trộn FB viral + Threads).
- Khó test isolated.
- File trộn nhiều platform khó tìm: `services/content/` chứa cả `news_scraper.py` (Threads) lẫn `media_processor.py` (FB) lẫn `video_protector.py` (cross-platform).

**Repo size**: 30K LOC, 12 service subdirs, 5 adapter platforms, 19 router files, 8 worker files.

## Goal

Định nghĩa rõ 3 lớp:
1. **`app/core/`** — base modules dùng chung (DB, queue, notifier, settings, observability, scheduling). Không biết gì về platform/feature.
2. **`app/features/<name>/`** — mỗi feature 1 thư mục self-contained (adapter + service + router + worker entry).
3. **`app/platform/`** (optional) — cross-feature platform glue (auth, dashboard shell, telegram bot core).

Mỗi feature owns: adapter, service logic, router, worker entry, templates riêng. Có thể delete cả feature bằng `rm -rf app/features/<name>/` + xoá registration trong `app/main.py` + xoá worker entry trong `ecosystem.config.js`.

**KHÔNG đổi behavior**, chỉ đổi cấu trúc thư mục + import path. Toàn bộ test + smoke check phải PASS sau mỗi phase.

## Scope

### Phân loại chốt (ADR-007 là authoritative — xem chi tiết trong ADR)

> **⚠️ 3 điều chỉnh từ bản đề xuất sơ bộ (Anti review 2026-05-03)**:
> 1. `compliance/` → KHÔNG vào core. Toàn bộ vào `features/facebook_publisher/compliance/` (FBComplianceChecker = FB-specific, chưa có consumer thứ 2).
> 2. Thêm `core/db_admin/` ← `services/db/` (ACL, sql_validator, database_service) — cross-feature shared infra.
> 3. `core/notifier/` source chính xác là `services/telegram/notifier/` (notifiers/ directory thực tế rỗng).

**Core** (không biết feature):
- `app/core/database/` ← `app/database/`
- `app/core/queue/` ← `app/services/jobs/`
- `app/core/notifier/` ← `app/services/notifier_service.py` + `app/services/telegram/` (phần generic broadcast)
- `app/core/settings/` ← `app/services/platform/settings.py` + `app/config.py`
- `app/core/observability/` ← `app/services/observability/`
- `app/core/compliance/` ← `app/services/compliance/` (rule engine generic, FB-specific tách ra feature)
- `app/core/ai/` ← `app/services/ai/` (Brain factory + Gemini client generic)

**Features** (self-contained):
- `app/features/facebook_publisher/` — adapter + viral processor + reup + worker `publisher.py`
- `app/features/threads_publisher/` — adapter + threads_news + scorer + topic_key + worker `threads_publisher.py` + `threads_news_worker.py` + `threads_auto_reply.py` + `threads_verifier.py`
- `app/features/instagram/` — adapter + worker (currently minimal)
- `app/features/tiktok/` — adapter (no publish worker; chỉ dùng cho viral discovery)
- `app/features/viral_intake/` — orchestrator + discovery + scan + tiktok_scraper (cross-platform reup pipeline; có thể tách FB-specific reup ra)
- `app/features/insights/` — insights_service + router + dashboard
- `app/features/affiliates/` — affiliate_ai + affiliate_service + router
- `app/features/telegram_bot/` — command_handler + event_router + poller (separate from notifier core)
- `app/features/system_panel/` — syspanel_service + workflow_registry + manage routes

**Platform / shell** (cross-feature):
- `app/platform/auth/` ← `app/routers/auth.py` + login/session
- `app/platform/dashboard_shell/` — main dashboard chrome (cross-feature)
- `app/platform/health/` ← `app/routers/health.py`

### Out of scope (Phase 1)

- Đổi business logic / SQL.
- Tách worker process (`ecosystem.config.js` giữ nguyên list worker).
- Frontend asset reorg (`app/templates/` + `static/` để Phase sau).
- Database schema change.
- Multi-tenant module loading.

## Approach (5 phases incremental)

### Phase 0 — Spec + ADR (1 ngày)

1. Anti / Claude Code viết **ADR-007 — Module boundary**: chốt danh sách core / feature / platform, naming convention, import rule (vd `features/foo/` chỉ được import `core/*`, KHÔNG được import `features/bar/`).
2. Tạo file `agents/decisions/ADR-007-module-boundary.md`.
3. Anti sign-off ADR-007 trước khi phase tiếp.

### Phase 1 — Carve out `app/core/` (skeleton, tooling-friendly)

Move "obvious shared" modules — semantic không đổi, chỉ rename + update import:

| From | To | Files | LOC ước tính |
|---|---|---|---|
| `app/database/` | `app/core/database/` | ~15 file | ~3000 |
| `app/services/jobs/` | `app/core/queue/` | 6 file | ~1450 |
| `app/services/observability/` | `app/core/observability/` | 9 file | ~1500 |
| `app/services/ai/` | `app/core/ai/` | 7 file | ~2000 |

**Verify mỗi move**: `from app.main import app` PASS, `pytest -q` PASS, `pm2 restart` smoke.

**Risk**: ~50-100 import path cập nhật. Codex dùng `git grep -l "from app.database"` + sed batch.

### Phase 2 — Pilot 1 feature: Threads (1-2 ngày)

Threads tách clean nhất (đã isolated platform-wise):

```
app/features/threads/
├── adapter.py            ← app/adapters/threads/adapter.py
├── service/
│   ├── news_scraper.py   ← app/services/content/news_scraper.py
│   ├── threads_news.py   ← app/services/content/threads_news.py
│   ├── topic_key.py      ← app/services/content/topic_key.py
│   └── article_scorer.py ← app/services/content/article_scorer.py
├── dashboard.py          ← app/services/dashboard/threads_service.py
├── router.py             ← app/routers/threads.py
└── workers/
    ├── publisher.py      ← workers/threads_publisher.py
    ├── news_worker.py    ← workers/threads_news_worker.py
    ├── auto_reply.py     ← workers/threads_auto_reply.py
    └── verifier.py       ← workers/threads_verifier.py
```

`workers/` ở project root → đổi `ecosystem.config.js` script path: `app/features/threads/workers/publisher.py` (cần venv shebang + sys.path init giữ nguyên).

**Verify**: pytest `tests/test_threads_world_news.py` + `tests/test_article_scorer.py` 24/24 PASS; `pm2 restart Threads_Publisher` chạy không lỗi import.

**Risk**: Threads dùng `core/queue` + `core/notifier` + `core/ai` cross-cutting → phải làm sau Phase 1.

### Phase 3 — Carve out các feature còn lại (3-5 ngày)

Theo thứ tự độ rủi ro tăng dần:

1. `instagram` (gần như empty)
2. `tiktok` (read-only viral discovery)
3. `affiliates` (isolated module)
4. `system_panel` + `workflow_registry`
5. `insights` (đụng dashboard service)
6. `telegram_bot` (shared notifier với core)
7. `viral_intake` (heavy — orchestrator 651 dòng, đụng FB + cross-platform)
8. `facebook_publisher` (heaviest — adapter 6500 dòng, engagement, page mismatch, compliance)

Mỗi feature 1 PR riêng, mỗi PR Anti review + Claude Code verify.

### Phase 4 — Cleanup `app/services/content/orchestrator.py` (1 ngày)

651 dòng trộn FB viral reup + cross-platform. Tách:
- `app/features/viral_intake/orchestrator.py` — phần generic (scan, pick, dispatch).
- `app/features/facebook_publisher/reup_pipeline.py` — phần FB-specific (compliance, page binding, compose).

### Phase 5 — Lint guard (1 ngày)

Thêm import-linter rule (`importlinter`) hoặc custom pytest:
- `features/foo/` KHÔNG được `from app.features.bar import ...`.
- `core/*` KHÔNG được `from app.features.* import ...`.
- Vi phạm → CI fail.

File: `.importlinter.ini` + `pytest_plugins/import_boundary.py`.

## Acceptance Criteria

1. [x] **ADR-007 module boundary** committed + Anti sign-off. (Phase 0 — 2026-05-03)
2. [ ] Mỗi phase end-state: `from app.main import app` PASS (route count không đổi 207 ± routes thật sự thêm), `pytest -q` PASS (24 test threads + ~18 test ai/services baseline).
3. [ ] `pm2 list` sau mỗi worker move: 5 worker (FB_Publisher_1/2, AI_Generator_1/2, Threads_Publisher, Maintenance, Threads_News_Scraper, AI_Reporter) đều `online` ≥ 5 phút không restart loop.
4. [ ] Live smoke (post-Phase 2 + post-Phase 3): 1 FB job + 1 Threads job publish thành công trên VPS sau move (so với baseline 24h trước).
5. [ ] Lint guard (Phase 5) chặn được vi phạm cross-feature import.
6. [x] Rollback plan: mỗi phase = 1 commit độc lập, có thể `git revert` trong vòng 5 phút nếu phát sinh issue production.
7. [ ] Updated `agents/RULES.md` + CLAUDE.md với module boundary rule.

## Risks

- **Import path explosion**: ~30K LOC, vài trăm import statement. Mitigation: dùng `git grep -l` + sed batch + IDE refactor; mỗi move 1 commit nhỏ; verify import sau mỗi move.
- **Production downtime trong khi pull develop + restart pm2**: 30s-2min. Mitigation: deploy lúc thấp tải (~03:00 sáng), `pm2 restart` từng worker thay vì batch.
- **Hidden circular import** sau khi move (vd `core/queue` import `notifier_service` import `core/queue`). Mitigation: Phase 1 carve core trước → kiểm tra `python -c "import app"` không warning.
- **`workers/` path change phá script chạy thẳng** (vd cron `python workers/publisher.py`). Mitigation: giữ shim `workers/publisher.py` import từ `app/features/.../workers/publisher.py` 1 thời gian (1 sprint), sau đó xoá.
- **Codex bypass Anti gate** (như PLAN-036): PLAN-037 dài → Codex có thể tự execute. Gate đã bổ sung vào template; Anti theo dõi commit log thường xuyên.
- **Refactor scope creep**: kèm theo logic cleanup. Mitigation: PLAN-037 ENFORCE "không đổi behavior" — nếu Codex thấy bug trong khi move, mở task riêng, KHÔNG fix tại chỗ.
- **Test coverage gap** ở các feature chưa có test (Insights, Compliance, FB engagement). Mitigation: pre-Phase smoke = manual `curl` + UI click → ghi proof vào TASK.

## Verify Plan

```bash
# Per phase
cd /home/vu/toolsauto && \
  venv/bin/python -c "from app.main import app; print(len(app.routes))" && \
  venv/bin/python -m py_compile $(find app -name "*.py") && \
  venv/bin/pytest tests/ -q --ignore=tests/test_facebook_engagement.py

# Per worker move
pm2 restart <worker> && pm2 logs <worker> --lines 100 | grep -E "ERROR|Traceback"

# Boundary lint (Phase 5)
venv/bin/lint-imports
```

## Deploy Strategy

- **Mỗi phase 1 PR riêng** lên develop → merge sau Anti sign-off.
- **VPS deploy mỗi phase end**: pull develop → `pm2 restart <affected workers>` → monitor 24h → next phase.
- **Rollback**: `git revert <phase-merge-commit>` + pull develop + `pm2 restart`. Test rollback path 1 lần ở Phase 1 để confirm.
- **Total estimate**: 10-14 ngày work nếu Codex full-time + Anti review trong 24h.

## Out of scope follow-ups (mở plan riêng nếu cần)

- Frontend `templates/` + `static/` reorg theo feature.
- Multi-tenant feature loading (vd disable `viral_intake` qua config).
- Module-level test coverage gap.
- `ecosystem.config.js` → `pm2.config.ts` cho type safety.

---

## Anti Sign-off Gate

**Reviewed by**: Antigravity — 2026-05-03

### Review Summary

1. **Module boundary (ADR-007)**: APPROVED. 7 core + 9 features + 3 platform. 3 adjustments from original proposal applied (compliance → FB feature, db_admin added, notifier source corrected).
2. **5-phase approach**: APPROVED. Incremental migration with per-phase PR + verify is the right strategy for 30K LOC codebase.
3. **Estimate 10-14 ngày**: REASONABLE. 2 sprint split (Phase 0-2 / Phase 3-5) is correct cadence.
4. **ADR-007**: WRITTEN and committed as Phase 0 deliverable.
5. **Risk mitigations**: Adequate — re-export shim (ADR-005) stays during migration, worker shim 1 sprint, per-phase rollback via git revert.

### Acceptance Criteria Pre-check

| # | Criterion | Pre-approved? |
|---|---|---|
| AC1 | ADR-007 committed + Anti sign-off | ✅ Done |
| AC2 | Per-phase smoke (routes + pytest + pm2) | ✅ Criteria clear |
| AC3 | pm2 worker online ≥5min | ✅ Criteria clear |
| AC4 | Live smoke (post-Phase 2 + 3) | ✅ Criteria clear |
| AC5 | Lint guard (Phase 5) | ✅ Criteria clear |
| AC6 | Rollback plan (per-phase commit) | ✅ Criteria clear |
| AC7 | Updated RULES.md + CLAUDE.md | ✅ Criteria clear |

### Verdict

> **APPROVED** — Codex có thể bắt đầu execute Phase 1 (carve `app/core/`). Mỗi phase end phải có PR + Anti review trước khi tiến phase tiếp.
>
> **Ordering**: Phase 1 bắt đầu với `database/` → `queue/` → `observability/` → `ai/` → `settings/` → `notifier/` → `db_admin/`. ADR-007 là tài liệu gốc cho module boundary — khi có conflict giữa PLAN và ADR, ADR thắng.

---

## Phase 1 Sign-off

**Reviewed by**: Antigravity — 2026-05-03T14:27+07:00
**Verdict**: **B — APPROVED with follow-up**

### Independent Verification Results

| Gate | Expected | Actual | Status |
|------|----------|--------|--------|
| \rom app.main import app\ → routes | 207 | 207 | ✅ |
| \lembic heads\ | \8e7f6d5c4b3 (head)\ | \8e7f6d5c4b3 (head)\ | ✅ |
| \pytest tests/ -q --co\ | 77 collected, 11 errors | 77 collected, 11 errors | ✅ |
| Legacy import \pp.services.gemini_api\ | Resolves | ✅ \pp.core.ai.gemini_api\ | ✅ |
| Legacy import \pp.services.job_queue\ | Resolves | ✅ \pp.core.queue.queue\ | ✅ |
| Legacy import \pp.services.incident_logger\ | Resolves | ✅ \pp.core.observability.incident_logger\ | ✅ |
| Old directories removed | Deleted | Deleted | ✅ |
| No force-push | Normal push | Normal push | ✅ |
| No business logic changes | Import-only diffs | Import-only diffs | ✅ |

### Commit Review

All 4 commits inspected — **pure file move + import path update**, zero behavior changes.

- \ef64c50\ Move A: 92 files, 174+/174- — database move + direct callsite sed
- \225f83c\ Move B: 25 files, 40+/34- — observability move + shim create_module() upgrade
- \cd0f60a\ Move C: 9 files, 8+/7- — ai move + shim alias (0 direct callsites)
- \df7a5d9\ Move D: 7 files, 6+/5- — queue move + shim alias (0 direct callsites)

### Follow-up

- **TASK-038**: Fix 11 broken local test files (pre-existing, out of scope Phase 1). Should be done before Phase 5 lint guard.

### Phase 2 Gate

> **Phase 1 APPROVED. Phase 2 (pilot Threads feature) is CLEARED.**
>
> Codex or Claude Code may execute TASK-037 steps 10–16.

---

## Phase 2 Execution Notes

**Executed by**: Codex — 2026-05-03
**Status**: Code/static-smoke done. PM2/VPS runtime proof pending.

### Commits

- `894d18b` — Step A skeleton `app/features/threads/{,service,workers}/__init__.py`.
- `ab9101e` — Step B adapter moved to `app/features/threads/adapter.py`.
- `f715fee` — Step C service files moved to `app/features/threads/service/`.
- `6f71310` — Step D dashboard service moved to `app/features/threads/dashboard.py`.
- `44f0fba` — Step E router moved to `app/features/threads/router.py` and `app/main.py` import updated.
- `eea48e3` — Step F worker entries moved to `app/features/threads/workers/`; existing PM2 Threads script paths updated.

### Verification Proof

```text
$ find app -name '*.py' | xargs venv/bin/python -m py_compile
PASS (pre-existing app/adapters/facebook/adapter.py SyntaxWarning only)

$ venv/bin/python -c "from app.main import app; print('ROUTES', len(app.routes))"
ROUTES 207

$ venv/bin/pytest tests/test_threads_world_news.py tests/test_article_scorer.py -q
24 passed in 1.79s

$ venv/bin/pytest tests/ -q --ignore=tests/test_facebook_engagement.py --co
77 tests collected, 11 errors

$ venv/bin/python -c "import app.features.threads.workers.publisher, app.features.threads.workers.news_worker, app.features.threads.workers.auto_reply, app.features.threads.workers.verifier; print('THREADS_WORKER_IMPORT_OK')"
THREADS_WORKER_IMPORT_OK
```

### Runtime Gap

- PM2 restart was not run in local execution to avoid live worker side effects.
- `ecosystem.config.js` had existing entries for `Threads_AutoReply`, `Threads_NewsWorker`, and `Threads_Publisher`; all three script paths now point to `app/features/threads/workers/*`.
- No existing verifier PM2 entry was present in `ecosystem.config.js`; Codex did not add a new process because that would change runtime behavior.

Execution Done. Cần Claude Code verify + handoff.

---

## Phase 2 Sign-off

**Reviewed by**: Antigravity — 2026-05-04
**Verdict**: **A — APPROVED Phase 2 → mở Phase 3**

### Independent Verification Results

| Gate | Expected | Actual | Status |
|------|----------|--------|--------|
| \rom app.main import app\ → routes | 207 | 207 | ✅ |
| \pytest tests/test_threads_world_news.py ...\ | 24 passed | 24 passed | ✅ |
| \pytest tests/ -q --co\ | 77 collected, 11 errors | 77 collected, 11 errors | ✅ |
| Legacy alias \app.services.threads_news\ | Resolves | ✅ \app.features.threads.service.threads_news\ | ✅ |
| \app/services/content/\ remaining files | 4 non-Threads files | 4 non-Threads files | ✅ |
| Directory structure \app/features/threads/\ | 11 logic files + \__init__.py\ | 11 logic files + \__init__.py\ | ✅ |
| \ecosystem.config.js\ worker paths | 3 updated paths | 3 updated paths | ✅ |
| ADR-007 Import Rules | No cross-feature imports | 0 cross-feature imports | ✅ |

### Commit Review

All 6 commits inspected — **pure file move + import path update**, zero behavior changes.
- \894d18b\ Step A: skeleton.
- \ab9101e\ Step B: adapter move.
- \f715fee\ Step C: service files move.
- \6f71310\ Step D: dashboard move.
- \44f0fba\ Step E: router move.
- \eea48e3\ Step F: workers move.

### Phase 3 Gate

> **Phase 2 APPROVED. Phase 3 (carve remaining features) is CLEARED.**
>
> Codex (hoặc Claude Code) execute Phase 3 theo TASK-037 step 17–24: 8 feature theo thứ tự rủi ro tăng dần (instagram → tiktok → affiliates → system_panel → insights → telegram_bot → viral_intake → facebook_publisher). Mỗi feature 1 PR riêng.

---

## Phase 3: Step 17 (Instagram) Sign-off

**Reviewed by**: Antigravity — 2026-05-04
**Verdict**: **A — APPROVED Step 17 → mở Step 18 (tiktok)**

- **Collaterals Verified**: `app/templates/pages/platform_config.html` (KNOWN_ADAPTERS dict updated), `app/adapters/dispatcher.py` (import path updated), `alembic/versions/b4c8f0e9d3a1_...` (DB adapter_class updated).
- **Smoke Gates**: `py_compile`, `ROUTES 207`, `pytest 77/11`, `alembic head`, and `python import` all passed cleanly.
- **Pattern Note**: This exact collateral pattern (Template update + Alembic DB update + Dispatcher fallback) WILL REPEAT for **tiktok** (Step 18) and **facebook_publisher** (Step 24). Both have `KNOWN_ADAPTERS` entries in the template and DB rows pointing to their adapter paths. Codex is pre-authorized to apply these 3 collateral changes in those steps.

---

## Phase 3: Step 18 (TikTok) Sign-off

**Reviewed by**: Antigravity — 2026-05-04
**Verdict**: **A — APPROVED Step 18 → mở Step 19 (affiliates)**

- **Collaterals Verified**: `app/templates/pages/platform_config.html` lines 354 and 720 updated, `alembic/versions/c7d9e1f2a3b4...` DB migration created, `app/adapters/dispatcher.py` `Platform.TIKTOK` fallback correctly added.
- **Smoke Gates**: `py_compile`, `ROUTES 207`, `pytest 77/11`, `alembic head`, and `python import` all passed cleanly. ADR-007 module boundaries respected (0 cross-feature imports).
- **Next Step Note**: Step 19 (affiliates) is a medium risk component and DOES NOT use the collateral pattern from Steps 17/18.

---

## Phase 3: Step 19 (Affiliates) Sign-off

**Reviewed by**: Antigravity — 2026-05-04
**Verdict**: **A — APPROVED Step 19 → mở Step 20 (system_panel + workflow_registry)**

- **Scope Verified**: `app/features/affiliates/` created with `ai.py`, `service.py`, `router.py`, and `__init__.py`. Replaced the previous ones in `app/services/compliance/` and `app/routers/affiliates.py`.
- **Imports & Shims**: Verified updates in `app/main.py`, `app/routers/manual_job.py`, `app/routers/pages.py`, and `workers/ai_generator.py`. Shim aliases `affiliate_ai` and `affiliate_service` correctly mapped. No DB migrations (Alembic at `c7d9e1f2a3b4`).
- **Smoke Gates**: `py_compile`, `ROUTES 207`, `pytest 77/11`, `AFF_OK`, `AFF_AI_OK`, `AFF_ROUTER_OK`, `SHIM_OK`. ADR-007 module boundaries respected.
- **Process Review**: The missing `__init__.py` was caught and fixed in a fast-follow chore commit. Confirmed that future step executions involving `git mv` and new directories must `git add -A` to track `__init__.py` files properly.

---

## Phase 3 Instagram Execution Notes

**Executed by**: Codex — 2026-05-04
**Status**: Step 17 code/static-smoke done. Claude Code / Anti per-feature review pending.
**Code commit**: `2fee8f6` — `refactor(P037-Phase3): move instagram to app/features/instagram/ (no behavior change)`

### Changes

- `app/adapters/instagram/adapter.py` → `app/features/instagram/adapter.py`.
- `app/adapters/instagram/selectors.py` → `app/features/instagram/selectors.py`.
- Added empty `app/features/instagram/__init__.py`.
- Removed old `app/adapters/instagram/` source directory.
- Updated Instagram selector import path only; no business logic edits.
- Collateral A: updated `app/templates/pages/platform_config.html` `KNOWN_ADAPTERS["instagram"]`.
- Collateral B: added Alembic data migration `b4c8f0e9d3a1_p037_p3_instagram_adapter_path.py`.
- Collateral C: added dispatcher `Platform.INSTAGRAM` fallback to `InstagramAdapter`.

### Verification Proof

```text
$ find app -name '*.py' | xargs venv/bin/python -m py_compile && echo PY_COMPILE_OK
PY_COMPILE_OK
app/adapters/facebook/adapter.py:1630: SyntaxWarning: invalid escape sequence '\d'
  return self.page.evaluate("""

$ venv/bin/python - <<'PY'
from app.main import app
print("ROUTES", len(app.routes))
PY
ROUTES 207

$ venv/bin/pytest tests/ -q --ignore=tests/test_facebook_engagement.py --co
77 tests collected, 11 errors in 74.29s (0:01:14)

$ venv/bin/python - <<'PY'
from app.features.instagram.adapter import InstagramAdapter
print("IG_OK")
PY
IG_OK

$ venv/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade a8e7f6d5c4b3 -> b4c8f0e9d3a1, P037 Phase 3: update platform_configs.adapter_class for instagram

$ venv/bin/python - <<'PY'
from app.core.database.core import SessionLocal
from sqlalchemy import text
db = SessionLocal()
r = db.execute(text("SELECT adapter_class FROM platform_configs WHERE platform='instagram'")).scalar()
assert r == 'app.features.instagram.adapter.InstagramAdapter', r
print('DB_MIGRATION_OK', r)
db.close()
PY
DB_MIGRATION_OK app.features.instagram.adapter.InstagramAdapter
```

### Risk / Pending

- Local DB alembic_version is now `b4c8f0e9d3a1`; VPS must run `venv/bin/alembic upgrade head` during deploy.
- No PM2 restart was run locally; Instagram has no dedicated worker in this step.
- Do not proceed to Step 18 (`tiktok`) until per-feature review is complete.

---

## Phase 3 Tiktok Execution Notes

**Executed by**: Codex — 2026-05-04
**Status**: Step 18 code/static-smoke done. Claude Code / Anti per-feature review pending.
**Code commit**: `d4514f6` — `refactor(P037-Phase3): move tiktok to app/features/tiktok/ (no behavior change)`

### Changes

- `app/adapters/tiktok/adapter.py` → `app/features/tiktok/adapter.py`.
- `app/adapters/tiktok/selectors.py` → `app/features/tiktok/selectors.py`.
- Added empty `app/features/tiktok/__init__.py`.
- Removed old `app/adapters/tiktok/` source directory after clearing generated `__pycache__`; source path verified gone.
- Updated Tiktok selector import path only; no business logic edits.
- Collateral A: updated `app/templates/pages/platform_config.html` tiktok placeholder and `KNOWN_ADAPTERS["tiktok"]`.
- Collateral B: added Alembic data migration `c7d9e1f2a3b4_p037_p3_tiktok_adapter_path.py`.
- Collateral C: added dispatcher `Platform.TIKTOK` fallback to `TiktokAdapter` because `Platform.TIKTOK` exists.

### Verification Proof

```text
$ bash smoke.sh
ROUTES:  207
IMPORT OK
app/adapters/facebook/adapter.py:1630: SyntaxWarning: invalid escape sequence '\d'
  return self.page.evaluate("""

$ find app -name '*.py' -print0 | xargs -0 venv/bin/python -m py_compile
PY_COMPILE_OK
app/adapters/facebook/adapter.py:1630: SyntaxWarning: invalid escape sequence '\d'
  return self.page.evaluate("""

$ venv/bin/python -c "from app.main import app; print('ROUTES', len(app.routes))"
ROUTES 207

$ venv/bin/pytest tests/ -q --ignore=tests/test_facebook_engagement.py --co
77 tests collected, 11 errors in 74.44s (0:01:14)

$ venv/bin/python -c "from app.features.tiktok.adapter import TiktokAdapter; print('TT_OK')"
TT_OK

$ venv/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade b4c8f0e9d3a1 -> c7d9e1f2a3b4, P037 Phase 3: update platform_configs.adapter_class for tiktok

$ venv/bin/python - <<'PY'
from app.core.database.core import SessionLocal
from sqlalchemy import text
db = SessionLocal()
r = db.execute(text("SELECT adapter_class FROM platform_configs WHERE platform='tiktok'")).scalar()
assert r == 'app.features.tiktok.adapter.TiktokAdapter', r
print('DB_MIGRATION_OK', r)
db.close()
PY
DB_MIGRATION_OK app.features.tiktok.adapter.TiktokAdapter

$ venv/bin/alembic heads
c7d9e1f2a3b4 (head)

$ git diff --cached --find-renames --stat
6 files changed, 34 insertions(+), 3 deletions(-)
```

### Risk / Pending

- Local DB alembic_version is now `c7d9e1f2a3b4`.
- PM2/VPS runtime proof was not run for Tiktok because this step only moves adapter/config path and does not add a worker.
- Pytest collection remained at the Phase 2/Step 17 baseline (`77/11`); the 11 collection errors are pre-existing and not in new Tiktok files.
- Do not proceed to Step 19 (`affiliates`) until per-feature review is complete.

Execution Done. Cần Claude Code verify + handoff.

---

## Phase 3 Step 22 Execution Notes

**Executed by**: Codex — 2026-05-04
**Status**: Step 22 code/static-smoke done. Claude Code / Anti per-feature review pending.
**Code commits**:
- `66c9826` — `refactor(P037-Phase3): move notifier → app/core/notifier/ (no behavior change)`
- `f3bbb64` — `refactor(P037-Phase3): move telegram bot → app/features/telegram_bot/ (no behavior change)`

### Changes

- `app/services/telegram/notifier/` → `app/core/notifier/`.
- `app/services/telegram/{client,command_handler,event_router,poller,service}.py` → `app/features/telegram_bot/`.
- `app/routers/telegram.py` → `app/features/telegram_bot/router.py`.
- Removed `app/services/telegram/` after notifier and bot files were moved.
- Updated `app/services/__init__.py` aliases for notifier and Telegram bot compatibility.
- Updated direct notifier and Telegram callsites, including workers and `app.features.threads.workers.publisher`.

### Verification Proof

```text
$ find app -name '*.py' | xargs venv/bin/python -m py_compile && echo PY_COMPILE_OK
PY_COMPILE_OK
app/adapters/facebook/adapter.py:1630: SyntaxWarning: invalid escape sequence '\d'

$ venv/bin/python -c "from app.main import app; print('ROUTES', len(app.routes))"
ROUTES 207

$ venv/bin/pytest tests/ -q --ignore=tests/test_facebook_engagement.py --co
77 tests collected, 11 errors in 74.71s (baseline match)

$ venv/bin/python -c "from app.core.notifier.service import NotifierService, TelegramNotifier; print('NOTIFIER_OK')"
NOTIFIER_OK

$ venv/bin/python -c "from app.services.notifier_service import NotifierService; print('NOTIFIER_SHIM_OK')"
NOTIFIER_SHIM_OK

$ venv/bin/python -c "import workers.publisher; print('WORKER_PUBLISHER_OK')"
WORKER_PUBLISHER_OK

$ venv/bin/python -c "import workers.ai_generator; print('WORKER_AI_GENERATOR_OK')"
WORKER_AI_GENERATOR_OK

$ venv/bin/python -c "import workers.maintenance; print('WORKER_MAINTENANCE_OK')"
WORKER_MAINTENANCE_OK

$ venv/bin/python -c "from app.features.telegram_bot.service import TelegramService; print('TG_OK')"
TG_OK

$ venv/bin/python -c "from app.features.telegram_bot.router import router; print('TG_ROUTER_OK', len(router.routes))"
TG_ROUTER_OK 1

$ venv/bin/python -c "from app.services.telegram_service import TelegramService; print('TG_SHIM_OK')"
TG_SHIM_OK

$ venv/bin/python -c "from app.features.threads.workers.publisher import *; print('THREADS_PUBLISHER_IMPORT_OK')"
THREADS_PUBLISHER_IMPORT_OK

$ bash smoke.sh
ROUTES:  207
IMPORT OK
```

### Risk / Pending

- PM2/VPS runtime proof was not run locally for this no-behavior-change move.
- `TelegramNotifier` uses `app.features.telegram_bot.client.TelegramClient` after the requested `client.py` feature move.
- Stop before Step 23 (`viral_intake`) pending Anti per-feature review.

---

## Phase 3 Step 23 Execution Notes

**Executed by**: Codex — 2026-05-04
**Status**: Step 23 code/static-smoke done. Claude Code / Anti per-feature review pending.
**Code commit**: Step 23 refactor commit (`refactor(P037-Phase3): move viral_intake to app/features/viral_intake/ (no behavior change)`)

### Changes

- Added empty `app/features/viral_intake/__init__.py`.
- Moved 7 modules from `app/services/viral/` into `app/features/viral_intake/`: `discovery_scraper.py`, `processor.py`, `reup_processor.py`, `scan.py`, `service.py`, `strategic.py`, `tiktok_scraper.py`.
- Moved `app/routers/viral.py` → `app/features/viral_intake/router.py`.
- Removed old `app/services/viral/` and `app/routers/viral.py`.
- Updated direct imports in the moved modules plus `app/main.py`, `app/services/dashboard/dashboard_service.py`, `app/features/insights/service.py`, `workers/maintenance.py`, and `manage.py`.
- Updated `app/services/__init__.py` aliases for `discovery_scraper`, `tiktok_scraper`, `viral_processor`, `viral_scan`, `viral_service`, `reup_processor`, and `strategic`.
- Did not touch `app/services/content/orchestrator.py`; Phase 4 remains reserved for orchestrator split.

### Verification Proof

```text
$ find app -name '*.py' -print0 | xargs -0 venv/bin/python -m py_compile && echo PY_COMPILE_OK
PY_COMPILE_OK
app/adapters/facebook/adapter.py:1630: SyntaxWarning: invalid escape sequence '\d'

$ venv/bin/python -c "from app.main import app; print('ROUTES', len(app.routes))"
ROUTES 207

$ venv/bin/pytest tests/ -q --ignore=tests/test_facebook_engagement.py --co
77 tests collected, 11 errors in 76.31s (0:01:16)

$ venv/bin/python -c "from app.features.viral_intake.processor import ViralProcessorService; print('VP_OK')"
VP_OK
$ venv/bin/python -c "from app.features.viral_intake.scan import run_tiktok_competitor_scan; print('VS_OK')"
VS_OK
$ venv/bin/python -c "from app.features.viral_intake.discovery_scraper import DiscoveryScraper; print('DS_OK')"
DS_OK
$ venv/bin/python -c "from app.features.viral_intake.strategic import PageStrategicService; print('STR_OK')"
STR_OK
$ venv/bin/python -c "from app.features.viral_intake.service import ViralService; print('VSVC_OK')"
VSVC_OK
$ venv/bin/python -c "from app.features.viral_intake.tiktok_scraper import *; print('TS_OK')"
TS_OK
$ venv/bin/python -c "from app.features.viral_intake.reup_processor import *; print('REUP_OK')"
REUP_OK
$ venv/bin/python -c "from app.features.viral_intake.router import router; print('VIRAL_ROUTER_OK', len(router.routes))"
VIRAL_ROUTER_OK 4

$ venv/bin/python -c "from app.services.viral_processor import ViralProcessorService; print('VP_SHIM_OK')"
VP_SHIM_OK
$ venv/bin/python -c "from app.services.viral_scan import run_tiktok_competitor_scan; print('VS_SHIM_OK')"
VS_SHIM_OK
$ venv/bin/python -c "from app.services.discovery_scraper import DiscoveryScraper; print('DS_SHIM_OK')"
DS_SHIM_OK
$ venv/bin/python -c "from app.services.strategic import PageStrategicService; print('STR_SHIM_OK')"
STR_SHIM_OK

$ venv/bin/python -c "import workers.maintenance; print('MAINT_IMPORT_OK')"
MAINT_IMPORT_OK
$ venv/bin/python -c "import workers.publisher; print('PUB_IMPORT_OK')"
PUB_IMPORT_OK
$ venv/bin/python -c "import manage; print('MANAGE_IMPORT_OK')"
MANAGE_IMPORT_OK
$ venv/bin/python -c "from app.features.insights.service import *; print('INS_VIRAL_INTEGRATION_OK')"
INS_VIRAL_INTEGRATION_OK
```

### Risk / Pending

- PM2/VPS runtime proof was not run locally for this no-behavior-change move.
- Maintenance worker import smoke passed (`MAINT_IMPORT_OK`), but deploy still needs controlled restart/monitor.
- `app/services/content/orchestrator.py` remains reserved for Phase 4 and was not edited.
- Stop before Step 24 (`facebook_publisher`) pending Anti per-feature review.

Execution Done. Cần Claude Code verify + handoff.
