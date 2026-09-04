# TASK-050 — Hàng đợi nhận mọi job_type

## Plan
PLAN-052

## Executor
Claude Code (ngoại lệ theo ADR-010)

## Acceptance
- [x] `claim_next_job` không liệt kê cứng job_type
- [x] FEED + STORY đến hạn được claim
- [x] Job chưa đến hạn vẫn bị chặn
- [x] Suite 184 passed

## Notes
Phát hiện khi khảo sát cho Combo 2 — bug có sẵn, không phải do đợt này gây ra.
