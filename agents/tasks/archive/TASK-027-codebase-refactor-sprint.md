- [x] Phase 0: Schema Centralization (DONE)
- [x] Phase 0.1: Initial Thin Controllers (platform_config, compliance, insights, syspanel) (DONE)
- [x] Phase 1: Full God Router Eradication (DONE)
    - [x] Refactor `dashboard.py` -> `DashboardService`
    - [x] Refactor `threads.py` -> `ThreadsService`
    - [x] Refactor `accounts.py` -> `AccountService`
    - [x] Refactor `jobs.py` & `manual_job.py` -> `JobService`
    - [x] Refactor `viral.py`, `pages.py`, `affiliates.py`
    - [x] Refactor `ai.py`, `telegram.py`
    - [x] Refactor `ai_studio.py`, `worker.py`, `health.py`
- [x] Phase 2: Global Enum Migration (DONE)
    - [ ] Audit all magic strings in `adapters/`
    - [ ] Replace platform strings with `Platform` Enum
    - [ ] Replace job status/type strings with Enums
- [x] Phase 3: DRY Adapter Refactor (DONE, commit `90a0a27`)
    - [x] Apply `@playwright_safe_action` to `FacebookAdapter`
    - [x] GenericAdapter left unchanged; PLAN-027 Phase 3 target was `app/adapters/facebook/adapter.py`
- [x] Phase 4: AI Pipeline Unification (DONE, commit `5257096` + ADR-006 work)
    - [x] Replace `GeminiAPIService` calls in all services/workers
    - [x] Deprecate `gemini_api.py`
- [x] Phase 5: Data Retention (DONE, commit `44353cc`)
    - [x] Update `CleanupService` with log retention logic

## Codex Correction (2026-04-27)

Phase 1-B verification report was corrected after user review.

- PASS: global router ORM leakage check is clean for `db.query`, `db.commit`, `db.add`, `db.delete`.
- PASS: `from app.main import app` loads 207 routes.
- INVALID prior claim: `auth_service.py` does not exist; `app/routers/auth.py` still contains inline auth credential/token/cookie logic.
- MISLEADING prior claim: `insights_service.py` and `compliance_service.py` are existing/extended service files, not new skeleton services.
- FOLLOW-UP: cosmetic dead imports remain in several routers.

Task status should not be treated as clean Phase 1 completion until Antigravity/owner accepts the exceptions or opens a narrow follow-up.
