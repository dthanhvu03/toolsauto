# PLAN-045 — Reup VIP: Outro + Hook text + Settings wiring fix

**Status:** Done (pending Owner verify)  
**Executor:** Claude Code  
**Owner approved:** 2026-07-29  

## Goal

1. Audit + fix Settings UI → backend (dotted keys không setattr config).  
2. Reup VIP: **outro brand ≤3s** cuối clip + **hook text** 0–2s đầu nội dung.

## Scope

### A — Settings wiring
- `_push_config_value`: map `env_var_name` → `config.ATTR`
- Threads delay: đúng key `publish.delay_*`
- Wire `IDLE_ENGAGEMENT_PROBABILITY`
- Viral scan: fallback `runtime_settings.get` nếu SystemState trống
- `job.py` MAX_FILES đọc config module (đã OK sau push fix)

### B — Outro (mirror intro)
- Config keys `outro_*` + dirs `storage/media/outros/`
- Append sau intro; fade khớp body
- UI upload trên Target Pages panel

### C — Hook text
- `hook_enabled`, `hook_max_sec`, `hook_default_text`, page/account maps
- drawtext overlay trên body trước khi ghép intro
- UI textarea trên panel

## Out of scope
- Safe zone / score card (phase sau)
- Subtitle Whisper burn-in
- Auto-gen intro/outro AI
