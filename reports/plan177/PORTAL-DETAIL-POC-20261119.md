# PLAN-177 — Portal detail lookup and commission POC, 2026-11-19

Status: technical evidence for Phase 0.1 obtained; Phase 0.2 sample comparison available, cached-source caveat below. Phase 0.3 source decision / Anti sign-off / Claude 2.0 / stable production bridge remain pending. No native customer quote enabled.

## Result

- Official portal JavaScript exposes GET /api/v3/offer/product?item_id={item_id}, separate from GET /api/v3/offer/product/list. This detail path removes the name-search dependency.
- Eight distinct detail responses have HTTP 200 / code 0 and exact requested item_id plus expected shop_id. All six original S1–S6 are covered after retries; seven XTRA and one non-XTRA (PD classification). S3 exists on detail despite previous list searches returning empty.
- Price and mapped sure commission match Product Data on all eight samples. Default-as-total overquotes on five samples. B/C are equivalent for the sampled nonnegative splits; use explicit native components and cap, not a field-name heuristic.
- These are eight successful distinct records, NOT an 8/8 availability claim. Initial batch: 6 successes / 12 attempts; three portal errors without code and three origin redirects. Standalone retries of S3 and S4 succeeded. Those failures remain in portal-detail-live-20261119.jsonl. No repeated retry loop, CAPTCHA solving or buyer PDP requests.

## Native detail schema

- Identity: data.item_id and data.batch_item_for_item_card_full.shopid. Verify both against the resolved customer link; reject mismatch.
- Display percentages: data.commission_rate.seller_commission_rate, shopee_commission_rate, default_commission_rate. Comma-decimal strings, e.g. 7%, 2,5%, 9,5%.
- Detail numeric rates: data.commission_rate_detail fields use fraction = raw / 100000; example seller 7000 = 7%. Confirmed against percent strings on all eight records (24 parity checks). Do not treat raw 7000 as bps.
- Price: batch_item_for_item_card_full.price / 100000 VND. Preserve price_min/max and variant-price uncertainty.
- Cap: commission_rate_detail.channel_cap.exist_user.social_media_cap (fallback commission_cap only when applicable) / 100000 VND. All eight observed caps = 40000 VND. Detail also exposes channel/user/attribution-specific fields; do not mix Facebook Reels, video, live and social-media rates.
- For social-media same-shop existing-user data: commission_rate_detail.shopee_commission_detail.social_media_shop_base_exist_commission_rate and seller_commission_detail.social_media_default_exist_commission_rate are available. Checkout-base platform rate is a separate field (often 2.5% here).
- List max is 0% on the earlier rows; detail max has actual values. Never infer a universal max-field rule across endpoints.

## Mapping to current policy (POC only)

Parse percent using Decimal, replace comma with dot, validate finite 0..100 and distinguish empty from zero. Keep fixed-point arithmetic through price/cap conversion. Floor whole VND at the same component boundaries as current ProductQuote.

For observed direct social-media samples: seller = floor(price * seller_rate); platform = min(floor(price * platform_rate), explicit platform cap). Raw total = seller + platform. Current sure = min(raw total, seller + min(platform, floor(price * 2.5%))). This preserves SHOPEE_BASE_BPS=250 in cashback_bot/product_data.py and cashback_for remains unchanged.

This is a compatibility mapping to existing policy, not a new owner-approved payout formula. Different channels/indirect orders, missing cap, missing split, out-of-period offers and rate precision beyond bps need explicit production handling. Never fall back from missing split to unchecked total via ProductQuote.sure_commission_vnd.

| Sample | PD XTRA | Price VND | Seller / Shopee / default % | A default total | Native mapped sure | PD sure | A minus PD | Mapped minus PD |
|---|---|---:|---|---:|---:|---:|---:|---:|
| S1 | yes | 1354000 | 7 / 2.5 / 9.5 | 128630 | 128630 | 128630 | 0 | 0 |
| S2 | yes | 60000 | 7 / 2.5 / 9.5 | 5700 | 5700 | 5700 | 0 | 0 |
| S5 | yes | 162000 | 10 / 2.5 / 12.5 | 20250 | 20250 | 20250 | 0 | 0 |
| S6 | yes | 284000 | 6 / 7 / 13 | 36920 | 24140 | 24140 | 12780 | 0 |
| N1 | yes | 159000 | 10 / 7 / 17 | 27030 | 19875 | 19875 | 7155 | 0 |
| N2 | yes | 348000 | 7 / 7 / 14 | 48720 | 33060 | 33060 | 15660 | 0 |
| S3 | no | 138475 | 0 / 7 / 7 | 9693 | 3461 | 3461 | 6232 | 0 |
| S4 | yes | 167500 | 8 / 7 / 15 | 25125 | 17587 | 17587 | 7538 | 0 |

