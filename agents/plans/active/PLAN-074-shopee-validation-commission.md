# PLAN-074 — Shopee Validation & Commission V1

| | |
|---|---|
| Trạng thái | **DONE trên nhánh `cursor/cashback-plan074-validation`. Chưa triển khai (NOT AUTHORIZED)** |
| Executor | Claude Code (chủ bot giao trực tiếp, 2026-10-24; ngoại lệ backend như ADR-010) |
| Đầu vào | PLAN-073 đã triển khai (`a9bb42a`), `reports/CASHBACK_FULL_AUDIT.md` |
| Phạm vi | `commission_validation.py` (mới), `admin_validation.py` (mới), `db.py`, `shopee_sync.py`, `admin_notify.py`, `wallet.py`, `payout_gate.py`, `admin_policy.py`, `admin_ui.py`, tests, ADR-051 |

## Scope
1. Khảo sát field Shopee từ response đã lưu, kết luận mức xác minh (không gọi Shopee).
2. Tách 3 trạng thái: đơn / duyệt hoa hồng / tiền Shopee đã trả.
3. Phát hiện thay đổi hoa hồng, lưu lịch sử, không để thiếu field ghi đè, giữ Sub ID ban đầu.
4. Màn 🧾 Duyệt hoa hồng (chỉ xem, lọc, lịch sử, "đã kiểm tra" có audit).
5. Giữ khoá tài chính, thêm điều kiện APPROVED.

## Không làm
Settlement, mở ví, payout, đổi công thức báo giá, Membership, gọi Shopee thật, deploy.

## Proof — Claude Code, 2026-10-24
- Khảo sát: APPROVED = **BLOCKED** (không field nào chứng minh), FRAUD = PARTIAL (1 mẫu thật), SETTLED = BLOCKED.
- `tests/test_cashback_*.py`: **368 passed** (334 cũ + 34 trong `tests/test_cashback_validation.py`), ruff sạch.
- Diễn tập `migrate()` trên bản sao DB production (0600, đã xoá): chỉ thêm `shopee_conversion_changes`, 4 trigger còn nguyên, sổ ví không đổi. 2 đơn bot = PENDING, đơn 23/09 = FRAUD, không đơn nào APPROVED.
- Production không đổi: `main@539e3d9`, PID 597550 không restart, DB chỉ mở `mode=ro`, không gọi Shopee.
- Báo cáo: `reports/CASHBACK_PLAN074_VALIDATION.md`.
