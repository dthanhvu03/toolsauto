# PLAN-177 Phase 2 independent review

Reviewer: Codex subagent phase2_verification. Date: 2026-11-19. Offline tests only; root owns runtime staging and PLAN/TASK/status.

## Verdict so far

No confirmed actionable money/identity/source-snapshot defect found in the reviewed Python implementation. Production promotion remains blocked by live verification and existing Claude/Owner gates. This review does not approve native default or service restart.

Root's first repo-bridge live smoke is a failure, not replaced by offline passing tests: Windows/WSL health200; two native requests timed out around8.04s/8.06s, shortlink504 around18.12s. Root restored legacy. Root has assigned bridge cold-start/page-reuse recovery; final Node tests and review of that revision are pending.

## Reviewed contracts

- Default PRIMARY remains product_data; native explicitly opted in. Native→valid PD→unquoted ladder checks exact shop+item; canonical links can still be created unquoted after provider deadline.
- Native parser requires schema/context/currency/status, exact actual/requested IDs, explicit same-channel split/cap, numeric bounds, periods and retrieved-age validation. Missing values cannot become a zero quote. Non-XTRA historical start/end0 is handled only with seller0/nonfuture start.
- Fixed-point native money feeds existing ProductQuote.sure_commission_vnd; cashback_for unchanged. Native product_last_update remains NULL; fetched_at, range and price_basis stored separately in note. No source-update claim is invented.
- Current HTTP deadlines cover provider/socket work and lock waits, with socket shutdown for trickled headers/body. Synchronous OS DNS/TLS establishment, SQLite writes and scheduler suspension are not hard-cancelled. Do not advertise a hard whole-handle20s SLA from these tests.
- Existing Meta signing/sub_id behavior preserved; tiny malformed-result and missing-channel_type guards fail safely.
- Initial bridge review: one serialized queue keeps ownership until context cancellation/finally drains; fixed portal endpoint, bounded DTO/body, exact peer + Origin/Host checks, no raw auth/response export. Package server index is not imported. Final bridge recovery revision not yet covered here.
- Fixture product name/currency/status are synthetic because POC captures scrubbed them; exact IDs/rates/prices/caps/periods are captured values. Live metadata validation remains necessary.

## Actual Python proof

Command:

```text
.venv/bin/python -m pytest -q tests/test_native_shopee_quote.py tests/test_cashback_native_quote.py tests/test_cashback_plan177.py tests/test_cashback_bot.py tests/test_cashback_affipad.py tests/test_cashback_shopee_shortener.py tests/test_shopee_resolve.py tests/test_cashback_zalo.py
239 passed, 1 failed in 251.65s
```

The sole failure was test_full_native_pd_timeout_returns_canonical_unquoted_inside_budget: whole handle0.9014575s exceeded arbitrary0.85s bound. Its provider cutoff<deadline+0.12s assertion passed; no-shortlink-after-expiry passed; all actual slow-header/trickled-body transport tests passed.

Root explicitly authorized narrowing that test to the implemented external-I/O contract. Removed only the DB/scheduler whole-handle pass/fail bound and recorded whole_handle_elapsed_seconds as a pytest property; strict provider cutoff and no-followup-call assertions remain. No production code changed by this reviewer.

Also replaced old Phase1 test_deadline_budget_not_exceeded_with_slow_bridge: it started a wall clock before repo migration and deliberately slept beyond the deadline it was meant to prove. The replacement test_deadline_budget_is_forwarded_and_expiry_skips_remaining_calls constructs the repo first, uses a deterministic clock, asserts the same deadline and bounded timeout reach the provider, consumes that budget, and asserts ALT/AffiPad are skipped afterward. Actual HTTP timing proof remains in Step2.3 tests.

Final focused rerun:

