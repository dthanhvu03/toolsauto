# TASK-037 — Refactor sang feature-based architecture

**Status**: Phase 3 Step 23 viral_intake code/static-smoke done; Claude Code / Anti review pending
**Plan**: [PLAN-037](../../plans/active/PLAN-037-feature-based-module-refactor.md)
**ADR**: [ADR-007](../../decisions/ADR-007-module-boundary.md)
**Executor**: Codex (heavy file-move + import update)
**Verifier**: Claude Code (per-phase smoke + handoff)

> **Gate**: PLAN-037 Status = Approved (Anti sign-off 2026-05-03). Codex MAY execute Phase 1.

## Background

Codebase hiện tổ chức theo technical layer (`adapters/`, `services/`, `routers/`, `workers/`). Mỗi feature bị xé ra rải vào 4-5 thư mục → onboarding chậm, khó delete feature, cross-feature coupling ngầm. Anh Vu yêu cầu refactor sang feature-based để mỗi feature self-contained.

Repo size: 30K LOC, 12 service subdir, 5 adapter platform, 19 router, 8 worker.

## Steps (5 phases — mỗi phase 1 PR + Anti review)

### Phase 0 — ADR module boundary ✅
1. [x] Anti / Claude Code viết `agents/decisions/ADR-007-module-boundary.md`.
2. [x] Chốt danh sách core / features / platform — **7 core + 9 features + 3 platform** (3 điều chỉnh từ bản đề xuất sơ bộ: compliance → FB feature, db_admin added, notifier source corrected).
3. [x] Định nghĩa import rule: `features/foo/` chỉ được import `core/*`, KHÔNG import `features/bar/`.
4. [x] Anti sign-off ADR-007.

### Phase 1 — Carve out `app/core/` ✅
5. [x] Move `app/database/` → `app/core/database/` — commit `ef64c50`. 92 files / 174+/174-.
6. [x] Move `app/services/observability/` → `app/core/observability/` — commit `225f83c`. 25 files / 40+/34-.
7. [x] Move `app/services/ai/` → `app/core/ai/` — commit `cd0f60a`. 9 files / 8+/7-.
8. [x] Move `app/services/jobs/` → `app/core/queue/` — commit `df7a5d9`. 7 files / 6+/5-.
9. [x] Smoke after each move: py_compile PASS, app import → ROUTES 207, alembic heads → a8e7f6d5c4b3, pytest 77/11 (= baseline; 1 test test_incident_logger fixed by Move B).
   - Shim `app/services/__init__.py` mở rộng: `_ALIASES` value support absolute path (`app.core.X`); `create_module()` detect prefix → import absolute hoặc relative.
   - Local untracked tests/ có 11 broken imports pre-existing (trỏ tới `app.core.observability.X` không tồn tại) — out of scope Phase 1, không fix.

### Phase 2 — Pilot Threads feature
10. [x] Tạo `app/features/threads/` skeleton (adapter, service/, dashboard, router, workers/) — commit `894d18b`.
11. [x] Move 4 worker entry threads_*.py → `app/features/threads/workers/` — commit `eea48e3`. Worker shim không giữ lại theo Phase 2 execution prompt; `ecosystem.config.js` updated for 3 existing PM2 Threads entries.
12. [x] Move adapter + 4 service file (news_scraper, threads_news, topic_key, article_scorer) — commits `ab9101e`, `f715fee`.
13. [x] Move dashboard + router — commits `6f71310`, `44f0fba`.
14. [x] Update `ecosystem.config.js` script paths — commit `eea48e3` (`Threads_AutoReply`, `Threads_NewsWorker`, `Threads_Publisher`; no existing verifier PM2 entry in file).
15. [x] Smoke: pytest threads PASS, `pm2 restart Threads_Publisher` OK. Static/local smoke PASS (`py_compile`, routes 207, 24/24 Threads tests, collection 77/11); PM2 restart not run to avoid live worker side effects.
16. [ ] VPS deploy + 24h monitor → 1 threads publish thành công. Pending controlled deploy/runtime proof.

### Phase 3 — Carve remaining features (theo thứ tự rủi ro)
17. [x] `instagram` (low risk) — code commit `2fee8f6`.
18. [x] `tiktok` (low risk) — code commit `d4514f6`.
19. [x] `affiliates` (medium) — code commit `f564c54`.
20. [x] `system_panel` + `workflow_registry` (medium) — code commit `498569e`. (Anti Verdict B: Follow-up move workflow_registry to core/)
21. [x] `insights` (medium) — code commit `29c087c`.
22. [x] `telegram_bot` (medium — shared notifier) — notifier core commit `66c9826`, telegram bot commit `f3bbb64`.
23. [x] `viral_intake` (high — orchestrator 651 dòng) — code/static-smoke done in the Step 23 refactor commit.
24. [ ] `facebook_publisher` (highest — adapter 6500 dòng + engagement + compliance).

