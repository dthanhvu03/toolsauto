# Local branch audit - 2026-11-22

## Main update

- Local `main`: fast-forwarded from `37f5c0d` through `4e1133e` and audit commit `e941d2a`, then through `cursor/store-fatcat-actual-cost` at `5e3c46b` in the separate clean worktree.
- The source branch originally contained 61 commits not previously reachable from main; their committed diff covered 378 paths. The cleanup added 15 focused commits after `e941d2a`, covering the remaining plan artifacts and evidence. At the last pre-report check, local main was 77 commits ahead of `origin/main`; `origin/main` remains `37f5c0d`, and no push was performed.
- `cursor/task-063-shopee-native-product-quote` and `feat/xe-tet` now point to commits reachable from main. No branches were deleted.

## Remaining branches kept separate

| Branch | Relation to main | Dry-run finding | Action |
|---|---:|---|---|
| `cursor/feat-douyin-longvideo-login` (also origin) | 5 unique / 496 behind | Conflicts in current-status, notifier, Telegram flow, viral intake, admin API, built assets, and tests; also modify/delete conflicts. | Kept; requires feature-by-feature port and current tests. |
| `develop` | 472 unique / 1,135 behind | Deeply diverged legacy line. | Kept; not merged wholesale. |
| `rollback/plan079-compat` (also origin) | 2 unique / 399 behind | Intentional rollback deletes/modifies cashback files; numerous content and modify/delete conflicts. | Kept as rollback reference. |
| `origin/feat/xe-tet-sum-vay` | 2 unique / 241 behind | Dry-run has add/add conflicts across Xe Tet files already present on main in a different version, plus current-status. | Kept; requires choosing the canonical version before merging. |

## Worktree state

- Main merge worktree fast-forwarded cleanly to `5e3c46b`; status was clean after the fast-forward.
- The original 345-file WIP was captured in focused commits; 10 active/local-only files remain outside Git (runtime locks plus PLAN189 live `state.json` and `candidates.json`). Two safety stashes remain intact. No reset, branch deletion, or push was done. PLAN187 cancellation was verified; PLAN189 stays hourly active through 2026-11-24 23:51 VN.
- An earlier write accidentally truncated `current-status.md`. It was restored byte-for-byte from the last committed 6,186-line version. The uncommitted text lost in that overwrite was not available in Local History or Git; latest PLAN-190 facts were reconstructed from its PLAN, TASK, and review artifact.
