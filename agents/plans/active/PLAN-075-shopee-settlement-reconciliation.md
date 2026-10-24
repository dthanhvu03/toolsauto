# PLAN-075 — Shopee Settlement & Fund Reconciliation V1

| | |
|---|---|
| Trạng thái | **DONE trên nhánh `cursor/cashback-plan075-settlement`** |
| Executor | Claude Code (chủ bot giao trực tiếp, cho phép triển khai phần an toàn; chủ bot restart) |
| Đầu vào | PLAN-074 (`cef3467`), ADR-050, ADR-051 |
| Phạm vi | `settlement.py`, `settlement_import.py`, `admin_settlement.py` (mới); `db.py` (5 bảng), `shopee_sync.py` (quét điều chỉnh), `admin_policy.py`, `admin_ui.py`; tests; ADR-052 |

## Scope
Khung chứng cứ có kiểm soát, engine đối soát 3 bước, phân bổ quỹ, điều chỉnh sau kỳ, màn 🧾 Đối soát thanh toán. Không parser đoán cột Shopee, không APPROVED, không mở ví/payout.

## Proof — Claude Code, 2026-10-24
- Không có mẫu báo cáo Shopee/sao kê thật trên máy → Evidence Discovery CONDITIONAL, APPROVED BLOCKED; dùng fixture định dạng chuẩn.
- `tests/test_cashback_*.py`: **412 passed** (368 cũ + 44 trong `tests/test_cashback_settlement.py`), ruff sạch.
- Diễn tập migrate trên bản sao DB production (0600, đã xoá): chỉ thêm 5 bảng + 3 trigger chỉ-thêm; bảng cũ, conversion, sổ ví không đổi; 4 trigger khoá còn; ví khoá.
- Báo cáo: `reports/CASHBACK_PLAN075_SETTLEMENT.md`.
