# ADR-008: Platform silo surfaces (UI + hooks)

## Status
Active

## Context

ADR-007 defines feature folders per MXH but operators still saw a flat “Vận hành” nav mixing FB pipeline (viral, TikTok links, insights, compliance) with Threads and shared jobs/accounts.

PLAN-040 hardens **product surfaces** without splitting DB or apps.

## Decision

1. **Sidebar grouping** (`app/templates/layouts/app.html`):
   - **Chung:** Tổng quan, Hàng đợi job, Tài khoản, Affiliate
   - **Facebook:** Nội dung viral, Nguồn TikTok, Phân tích & boost, Vi phạm Facebook
   - **Threads:** Threads dashboard
   - **Giám sát / Cấu hình:** unchanged buckets

2. **Dispatch contract:** `normalize_platform()` in `app/adapters/dispatcher.py`; keys match `app.constants.Platform`. Package `__init__.py` documents public API for `facebook`, `threads`, `instagram`, `tiktok`.

3. **Strategic boost ownership:** Logic remains `app.core.strategic` (cross-feature consumers). Documented as **Facebook product**; maintenance invokes `feature_hooks` key `facebook.strategic_boost` registered in `bootstrap_hooks.py` (composition root), not direct cross-feature imports from `system_panel` → `facebook`.

4. **No move** of `strategic.py` into `features/facebook/` in this ADR — would violate Rule 2 (`viral_intake` → `facebook`) or Rule 3 (core shim importing features).

## Impact

- UX: clearer MXH mental model; URLs unchanged.
- Ops: no migration; behavior identical.

## Related

- ADR-007
- PLAN-040-platform-silos
