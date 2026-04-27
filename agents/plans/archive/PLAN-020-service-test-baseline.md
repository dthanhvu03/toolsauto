---
Status: Done (Archived)
Created: 2026-04-26
Archived: 2026-04-26
Assigned: Codex
Reference: DECISION-006 §2.6
---

# PLAN-020: Service Test Baseline (Incident + AI Pipeline)

## 1. Mục tiêu
Xây dựng bộ test nền tảng cho các service mới (TASK-018/019) và AI pipeline.
Đây là prerequisite bắt buộc trước khi thực hiện refactor models.py (TASK-022) và AI unify.

## 2. Scope — 3 test files

### 2.1. `tests/test_incident_logger.py`
- Test `redact_context()`: assert các key nhạy cảm (cookie, token, password, proxy_auth) bị thay bằng `[REDACTED]`
- Test `build_error_signature()`: assert SHA1 hash từ error_type + normalized message
- Test UPSERT logic: tạo IncidentGroup mới → gọi log_incident lần 2 cùng signature → assert count tăng lên 2
- Dùng test DB session (SQLite in-memory hoặc test PostgreSQL)

### 2.2. `tests/test_ai_reporter.py`
- Test `build_report()` với mock `pipeline.generate_text` trả về text → assert output chứa `<b>Daily Health Report</b>`
- Test `build_report()` khi pipeline fail → assert fallback report được tạo
- Test `build_report()` khi groups rỗng → assert "Không có incident mới"
- Test `_incident_rows_for_prompt()` format đúng

### 2.3. `tests/test_ai_pipeline.py`
- Test `generate_text()` với mock HTTP 200 → assert trả về (text, meta) với meta["ok"]=True
- Test `generate_text()` với mock HTTP 429 → assert circuit breaker ghi nhận failure
- Test `generate_text()` khi disabled → assert meta["fail_reason"]="router_disabled"
- Test `_extract_and_parse_json()` với JSON hợp lệ và không hợp lệ

## 3. Quy tắc
- Mock external: `requests.post` (9Router), Telegram API, Playwright
- Dùng `pytest` + `unittest.mock.patch`
- KHÔNG gọi live API trong test mặc định
- Test phải chạy nhanh (< 5 giây tổng)

## 4. Verification
```bash
cd /home/vu/toolsauto && source venv/bin/activate
pytest tests/test_incident_logger.py tests/test_ai_reporter.py tests/test_ai_pipeline.py -v
```
- Tất cả test PASS
- Không có warning/error liên quan import

## 4.1. Execution Notes

- 2026-04-26 Codex: Thêm `tests/test_incident_logger.py` cover `redact_context`, `build_error_signature`, và UPSERT `IncidentLogger.log_incident()` trên PostgreSQL session hiện tại. Test dọn `incident_logs`/`incident_groups` theo synthetic signature trước/sau khi chạy.
- 2026-04-26 Codex: Thêm `tests/test_ai_reporter.py` cover `build_report()` với mock `pipeline.generate_text`, fallback khi pipeline fail, heartbeat khi không có group, và format `_incident_rows_for_prompt()`.
- 2026-04-26 Codex: Thêm `tests/test_ai_pipeline.py` cover `AICaptionPipeline.generate_text()` với mock `requests.post` cho HTTP 200/429, router disabled, và `_extract_and_parse_json()` với JSON hợp lệ/không hợp lệ.
- 2026-04-26 Codex: Execution Done. Cần Claude Code verify + handoff / Anti sign-off gate.

## 4.2. Verification Proof

Command:

```bash
cd /home/vu/toolsauto && source venv/bin/activate && pytest tests/test_incident_logger.py tests/test_ai_reporter.py tests/test_ai_pipeline.py -v
```

Output:

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0 -- /home/vu/toolsauto/venv/bin/python3
cachedir: .pytest_cache
rootdir: /home/vu/toolsauto
plugins: anyio-4.12.1
collecting ... collected 11 items

tests/test_incident_logger.py::test_redact_context_removes_sensitive_keys_and_masks_token_values PASSED [  9%]
tests/test_incident_logger.py::test_build_error_signature_uses_error_type_and_normalized_message PASSED [ 18%]
tests/test_incident_logger.py::test_log_incident_upserts_group_count PASSED [ 27%]
tests/test_ai_reporter.py::test_build_report_uses_mock_pipeline PASSED   [ 36%]
tests/test_ai_reporter.py::test_build_report_falls_back_when_pipeline_fails PASSED [ 45%]
tests/test_ai_reporter.py::test_build_report_empty_groups_returns_heartbeat_without_pipeline PASSED [ 54%]
tests/test_ai_reporter.py::test_incident_rows_for_prompt_formats_operational_fields PASSED [ 63%]
tests/test_ai_pipeline.py::test_generate_text_http_200_returns_text_and_ok_meta PASSED [ 72%]
tests/test_ai_pipeline.py::test_generate_text_http_429_records_circuit_failure PASSED [ 81%]
tests/test_ai_pipeline.py::test_generate_text_disabled_returns_router_disabled PASSED [ 90%]
tests/test_ai_pipeline.py::test_extract_and_parse_json_valid_and_invalid PASSED [100%]

============================== 11 passed in 1.00s ==============================
```

## 5. Anti Sign-off Gate
- [x] 3 test files tồn tại và chạy pass
- [x] Mock đúng (không gọi live API)
- [x] Coverage cho redact, signature, UPSERT, report build, pipeline text
- [x] Test chạy < 5 giây (actual: 0.89s)

**Chữ ký Anti:** [x] APPROVED / [ ] REJECTED
