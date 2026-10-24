# PLAN-078 — Wallet & Payout Readiness V1

| | |
|---|---|
| Trạng thái | **CODE READY, CHỜ RELEASE REVIEW (Gate A).** Gate B (Financial Activation): NOT AUTHORIZED |
| Executor | Claude Code (chủ bot giao trực tiếp ngày 2026-10-24) |
| Đầu vào | `main@88ebf63` (production `5a14fc1`), ADR-049/050/052/053/054 |
| Nhánh | `cursor/cashback-plan078-payout`, worktree `/home/vu/toolsauto-cashback-payout` |
| ADR | ADR-055 |

## Scope
Sổ ví truy vết theo đơn; máy trạng thái yêu cầu rút; chống rút trùng; quỹ có chứng từ; hạn mức (mặc định không có); quy trình chuyển khoản tay có chứng từ; xử lý thất bại và hoàn tiền; xác minh tài khoản; màn admin và khách ở trạng thái khoá; điều kiện chi trả nhiều cấp.

**Không làm:** bật ví, payout thật, API ngân hàng, gán APPROVED / SETTLED cho đơn thật, chọn thuế, hạn mức hay chính sách thu hồi, công bố điều khoản chi trả.

## Proof — Claude Code, 2026-10-24
- Baseline 521 passed. Sau PLAN-078: **554 passed** (+33 `tests/test_cashback_payout_lifecycle.py`; 17 test cũ viết lại theo máy trạng thái), ruff sạch.
- Diễn tập trên bản sao DB production (0600, đã xoá): thêm 6 bảng trống, 3 cột, 2 index unique, 2 trigger; ghi 1 dòng lịch sử cho tài khoản đã khai; 2 khoản pending giữ số; bật ví và tạo yêu cầu rút vẫn bị chặn; bất biến ổn; integrity ok.
- Báo cáo: `reports/CASHBACK_PLAN078_WALLET_PAYOUT.md`.
