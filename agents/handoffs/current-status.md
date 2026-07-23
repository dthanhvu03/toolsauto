# Current Status

## System State

- Local: **http://127.0.0.1:8002**
- **PLAN-040 platform silos:** Done (sidebar + dispatch + hooks)
- **Audit 20691a61 — frontend silo UX (3 bước):** Done this session (overview shortcuts, jobs `?platform=`, insights FB chrome)

## Done This Session [2026-07-23]

### Frontend silo UX (audit 20691a61)

1. **Overview** (`app_overview.html`): Gỡ panel Threads News; lối tắt tách **Chung** / **Facebook**; link sang `/threads`.
2. **Jobs** (`app_jobs.html`, `jobs_table.html`, `JobService.get_jobs_paged`, `jobs/router.py`): Chip/filter nền tảng + deep-link `?platform=`; sidebar **Hàng đợi Threads** → `/app/jobs?platform=threads`; Insights nav → `?platform=facebook`.
3. **Insights** (`insights.html`): Badge/subtitle Facebook, đổi Universal → Tất cả nền tảng, nhấn mạnh panel strategic khi Facebook, init từ query.

**Smoke (venv):** `venv\Scripts\python.exe -c "import app.main"` → **ok**

## Next Action

1. Owner: xác nhận overview shortcuts + jobs platform filter + insights badge trên browser.
2. Optional: commit perf N+1 batch (tách khỏi silos).
