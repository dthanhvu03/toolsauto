# PLAN-047 — Affiliate ASR→Keyword→Shopee Lookup Queue

**Status:** Done (Phase 1–2)  
**Executor:** Claude Code  
**Owner direction:** 2026-07-30  
**Task:** TASK-048  

## Goal

Khi AI viết caption: bóc keyword sản phẩm → match kho local → nếu miss thì đẩy queue tra Shopee; operator resolve URL → lưu kho + gắn lại job DRAFT nếu còn.

## Scope Done

1. Fuzzy match affiliate hints trong `ai_generator.py`
2. Runtime queue `storage/db/config/affiliate_lookup_queue.json`
3. `lookup_queue.py`: auto-resolve vs warehouse + resolve manual + dismiss
4. UI panel trên `/affiliates` + endpoints lookup-*
5. AI worker tick gọi `process_pending_against_warehouse`

## Out of scope

- Open API Shopee / Playwright auto-convert link (Phase 3 sau khi có session ổn định)
- Migration DB

## Definition of Done

- [x] Miss-match → PENDING_LOOKUP (dedupe fingerprint)
- [x] Warehouse match → RESOLVED + optional attach DRAFT job
- [x] UI resolve paste `s.shopee.vn` → AffiliateLink
- [x] Handoff updated
