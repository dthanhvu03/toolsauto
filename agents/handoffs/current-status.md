# Current Status

## System State

- **Product**: ToolsAuto — auto-publish (Facebook / Threads + related).
- **Architecture**: ADR-007 (`core` / `features` / `platform`). Overlap cleanup [2026-07-22] committed locally.
- **Onboarding**: [docs/TREE.md](../../docs/TREE.md), root [README.md](../../README.md).
- **Active plans/tasks**: none.

## Done This Session [2026-07-22]

### A–C) Security + debt + tree 1A
(see prior notes)

### D) Overlap cleanup (ops → consolidate)

**Phase 1 — ops**
- `start.sh` / `stop.sh` align với `ecosystem.config.js`.
- Single source [`app/core/pm2_apps.py`](../../app/core/pm2_apps.py).

**Phase 2 — consolidate**
- Shared [`publisher_runtime.py`](../../app/core/queue/publisher_runtime.py): kill/locks/heartbeat/resource gate + `claim_precheck` / `postpone_if_sleeping`.
- Affiliate / compliance / ai_studio text → **pipeline** (không GeminiAPI trực tiếp).
- `VideoProtector` → `app/core/media/`; notifier thumb → `app/core/media/thumbnail.py`.
- ADR-007 hooks: `feature_hooks` + `bootstrap_hooks`.

### E) Tighten AI + publisher loop

- FB + Threads publishers dùng `claim_precheck`, `postpone_if_sleeping`, `start_heartbeat_thread`.
- Guard: `tests/test_overlap_cleanup.py` assert publishers dùng shared helpers.
- Proof: `pytest` guards — 9 passed; Codacy clean trên runtime + test (Lizard complexity pre-existing trên publishers).

**Cố ý giữ**: Orchestrator RPA fallback caption/vision (ADR-006).

## Unfinished + Blockers

- Push remote / VPS restart PM2 — tùy user.
- Local Windows: dùng `venv\Scripts\` + uvicorn; `start.sh`/ecosystem `venv/bin/python` là path Linux/VPS.

## Next Action

1. Push nếu cần deploy.
2. Local: `.env` + `venv` + Postgres + `python manage.py db upgrade` + `uvicorn app.main:app`.
3. Optional: DRY sâu hơn body `process_single_job`.
