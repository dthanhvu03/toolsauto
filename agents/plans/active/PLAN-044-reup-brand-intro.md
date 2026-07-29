# PLAN-044 — Brand intro 3s trước reup

**Status:** Phase 2 Done (UI upload)  
**Executor:** Claude Code  
**Owner approved:** 2026-07-24  

## Goal

Ghép **intro brand ≤3s** (asset của anh) vào đầu file `_reup`, resolve theo:

1. Explicit path  
2. Target Page  
3. Niche của page  
4. Account  
5. Default  
6. Không có → bỏ qua (reup như cũ)

## Phase 1 — Backend (Done)

- Config trong `storage/db/config/reup_presets.json` (+ defaults code)
- Thư mục `storage/media/intros/` + README
- `resolve_intro_path()` trong `reup_config.py`
- `ReupProcessor`: sau anti-dupe, concat intro (scale khớp resolution)
- Viral `processor` truyền `page_url` / niches / `account_id`
- Metrics: `intro_applied`, `intro_path`

## Phase 2 — UI upload (Done)

- API: `GET/POST /viral/intros/{panel,toggle,upload,delete}`
- Fragment `intro_upload_panel.html` lazy-load trên tab **Target Pages** (`/app/accounts`)
- Upload mp4/mov/webm ≤40MB → Default / Account / từng Page
- Toggle BẬT/TẮT `intro_enabled` trên UI (upload tự bật)

## Out of scope

- “Lách bản quyền” — intro chỉ brand asset hợp lệ
- Auto-generate intro
- Upload niche riêng trên UI (map niche vẫn dùng được qua filesystem / JSON)

## Verify

- Không có intro map → reup OK như cũ  
- Upload default + BẬT → Reup lại → `_reup` dài hơn ~3s, metrics `intro_applied=true`  
- Map page ưu tiên hơn default  

## Rollback

Tắt toggle trên UI (`intro_enabled: false`) hoặc xóa intro trên panel.
