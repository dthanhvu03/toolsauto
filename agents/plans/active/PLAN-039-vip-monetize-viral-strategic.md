# PLAN-039: VIP harden — Monetize + Viral + Strategic

| Field | Value |
|---|---|
| **Status** | Implemented — chờ Owner verify UI |

| **Priority** | P1 |
| **Executor** | Claude Code (+ thin backend wiring) |
| **Related Task** | TASK-041 |
| **Created** | 2026-07-23 |

---

## Goal

Đưa 3 chức năng VIP từ “gần VIP / chưa VIP” → **VIP vận hành được**:
1. Monetize publish (affiliate + tracking + DRAFT preview)
2. Viral reup (hard-fail + anti-dupe signal trên UI)
3. Strategic boost (đúng nguồn material + Approve human-in-the-loop)

## Scope

### 1. Monetize
- AI inject set `affiliate_url` + `tracking_code` + comment dùng tracking URL (parity bulk).
- DRAFT: preview/edit `auto_comment_text` trên job row.
- Match keyword case-insensitive.

### 2. Viral
- Reup fail → mark material FAILED (không fallback file gốc im).
- `ReupProcessor`: bỏ `nice` trên Windows.
- Job DRAFT/row: badge anti-dupe khi media `_reup.mp4`.

### 3. Strategic
- Tìm material nguồn `tiktok` (và fallback) khi boost page FB.
- Persist BOOST_CONTEXT vào title marker.
- `run_auto_boost` → status `BOOST_PENDING` (chờ Approve).
- Insights UI: panel đề xuất boost Approve/Reject.

## Out of scope
- Migration cột DB mới
- Threads affiliate
- Rewrite Insights scraper từ archive
- VideoProtector gắn intake

## Verify
- Unit/logic: keyword match + tracking fields set (mock hoặc code review path)
- UI: DRAFT hiện comment; Insights hiện boost proposals
- Reup fail path logs FAILED reason
