# Feature: threads

Tin tức → AI caption → job Threads → Playwright publish.

| Entry | Path |
|-------|------|
| HTTP | `router.py`, dashboard helpers in `dashboard.py` |
| Adapter | `adapter.py` |
| Business | `service/` (`news_scraper`, `threads_news`, `article_scorer`, `topic_key`) |
| Workers (PM2) | `workers/publisher.py`, `news_worker.py`, `auto_reply.py`, `verifier.py` |

Depends on: `app.core.queue`, `app.core.ai`, `app.adapters.dispatcher` / contracts.

## Growth — kéo khách về bot (PLAN-158, ADR-066)

`growth/`: quét Threads theo từ khóa → AI viết reply A/B → tự đăng bài đủ điểm / chờ duyệt.
Web `/app/go/threads-growth` (API `growth/router.py`), Telegram `/keokhach` + nút `gr:*`, worker PM2 `Threads_Growth`
(`growth/worker.py`, chạy tay một vòng: `python -m app.features.threads.growth.worker --once`). Cấu hình `growth.*` ở
/app/settings. Dữ liệu: `data/threads_growth.sqlite`. Tài khoản `threads_growth` (profile `instagram_5`).
