# PLAN-081 — Đối soát vòng đời đơn Shopee quá 30 ngày

| | |
|---|---|
| Trạng thái | Gate A DONE. **Gate B (Phương án B) CODE READY** trên `cursor/cashback-plan081-reconciliation`, chưa triển khai. Phương án A chờ chủ bot xác nhận thử nguồn |
| Executor | Claude Code (chủ bot giao trực tiếp, nội dung PLAN dán trong phiên) |
| Đầu vào | `main@4f4a701`, ADR-057 |
| ADR | ADR-058 (DRAFT) |

## Scope Gate A
Audit chỉ đọc khung quét 30 ngày, nguồn Shopee, trường DB, tuổi đơn; đặc tả backlog đối soát, cảnh báo admin, test matrix, migration và rollback (chỉ thiết kế).

**Không làm:** sửa code, migration, sửa DB / `.env`, restart, gọi Shopee, gửi tin, đổi Financial Lock.

## Proof — Claude Code, 2026-10-24
- **Khung quét:** `shopee_sync.py:232, 291–292`; `shopee_client.py:239–240`; bộ điều phối không truyền `days_back` (`sync_scheduler.py:302`).
- **Bằng chứng production:** đơn …7156 (mua 2026-09-23) vắng từ lượt #4. Hai đơn qua bot ra khung ngày 2026-11-22.
- **Nguồn:** website > 30 ngày UNVERIFIED; Open API khung 3 tháng nhưng không có quyền.
- **Báo cáo:** `reports/CASHBACK_PLAN081_GATE_A_AUDIT.md`.

## Quyết định chờ chủ bot
Mục 21 báo cáo: phương án (khuyến nghị B trước), ngưỡng 20 / 30 / 45 ngày, lần thử nguồn, backfill `last_seen_at`, tần suất báo admin, phạm vi, trần của A.

## Proof Gate B — Claude Code, 2026-10-24
- **Test:** 666 passed (+17 `tests/test_cashback_reconciliation.py`); ruff sạch.
- **Diễn tập trên bản sao DB:** migrate không đổi dữ liệu khác; mô phỏng mốc 12/11, 22/11, 08/12 cho 2 đơn qua bot cho đúng nhãn và tin admin; tiền và lịch không đổi.
- **Báo cáo:** `reports/CASHBACK_PLAN081_GATE_B.md`.
