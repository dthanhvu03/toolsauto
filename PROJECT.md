# Project: Cashback Bot Security Hardening & Edge-Case Remediation

## Architecture
- Module boundaries:
  - `cashback_bot/sale_relay.py`: Deal scraping from public Telegram channels, Shopee link extraction, safe redirect resolution, tracking parameter cleaning, affiliate wrapping, safe image download & Telegram channel broadcast, subscriber notification queueing.
  - `cashback_bot/shop_voucher.py`: Bridge service communication (port 9224), caching & LRU eviction, safe voucher formatting, card row generation.
  - `cashback_bot/messages.py`: Telegram message template formatting, HTML escaping, BotReply markup & button URL validation.
  - `cashback_bot/poller.py`: Main polling loop, non-blocking execution of periodic tasks, exception resilience.
  - `cashback_bot/db.py`: SQLite connection configuration (WAL mode, busy_timeout).

## Feature Inventory
| # | Feature / Security Vulnerability | Description | Milestone | Source | Status |
|---|----------------------------------|-------------|-----------|--------|--------|
| 1 | VULN-SSRF: Strict Domain & IP Validation | Replace substring domain matching with URL parsing & hostname whitelist, block private/loopback/link-local/reserved IPs (DNS rebinding check), safe manual redirect resolution (max 3 hops) | M1 | explorer_survey_1, 2, 3 | DONE |
| 2 | VULN-EXFIL: Photo URL Validation & Safe Streaming | Enforce HTTPS and Telegram CDN whitelist on `photo_url`, use `stream=True` with `MAX_IMAGE_BYTES` (10MB) limit to prevent DoS/OOM/data exfiltration | M1 | explorer_survey_1, 3 | DONE |
| 3 | VULN-DOS-THREAD: ThreadPoolExecutor & Poller Blocking | Bound max workers (<=4) and links (<=10), set connect/read timeouts (2s, 3s), isolate or timeout `sale_relay.tick()` in poller loop so main thread never freezes | M1 | explorer_survey_1, 3 | DONE |
| 4 | VULN-AFFILIATE: Affiliate Double-Wrapping & Prefix Replace | Call `_unwrap()` before `_clean_shopee_url()` to avoid nested `an_redir`; sort links descending by length before `text.replace` | M1 | explorer_survey_1 | DONE |
| 5 | VULN-HTML-BR: Fix Telegram HTML `<br>` Rejection | Remove `.replace("\n", "<br>")` in `enqueue_for_subscribers` (use raw `\n`), fixing 100% notification drop | M1 | explorer_survey_1, 2, 3 | DONE |
| 6 | VULN-HTML-ESCAPE: Telegram HTML Escaping in Sale Relay | Escape raw text (`<`, `>`, `&`) in `send_to_channel` before sending to Telegram HTML mode | M1 | explorer_survey_1, 2, 3 | DONE |
| 7 | VULN-URL-SCHEME: Inline Keyboard Button URL Validation | In `BotReply.markup()`, validate `button_url` and keyboard row URLs (allow only `https://`, `http://`, `tg://`), reject invalid schemes and whitespace, route `tg://` to URL button | M1 | explorer_survey_2 | DONE |
| 8 | VULN-MSG-ESCAPE: Messages Escaping & Tag Balancing | Escape dynamic variables in `order_new_notice`, `order_update_notice`, `order_detail_reply` | M1 | explorer_survey_2 | DONE |
| 9 | VULN-BRIDGE: Shop Voucher Bridge Hardening & Eviction | Use LRU/oldest eviction instead of clearing all 500 cache entries, set strict (0.5s, 0.8s) timeout, type guard voucher fields (e.g. float/int discount percentage), truncate detail text to <= 4000 chars | M1 | explorer_survey_2 | DONE |
| 10| VULN-DB-WAL: SQLite Concurrency & Lock Contention | Enable `PRAGMA journal_mode = WAL`, `PRAGMA synchronous = NORMAL`, `PRAGMA busy_timeout = 15000` in `cashback_bot/db.py` | M1 | explorer_survey_3 | DONE |
| 11| VULN-IDEMPOTENT: Idempotent Relay State | Save state or handle failure atomically so failed relay steps don't cause duplicate Telegram broadcasts on retry | M1 | explorer_survey_3 | DONE |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Comprehensive Security Hardening | Patch sale_relay.py, shop_voucher.py, messages.py, poller.py, db.py and verify via tests | none | DONE |

## Interface Contracts
- `sale_relay.resolve_shopee_link(url: str, affiliate_id: str, sub_id: str) -> str`: Safely resolves redirects only within allowed Shopee domains, blocks private IPs, unwraps existing affiliate links, wraps in `an_redir`.
- `sale_relay.is_safe_shopee_url(url: str) -> bool`: Checks scheme is https, host in allowed Shopee hosts, resolves DNS and verifies IP is not private/loopback/reserved.
- `sale_relay.is_safe_photo_url(url: str) -> bool`: Checks scheme is https, host in allowed Telegram CDN domains.
- `messages._is_safe_button_url(url: str) -> bool`: Validates URL format and allowed schemes (`https://`, `http://`, `tg://`), rejecting spaces and unallowed schemes.
- `db.connect()`: Sets `PRAGMA journal_mode = WAL`, `PRAGMA synchronous = NORMAL`, `PRAGMA busy_timeout = 15000`.

## Code Layout & Verified Key Outputs
- `cashback_bot/sale_relay.py` (SSRF, photo streaming, tracking params, unwrap, HTML escape)
- `cashback_bot/shop_voucher.py` (Bridge timeout, LRU cache eviction, voucher type guards)
- `cashback_bot/messages.py` (Safe button URL scheme validation, dynamic field HTML escape)
- `cashback_bot/poller.py` (Poller loop isolation)
- `cashback_bot/db.py` (SQLite WAL mode & busy_timeout)
- `tests/test_cashback_sale_relay.py` (14 passing tests)
- `tests/test_cashback_shop_voucher.py` (13 passing tests)
- `tests/test_cashback_messages.py` (7 passing tests)
- `tests/test_cashback_adversarial_m1.py` (98 passing adversarial tests)
- `tests/test_cashback_challenger_m1_2.py` (10 passing concurrency/resilience tests)
