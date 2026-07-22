# Feature: system_panel

Admin ops: PM2, logs, metrics, platform config, AI studio, maintenance tick.

| Entry | Path |
|-------|------|
| HTTP | `router.py`, `config_router.py`, `worker_router.py`, `ai_studio_router.py` |
| Logic | `service.py`, `ai_studio_service.py` |
| Workers (PM2) | `workers/maintenance.py`, `workers/ai_reporter.py` |

Destructive UI actions gated by `SYSPANEL_DESTRUCTIVE_ENABLED`. Depends on: `app.core.*`.
