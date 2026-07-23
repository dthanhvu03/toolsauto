# Current Status

## System State

- Local: **http://127.0.0.1:8002**
- AI: `AIUseCases` · VIP: `d3c0ed2` · Perf N+1: working tree (uncommitted)

## Done This Session [2026-07-23]

### VIP (committed)
- Accounts Config/Target split + Viral `_reup` preview + Insights closed-loop → `d3c0ed2`

### Perf N+1 (implemented, chưa commit)
1. Viral table: `batch_reup_by_id` (1 walk disk + 1 Job batch)
2. Jobs + Discovery: `selectinload(account)`
3. `scan.py`: prefetch normalized URL set
4. `processor.py`: prefetch NEW **per account** (A queries, cap/limit) + REUP cap GROUP BY
5. `strategic.run_auto_boost`: batch cooldown/accounts/top posts; niche pool + **SQL fallback** nếu miss
6. `discovery_scraper` + `ai_generator` cache/selectinload

**Review pass 2:** siết memory starve + niche miss; chưa có benchmark SQL runtime.

## Next Action

1. Commit perf N+1 khi Owner OK.
2. Optional: log timer `get_viral_table_data` để đo trước/sau.
3. Archive PLAN-038/039 + TASK-040/041 sau UI confirm.
