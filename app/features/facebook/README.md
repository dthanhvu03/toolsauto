# Feature: facebook

Đăng Reels/post Facebook qua Playwright, pages UI, media prep, engagement.

| Entry | Path |
|-------|------|
| HTTP | `pages_router.py`, `manual_job_router.py` |
| Adapter | `adapter.py`, `selectors.py`, `engagement.py` |
| Media | `media_processor.py`, `pages/`, `core/session.py` |
| Workers (PM2) | `workers/publisher.py` (`FB_Publisher_1/2`) |

Flat layout (không bắt buộc `service/`). Depends on: `app.core.queue`, `app.core.compliance`, `app.adapters.*`.

**Strategic boost / page growth:** implemented in `app.core.strategic.PageStrategicService` (FB-owned; shared via core for Insights + viral_intake).
