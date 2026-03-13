# Implementation tasks (Agent checklist)

## Phase 1 — Core infra
- [ ] Setup FastAPI app skeleton + Jinja2 templates
- [ ] Setup Tailwind via CDN
- [ ] Setup HTMX in base.html
- [ ] Setup SQLAlchemy models + Alembic migrations
- [ ] Implement JobQueue service:
      - enqueue
      - fetch_due
      - lock_job (atomic)
      - mark_done/failed/reschedule

## Phase 2 — UI pages
- [ ] /dashboard (stats)
- [ ] /jobs list + filters
- [ ] HTMX partials for jobs table + row
- [ ] job actions:
      - retry
      - reschedule
      - edit caption
- [ ] /content upload + inbox
- [ ] /accounts CRUD minimal

## Phase 3 — Worker
- [ ] worker loop tick + batch
- [ ] account checks (active, daily_limit, cooldown)
- [ ] retry backoff
- [ ] logging + job_events

## Phase 4 — Adapter layer
- [ ] BaseAdapter + Dispatcher
- [ ] FB adapter scaffolding:
      - persistent context
      - step-based flow
      - fallback selectors framework
      - artifacts on failure

## Phase 5 — QA & hardening
- [ ] Add tests for DB operations and state transitions
- [ ] Add smoke test script for worker loop
- [ ] Add "dry-run" mode to validate pipeline without publishing

## Definition of Done
- UI tạo job -> worker chạy -> status đổi -> log đầy đủ
- Fail -> retry/backoff -> cuối cùng FAILED có artifacts