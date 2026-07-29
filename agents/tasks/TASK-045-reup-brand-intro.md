# TASK-045 — Reup brand intro

**Plan:** PLAN-044  
**Assignee:** Claude Code  
**Status:** Done (Phase 1 + Phase 2 UI)

## DoD Phase 1

- [x] PLAN-044 written  
- [x] `resolve_intro_path` + config keys (`intro_enabled` default **false**)  
- [x] `ReupProcessor` prepend intro ≤3s after anti-dupe  
- [x] Viral processor + reprocess wires page/niche/account  
- [x] `storage/media/intros/README.md` + dirs  

## DoD Phase 2

- [x] `intro_service` + `intro_router` (upload / delete / toggle / panel)  
- [x] Fragment `intro_upload_panel.html` trên Target Pages  
- [x] Handoff update  

## Owner dùng UI

1. Mở `/app/accounts` → account → tab **Target Pages**
2. Panel **Intro brand** → upload Default / Account / từng Page
3. Đảm bảo nút **Đang BẬT** (upload sẽ tự bật)
4. Trên Viral: **Reup lại** 1 video → xem ~3s đầu
