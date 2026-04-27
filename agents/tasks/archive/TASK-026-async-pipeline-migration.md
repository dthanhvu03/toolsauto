# TASK-026: Async Pipeline & Threads Caller Migration

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-026 |
| **Status** | Done |
| **Priority** | P2 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-026 |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Objective
Cung cấp async interface cho AI Pipeline và di chuyển worker Threads auto-reply sang sử dụng pipeline mới để dứt điểm việc tách rời legacy code.

---

## Scope
- Triển khai `generate_text_async` trong `AICaptionPipeline`.
- Cập nhật `workers/threads_auto_reply.py` để sử dụng async pipeline.
- Đảm bảo cơ chế fallback Tier 2 hoạt động chính xác trong môi trường async.

---

## Acceptance Criteria
- [ ] `generate_text_async` trả về kết quả đúng với 2 tầng fallback.
- [ ] Worker Threads không còn phụ thuộc vào `GeminiAPIService.ask`.
- [ ] Dashboard ghi nhận chính xác các request từ Threads worker.

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-27 | New | Task được tạo bởi Anti để hoàn thiện việc migrate text callers |
| 2026-04-27 | Assigned | Reassigned to Codex (Claude Code limit token) |
| 2026-04-27 | Verified | Codex implemented async pipeline/fallback, migrated Threads worker, and recorded proof |

---

## Verification Proof
```
Command:
python -m py_compile app\services\ai_pipeline.py app\services\ai_native_fallback.py workers\threads_auto_reply.py tests\test_ai_pipeline_async.py

Output:
exit code 0

Command:
pytest -q tests\test_ai_pipeline_async.py tests\test_ai_pipeline.py tests\test_ai_native_fallback.py

Output:
.......................                                                  [100%]
23 passed in 2.63s

Command:
Select-String -Path 'app\services\ai_pipeline.py' -Pattern '^\s*(from google|import google|from google\.genai|import google\.genai)'

Output:
exit code 0, no matches

Command:
Select-String -Path 'workers\threads_auto_reply.py' -Pattern 'GeminiAPIService|generate_text_async|app.services.ai_runtime'

Output:
workers\threads_auto_reply.py:22:from app.services.ai_runtime import pipeline
workers\threads_auto_reply.py:76:                    ai_reply, ai_meta = await pipeline.generate_text_async(prompt)
```

Execution Done. Cần Claude Code verify + handoff.

Note: Manual `threads_auto_reply.py` live run was not executed because it can open a real Threads session and post replies. Automated proof covers async pipeline behavior, ADR-006 isolation, and the worker callsite migration.
