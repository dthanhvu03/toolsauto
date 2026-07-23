# PLAN-040 — Platform silos (FB / Threads / TikTok source / shared)

**Executor:** Claude Code  
**Status:** Done (2026-07-23)

## Proof log

| Phase | Commit | Smoke |
|-------|--------|-------|
| 0 | PLAN-040 | — |
| 1–4 | see git log | `py -3 -c import app.main` (if Python on PATH) |
| 5 | ADR-008 + archive | handoff updated |

## Phase checklist

- [x] Phase 0 inventory
- [x] Phase 1 normalize_platform + package API
- [x] Phase 2 strategic FB ownership docs
- [x] Phase 3 sidebar silos
- [x] Phase 4 facebook.strategic_boost hook
- [x] Phase 5 ADR-008


## Goal

Làm rõ ranh giới sản phẩm theo MXH (silos) mà không tách DB/app: adapter+worker+UI nhóm theo nền tảng; shared ở `core` + queue/accounts/jobs.

## Phase 0 — Inventory (read-only)

### FB-only (`app/features/facebook/`)

| File | Role |
|------|------|
| `adapter.py`, `selectors.py`, `engagement.py` | Playwright publish + engagement |
| `core/session.py`, `pages/reels.py` | Session + Reels PO |
| `media_processor.py` | FFmpeg prep (dispatcher gọi khi publish) |
| `workers/publisher.py` | PM2 FB publisher |
| `pages_router.py`, `manual_job_router.py` | HTTP pages / manual job |

**Core (FB-owned logic, cross-feature consumers):** `app/core/strategic.py` — growth/boost chủ yếu `platform="facebook"`.

**UI FB-branded:** `/compliance/` (label “Vi phạm Facebook”), Insights strategic/boost, viral→FB pipeline.

### Threads-only (`app/features/threads/`)

| File | Role |
|------|------|
| `adapter.py`, `dashboard.py`, `router.py` | UI + adapter |
| `service/*` | News scrape, scoring, topic_key |
| `workers/publisher.py`, `news_worker.py`, `auto_reply.py`, `verifier.py` | PM2 |

### TikTok / IG (adapter-only silos)

| Package | Files |
|---------|--------|
| `features/tiktok/` | `adapter.py`, `selectors.py` |
| `features/instagram/` | `adapter.py`, `selectors.py` |

### Viral intake (TikTok **source** → FB **sink**)

| File | Role |
|------|------|
| `tiktok_scraper.py`, `scan.py`, `discovery_scraper.py` | Thu thập TikTok |
| `processor.py`, `reup_processor.py`, `service.py`, `router.py` | Pipeline → FB jobs |
| `workers/ai_generator.py` | AI caption worker |

### Shared / cross-platform

| Area | Location |
|------|----------|
| Dispatch | `app/adapters/dispatcher.py` → 4 dedicated adapters |
| Queue / Job | `app/core/queue/*`, `job.platform` string key |
| Accounts, Jobs UI | `features/accounts`, `features/jobs` |
| Insights (multi-platform filter) | `features/insights` → `core.strategic` |
| Maintenance | `features/system_panel/workers/maintenance.py` (FB backlog gate + viral hooks + strategic inline) |
| Hooks | `bootstrap_hooks.py` (viral.*, telegram.*) |
| Orchestrator | `core/orchestrator.py` (AI caption, platform-agnostic) |

### Cross-imports violating ideal silo (documented, not all fixable in one sprint)

| From | To | Rule | Mitigation in this plan |
|------|-----|------|-------------------------|
| `adapters/dispatcher` | `features/facebook`, all adapters | OK (composition) | Document `Platform` keys + normalize |
| `insights` | `core.strategic` (FB boost) | OK via core | Doc FB ownership on strategic |
| `viral_intake/processor` | `core.strategic` | OK via core | Same |
| `maintenance` | `core.strategic` direct | system_panel→core OK | Phase 4: `feature_hooks` `facebook.strategic_boost` |
| `viral_intake` | would violate if → `facebook` | ADR Rule 2 | Keep strategic in core |

**No** `features/X` → `features/Y` imports found in grep (good).

### Definition of Done (all phases)

- [ ] PLAN inventory complete (Phase 0)
- [ ] `Platform` normalize + package `__init__` public API documented (Phase 1)
- [ ] FB ownership documented; no risky file moves that break Rule 2/3 (Phase 2)
- [ ] Sidebar grouped: Facebook / Threads / Chung / Giám sát / Cấu hình (Phase 3)
- [ ] Maintenance strategic boost via feature hook (Phase 4)
- [ ] ADR addendum + handoff + archive PLAN (Phase 5)
- [ ] Smoke: `python -c "import app.main"` OK after each phase

## Phase 1 — Contract / dispatch clarity

- `normalize_platform()` in dispatcher; use in `get_adapter` / `dispatch`
- `__init__.py` + README public API: facebook, instagram, tiktok (threads already has)
- `app/adapters/README.md` dispatch contract

## Phase 2 — Obvious misplacements

- Module docstring `core/strategic.py`: FB product ownership
- Update `features/facebook/README.md` strategic cross-ref
- **No** physical move of `strategic.py` (would force viral→facebook import or core→features violation)

## Phase 3 — UI navigation silos

- Reorder `app/templates/layouts/app.html` nav sections

## Phase 4 — Maintenance boundaries

- Register `facebook.strategic_boost` in `bootstrap_hooks.py`
- `maintenance.py` calls hook instead of direct import

## Phase 5 — Docs + archive

- `agents/decisions/ADR-008-platform-silo-surfaces.md`
- Update `agents/handoffs/current-status.md`
- Move PLAN → archive when DoD checked

## Proof log

| Phase | Commit | Smoke |
|-------|--------|-------|
| 0 | (in PLAN commit) | — |
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