### Phase 4 — Cleanup orchestrator
25. [ ] Tách `app/services/content/orchestrator.py` thành `viral_intake/orchestrator.py` (generic) + `facebook_publisher/reup_pipeline.py` (FB-specific).
26. [ ] Verify smoke + 24h monitor.

### Phase 5 — Lint guard
27. [ ] Add `import-linter` config + pytest plugin chặn cross-feature import.
28. [ ] CI fail nếu vi phạm.
29. [ ] Update `agents/RULES.md` + `CLAUDE.md` với module boundary rule.

### Closing
30. [ ] Codex update PLAN/TASK status sau mỗi phase commit.
31. [ ] Claude Code verify per-phase + update handoff.
32. [ ] Anti final sign-off sau Phase 5 → archive.

## Files Touched (estimate)

- ~50-80 file move (`git mv`).
- ~200-400 import statement update (sed batch).
- 1 ADR mới.
- `ecosystem.config.js` 1 lần.
- `agents/RULES.md` + `CLAUDE.md` 1 lần.
- `.importlinter.ini` + 1 pytest plugin (Phase 5).

## Out of Scope

- Đổi business logic / SQL.
- Frontend `templates/` + `static/` reorg.
- Database schema change.
- Multi-tenant feature loading.
- Tách worker process (`ecosystem.config.js` giữ list worker).

## Acceptance Trace (Anti per-phase)

Sau mỗi phase commit, Anti chấm theo PLAN-037 §"Acceptance Criteria" (`AC2` smoke, `AC3` pm2 online, `AC4` live publish post-Phase 2 + post-Phase 3, `AC5` lint guard, `AC6` rollback test, `AC7` doc updates).

## Phase 3 Step 17 — Instagram Execution Notes

**Executed by**: Codex — 2026-05-04
**Status**: COMPLETED
**Code commit**: `2fee8f6` — `refactor(P037-Phase3): move instagram to app/features/instagram/ (no behavior change)`

### Scope completed

- Moved `app/adapters/instagram/adapter.py` → `app/features/instagram/adapter.py`.
- Moved `app/adapters/instagram/selectors.py` → `app/features/instagram/selectors.py`.
- Added empty `app/features/instagram/__init__.py`.
- Removed `app/adapters/instagram/` after clearing generated `__pycache__`; source path verified gone.
- Updated in-module selector import to `app.features.instagram.selectors`.
- Updated allowed collateral A: `app/templates/pages/platform_config.html` `KNOWN_ADAPTERS["instagram"]`.
- Updated allowed collateral B: Alembic migration `b4c8f0e9d3a1_p037_p3_instagram_adapter_path.py`.

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

$ git diff --cached --find-renames --stat
6 files changed, 36 insertions(+), 2 deletions(-)
```

### Risk Log

- Local DB has been advanced to Alembic revision `b4c8f0e9d3a1`.
- PM2/VPS runtime proof was not run for Instagram because this step only moves adapter/config path and does not add a worker.
- Pytest collection remained at the Phase 2 baseline (`77/11`); the 11 collection errors are pre-existing and not in new Instagram files.

## Phase 3 Step 18 — Tiktok Execution Notes

**Executed by**: Codex — 2026-05-04
**Status**: COMPLETED (code/static-smoke); Anti review pending
**Code commit**: `d4514f6` — `refactor(P037-Phase3): move tiktok to app/features/tiktok/ (no behavior change)`

### Scope completed

- Moved `app/adapters/tiktok/adapter.py` → `app/features/tiktok/adapter.py`.
- Moved `app/adapters/tiktok/selectors.py` → `app/features/tiktok/selectors.py`.
- Added empty `app/features/tiktok/__init__.py`.
- Removed `app/adapters/tiktok/` after clearing generated `__pycache__`; source path verified gone.
- Updated in-module selector import to `app.features.tiktok.selectors`.
- Updated allowed collateral A: `app/templates/pages/platform_config.html` tiktok placeholder + `KNOWN_ADAPTERS["tiktok"]`.
- Updated allowed collateral B: Alembic migration `c7d9e1f2a3b4_p037_p3_tiktok_adapter_path.py`.
- Updated allowed collateral C: `app/adapters/dispatcher.py` `Platform.TIKTOK` fallback because `Platform.TIKTOK` exists.

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

$ git diff --cached --find-renames --stat
6 files changed, 34 insertions(+), 3 deletions(-)
```

### Risk Log

