# PLAN-046 — Source Diversify VIP

**Status:** Done  
**Executor:** Claude Code  
**Owner direction:** 2026-07-30  
**Task:** TASK-047  

## Goal

Đa dạng hóa nguồn viral TikTok theo page/niche: quota per handle, cảnh báo mono-source, lọc mega-views, gợi ý keyword — **không migration**.

## Proof

- `source_diversity_stats`: warn=True, top=`rinabeauty859` 100% trên 45 NEW
- Settings keys `viral.diversify_*` / mega / mono registered
- `extract_tiktok_handle` unit smoke OK
- Scan return `(new, channels, skipped_quota, skipped_mega)`; Maintenance + manage.py + force_scan toast updated

## Definition of Done

- [x] Quota + mega gate trong `scan.py` khi diversify_enabled  
- [x] Banner mono-source trên `/app/viral`  
- [x] Keyword suggest trên `/app/tiktok-links`  
- [x] Handoff `current-status.md`  
