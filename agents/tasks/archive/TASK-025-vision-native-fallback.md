# TASK-025: Native Fallback cho Vision Path (Multimodal)

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-025 |
| **Status** | Done |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Claude Code |
| **Related Plan** | PLAN-025 |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Objective
Mở rộng cơ chế dự phòng Native Gemini (ADR-006) cho luồng xử lý hình ảnh và video để đảm bảo tính ổn định của pipeline sinh Caption.

---

## Scope
- Triển khai `call_native_gemini_vision` trong `app/services/ai_native_fallback.py`.
- Tích hợp Tier 2 fallback vào method `generate_caption` của `AICaptionPipeline`.
- Cập nhật `ContentOrchestrator` để sử dụng pipeline thay vì gọi trực tiếp legacy API.

---

## Acceptance Criteria
- [x] `call_native_gemini_vision` hoạt động đúng với model rotation.
- [x] `generate_caption` tự động chuyển sang Native khi 9Router lỗi vision.
- [x] Codebase sạch bóng các lời gọi legacy `ask_with_file` trong luồng chính (chỉ còn RPA path `GeminiRPAService` — out of scope theo DECISION-006 §2.2 vote).
- [x] Dashboard hiển thị đúng banner "FALLBACK MODE" cho tác vụ vision (banner code generic, đọc `meta.fallback_used` đã có trong contract của `generate_caption`).

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-27 | New | Task được tạo bởi Anti theo yêu cầu mở rộng ADR-006 |
| 2026-04-27 | In Progress | Claude Code bắt đầu Phase 4 — đọc PLAN-025, xác nhận API surface khớp với spec, tiến hành code |
| 2026-04-27 | Done (Awaiting Sign-off) | Code + 8 test mới + smoke UI hoàn tất; Verification Proof đã điền |

---

## Verification Proof

### Files thay đổi

| File | Thay đổi |
|---|---|
| `app/services/ai_native_fallback.py` | Thêm `NATIVE_VISION_MODELS = ["gemini-2.5-flash","gemini-2.0-flash","gemini-2.5-pro"]`, hàm `call_native_gemini_vision(prompt, image_path)` (~95 LOC) + helper `_path_exists`. Lazy-import `google.genai` + `PIL.Image` chỉ khi function chạy. Cooldown registry dùng chung với text path (rate-limit là per-model phía Google). |
| `app/services/ai_pipeline.py` | `generate_caption()` rewrite Tier 1→Tier 2: 9Router fail → call native vision → parse JSON → return `(CaptionPayload, meta)`. Meta unified: thêm `fallback_used`, `primary_fail_reason`, optional `fallback_failed`. **KHÔNG có dòng `from google import genai`** — delegate qua lazy import từ `ai_native_fallback`. |
| `app/services/content_orchestrator.py` | Xoá block 7 dòng `from app.services.gemini_api import GeminiAPIService; api_fallback = GeminiAPIService(); raw_json = api_fallback.ask_with_file(...)` ở `_fallback_rpa_generation`. Thay bằng comment giải thích: pipeline (gồm cả native vision) đã cover, chỉ còn RPA → poorman. |
| `tests/test_ai_native_fallback.py` | +4 test vision: no_api_key / image_not_found / first model success (verify prompt + image forwarded) / 429 rotation across vision models. |
| `tests/test_ai_pipeline.py` | +4 test `generate_caption`: 9Router success no fallback / 9Router fail + native vision success / both tiers fail / no_image skips native vision. |

### ADR-006 Isolation Rule — Verified

```
$ grep -n "from google" app/services/ai_pipeline.py app/services/content_orchestrator.py
# (no matches except a comment "must NOT import google.genai directly (ADR-006)")

$ grep -n "from google import genai" app/services/ai_native_fallback.py
88:        from google import genai            # text path lazy import
194:       from google import genai            # vision path lazy import
```

✅ `ai_native_fallback.py` là module DUY NHẤT import `google.genai` cho cả text và vision path.

### Pytest — 26/26 PASS (tăng 8 test mới so với baseline 18)