- Local DB has been advanced to Alembic revision `c7d9e1f2a3b4`.
- PM2/VPS runtime proof was not run for Tiktok because this step only moves adapter/config path and does not add a worker.
- Pytest collection remained at the Phase 2/Step 17 baseline (`77/11`); the 11 collection errors are pre-existing and not in new Tiktok files.
- Stop before Step 19 (`affiliates`) pending Anti per-feature review.

## Phase 3 Step 22 — Telegram Bot + Notifier Execution Notes

**Executed by**: Codex — 2026-05-04
**Status**: COMPLETED (code/static-smoke); Anti review pending
**Code commits**:
- `66c9826` — `refactor(P037-Phase3): move notifier → app/core/notifier/ (no behavior change)`
- `f3bbb64` — `refactor(P037-Phase3): move telegram bot → app/features/telegram_bot/ (no behavior change)`

### Scope completed

- Moved `app/services/telegram/notifier/` → `app/core/notifier/`.
- Updated notifier callsites from `app.services.notifier_service` to `app.core.notifier.service`.
- Updated notifier shim aliases to `app.core.notifier.*`.
- Moved Telegram bot files from `app/services/telegram/` + `app/routers/telegram.py` → `app/features/telegram_bot/`.
- Removed `app/services/telegram/` and `app/routers/telegram.py`.
- Updated Telegram bot shim aliases to `app.features.telegram_bot.*`.
- Updated `app/main.py` router registration to import Telegram router from feature path.

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

### Risk Log

- Static/local smoke only; no PM2 restart or VPS live publish proof in this step.
- `TelegramNotifier` now resolves `TelegramClient` through `app.features.telegram_bot.client`, matching the requested file placement while preserving behavior.
- Do not proceed to Step 23 (`viral_intake`) until Anti per-feature review is complete.

## Phase 3 Step 23 — Viral Intake Execution Notes

**Executed by**: Codex — 2026-05-04
**Status**: COMPLETED (code/static-smoke); Anti review pending
**Code commit**: Step 23 refactor commit (`refactor(P037-Phase3): move viral_intake to app/features/viral_intake/ (no behavior change)`)

### Scope completed

- Added empty `app/features/viral_intake/__init__.py`.
- Moved `app/services/viral/discovery_scraper.py` → `app/features/viral_intake/discovery_scraper.py`.
- Moved `app/services/viral/processor.py` → `app/features/viral_intake/processor.py`.
- Moved `app/services/viral/reup_processor.py` → `app/features/viral_intake/reup_processor.py`.
- Moved `app/services/viral/scan.py` → `app/features/viral_intake/scan.py`.
- Moved `app/services/viral/service.py` → `app/features/viral_intake/service.py`.
- Moved `app/services/viral/strategic.py` → `app/features/viral_intake/strategic.py`.
- Moved `app/services/viral/tiktok_scraper.py` → `app/features/viral_intake/tiktok_scraper.py`.
- Moved `app/routers/viral.py` → `app/features/viral_intake/router.py`.
- Removed old `app/services/viral/` and `app/routers/viral.py`.
- Updated direct imports in `app/main.py`, `app/services/dashboard/dashboard_service.py`, `app/features/insights/service.py`, `workers/maintenance.py`, `manage.py`, and moved viral intake modules.
- Updated 7 `app/services/__init__.py` shim aliases to `app.features.viral_intake.*`.
- Did not touch `app/services/content/orchestrator.py` or other Phase 4-reserved content files.

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

### Risk Log

- Static/local smoke only; no PM2 restart or VPS runtime proof in this step.
- Maintenance worker import smoke passed, reducing immediate production crash risk after deploy, but live worker restart/monitor is still required.
- `app/services/content/orchestrator.py` remains unmoved for Phase 4.
- Do not proceed to Step 24 (`facebook_publisher`) until Anti per-feature review is complete.

## Risks (xem chi tiết PLAN-037 §"Risks")

- Import path explosion → batch sed.
- Production downtime → deploy lúc thấp tải, restart từng worker.
- Hidden circular import → Phase 1 verify trước.
- workers/ path change phá cron script → giữ shim 1 sprint.
- Codex bypass Anti gate (như PLAN-036) → Anti theo dõi commit log mỗi ngày.
- Refactor scope creep → ENFORCE "không đổi behavior".

## Estimate

10-14 ngày work nếu Codex full-time + Anti review 24h cho mỗi phase. Có thể chia làm 2 sprint:
- Sprint 1 (5-7 ngày): Phase 0 + Phase 1 + Phase 2 (pilot Threads).
- Sprint 2 (5-7 ngày): Phase 3 + Phase 4 + Phase 5.
