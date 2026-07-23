# Feature: viral_intake

Thu thập / bảo vệ video viral → tạo DRAFT/PENDING job (chủ yếu feed Facebook).

**Silo:** TikTok **source** (scrapers) → Facebook **sink** (jobs/pages). UI nav grouped under sidebar “Facebook”.

| Entry | Path |
|-------|------|
| HTTP | `router.py` |
| Logic | `processor.py`, `service.py`, `scan.py`, `discovery_scraper.py`, `tiktok_scraper.py`, `reup_processor.py`, `video_protector.py` |
| Workers (PM2) | `workers/ai_generator.py` |

Depends on: `app.core.queue`, `app.core.orchestrator`, `app.core.ai`.
