---
Status: Done (Archived)
Created: 2026-04-26
Archived: 2026-04-27
Assigned: Claude Code
Reference: ADR-006
---

# PLAN-022: Unify AI Pathway (ADR-006 Implementation)

## 1. Mục tiêu
Hợp nhất các luồng gọi AI về một mối `AICaptionPipeline`, triển khai cơ chế Fallback Native an toàn, minh bạch và cô lập theo ADR-006.

## 2. Các bước thực hiện

### Phase 1: Native Fallback (Owner: Codex)
1. **Tạo `app/services/ai_native_fallback.py`**:
   - Di chuyển logic gọi `google-genai` tối giản từ `gemini_api.py` sang đây.
   - Hàm chính: `call_native_gemini(prompt: str) -> Optional[str]`.
2. **Cập nhật `AICaptionPipeline`**:
   - Thêm phương thức `_generate_with_fallback(prompt)`.
   - Logic: `try 9Router -> if fail -> try Native Fallback -> if fail -> return Error`.
   - Đảm bảo `meta` trả về đủ: `ok`, `provider`, `model`, `fallback_used`, `primary_fail_reason`.
3. **Unit Test**:
   - Mock 9Router (fail) + Native (success) -> assert `fallback_used=True`.

### Phase 2: Migration & UI (Owner: Claude Code)
1. **Cập nhật Workers**:
   - `content_orchestrator.py`: Thay `GeminiAPIService` bằng `pipeline.generate_text`.
   - Xóa bỏ logic fallback thủ công trong worker (vì pipeline đã lo rồi).
2. **UI/UX Surface**:
   - `ai_reporter.py`: Nếu `meta["fallback_used"]` -> Thêm footer Telegram: `⚠️ Dự phòng: Gemini Native`.
   - Templates Dashboard: Thêm logic hiển thị Badge "Dự phòng" nếu report metadata có flag fallback.
3. **Cleanup**:
   - Xóa `GeminiAPIService` (hoặc giữ class rỗng với DeprecationWarning).

## 3. Quy tắc an toàn (Guardrails)
- **Max 2 Tiers**: Không fallback quá 2 lần để tránh loop.
- **Explicit Logging**: Ghi log `[AI FALLBACK]` kèm lý do lỗi của tầng 9Router.
- **Isolation**: `ai_pipeline.py` không được import trực tiếp `google.genai`, chỉ dùng wrapper từ `ai_native_fallback.py`.

## 4. Verification
- `pytest tests/test_ai_pipeline.py` (cập nhật thêm test case fallback).
- Chạy thử `workers/ai_reporter.py` với 9Router bị disable giả lập.

## 5. Anti Sign-off Gate
- [x] Module `ai_native_fallback.py` tồn tại và cô lập.
- [x] `AICaptionPipeline` trả về đúng metadata khi dùng fallback.
- [x] Content Orchestrator đã chuyển sang dùng chung pipeline (text path; vision path còn out-of-scope — xem §6.4).
- [x] UI Dashboard hiện được trạng thái Fallback.

**Chữ ký Anti:** [x] APPROVED / [ ] REJECTED — 2026-04-27

---

## 6. Execution Notes (Claude Code — 2026-04-27)

> **Bối cảnh:** Codex bị limit token, Claude Code đảm nhiệm toàn bộ Phase 1 + Phase 2 + Phase 3 (test).
> Phiên trước (2026-04-26) Claude Code chỉ kịp viết khung Phase 2.2 / 2.3 và hit token limit;
> phiên này (2026-04-27, sau reset) hoàn tất Phase 1 (native module + pipeline integration),
> Phase 2.1 (orchestrator), tinh chỉnh 2.2/2.3, viết toàn bộ test, smoke test live UI.

### 6.1. Files thay đổi

