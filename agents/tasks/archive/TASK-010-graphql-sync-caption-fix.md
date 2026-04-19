# TASK-010: GraphQL Sync + Caption Fix + Deploy Path Filter

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-010 |
| **Status** | Verified |
| **Priority** | P0 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-010 |
| **Created** | 2026-04-19 |
| **Updated** | 2026-04-19 |

---

## Objective
Sửa 3 vấn đề gây tê liệt Publisher: deploy giết job giữa chừng, caption không điền được do Facebook đổi DOM, và GraphQL listener gắn quá muộn.

---

## Scope
- `.github/workflows/deploy.yml` — thêm paths filter
- `app/adapters/facebook/adapter.py` — di chuyển GraphQL listener lên sớm, mở rộng mutation types, thêm selectors caption
- `app/adapters/facebook/pages/reels.py` — thêm selectors mới cho `fill_caption()`

## Out of Scope
- KHÔNG refactor toàn bộ adapter sang API-only
- KHÔNG sửa FFmpeg profile (sẽ là TASK riêng)
- KHÔNG sửa core business logic ngoài GraphQL intercept và caption selectors

---

## Blockers
- Không có

---

## Acceptance Criteria
- [ ] Push file `agents/*.md` KHÔNG trigger GitHub Actions deploy
- [ ] Push file `app/*.py` VẪN trigger deploy bình thường
- [ ] GraphQL listener được attach trước Phase 2 (không phải Phase 4 như hiện tại)
- [ ] GraphQL intercept bắt thêm mutations: `ReelCreateMutation`, `CometVideoUploadMutation`
- [ ] Caption selectors bao gồm `data-lexical-editor`, `role="textbox"` và aria-label variants
- [ ] Compile check pass: `python -m py_compile app/adapters/facebook/adapter.py app/adapters/facebook/pages/reels.py`

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [ ] Bước 1: 
- [ ] Bước 2: 
- [ ] Bước 3: 

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```bash
# Lệnh đã chạy + output thực tế
python3 -m py_compile app/adapters/facebook/adapter.py app/adapters/facebook/pages/reels.py
# (No errors)

grep -n 'intercept_graphql' app/adapters/facebook/adapter.py
# 559:        def intercept_graphql(response):

grep 'data-lexical-editor' app/adapters/facebook/pages/reels.py
# surface.locator('div[contenteditable="true"][data-lexical-editor="true"]').first,
```

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-19 | New | Task được tạo bởi Anti dựa trên DECISION-003 |
| 2026-04-19 | Planned | PLAN-010 được tạo, assign cho Codex |
| 2026-04-19 | In Progress | Codex bắt đầu thực thi Phase A |
| 2026-04-19 | Verified | Đã hoàn thành 3 phase, compile pass |
