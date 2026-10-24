# PLAN-077 — Customer Terms, Tax & Payout Policy Readiness V1

| | |
|---|---|
| Trạng thái | **CODE + TEST XONG, CHỜ RELEASE REVIEW.** Production Deployment: NOT AUTHORIZED UNTIL REVIEW |
| Executor | Claude Code (chủ bot giao trực tiếp ngày 2026-10-24) |
| Đầu vào | `main@cca8f8c` (code production `13eb3f5`), ADR-050, ADR-053 |
| Nhánh | `cursor/cashback-plan077-terms`, worktree `/home/vu/toolsauto-cashback-terms` |
| ADR | ADR-054 |

## Scope
- Điều khoản theo phiên bản; chấp thuận thật; liên kết link ↔ phiên bản điều khoản.
- Dự thảo điều khoản V1 (DRAFT, chưa công bố).
- `/hotro` và ticket hỗ trợ; màn admin 📩 Hỗ trợ, 📋 Điều khoản, ⚖️ Sẵn sàng chi trả.
- Bản đồ thuế và bảng quyết định thu hồi hoa hồng (PENDING_REVIEW).
- Audit dữ liệu cá nhân; chặn link `unresolved` ở cổng tài chính.

**Không làm:** công bố điều khoản, bật bắt buộc đồng ý, gửi tin hàng loạt, chọn mức thuế, chọn chính sách thu hồi, mở ví, payout.

## Proof — Claude Code, 2026-10-24
- Baseline 493 passed. Sau PLAN-077: **521 passed** (+28 `tests/test_cashback_terms_support.py`), ruff sạch.
- Diễn tập trên bản sao DB production (0600, đã xoá): thêm 5 bảng trống; bảng cũ không đổi (hash, trừ `updated_at` sổ ví); 2 khoản pending giữ số; 0 link chưa chứng minh chính sách; khoá còn; integrity ok.
- Báo cáo: `reports/CASHBACK_PLAN077_TERMS_POLICY.md`.
