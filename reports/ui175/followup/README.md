# PLAN-175 follow-up: executive overview and customer pagination

Owner requested pagination and an overview suitable for COO/CEO, beyond Buffer. Implemented read-only executive sources for Cashback, Store, Studio and Threads, growth per bot, service status, and a separate Buffer section. Financial figures retain each source's period and definition; no combined revenue is inferred. Missing sources show unavailable rather than zero. Scheduled DB backup being stopped is excluded from the online denominator.

Bot users now returns 25 people per page (maximum 100); summary-only responses contain no individual rows. Search/bot changes reset the current page. Cashback customers uses 50 per page, clamps the requested page, and preserves filters through relative query links so a reverse proxy cannot introduce an internal host/scheme.

Primary-list inventory: Jobs, video warehouse, Logs, compliance keywords and DocType records already have pagination. This change adds the missing customer lists; it does not claim every list is now paginated. Both customer backends still aggregate the full source before slicing the response; database-level pagination is not implemented here.

## Verification observed 2026-11-17

```text
.venv/bin/python -m pytest -q tests/test_bot_users.py tests/test_cashback_insights.py tests/test_executive_overview.py tests/test_admin_api_lists.py
41 passed; first run 60.48s, final run 10.68s

# After changing Cashback links to relative query URLs:
.venv/bin/python -m pytest -q tests/test_cashback_insights.py
28 passed, 14 warnings in 7.12s

cd frontend && npm run build -- --outDir /tmp/toolsauto-ceo-ui-dist
tsc --noEmit: PASS; 1871 modules transformed; built in 7.36s
JS 597.64 kB (gzip 176.92 kB); existing >500 kB warning remains

.venv/bin/python reports/ui175/followup/check.py
PASS: widths 320/390/768/1440; next page 2; search resets page;
summary-only requested; Buffer failure isolated; missing bot unavailable;
scheduled backup not alerted / denominator 1/1; page_errors=[]

env PYTHONPATH=. .venv/bin/python reports/ui175/followup/live_check.py
PASS: login=200; core routes /health, /app, Cashback, executive, processes,
summary-only all 200; normal bot page returned 25/25; Cashback page 50/50;
all four executive sources available; eight SPA route/viewport checks without
overflow; page_errors=[]; blocked_requests=[]; Web_Dashboard online, restarts=5;
authenticated tailnet login and executive API 200, TLS verified
```

Ruff checks passed for changed Python source/tests and live proof script; `git -c core.autocrlf=false diff --check` passed. Warnings remain for the existing Starlette TemplateResponse signature and an unawaited coroutine in the SQL admin test. The first verification attempts through Windows could not execute the Linux tools correctly; the results above come from Ubuntu, not those attempts.

Tests use real fixture schemas, assert read-only Store connections reject DELETE, no missing DB is created, configured admin purchases are excluded, sources fail independently, and customer pagination retains filters. Runtime smoke performs only authenticated login and read-only GETs; it saves no customer data, credentials, session cookies or screenshots.

## Deployment

Owner previously authorized deployment and commit/push for this UI program. Backup `/tmp/toolsauto-ceo-ui-backup-20261117-followup` contains 11 verified files. Staging contains 9 files. Assets copied first, manifest updated, index replaced atomically; the temporary index was confirmed absent and destination matched. Old assets retained for open tabs.

```text
index SHA-256: 16d9e82ec86189b7bc2ce32cb2a540ba88351cf86e77d426137ed45c2c735b3b
JS SHA-256: 00bd5a97c43e4c36c41749ccd0642fe6fc6e7c26bdb75765c71514fc645b37ad
```

Restarted only `Web_Dashboard` to load the new Python route, restart count 4 -> 5; other PM2 processes were left running. Authenticated `/api/admin/executive` returned 200 with `errors=[]`. Detailed sanitized runtime output is in `live-proof.json`. Rollback: restore the previous static index/manifest from the backup and revert only this follow-up's Python changes, then restart only Web_Dashboard; do not reset the branch or unrelated audit patches.

## Review and remaining acceptance

Read-only self-review follows `C:/Users/Admin/.codex/skills/.system/review-agent/SKILL.md`: No findings. This is not independent sign-off. The review led to correcting the scheduled-backup denominator and using relative Cashback page links before the final checks.

Xe Tết operational metrics are not connected. There is no consolidated revenue KPI or comparable-period growth trend. Physical phone/iOS Safari and independent Claude/Antigravity acceptance remain pending. This is an executive-dashboard increment, not a claim of complete COO/CEO coverage or a clean whole-repository audit.

Execution Done. Cần Claude Code verify + handoff.
