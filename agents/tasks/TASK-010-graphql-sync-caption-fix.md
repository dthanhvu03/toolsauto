# TASK-010: Đồng bộ GraphQL + Fix Caption Drift + Deploy Path Filter

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-010 |
| **Status** | New |
| **Priority** | P0 — Critical |
| **Owner** | Antigravity |
| **Executor** | Antigravity (trực tiếp) |
| **Related Plan** | PLAN-010 |
| **Related ADR** | DECISION-003 |
| **Created** | 2026-04-19 |
| **Updated** | 2026-04-19 |

---

## Objective
Sửa 3 vấn đề gây tê liệt Publisher hiện tại:
1. **Deploy path filter** — Ngăn push agent docs trigger deploy, giúp Publisher không bị giết giữa chừng.
2. **Caption area not found** — Facebook đổi DOM Reels Step 3, selector cũ không tìm thấy ô caption.
3. **GraphQL đồng bộ** — Tăng cường sử dụng GraphQL intercept xuyên suốt flow, không chỉ ở Phase 4, để xác minh nhanh và đáng tin hơn.

---

## Scope

### Phase A: Deploy Path Filter (deploy.yml)
- Thêm `paths` filter để chỉ deploy khi thay đổi code thực sự
- Bỏ qua `agents/`, `docs/`, `CLAUDE.md`, `README.md`

### Phase B: Caption Selector Fix (adapter.py + reels.py) 
- Debug DOM Facebook Reels Step 3 mới
- Cập nhật selector trong `fill_caption()` + `adapter.py` Phase 3
- Thêm fallback selector layers

### Phase C: GraphQL Sync Enhancement (adapter.py)
- Gắn GraphQL response listener sớm hơn (từ Phase 1, không chỉ Phase 4)
- Intercept thêm mutation types: `ComposerStoryCreateMutation`, `VideoPublishMutation`, `ReelCreateMutation`
- Dùng GraphQL response để xác nhận upload thành công sớm, giảm timeout DOM-based
- Cải thiện error handling khi GraphQL trả về error payload

## Out of Scope
- KHÔNG refactor toàn bộ adapter sang API-only (quá rủi ro, cần browser cho login/session)
- KHÔNG sửa FFmpeg profile (TASK-011 riêng)

---

## Blockers
- Cần screenshot DOM thực tế từ VPS để xác nhận selector mới cho caption

---

## Acceptance Criteria
- [ ] Push file `agents/*.md` KHÔNG trigger GitHub Actions deploy
- [ ] Push file `app/*.py` VẪN trigger deploy bình thường
- [ ] Caption được điền thành công ở Reels Step 3 (không còn WARNING "Caption area not found")
- [ ] GraphQL listener bắt được `post_id` sớm hơn, giảm thời gian chờ DOM verification
- [ ] Compile check pass: `python -m py_compile app/adapters/facebook/adapter.py app/adapters/facebook/pages/reels.py`

---

## Execution Notes
*(Điền vào trong khi làm)*

- [ ] Phase A: 
- [ ] Phase B: 
- [ ] Phase C: 

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```
# Lệnh đã chạy + output thực tế
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-19 | New | Task được tạo bởi Anti dựa trên DECISION-003 |
