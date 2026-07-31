# PLAN-048 — Local auto-coordination (D: Supervisor + Smart gates)

## Status: Done (implemented)

## Goal

Owner chạy một lệnh để giữ stack local; Publisher không pause claim vì Chrome cá nhân; không auto-approve DRAFT.

## Scope

- Windows local supervisor (`manage.py stack` / `start.ps1 -Stack`)
- Smart gate: `chrome_toolsauto_count` cho claim
- Orphan Chromium purge dưới `storage/profiles` (Windows-safe)
- Docs/handoff

## Out of scope

- Auto-approve DRAFT
- Thay PM2 VPS
- Kill Chrome user thường

## Implementation

| Piece | Path |
|-------|------|
| Supervisor | `app/platform/local_supervisor.py` |
| CLI | `manage.py stack` |
| Start script | `start.ps1 -Stack` |
| Chrome count | `app/core/observability/system_monitor.py` |
| Claim gate | `app/core/queue/publisher_runtime.py` `resource_blocks_claim` |
| Orphan purge | `SystemMonitorService.purge_orphan_toolsauto_browsers` + maintenance `_purge_zombies` |
| State | `storage/db/config/local_stack.json` (+ `.lock`) |

## Verify

- Chrome tổng cao, `chrome_toolsauto_count=0` → `resource_blocks_claim=False`
- `manage.py stack` singleton via lock
- DRAFT vẫn cần Owner approve

## Hardening (code review 2026-07-31)

| Vấn đề | Sửa |
|---|---|
| Token dotted không khớp cmdline PM2 (`app/features/.../publisher.py`) → purge giết browser worker sống, supervisor spawn trùng | `app/core/process_scan.py`: match cả 2 cách chạy, dùng chung cho monitor + supervisor |
| Marker `/ms-playwright/`, `storage/profiles` quá rộng | Chỉ nhận `--user-data-dir` nằm trong profile root chuẩn, hoặc có ancestor là worker ToolsAuto |
| `STATE_PATH`/`LOCK_PATH` theo cwd | Tuyệt đối theo `config.RUNTIME_CONFIG_DIR`; lock `O_CREAT\|O_EXCL` + thu hồi stale |
| `_profile_path_markers()` stat lại theo từng process | Tính 1 lần/scan; metadata process hydrate lazy (8.3s → 0.02s), đếm browser cache 30s |
| Purge có thể giết nhầm | Chỉ browser root, có bằng chứng profile, không ancestor sống, tuổi > 120s, chống PID reuse |

Metric mới: `chrome_toolsauto_count` = số **instance** browser (root), không phải số process.
