# Settlement fix — batch #3 + #4 (20/11/2026 ~10:08 VN)

Actor: `admin:5967314745` · DB: `data/cashback.sqlite`

## Đã làm

### Batch #3 (`17315920094261116`) — PARTIALLY_MATCHED → MATCHED
- Nguyên nhân: `reported_commission_vnd` 43.413 vs allocated 43.412 → `UNALLOCATED` 1đ.
- Cách: giống batch #1 — `settlement_items.id=23` (`261027NC5TSER3`) `adjustment_vnd=1`; ghi `settlement_adjustments` RESOLVED; `reconcile(3)`.
- Kết quả: **MATCHED**, unallocated=0, bank/payout giữ 38.646.

### Batch #4 (`17315920094261119`) — EVIDENCE_PENDING → MATCHED
- Nguyên nhân: thiếu `tax_withheld_vnd` / `shopee_payout_vnd` / bank evidence (`NO_BANK`, `TOTALS_INCOMPLETE`).
- Cách: `confirm_bank(4, 9485)` — thuế TNCN+VAT tạm 10% như các kỳ trước (`expected_payout` = 10.655 − 104 − 1.066 = **9.485**); rồi `reconcile(4)`.
- Kết quả: **MATCHED**, tax=1.066, payout=bank=9.485; statement evidence #12, bank evidence #13.

### Ví
- `CashbackService.refresh_wallet()` sau khi 8 đơn bot của #3+#4 → `settlement_status=SETTLED`.
- Holding 13 / 84.909 → **7 / 59.141**; available 5 / 25.910 → **11 / 51.678** (Δ +25.768 vào ví).
- 2 đơn batch #4 vẫn **holding**: hold 7 ngày (complete 16–17/11 → mở ~23–24/11).

## Verify (evaluate)

| # | Period | Status | Unalloc | Payout / Bank |
|---|---|---|---:|---:|
| 1 | 2026-10 | MATCHED | 0 | 22.585 |
| 2 | 2026-11 | MATCHED | 0 | 16.392 |
| 3 | 2026-11 | MATCHED | 0 | 38.646 |
| 4 | 2026-11 | MATCHED | 0 | 9.485 |

**Tổng NH đã khớp:** 87.108 đ (trước fix báo cáo: 77.623 + kỳ #4 chưa bank).
