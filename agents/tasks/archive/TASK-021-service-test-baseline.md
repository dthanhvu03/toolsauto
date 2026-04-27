# TASK-021: Service Test Baseline (Incident + AI Pipeline)

**Status:** Done  
**Priority:** P1  
**Type:** Quality / Testing  
**Owner:** Codex  
**Created:** 2026-04-26  
**Reference:** DECISION-006 §2.6, Vote 2/3 đồng ý sớm  

---

## Objective
Viết bộ test nền tảng cho các service mới từ TASK-018/019 và AI pipeline, đảm bảo có safety net trước khi thực hiện các refactor tiếp theo (models split, AI unify).

## Acceptance Criteria
- [x] Unit test cho `incident_logger.py`: redact_context, build_error_signature, UPSERT logic
- [x] Unit test cho `ai_reporter.build_report()` với mock pipeline
- [x] Unit test cho `ai_pipeline.generate_text()` với mock 9Router HTTP
- [x] Tất cả test pass với `pytest -v`
- [x] External API (9Router/Telegram/Playwright) phải mock, không gọi live

## Status History
- 2026-04-26: `Planned` — Created by Antigravity
- 2026-04-26: `Done` — Tests implemented by Codex, verified by Anti.
