# Feature: threads

Tin tức → AI caption → job Threads → Playwright publish.

| Entry | Path |
|-------|------|
| HTTP | `router.py`, dashboard helpers in `dashboard.py` |
| Adapter | `adapter.py` |
| Business | `service/` (`news_scraper`, `threads_news`, `article_scorer`, `topic_key`) |
| Workers (PM2) | `workers/publisher.py`, `news_worker.py`, `auto_reply.py`, `verifier.py` |

Depends on: `app.core.queue`, `app.core.ai`, `app.adapters.dispatcher` / contracts.
