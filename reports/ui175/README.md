# PLAN-175 — Mobile UI execution proof, 2026-11-17

Implementation covers a first pass across the SPA, Xe Tết control, Cashback and shared Jinja layouts. Owner authorized Codex to execute UI changes directly, with phone as the primary device. Review/sign-off and real-device acceptance remain pending.

## Result

| Scope | Browser route × viewport checks | Result |
|---|---:|---|
| Overview / Jobs / SPA drawer | 8 | PASS |
| Studio / video warehouse / sources | 12 | PASS |
| Settings / Threads / bot users / database / system panel | 20 | PASS |
| Xe Tết control, all settings groups expanded | 4 | PASS |
| Cashback users / Jinja logs / both Jinja drawers | 8 | PASS |
| Editor / assets / setup / TikTok / documentary / logs / AI / compliance / Telegram / DocType pages | 60 | PASS |
| **Total** | **112** | **No document horizontal overflow; page_errors=[]** |

Viewports: 320×740, 390×844, 768×1024, 1440×900. Test data includes long unbroken channel/customer names, errors, empty lists and an HTTP 503 state. Numerical/detail tables intentionally retain internal horizontal scrolling on larger screens and in schema/SQL editors.

Interactions verified: drawer Escape, focus return/trap and desktop resize; job search; pagination above bottom navigation; mock Studio approval and viral processing; source scan followed by page change; canceled deletion sends no request; toast and unsaved-change notification above navigation; settings section jump and exact save payload; database preview; mobile record navigation; Cashback details; Jinja log tabs. All network requests are intercepted. No live upload, publish, delete, SQL command, bot message or process action was performed.

## Commands and observed outputs

```text
cd frontend
npm run build -- --outDir /tmp/toolsauto-ui175-dist
tsc --noEmit: PASS
Vite: 1870 modules transformed; built in 5.46s
JS: 589.18 kB (gzip 174.90 kB)

cd xe_tet/overlay
npm run build -- --outDir /tmp/toolsauto-ui175-overlay-dist
26 modules transformed; built in 6.54s
JS: 840.05 kB (gzip 231.51 kB)

.venv/bin/python -m pytest -q tests/test_cashback_admin_ui_ux.py tests/test_cashback_zalo.py tests/test_store_bot.py
147 passed in 23.94s

Jinja Environment.parse over app/templates/**/*.html
jinja-parse=PASS (57 templates)

git -c core.autocrlf=false diff --check
exit 0, no output
```

Both builds retain existing bundle-size warnings. Output was written under `/tmp`, not the frontend static directories served by the application.

## Reproduce browser verification

Run from `/home/vu/toolsauto` after the isolated frontend build above. Python Playwright and its Chromium must be installed in `.venv`.

```bash
.venv/bin/python reports/ui175/phase1/check.py
.venv/bin/python reports/ui175/phase2/check.py
.venv/bin/python reports/ui175/phase3/check.py
.venv/bin/python reports/ui175/phase4/check.py
cp reports/ui175/jinja-fixture.css /tmp/ui175-jinja.css
.venv/bin/python reports/ui175/phase56/check.py
.venv/bin/python reports/ui175/remaining/check.py
```

Each script prints JSON and writes fresh screenshots/JSON under its `/tmp/toolsauto-ui175-proof*` directory. Checked-in JSON in this folder records this execution. Phone screenshots and `mobile-preview.png` are local review artifacts, ignored by the existing `*.png` rule. `jinja-fixture.css` was compiled locally from Jinja template classes using the installed Tailwind CLI; production CDN/font delivery was not exercised.

## Review

**No findings.** Root performed a read-only defect review using `C:/Users/Admin/.codex/skills/.system/review-agent/SKILL.md`, after implementation and verification. This is self-review, not independent Claude/Antigravity sign-off.

The browser run identified and fixed the preexisting source-row lock: `useViralSources` used mutation variables after completion. Busy state now applies while a mutation is pending. No API contract changed.

Git previously ignored the complete `frontend/src/features/logs/` source folder through the general `logs/` pattern. The exact source-folder exception now exposes the existing API/hook/type files and the updated page; runtime log directories remain ignored.

## Acceptance still open

- Physical phone / iOS Safari, software keyboard and real safe-area behavior.
- Authenticated backend and actual customer/channel datasets, including HTMX fragment responses and production CDN/font delivery.
- Overlay runtime/visual test during an isolated test session; this pass builds the unchanged overlay and mocks control API responses.
- Remaining Jinja page bodies inherit shared controls/navigation; only Cashback users and logs have full rendered browser fixtures in this pass.
- Existing whole-repo audit findings are separate: the 147 passing tests are the related subset, not a claim that root pytest collection or all repository checks pass.
- The initial fixture pass performed no deployment. Owner subsequently requested deployment; live results follow below. No commit, push or restart was performed.

## Authorized deployment — 2026-11-17

Owner requested deployment directly. Fresh staged build passed TypeScript/Vite (1,870 modules, 6.89s). Static files were deployed at **14:53:19 UTC** to `/home/vu/toolsauto/app/static/admin`; assets were copied first, then the index was replaced atomically. Old assets remain for existing tabs. Backup `/tmp/toolsauto-ui175-backup-20261117T145319Z` has 9 verified files. Rollback: copy its assets back if necessary, atomically restore its index and restore `.vite/manifest.json`; keep unrelated working-tree changes.

Actual live results in `deployment.json`:
- Login HTTP 200; `/app`, `/app/go/studio`, `/cashback/users`, `/app/logs`, `/health` HTTP 200. Rendered Jinja contains the new navigation script.
- Seven JS/CSS/font assets returned HTTP 200 and matched staging SHA-256.
- Authenticated Chromium `/app` used the real read-only `/api/admin/overview` (200). Widths 320/390/768/1440: no document overflow; mobile drawer/Escape passed; page_errors=[], blocked_requests=[]. No customer data/screenshots or session credentials saved in the proof.
- HTTPS shell on `https://laptop-t2hf25cd.tail15ebd5.ts.net:8443/app`: HTTP 200, index hash matched, TLS certificate verified using tailnet IP `100.102.93.11` with the original hostname. Public DNS resolves the Funnel address and its 8443 probe failed SSL EOF. This endpoint is tailnet-only: phone access needs Tailscale. Port 443 serves the separate Store app; networking was not changed.
- PM2 Web_Dashboard stayed online, restart count unchanged at 4. Jinja and control files are read directly from this checkout; no restart required. No Xe Tết server listener was found, so the game was not started.

This live smoke covers the overview and rendered Jinja HTTP responses; physical phone/iOS, remaining authenticated workflows, HTMX interactions and independent acceptance remain open.

Execution Done. Cần Claude Code verify + handoff.

## Commit preparation

Owner subsequently authorized commit/push on `feat/xe-tet`. The UI source, deployed bundle and proof belong to this change; two preexisting audit test patches are excluded. Staged source/proof whitespace validation uses `git diff --cached --check -- . ':!app/static/admin/assets/*'`. The generated Vite JS retains five whitespace-only lines inside a dependency CSS template string; editing the hashed build would invalidate the recorded deployment hash.