| File | Thay đổi |
|---|---|
| `app/services/ai_native_fallback.py` | **MỚI** (~135 LOC). Hàm `call_native_gemini(prompt) -> (text, meta)`. Lazy-import `google.genai`, model rotation 5 model với cooldown 60s, trả meta đầy đủ. ADR-006 isolation rule: chỉ file này import `google.genai` cho text path. |
| `app/services/ai_pipeline.py` | `generate_text()` rewrite. Tier 1 (9Router) → Tier 2 (native) → fail. Meta unified: `ok`, `provider`, `model`, `latency_ms`, `fallback_used`, `primary_fail_reason`, optional `fallback_failed`. Delegate native qua lazy import — KHÔNG import `google.genai` trực tiếp. |
| `app/services/gemini_api.py` | Module-level `DeprecationWarning` + docstring giải thích vì sao chưa xoá (vision/async path còn dùng — ngoài scope ADR-006). |
| `app/services/content_orchestrator.py` | Comment hoá block `_fallback_rpa_generation` để nói rõ tier `GeminiAPIService.ask_with_file` còn giữ vì vision path chưa có native fallback. **Block không bị xoá** — xem ghi chú lệch scope §6.4. |
| `workers/ai_reporter.py` | `build_report()` thêm header `<i>⚠️ Dự phòng: Gemini Native (model=..., 9Router fail_reason=...)</i>` khi `meta["fallback_used"]`. Log warning khi fallback active. |
| `app/routers/dashboard.py` | Route `GET /app/logs/ai-report/live` thêm yellow banner "FALLBACK MODE" + meta line dày đặc (`provider`, `model`, `fallback_used`, `generated_at`). |
| `tests/test_ai_pipeline.py` | Rewrite. 6 test (4 cũ updated + 2 mới): 200 OK / 429+native fail / disabled+native fail / 9R fail+native success / circuit open+native success / JSON parser. |
| `tests/test_ai_native_fallback.py` | **MỚI**. 4 test: no_api_key / first model success / 429 rotation / all fail. Mock `google.genai` qua `sys.modules` injection. |
| `tests/test_ai_reporter.py` | Thêm test `test_build_report_surfaces_fallback_warning_when_native_used` — assert header chứa "Dự phòng", model name, primary_fail_reason. |

### 6.2. Quy tắc ADR-006 đã tuân thủ tuyệt đối

- ✅ **Isolation**: `ai_pipeline.py` không có `from google import genai` ở đâu hết. Chỉ `from app.services.ai_native_fallback import call_native_gemini` (lazy, trong function body).
- ✅ **Cap 2 tier**: nếu native cũng fail → return `{ok: False, fallback_used: True, fallback_failed: True}`. KHÔNG cascade tiếp.
- ✅ **Explicit logging**: `[AI FALLBACK]` prefix cho cả native module + pipeline + ai_reporter.
- ✅ **Meta unified**: tất cả path (success / fail / fallback) đều có `fallback_used` key — caller không phải kiểm tra `if "fallback_used" in meta`.
- ✅ **Surface UX**: Telegram header + Dashboard yellow banner. Người dùng KHÔNG thể bỏ qua khi đang ở fallback mode.

### 6.3. Verification Proof

**a) Compile sạch:**
```
$ venv/bin/python -m py_compile app/services/ai_native_fallback.py app/services/ai_pipeline.py
                                 app/services/gemini_api.py app/services/content_orchestrator.py
                                 workers/ai_reporter.py app/routers/dashboard.py
# exit 0
```

**b) Pytest baseline + new tests — 18/18 PASS:**
```
$ venv/bin/pytest tests/test_ai_pipeline.py tests/test_ai_reporter.py
                  tests/test_ai_native_fallback.py tests/test_incident_logger.py -v
collected 18 items

tests/test_ai_pipeline.py::test_generate_text_http_200_returns_text_and_ok_meta PASSED
tests/test_ai_pipeline.py::test_generate_text_http_429_records_circuit_failure_and_invokes_fallback PASSED
tests/test_ai_pipeline.py::test_generate_text_disabled_still_tries_native_fallback PASSED
tests/test_ai_pipeline.py::test_generate_text_9router_fail_native_success_marks_fallback_used PASSED
tests/test_ai_pipeline.py::test_generate_text_circuit_open_does_not_call_9router_but_tries_native PASSED
tests/test_ai_pipeline.py::test_extract_and_parse_json_valid_and_invalid PASSED
tests/test_ai_reporter.py::test_build_report_uses_mock_pipeline PASSED
tests/test_ai_reporter.py::test_build_report_surfaces_fallback_warning_when_native_used PASSED
tests/test_ai_reporter.py::test_build_report_falls_back_when_pipeline_fails PASSED
tests/test_ai_reporter.py::test_build_report_empty_groups_returns_heartbeat_without_pipeline PASSED
tests/test_ai_reporter.py::test_incident_rows_for_prompt_formats_operational_fields PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_no_api_key_returns_disabled PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_first_model_succeeds PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_429_rotates_then_succeeds PASSED
tests/test_ai_native_fallback.py::test_call_native_gemini_all_models_fail PASSED
tests/test_incident_logger.py::test_redact_context_removes_sensitive_keys_and_masks_token_values PASSED
tests/test_incident_logger.py::test_build_error_signature_uses_error_type_and_normalized_message PASSED
tests/test_incident_logger.py::test_log_incident_upserts_group_count PASSED

============================== 18 passed in 2.16s ==============================
```

