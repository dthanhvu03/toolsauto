# Shopee bridge (PLAN-177 Step 2.1)

Repo-owned HTTP entrypoint; uses the installed `@bintangtimurlangit/shopee-mcp`
**0.3.0** browser and voucher exports. It never imports the installed server or
modifies npm files. Do not run two processes against the same browser profile.
The legacy launcher remains the default; this implementation is not deployed.

## Run after review

The existing `run_shopee_mcp.sh` accepts `SHOPEE_BRIDGE_IMPLEMENTATION=repo`.
Windows Node starts `scripts/shopee_bridge/index.mjs`. Standalone invocation must
set `SHOPEE_PROFILE_DIR` and `SHOPEE_DOMAIN=shopee.vn` exactly as the launcher does.
Package resolution defaults to `%APPDATA%/npm/node_modules`; override the package
directory with `SHOPEE_MCP_PACKAGE_DIR` when necessary. Existing portal cookies
are read in memory from the repo's credential file, or
`SHOPEE_AFFILIATE_COOKIE_FILE`; they are never returned, logged, or written.

The listener defaults to `127.0.0.1:9224`. To allow the WSL client, explicitly
configure `SHOPEE_BRIDGE_LISTEN_HOST` to the appropriate Windows interface (or
`0.0.0.0`) and `SHOPEE_BRIDGE_ALLOWED_PEERS` to **exact** WSL source IPs separated
by commas. Non-loopback binding without peers fails startup. No firewall rules
are changed. Numeric host/localhost requests only; browser `Origin` and cross-site
requests are rejected, with no CORS grants. Authentication cookies never cross
the HTTP boundary. Do not publish this listener to WAN.

## Routes and DTO

- `GET /health`: existing status/server/version fields plus implementation/schema.
- `GET /api/generate_shortlink?url=...&sub_id=...`: existing `success` and
  `short_link` fields, minimal compatible `data.data.batchCustomLink` envelope.
  `POST` accepts the same fields as bounded JSON. Accepts existing product,
  shop, voucher and campaign pages on the exact known origins `shopee.vn`,
  `www.shopee.vn`, `s.shopee.vn`, `shp.ee`, `vn.shp.ee`, `shope.ee`.
  Credentials, non-default ports, arbitrary/lookalike hosts and explicit
  off-origin redirect wrappers are rejected. Input URLs are never resolved or
  navigated by this bridge; they are submitted only to the fixed Affiliate GQL
  endpoint. Quote lookup remains exact shop/item IDs on the portal detail API.
- `GET /api/shop_vouchers?shop_id=...`: same cache/count/vouchers contract,
  output field allowlist, bounded one-hour cache.
- `GET /api/product_quote?shop_id=...&item_id=...&timeout_ms=...`:
  `{success:true,quote:{...}}`. Timeout is 1..20000 ms and includes queue time.
  Structured safe failures use `{success:false,error:"code"}` with 4xx/5xx.

`quote` schema version 1:

| Field | Type / meaning |
|---|---|
| `schema_version`, `source`, `context` | `1`, `native_shopee`, `social_media_shop_existing` |
| `requested_shop_id`, `requested_item_id`, `shop_id`, `item_id` | exact decimal ID strings |
| `name`, `currency`, `status`, `item_status` | bounded public name; VND / 1 / normal |
| `price_raw`, `price_min_raw`, `price_max_raw` | whole decimal strings; divide by 100000 for VND |
| `seller_rate_raw`, `platform_rate_raw` | whole decimal strings; divide by 100000 for fraction (7000 = 7%) |
| `platform_cap_raw` | exact existing-user social-media cap; raw money scale 100000 |
| `period_start_time`, `period_end_time` | Unix seconds; zero is preserved for parser evaluation |
| `fetched_at` | response retrieval ISO timestamp, **not** source freshness |

The DTO contains no updated-at claim. Missing/empty/zero-meaning-unknown cap and
missing channel-specific split fail closed. It does not choose a money policy,
infer from max/default rates, classify XTRA, or calculate cashback.

Every browser route shares one queue and one dependency context. Before opening
the listener, `backend.prepare(45000)` cold-launches and prepares **only** the
Affiliate portal. `backend.ready` remains false until that succeeds; a failed
startup closes resources and does not expose a ready listener. Request budgets
remain at most 20s and are separate from process initialization. The CLI has a
55s fail-safe exit for a dependency that cannot drain after preparation expires.

One bridge-owned portal page is reused across successful quotes/shortlinks.
If a persistent context already has an initial open page, the bridge adopts it
and navigates directly to the fixed Affiliate offer URL before reading content;
it opens a new page only when no open page exists. This avoids creating an extra
Chromium target during cold preparation. The adopted page closes on shutdown.
Navigation happens only when its current URL is outside the fixed portal offer
context. Page failure closes it, and shutdown closes the owned page/context in
`finally`. Timeout rejects the caller immediately and closes the context;
serialization remains held until old work and cancellation have drained.
A hung dependency can stop subsequent work rather than permit overlapping
navigation; caller deadlines still expire. No background retry/login loops.

Internal staging can pass `loadBackend(env, {diagnostics: callback})` (or the same
option to `createBrowserBackend`) and call `backend.prepare()` before creating a
server. Callback events contain only fixed operation/stage names, monotonic
elapsed milliseconds and an in-process sequence number. They contain no URLs,
product IDs/names, cookies, source payloads or exception text and are not exposed
by HTTP. `startPreparedBridge({backend,config})` enforces this startup ordering.

## Offline verification

Run `node --test scripts/shopee_bridge/bridge.test.mjs scripts/shopee_bridge/browser.test.mjs scripts/shopee_bridge/quote.test.mjs`. Tests use dependency injection
and local ephemeral HTTP sockets, never Shopee or a real browser. Live quote,
WSL access and shortlink proof remain separate rollout gates.
