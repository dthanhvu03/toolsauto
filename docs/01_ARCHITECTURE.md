# Architecture: FastAPI + HTMX + Workers (PM2)

> Tree map cho người mới: **[TREE.md](TREE.md)**. Module boundary: **[ADR-007](../agents/decisions/ADR-007-module-boundary.md)**.

## Core components

1. **FastAPI app (dashboard & API)** — `app/main.py`
   - Jinja2 + Tailwind + HTMX
   - Cookie session auth (`platform/auth`)
   - Routers gắn từ `platform/*`, `features/*/router.py`, `core/*/router.py`

2. **Database** — PostgreSQL + SQLAlchemy (`app/core/database/`)
   - Alembic migrations ở `alembic/`
   - Bảng chính: `accounts`, `jobs`, `job_events`, `news_articles`, insights/compliance, …

3. **Job queue** — `app/core/queue/`
   - Atomic `claim_next_job` (per-platform cooldown + fair-share + per-platform mutex)
   - Crash recovery, tracer, cleanup

4. **Workers (PM2)** — entry trong `app/features/*/workers/`
   - `FB_Publisher_*`, `Threads_Publisher`, `AI_Generator_*`, `Maintenance`, …
   - Config: `ecosystem.config.js` + `start.sh`

5. **Adapters** — shared layer `app/adapters/`
   - `dispatcher.py` chọn adapter theo `job.platform`
   - Platform-specific adapters sống trong `features/<platform>/adapter.py`
   - `contracts.py` + `common/` (session, locator, decorators)

6. **AI** — `app/core/ai/` (pipeline, Gemini API/RPA, fallback)
   - Viral / DRAFT generation: `features/viral_intake/`

## Process model

- Web: uvicorn (`Web_Dashboard`)
- Workers: PM2 processes độc lập (không còn single `worker.py` 24/7)
- Prefer `pm2 restart <name>` sau deploy Python (không dùng `reload` cho module cache)

## Layout rules

Xem [TREE.md](TREE.md). Không thêm module mới vào package legacy `app.services` (đã xóa).