**c) FastAPI live UI smoke — 7/7 checks PASS** (TestClient + cookie auth giả + stub `pipeline.generate_text`):
```
  [OK] badge text: 'FALLBACK MODE'
  [OK] banner mentions native: 'Native Gemini'
  [OK] surfaced primary_fail_reason: 'circuit_open'
  [OK] meta line shows flag: 'fallback_used=True'
  [OK] model name shown: 'gemini-2.5-flash'
  [OK] markdown rendered to body: 'Mock report'
  [OK] negative: no FALLBACK badge when fallback_used=False
--- ALL UI SMOKE CHECKS PASS ---
```

### 6.4. Lệch scope so với PLAN gốc — đã ghi rõ, có lý do

PLAN §2 Phase 2.1 nói: *"`content_orchestrator.py`: Thay `GeminiAPIService` bằng `pipeline.generate_text`. Xóa bỏ logic fallback thủ công trong worker (vì pipeline đã lo rồi)."*

**Thực tế:** block `GeminiAPIService` ở line 547 orchestrator gọi `api_fallback.ask_with_file(prompt, target_image)` — đây là **vision path** (image + prompt → JSON), KHÔNG phải text path. `pipeline.generate_text` không thay được vì nó text-only. Vision path canonical là `pipeline.generate_caption(prompt, image)` ở line 504, NHƯNG `generate_caption` chưa có native vision fallback (chỉ `generate_text` có theo ADR-006 Phase 1).

→ Nếu xoá block này theo literal PLAN, sẽ **mất behavior** (vision tier API fallback biến mất, hệ thống chỉ còn RPA → Poorman, downgrade reliability).

→ Quyết định: **giữ block** + thêm comment giải thích lý do còn giữ + flag là follow-up. Đây là conservative move đúng theo CLAUDE.md rule "không phá behavior khi chưa có thay thế tương đương".

**Đề xuất follow-up task** (chưa mở):
- TASK-025 (gợi ý): Mở rộng ADR-006 cho vision path. Tạo `pipeline.generate_caption_with_native_fallback()` hoặc gắn `call_native_gemini_vision()` vào `ai_native_fallback.py`. Sau đó mới được xoá block `ask_with_file` trong orchestrator.
- TASK-026 (gợi ý): Migrate `ask_async` (chỉ caller là `workers/threads_auto_reply.py`) — async wrapper qua `pipeline.generate_text_async` nếu cần.

### 6.5. Tổng kết

| Metric | Giá trị |
|---|---|
| File mới | 2 (`ai_native_fallback.py`, `test_ai_native_fallback.py`) |
| File sửa | 6 (`ai_pipeline.py`, `gemini_api.py`, `content_orchestrator.py`, `ai_reporter.py`, `dashboard.py`, 2 test files) |
| Test mới + cập nhật | 18/18 PASS (4 native + 6 pipeline + 5 reporter + 3 incident) |
| Live UI smoke | 7/7 PASS |
| `gemini_api.py` callers còn lại | 7 (vision/async — out of scope ADR-006) |
| ADR-006 isolation rule | ✅ `ai_pipeline.py` không import `google.genai` |
| ADR-006 cap 2 tier rule | ✅ |
| ADR-006 surface UX rule | ✅ Telegram header + Dashboard banner |

**Sẵn sàng cho Anti Sign-off Gate.**
