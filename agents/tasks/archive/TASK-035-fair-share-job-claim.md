# TASK-035 — Fair-share job claim ordering

**Status**: In Progress
**Plan**: [PLAN-035](../../plans/active/PLAN-035-fair-share-job-claim.md)
**Executor**: Claude Code (full authority [2026-05-01])

## Steps

1. [ ] Patch `app/services/jobs/queue.py:70` — đổi `ORDER BY j.schedule_ts ASC` → `ORDER BY COALESCE(a.last_post_ts, 0) ASC, j.schedule_ts ASC`.
2. [ ] `py_compile` + `app import` smoke.
3. [ ] Run existing tests: `tests/test_threads_world_news.py`, `tests/test_article_scorer.py`.
4. [ ] Simulate live DB: tạo 2 account giả + 4 job giả, claim 4 lần, verify thứ tự A→B→A→A.
5. [ ] Commit develop.
6. [ ] Update `current-status.md`, archive PLAN/TASK.

## Files Touched

- `app/services/jobs/queue.py` (1 line in ORDER BY).
