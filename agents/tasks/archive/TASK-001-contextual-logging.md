# TASK-001: Triển khai Contextual Logging (Job ID) cho FacebookAdapter

## Objective
Gắn `[Job ID]` vào mọi dòng log phát ra từ FacebookAdapter để hỗ trợ vận hành đa luồng (multi-worker) mà không bị loạn log.

## Scope
- Modify `app/adapters/facebook/adapter.py`.
- Define `JobLoggerAdapter`.
- Initialize it in `publish()`.
- Refactor all log calls within `FacebookAdapter` and its child pages (`reels.py`).

## Priority
P1 (Core refinement)

## Owner
Claude (Refactor & UX Specialist)

## Blockers
- None.

## Acceptance Criteria
- [ ] Log trong `logs/app.log` có tiền tố `[Job XXX]` cho mọi hành động của FacebookAdapter.
- [ ] Không làm gãy logic publish hiện tại.
- [ ] Đã kiểm tra bằng cách chạy ít nhất 1 Job và check log.

## Verification Snapshot (2026-04-18)
- `python3 -m py_compile app/adapters/facebook/adapter.py app/adapters/facebook/pages/reels.py` ✅
- `grep -n "logger." ... | grep -v "self.logger"` trên `adapter.py` và `reels.py` trả về rỗng ✅ (không còn logger trần trong class).
- Runtime log hiện có chưa phải bằng chứng sau refactor:
  - `logs/app.log`: `FacebookAdapter:` = 89 dòng, có `Job` = 0 dòng.
  - `logs/app.log.2026-04-17`: `FacebookAdapter:` = 163 dòng, có `Job` = 0 dòng.
  - `pm2 ls --no-color`: không có process đang chạy.

## Next Step
- Chạy UAT runtime có kiểm soát (ít nhất 1 Job publish) trên code hiện tại, sau đó xác nhận `logs/app.log` xuất hiện prefix `[Job <id>]` cho các dòng từ `FacebookAdapter` và `FacebookReelsPage`.
