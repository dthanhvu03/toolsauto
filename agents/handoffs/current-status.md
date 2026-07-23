# Current Status

## System State

- Local: **http://127.0.0.1:8002**
- **PLAN-040 platform silos:** Done (sidebar + dispatch + hooks)
- **Frontend silo UX (c6f0f19 + polish session):** Done — breadcrumb silo, accounts `?platform=`, jobs/insights/threads polish, sidebar insights active rule

## Done This Session [2026-07-23]

### Platform silo UX polish (hoàn thiện sau c6f0f19)

1. **Breadcrumb DRY** (`fragments/silo_breadcrumb.html` + `page_breadcrumb` trong `layouts/app.html`): Facebook/Threads/Chung trên viral, tiktok-links, insights, compliance, threads, jobs, accounts.
2. **Accounts** (`app_accounts_split.html`, `accounts/router.py`): Chip lọc nền tảng + `?platform=`; empty state; badge platform trên list item.
3. **Sidebar** (`app.html`): Insights active chỉ khi `platform=facebook` (mặc định); focus-visible nav/chip trong `cave-tokens.css`.
4. **Jobs** (`app_jobs.html`, `jobs_table.html`): Empty state theo nền tảng; aria-pressed chip; tiêu đề VI.
5. **Insights** (`insights.html`): Tiêu đề/subtitle/badge wrap mobile; copy Phân tích & boost.
6. **Threads** (`app_threads.html`): Workspace cockpit + breadcrumb + subtitle VI.
7. **Viral / TikTok links / Compliance**: Breadcrumb + tiêu đề rõ silo Facebook.

**Smoke (venv):** `venv\Scripts\python.exe -c "import app.main"` → **ok**

## Next Action

1. Owner F5: `/app/accounts?platform=facebook`, `/app/jobs?platform=threads`, `/insights?platform=facebook`, `/threads`, breadcrumb trên các trang silo.
2. Optional: commit perf N+1 batch (tách khỏi silos).