```text
.venv/bin/python -m pytest -q tests/test_cashback_native_quote.py::test_full_native_pd_timeout_returns_canonical_unquoted_inside_budget tests/test_cashback_plan177.py::test_deadline_budget_is_forwarded_and_expiry_skips_remaining_calls
2 passed in 25.18s
```

Scoped Ruff over eight production Python files and three test files: All checks passed! py_compile for eight production Python files: exit0. git diff --check for scoped paths: exit0.

## Reviewer changes

- tests/test_cashback_plan177.py: only the flawed timing test and its now-unused import.
- tests/test_cashback_native_quote.py: only root-authorized whole-handle diagnostic correction.
- This report.

No live network/browser calls, production DB writes, runtime flags, commits, pushes, restarts or native promotion performed by reviewer.

## Final bridge recovery review and offline proof

The recovery revision adds bounded portal-only prepare (25s) before listening, reuses a backend-owned portal page on successful calls, and closes it/context on errors or shutdown. Fixed-name stage timings are available through an internal callback; no URL/name/auth values enter diagnostics. Queue ownership remains held while cancellation drains. Native request budgets remain unchanged.

Independent final Node command:

```text
Windows Node --test scripts/shopee_bridge/bridge.test.mjs scripts/shopee_bridge/browser.test.mjs scripts/shopee_bridge/quote.test.mjs
# tests 30
# pass 30
# fail 0
# duration_ms 11815.7268
```

No further confirmed actionable Python/bridge correctness defect was identified in this scoped review. Health is a liveness signal, not proof that a subsequent native quote or shortlink succeeds; use the separate live smoke result. Root recovery live result pending at report time.

## Final stable verification run / live gate

Exact same8-file Python command rerun after the two test-only contract corrections, production Python unchanged:

```text
1 failed, 239 passed in 346.16s
FAILED tests/test_cashback_native_quote.py::test_affipad_actual_http_deadline_stops_headers_and_body[slow_headers]
Elapsed 0.358100344s vs required <0.28s for 0.13s provider deadline.
```

AffiPad returned None with a sanitized DeadlineHttpError; the strict elapsed bound failed. No scheduler excuse is treated as a passing result. All239 others, including actual PD/native trickle checks, full provider cutoff and no-calls-after-expiry, passed. An isolated rerun of the same failing case (no threshold/code changes) is pending.

Final bridge recovery revision uses initial existing context page when available and a bounded45s startup preparation, separate from unchanged request8s/20s budgets. Independent final Node tests:32passed/0failed, duration2274.9498ms.

Root final live attempt remains BLOCKED on Affiliate page.goto readiness: get_context_done8.753s, cookies13.364s, page_ready13.919s, navigate_start13.984s, abort45.063s, cleanup_done61.396s. No listener exposed while notready, no successful quote/shortlink calls from repo bridge. Root restored legacy finally. This evidence identifies the blocking stage; it does not establish an auth error or source API failure. Native promotion remains unapproved.

Isolated exact failing AffiPad slow_headers test rerun without code/threshold changes:

```text
.venv/bin/python -m pytest -q tests/test_cashback_native_quote.py::test_affipad_actual_http_deadline_stops_headers_and_body[slow_headers]
1 passed in 35.99s
```

This separate pass demonstrates the elapsed assertion is load-sensitive; it does not turn the preceding combined239/1 result into a clean240-test run. Final verified state:239 other combined tests pass, the one previously failed test passes isolated; strict elapsed guarantees under host scheduling load remain limited. No further production/test changes after that isolated check.

Root restoration proof update: legacy /health returns old server0.3.0/statusok, but its final shortlink attempt also timed out35s (TaskCanceledException at12:46:45Z). This prevents attributing the live problem exclusively to the repo bridge. Legacy health200 is confirmed; legacy shortlink end-state is NOT verified working. No more live probes; phase2-live-proof.json carries legacy_restore and overallblocked_live_portal_navigation. Native PRIMARY/bridgeimplementation overrides absent; defaultPD/legacy remain. No Cashbot restart or customer native promotion.
