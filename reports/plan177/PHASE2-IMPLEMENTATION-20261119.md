# PLAN-177 Phase 2 implementation — 2026-11-19

Status: implementation complete with native opt-in only; runtime/live acceptance BLOCKED. No production native promotion, no Cashbot/Zalo restart, no commit/push. Owner explicitly requested sequential subagents in this chat.

## Sequential delivery

1. bridge_implementation: repo-owned scripts/shopee_bridge entrypoint/server/browser queue/DTO; run_shopee_mcp.sh opt-in only. Peer/Origin/Host guards; no npm edits. Review fixed existing shop/voucher/campaign shortlink compatibility. Live-stage diagnosis led to bounded portal-only startup preparation, adopted persistent initial page, page reuse, fixed internal stage diagnostics and referenced fail-safe timers. Final startup45s/max45s/hard55s is separate from request20s maximum.
2. native_quote_client: NativeShopeeQuoteClient + NativeProductQuote and sanitized8fixtures;98focused tests. Fixed-point rawscale100000, explicit cap/channel, exact shop+item, periods including zero-seller/non-XTRA end0, signed64 range, minvariant basis; existing ProductQuote.sure_commission_vnd unchanged. No source-update timestamp; last_update=None/fetched_at separate.
3. quote_ladder_integration: PRODUCT_QUOTE_PRIMARY default product_data; native opt-in ->validPD->unquoted. Same Telegram/Zalo service. Bounded per-call PD/AffiPad/optionalALT/shortener transport, no shared timeout mutation, circuit/fallback/source/snapshot/sub_id behavior. Small AffiPad malformedresult/missingchannel guard.30focused integration tests passed.
4. phase2_verification: independent code/test review and scoped corrections to tests that measured SQLite setup/write as networkdeadline. Offline review found no additional confirmed money/ID/source defect. Full final run239passed/1timingfailure346.16s; remaining failure AffiPadslowheaders0.3581s vs0.28threshold with0.13deadline, safe None/DeadlineHttpError returned. Focused rerun and finalNode results in independent report. Never describe this as combined240green.

## Runtime evidence and unresolved gate

- First live repo stage: Windows/WSLhealth200, native default8s timeouts8.041/8.055s, shortlink504 after18.116s. Preserved phase2-live-proof-attempt1.json.
- Stage instrumentation isolated coldcontext launch, initial newPage stall, then fixedportal navigation timeout. Adoption regression fixed newPage use where a saved page exists; requestdeadline unchanged.
- Final45s preparation: get_context_done8.753s,cookies_sync_done13.364s,page_ready13.919s,navigate_start13.984s,abort45.063s,cleanup_done61.396s. Error timeout, no listenerready, no nativequote requests. Proof phase2-live-proof.json. Startup prepare timeout caller returns before cleanup drains; outer cleanup duration61.4s observed.
- Legacy restored in shell finally after each probe; final legacyhealth statusok/version0.3.0. Final legacyshortlink itself timed out35s, so runtime trouble is not isolated to newbridge. No proven rootcause beyond portal navigation readiness failing. Do not label expiredsession/captcha/network without evidence.
- No new defaultnative flags in .env, no repo-bridge default activation. Existing npm index hash unchanged9F8E47F0A9F02D198A0390E193A29B3937A92DF04E76937C5835B4BCAB8EECBC.

## Deadline limits

Per-call networkbody/header and lock budgets are bounded through socketshutdown; tests use real slow/trickled localHTTP. Synchronous OS DNS/TLS establishment, SQLite writes and suspended scheduler are not hardcancelled. Do not promise an absolute wholehandle20s SLA from this implementation. Native API has retrieval timestamp only; no independent sourcefreshness proof. Variant minimum/channel social_media_shop_existing behavior needs Claude review before customerpromotion.

## Files / rollout / rollback

Implementation: scripts/shopee_bridge/*, run_shopee_mcp.sh, cashback_bot/native_shopee_quote.py, deadline_http.py, config.py, service.py, product_data.py, affipad.py, alt_shopee_link.py, shopee_shortener.py; tests/fixtures/native_shopee_quote_poc.json, tests/test_native_shopee_quote.py, test_cashback_native_quote.py and narrowed oldPhase1 timingtest. Preserve existing unrelated dirtyfiles.

Rollout when runtimegate fixed: configure Windowslisten/exactWSLpeers for repo bridge and launch with SHOPEE_BRIDGE_IMPLEMENTATION=repo; verify prepare/readiness, WSLhealth, realquote+shortlink/voucher, then Claude/Ownercontrolledoptin PRIMARY=native. No .envchanges here. Rollback: PRIMARY=product_data and bridgeimplementationlegacy; unquotedfallback remains. ADDLIVETAGkey still required for otherconsumers. GateA ALTlive unchangedpending.

Next: diagnose Affiliate navigation/session connectivity in current Windowsprofile while keeping legacy and nativeoff; rerun bounded liveproof and failedtimingcase once scheduling stable. Then Claude2.0 + Anti review/signoff + Ownerrestart/smoke. Implementation work is reviewable; fulltask/live Step2.4 remains pending.

Execution Done for offline implementation. Cần Claude Code verify + handoff. Không mark toàn PLAN/TASK Done hoặc archive.

## Final independent check results

- Final Node suite:32 passed0failed2274.9498ms.
- Exact previously failing AffiPadslowheaders test rerun isolated, unchanged code/threshold:1 passed35.99s. This is separate from full239passed1failed346.16s; no claim combined240green.
- PM2 final snapshot: shopee-mcp onlinePID2627135, legacy; all other listed applicationPIDs match baseline.
- Ruff/py_compile/Node syntax/bashsyntax/diffcheck passed.
