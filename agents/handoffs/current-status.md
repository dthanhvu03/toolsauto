# Current Status

## System State

- **Product**: ToolsAuto — auto-publish (Facebook / Threads + related).
- **Local Windows**: **http://127.0.0.1:8002** (`.\start.ps1`).
- **AI**: Feature code → **`AIUseCases`** (facade + domain prompts); transport = `AICaptionPipeline` (9Router → Gemini).

## Done This Session [2026-07-23]

### AIUseCases tầng 2 (đào sâu)
- Domain methods + prompts gom vào `app/core/ai/use_cases.py`:
  - affiliate comment/bundle, compliance rewrite, threads reply, incident report
  - `is_enabled()` thay `pipeline.enabled`
- Callers thin: `affiliate_text`, affiliates `ai_generate`, `facebook_compliance.rewrite`, Threads `auto_reply`, `ai_reporter`, dashboard live report.
- Dọn: orchestrator bỏ `sys_pipeline`; strategic dùng `AIUseCases.is_enabled()`.
- ADR-006 §6: canonical entry = `AIUseCases`.
- Test: `tests/test_ai_use_cases.py` (mock pipeline).

### Tầng 1 trước đó
- Primitive facade + migrate call sites + `meta["purpose"]`.

## Next Action

1. (Optional) Syspanel 9Router tuner vẫn đọc `pipeline` — OK (ops).
2. Commit khi user yêu cầu.
