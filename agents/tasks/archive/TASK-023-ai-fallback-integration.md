# TASK-023: Implement AI Native Fallback & Pipeline Integration

**Status:** Done  
**Priority:** P3  
**Type:** Backend / System  
**Owner:** Claude Code  
**Created:** 2026-04-26  
**Reference:** ADR-006 (Consensus A + Guardrails)

---

## Objective
Xây dựng tầng dự phòng (Native Fallback) cho AI Pipeline để đảm bảo hệ thống không bị gián đoạn khi 9Router sập, đồng thời giữ kiến trúc cô lập.

## Acceptance Criteria
- [x] Tạo module `app/services/ai_native_fallback.py` cô lập hoàn toàn logic Google GenAI SDK.
- [x] `AICaptionPipeline` gọi 9Router trước, nếu fail (và Circuit Breaker cho phép) thì gọi Native Fallback.
- [x] Metadata trả về phải có `fallback_used: bool` và `fail_reason` của tầng primary (`primary_fail_reason`).
- [x] Test coverage: 9Router fail -> Native success, Cả 2 fail (18/18 pytest pass).
- [x] Không được có silent failure: Log `[AI FALLBACK]` khi switch.

## Status History
- 2026-04-26: `New` — Created by Antigravity
- 2026-04-26: `Reassigned` — Moved from Codex to Claude Code due to token limits.
- 2026-04-27: `Done` — Phase 1 implementation hoàn tất, Anti APPROVED tại PLAN-022 Sign-off Gate.