```
$ venv/bin/pytest tests/test_ai_pipeline.py tests/test_ai_native_fallback.py
                  tests/test_ai_reporter.py tests/test_incident_logger.py -v
collected 26 items

tests/test_ai_pipeline.py::test_generate_text_http_200_returns_text_and_ok_meta PASSED
tests/test_ai_pipeline.py::test_generate_text_http_429_records_circuit_failure_and_invokes_fallback PASSED
tests/test_ai_pipeline.py::test_generate_text_disabled_still_tries_native_fallback PASSED
tests/test_ai_pipeline.py::test_generate_text_9router_fail_native_success_marks_fallback_used PASSED
tests/test_ai_pipeline.py::test_generate_text_circuit_open_does_not_call_9router_but_tries_native PASSED
tests/test_ai_pipeline.py::test_generate_caption_9router_success_no_fallback PASSED
tests/test_ai_pipeline.py::test_generate_caption_9router_fail_native_vision_succeeds PASSED
tests/test_ai_pipeline.py::test_generate_caption_both_tiers_fail_returns_error_meta PASSED
tests/test_ai_pipeline.py::test_generate_caption_no_image_skips_native_vision PASSED
tests/test_ai_pipeline.py::test_extract_and_parse_json_valid_and_invalid PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_no_api_key_returns_disabled PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_first_model_succeeds PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_429_rotates_then_succeeds PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_vision_no_api_key_returns_disabled PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_vision_image_not_found_returns_error PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_vision_first_model_succeeds PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_vision_429_rotates_to_next_vision_model PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_all_models_fail PASSED
tests/test_ai_reporter.py::test_build_report_uses_mock_pipeline PASSED
tests/test_ai_reporter.py::test_build_report_surfaces_fallback_warning_when_native_used PASSED
tests/test_ai_reporter.py::test_build_report_falls_back_when_pipeline_fails PASSED
tests/test_ai_reporter.py::test_build_report_empty_groups_returns_heartbeat_without_pipeline PASSED
tests/test_ai_reporter.py::test_incident_rows_for_prompt_formats_operational_fields PASSED
tests/test_incident_logger.py::test_redact_context_removes_sensitive_keys_and_masks_token_values PASSED
tests/test_incident_logger.py::test_build_error_signature_uses_error_type_and_normalized_message PASSED
tests/test_incident_logger.py::test_log_incident_upserts_group_count PASSED

============================== 26 passed in 1.03s ==============================
```

### Live UI Banner Smoke — 6/6 PASS

Stub `pipeline.generate_text` để trả meta SHAPE giống `generate_caption` (`provider=native_gemini_vision`, `fallback_used=True`, `primary_fail_reason="rate_limited"`). Verify dashboard route `/app/logs/ai-report/live` render đúng banner cho meta shape của vision tier:

```
  [OK] yellow banner badge: 'FALLBACK MODE'
  [OK] vision provider name surfaced: 'native_gemini_vision'
  [OK] primary_fail_reason from vision tier-1 surfaced: 'rate_limited'
  [OK] meta line shows flag for vision response too: 'fallback_used=True'
  [OK] vision model name shown: 'gemini-2.5-flash'
  [OK] markdown body rendered: 'Vision regression check'
--- PLAN-025 UI banner generic-shape smoke PASS ---
```

### Audit `ask_with_file` còn lại (acceptance #3)

```
$ grep -rn "ask_with_file" app/services/ workers/ --include="*.py"
app/services/gemini_rpa.py:179:    def ask_with_file(...)        ← RPA Playwright (out of scope DECISION-006 §2.2)
app/services/gemini_api.py:11:                                   ← Docstring only (deprecated module)
app/services/gemini_api.py:222:   def ask_with_file(...)         ← Definition (deprecated)
app/services/gemini_api.py:300:                                   ← Internal error log (deprecated)
app/services/content_orchestrator.py:540:                        ← self.gemini.ask_with_file = GeminiRPAService (RPA)
```

**Kết luận**: Trong main caption flow của `content_orchestrator`, không còn lời gọi nào tới `GeminiAPIService.ask_with_file` (legacy native API). Lời gọi `ask_with_file` duy nhất còn lại là RPA path qua `GeminiRPAService` (Playwright cookie session) — đây là quyết định cố ý của DECISION-006 §2.2 (Codex vote: "giữ `gemini_rpa.py` riêng").

### Tổng kết

| Metric | Giá trị |
|---|---|
| File mới | 0 |
| File sửa | 5 (`ai_native_fallback.py`, `ai_pipeline.py`, `content_orchestrator.py`, 2 test files) |
| Hàm mới | 1 (`call_native_gemini_vision` ~95 LOC) + helper `_path_exists` |
| Test thêm | 8 (4 native vision + 4 pipeline.generate_caption) — tổng baseline 18 → 26 |
| ADR-006 isolation | ✅ `ai_pipeline.py` không import `google.genai` |
| Cap 2 tier | ✅ |
| Surface UX banner | ✅ generic, render đúng cho cả text path lẫn vision path |
| Legacy GeminiAPIService trong main caption flow | ✅ đã xoá |
