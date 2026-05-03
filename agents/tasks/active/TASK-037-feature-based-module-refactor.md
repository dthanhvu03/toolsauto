# TASK-037 — Refactor sang feature-based architecture

**Status**: Approved (Anti sign-off 2026-05-03) — Phase 0 DONE, Phase 1 ready for Codex
**Plan**: [PLAN-037](../../plans/active/PLAN-037-feature-based-module-refactor.md)
**ADR**: [ADR-007](../../decisions/ADR-007-module-boundary.md)
**Executor**: Codex (heavy file-move + import update)
**Verifier**: Claude Code (per-phase smoke + handoff)

> **Gate**: PLAN-037 Status = Approved (Anti sign-off 2026-05-03). Codex MAY execute Phase 1.

## Background

Codebase hiện tổ chức theo technical layer (`adapters/`, `services/`, `routers/`, `workers/`). Mỗi feature bị xé ra rải vào 4-5 thư mục → onboarding chậm, khó delete feature, cross-feature coupling ngầm. Anh Vu yêu cầu refactor sang feature-based để mỗi feature self-contained.

Repo size: 30K LOC, 12 service subdir, 5 adapter platform, 19 router, 8 worker.

## Steps (5 phases — mỗi phase 1 PR + Anti review)

### Phase 0 — ADR module boundary ✅
1. [x] Anti / Claude Code viết `agents/decisions/ADR-007-module-boundary.md`.
2. [x] Chốt danh sách core / features / platform — **7 core + 9 features + 3 platform** (3 điều chỉnh từ bản đề xuất sơ bộ: compliance → FB feature, db_admin added, notifier source corrected).
3. [x] Định nghĩa import rule: `features/foo/` chỉ được import `core/*`, KHÔNG import `features/bar/`.
4. [x] Anti sign-off ADR-007.

### Phase 1 — Carve out `app/core/`
5. [ ] Move `app/database/` → `app/core/database/`. Update import + verify.
6. [ ] Move `app/services/jobs/` → `app/core/queue/`. Update import + verify.
7. [ ] Move `app/services/observability/` → `app/core/observability/`. Update import + verify.
8. [ ] Move `app/services/ai/` → `app/core/ai/`. Update import + verify.
9. [ ] Smoke: `app import 207 routes`, `pytest -q` PASS, `pm2 restart` all workers `online`.

### Phase 2 — Pilot Threads feature
10. [ ] Tạo `app/features/threads/` skeleton (adapter, service/, dashboard, router, workers/).
11. [ ] Move 4 worker entry threads_*.py → `app/features/threads/workers/` (giữ shim ở `workers/` cũ trong 1 sprint).
12. [ ] Move adapter + 4 service file (news_scraper, threads_news, topic_key, article_scorer).
13. [ ] Move dashboard + router.
14. [ ] Update `ecosystem.config.js` script paths.
15. [ ] Smoke: pytest threads PASS, `pm2 restart Threads_Publisher` OK.
16. [ ] VPS deploy + 24h monitor → 1 threads publish thành công.

### Phase 3 — Carve remaining features (theo thứ tự rủi ro)
17. [ ] `instagram` (low risk).
18. [ ] `tiktok` (low risk).
19. [ ] `affiliates` (medium).
20. [ ] `system_panel` + `workflow_registry` (medium).
21. [ ] `insights` (medium — đụng dashboard).
22. [ ] `telegram_bot` (medium — shared notifier).
23. [ ] `viral_intake` (high — orchestrator 651 dòng).
24. [ ] `facebook_publisher` (highest — adapter 6500 dòng + engagement + compliance).

### Phase 4 — Cleanup orchestrator
25. [ ] Tách `app/services/content/orchestrator.py` thành `viral_intake/orchestrator.py` (generic) + `facebook_publisher/reup_pipeline.py` (FB-specific).
26. [ ] Verify smoke + 24h monitor.

### Phase 5 — Lint guard
27. [ ] Add `import-linter` config + pytest plugin chặn cross-feature import.
28. [ ] CI fail nếu vi phạm.
29. [ ] Update `agents/RULES.md` + `CLAUDE.md` với module boundary rule.

### Closing
30. [ ] Codex update PLAN/TASK status sau mỗi phase commit.
31. [ ] Claude Code verify per-phase + update handoff.
32. [ ] Anti final sign-off sau Phase 5 → archive.

## Files Touched (estimate)

- ~50-80 file move (`git mv`).
- ~200-400 import statement update (sed batch).
- 1 ADR mới.
- `ecosystem.config.js` 1 lần.
- `agents/RULES.md` + `CLAUDE.md` 1 lần.
- `.importlinter.ini` + 1 pytest plugin (Phase 5).

## Out of Scope

- Đổi business logic / SQL.
- Frontend `templates/` + `static/` reorg.
- Database schema change.
- Multi-tenant feature loading.
- Tách worker process (`ecosystem.config.js` giữ list worker).

## Acceptance Trace (Anti per-phase)

Sau mỗi phase commit, Anti chấm theo PLAN-037 §"Acceptance Criteria" (`AC2` smoke, `AC3` pm2 online, `AC4` live publish post-Phase 2 + post-Phase 3, `AC5` lint guard, `AC6` rollback test, `AC7` doc updates).

## Risks (xem chi tiết PLAN-037 §"Risks")

- Import path explosion → batch sed.
- Production downtime → deploy lúc thấp tải, restart từng worker.
- Hidden circular import → Phase 1 verify trước.
- workers/ path change phá cron script → giữ shim 1 sprint.
- Codex bypass Anti gate (như PLAN-036) → Anti theo dõi commit log mỗi ngày.
- Refactor scope creep → ENFORCE "không đổi behavior".

## Estimate

10-14 ngày work nếu Codex full-time + Anti review 24h cho mỗi phase. Có thể chia làm 2 sprint:
- Sprint 1 (5-7 ngày): Phase 0 + Phase 1 + Phase 2 (pilot Threads).
- Sprint 2 (5-7 ngày): Phase 3 + Phase 4 + Phase 5.
