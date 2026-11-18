# PLAN-175 executive analytics — implementation proof

User approved implementation on 2026-11-18 after requesting charts, Store product rankings, and money visibility. Owner authorized deploy, commit, push and dashboard restart on 2026-11-18. Static bundle is deployed and code commit 28f6b1f is pushed to origin/feat/xe-tet. Web_Dashboard was restarted and authenticated live checks passed. No schema/data change, vendor call or message is part of this release.

## What the overview shows

- Store and Cashback stay separate. Select 7 or 30 Vietnam calendar days including the current, potentially incomplete day. Store keeps its existing cashflow definitions; Cashback summary and trend now share the same start. This explicitly changes Cashback's previous rolling-7-day summary to a calendar period, with a visible label and period boundaries.
- Store: delivered orders, revenue after refunds, recorded cost, external expenses and net after those expenses. Top 5 by delivered units and top 5 by gross profit are ranked over all sold products, with quantity/revenue/gross profit on each row and configured admins excluded.
- Store chart uses daily 7-day buckets or existing rolling seven-day buckets for 30 days, sorted oldest to newest. Product gross profit does not allocate external expenses. Missing recorded cost is treated as zero by the existing repository, so the UI explicitly warns that profit is incomplete.
- Store money position is current/all-time: customer balances, cost needed for pending stock purchases, recorded capital including adjustments, and all-time cost used including admin orders. These are not bank/FatCat balances.
- Cashback: net commission and provisional margin chart, plus canonical money_flow snapshot. Owner settlement/upcoming values remain null when unknown; unverified payout funds are not shown as zero. Open adjustments are visible. Current/all-time money position is independent of date selector.
- Chart uses measured SVG coordinates and a zero line for losses; touch selection and keyboard-accessible period selection expose exact values. No chart library added. Errors, no data and old summary-only API are handled.

## Observed verification

Commands run from /home/vu/toolsauto:

```text
.venv/bin/python -m pytest -q tests/test_executive_overview.py tests/test_cashback_insights.py tests/test_bot_users.py tests/test_store_bot.py
139 passed, 14 warnings in 45.19s

# Final focused suite after test coverage was expanded and query variables simplified:
.venv/bin/python -m pytest -q tests/test_executive_overview.py
3 passed in 5.26s

.venv/bin/python -m ruff check app/platform/admin_api/executive.py tests/test_executive_overview.py reports/ui175/executive-analytics/check.py
All checks passed!

git diff --check
(no output; exit 0)

cd frontend && npm run build -- --outDir /tmp/toolsauto-executive-analytics-dist
TypeScript PASS; 1871 modules transformed; built in 16.52s
JS index-HuYiZsyk.js 606.98 kB (gzip 180.11 kB)

.venv/bin/python reports/ui175/executive-analytics/check.py
PASS: 8 combinations of 7/30 days and widths 320/390/768/1440
PASS: 5 additional empty/zero/source-unavailable/legacy-API/HTTP-error scenarios
page_errors=[]; unexpected=[]
```

Browser proof is saved in proof.json. Scripts intercept every request, fulfill fixtures locally, abort unexpected URLs and close Chromium in finally. Mock screenshots overview-390.png and overview-1440.png were visually inspected (locally generated images are ignored by repository rules). Fixture values are synthetic and must not be cited as business performance.

Read-only review by an independent subagent found no critical calculation issue. It confirmed delivered-unit ranking, admin exclusion, refund handling and separate money meanings. This is not Claude/Antigravity sign-off.

## Remaining acceptance

- Static deployment, Web_Dashboard restart and authenticated live acceptance are complete; see live-proof.json.
- Physical phone/iOS Safari not tested; browser emulation is Chromium.
- Existing Vite >500 kB bundle warning and Starlette TemplateResponse deprecation remain.
- No attribution ROI/CAC, bank cash balance, complete unrecorded costs, automated advice, or Xe Tet metrics are provided. Previous-period percentage comparisons are not implemented.
- Charts describe observations; small samples or current partial periods do not establish causes.

Execution Done. Cần Claude Code verify + handoff.

## Release staging — 2026-11-18

Fresh frontend build PASS (1,871 modules, 8.82s); final analytics tests 3 passed in 7.11s; 13 browser fixture cases PASS. Git fetch found HEAD and origin/feat/xe-tet both at 649d42e (0/0). Static backup /tmp/toolsauto-executive-backup-20261118T050911Z; 9 output files hash-verified, previous assets retained, index replaced atomically. New JS index-HuYiZsyk.js; index SHA-256 a786e524cd4d28f7bcc8070c686f3b20db9d7e92a98119dc5f31cbfa44e169f6

## Live acceptance — 2026-11-18 12:15 VN

Code/bundle commit **28f6b1f** pushed to origin/feat/xe-tet. Only Web_Dashboard restarted, restart count 6 → 7, PID 3668763, online. The first immediate login probe hit ECONNREFUSED during startup; next /health returned 200 and the complete smoke passed without another restart.

Authenticated login, /health, /app, overview/process APIs and executive 7/30-day APIs all returned HTTP 200. All four executive sources available, errors=[]. Store and Cashback trend totals matched their summary values for both periods. Store displayed 3 ranked products for 7 days and 5 for 30 days. Invalid period returned 422. Seven HTTP asset hashes and served index matched the deployed build.

Read-only live browser: 7/30 days × 320/390/768/1440 widths (8 checks), no overflow, chart geometry PASS, exact-point selector works; page_errors=[], blocked_requests=[]. No live screenshots, customer records or credentials saved. Authenticated tailnet HTTPS :8443 login and 30-day executive API returned 200 with valid TLS. Other PM2 PID/restart/status baselines unchanged, all four Store/Cashback systemd services active.

Execution Done. Cần Claude Code verify + handoff. Physical phone/iOS and formal independent sign-off remain pending.
