# Local branch audit - 2026-11-22

## Main update

- Local `main`: fast-forwarded from `37f5c0d` to `4e1133e` with `git merge --ff-only cursor/store-fatcat-actual-cost` in a separate clean worktree.
- The source branch contained 61 commits not previously reachable from main; their committed diff covered 378 paths. `origin/main` remains `37f5c0d`; no push was performed.
- `cursor/task-063-shopee-native-product-quote` and `feat/xe-tet` now point to commits reachable from main. No branches were deleted.

## Remaining branches kept separate

| Branch | Relation to main | Dry-run finding | Action |
|---|---:|---|---|
| `cursor/feat-douyin-longvideo-login` (also origin) | 5 unique / 496 behind | Conflicts in current-status, notifier, Telegram flow, viral intake, admin API, built assets, and tests; also modify/delete conflicts. | Kept; requires feature-by-feature port and current tests. |
| `develop` | 472 unique / 1,135 behind | Deeply diverged legacy line. | Kept; not merged wholesale. |
| `rollback/plan079-compat` (also origin) | 2 unique / 399 behind | Intentional rollback deletes/modifies cashback files; numerous content and modify/delete conflicts. | Kept as rollback reference. |
| `origin/feat/xe-tet-sum-vay` | 2 unique / 241 behind | Dry-run has add/add conflicts across Xe Tet files already present on main in a different version, plus current-status. | Kept; requires choosing the canonical version before merging. |

## Worktree state

- Main merge worktree is clean at `4e1133e` before this audit note.
- The original source worktree retains 127 uncommitted paths spanning separate PLAN/TASK work. No bulk commit, reset, stash, branch deletion, or push was done.
- An earlier write accidentally truncated `current-status.md`. It was restored byte-for-byte from the last committed 6,186-line version. The uncommitted text lost in that overwrite was not available in Local History or Git; latest PLAN-190 facts were reconstructed from its PLAN, TASK, and review artifact.
