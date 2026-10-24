# PLAN-073 — Cashback: Production Safety Hardening V1

| | |
|---|---|
| Trạng thái | **DONE trên nhánh `cursor/cashback-safety-hardening`. Chưa triển khai (NOT AUTHORIZED)** |
| Executor | Claude Code (user giao trực tiếp task "PRODUCTION SAFETY HARDENING V1", 2026-10-24; ngoại lệ backend như ADR-010) |
| Đầu vào | `reports/CASHBACK_FULL_AUDIT.md` (P0-4, P1-8, P1-9, khoá cho P0-1/2/3) |
| Phạm vi | `cashback_bot/` (poller, db, redact mới, telegram_api, shopee_sync, shopee_cookie, backup, payout_gate mới, wallet, admin_wallet, admin_ui, admin_stats, admin_notify, messages, migrations/007 DRAFT), tests, BACKUP.md, ADR-050 |

## Scope
1. Một update Telegram lỗi không làm kẹt bot: phân loại lỗi, thử lại có giới hạn, cách ly bền vững (`failed_updates`) rồi mới tiến offset.
2. Không lộ token, cookie, API key vào log: `redact`, `RedactingFormatter`, sửa mọi chỗ log lỗi thô.
3. Backup tự động mỗi ngày, kiểm tra khôi phục được, báo admin khi lỗi.
4. Khoá tài chính: không bật ví, không yêu cầu rút, không xác nhận đã chuyển, không `available` khi chưa có bằng chứng Shopee đã trả và thuế đã duyệt (ADR-050).

## Không làm
Không đổi công thức báo giá, không bật Membership, không tạo bảng bằng chứng trên production, không đổi quyền file production, không deploy.

## Proof — Claude Code, 2026-10-24
- `tests/test_cashback_*.py`: **334 passed** (291 cũ + 43 trong `tests/test_cashback_safety_hardening.py`), ruff sạch.
- Diễn tập `migrate()` trên bản sao DB production (0600, đã xoá): chỉ thêm `failed_updates` và 4 trigger `financial_lock_*`, số dòng mọi bảng giữ nguyên, 2 khoản pending không đổi, ví khoá.
- Production không đổi: `main@eca64fd`, PID 590993 không restart, DB chỉ mở `mode=ro`.
- Báo cáo đầy đủ: `reports/CASHBACK_SAFETY_HARDENING_V1.md`.