S1 retains PD is_capped=true while portal commission_rate.is_capped=false: PD has a higher raw platform rate capped at 40000, while native portal returns 2.5% platform for this account. Their sure amount matches; raw commission / cap flags are not interchangeable.

## Freshness and reliability limits

Portal observations span 09:56:47Z–10:08:07Z (16:56–17:08 VN). Final PD comparison fetched 10:12:48Z–10:12:54Z (17:12 VN), all reported source=db. PD last_update spans 09:21–10:00Z; earlier comparison rounds caused the new items to be cached. No claim of simultaneous fresh API observations or independently validated rate freshness. Native response has campaign period but no general last_update in the observed top-level schema. A retrieved-at timestamp must not be presented as source-updated-at.

The initial errors do not establish that failed items are absent from the catalog. Detail retries succeeding reinforce the need for bounded retries, navigation/session error classification and fallback within the shared deadline.

## Execution and verification proof

- Windows Node: node --check reports/plan177/portal-session-probe.mjs => exit 0.
- WSL: .venv/bin/python -m reports.plan177.compare_portal_detail portal-detail-matched-20261119.jsonl portal-detail-compare-20261119.json => 8 records, ids_exact=true, price_delta_vnd=0, delta_mapped_sure=0.
- WSL: .venv/bin/python -m reports.plan177.compare_portal_detail --check => {"contract_checks":59,"failures":0,"unique_exact_items":8,"non_xtra":1,"default_as_total_overquotes":5}.
- Checks include invalid/NaN/infinite/empty/zero rates, price/cap scale, fractional-VND rounding, synthetic cap below conservative 2.5%, current ProductQuote oracle, rate numeric/string parity and live comparison consistency.
- WSL Ruff: .venv/bin/python -m ruff check reports/plan177/compare_portal_detail.py => All checks passed!
- End state: Windows health HTTP 200; WSL get_bridge_url()+/health HTTP 200/status ok; shortlink_success=true, host=s.shopee.vn.
- Installed bridge SHA-256 remains 9F8E47F0A9F02D198A0390E193A29B3937A92DF04E76937C5835B4BCAB8EECBC. No installed npm edits or new HTTP routes. POC only used stdio, with bridge stopped while using the existing profile. Browser closed in finally; outer PowerShell finally restored shopee-mcp. Cashbot / Zalo were not restarted.
- Setup failures before successful capture: page execution context destroyed during navigation, profile-only login redirect, and stdin consumed before async initialization. Fixed POC waits/input ordering and copied the existing bridge's in-memory cookie synchronization. One hung POC process was terminated; installed bridge restored immediately afterward. No credentials were printed or saved by the POC.

## Reproduce (authorized POC only)

Use Windows Node with existing SHOPEE_PROFILE_DIR and SHOPEE_DOMAIN=shopee.vn. Stop only shopee-mcp first; pipe portal-final-commands.jsonl to portal-session-probe.mjs; restore shopee-mcp in an outer finally. Script reads the existing credential file in memory, as the bridge already does; outputs only field allowlist/IDs/rates, never cookies/CSRF/headers or product names. Do not run concurrently against the same browser profile. Do not expose this script over HTTP.

## Artifacts / next

- portal-source-evidence-20261119.json: official static app/detail asset references and relevant API/formula snippets.
- portal-detail-matched-20261119.jsonl: eight successful sanitized native responses with request/expected-shop proof.
- portal-detail-live-20261119.jsonl: complete initial 12-attempt batch including failures.
- portal-nonxtra-live-20261119.jsonl and portal-final-live-20261119.jsonl: successful standalone S3/S4 retries.
- portal-detail-compare-20261119.json: final eight-row PD comparison with source/fetch/update times.
- portal-runtime-proof-20261119.json: health/shortlink/hash and check summary.

Next: Anti/Owner 0.3 decision on portal REST detail; Claude 2.0 review; repo-owned production bridge access boundary and shared deadline/lock; session/circuit/fallback + missing-field/ID/period/variant tests; no default native promotion before those gates. No new production implementation was authorized by this POC completion.

Execution Done for the Phase 0 POC continuation. Cần Claude Code verify + handoff. PLAN/TASK remain active; no archive/commit/push.
