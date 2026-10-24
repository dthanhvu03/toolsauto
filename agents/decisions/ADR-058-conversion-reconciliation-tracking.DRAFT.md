# ADR-058 (DRAFT) — Theo dõi đơn Shopee đang chờ xác minh khi ra khỏi khung đồng bộ 30 ngày

| | |
|---|---|
| Trạng thái | **Accepted cho Phương án B** (chủ bot duyệt 2026-10-24); Phương án A chờ thử nguồn. Code: `reports/CASHBACK_PLAN081_GATE_B.md` |
| Ngày | 2026-10-24 |
| Liên quan | ADR-051 (trạng thái hoa hồng), ADR-056 (hàng đợi thông báo), ADR-057 (tự đồng bộ), PLAN-075 (chứng từ đối soát) |
| Audit | `reports/CASHBACK_PLAN081_GATE_A_AUDIT.md` |

## Bối cảnh
- Đồng bộ chỉ đọc đơn có `purchase_time` trong 30 ngày gần nhất (`shopee_sync.py:291–292`). Đơn ra khỏi khung không được đọc lại và không bị đánh dấu gì.
- Trên production, đơn …7156 đã vắng từ lượt #4.
- Không có `last_seen_at` riêng.
- Website endpoint có nhận khung cũ hơn 30 ngày hay không: chưa xác minh. Open API (khung 3 tháng) không dùng được vì không có App ID / Secret.

## Quyết định đề xuất
1. **Lớp theo dõi tách riêng.** Thêm `last_seen_at`, `last_seen_run_id`, `last_seen_source` vào `shopee_conversions`, chỉ ghi ở đường đồng bộ. Thêm bảng `conversion_reconciliation` (trạng thái hiện tại) và `conversion_reconciliation_events` (chỉ thêm).
2. **Nhãn theo dõi:** `OBSERVED_RECENTLY`, `APPROACHING_WINDOW`, `OUTSIDE_WINDOW_UNVERIFIED`, `RECONCILIATION_REQUIRED`, `RECONCILED`. Các nhãn này **không** thay `validation_status`, `settlement_status` hay trạng thái sổ ví, và không được ví / payout đọc.
3. **Phương án B trước:** cập nhật nhãn sau mỗi lượt PLAN-080, chỉ từ DB; màn admin "🧾 Đơn cần đối soát"; tin tổng hợp cho admin tối đa 1 lần/ngày khi danh sách đổi; kết luận chỉ đến từ dữ liệu Shopee thật hoặc chứng từ PLAN-075.
4. **Phương án A sau, có điều kiện:** chỉ khi một lần thử nguồn được duyệt chứng minh website endpoint trả đơn cũ hơn 30 ngày. Khi đó đọc khung giờ mua hẹp cho từng đơn đang chờ đã ra khung, trong cùng lượt và cùng khoá của `SyncCoordinator`, có trần số đơn mỗi lượt và 1 lần/đơn/ngày. Dữ liệu đi qua `record_conversion_snapshot`.
5. **Cấm:** quá hạn → REJECTED / CANCELLED; vắng mặt → FRAUD; COMPLETED → SETTLED; đối soát tay không chứng từ mở quyền rút.

## Hệ quả
- Admin biết đơn nào đang thiếu dữ liệu trước khi khách hỏi.
- Không thêm yêu cầu tới Shopee với B.
- Không đổi tiền, không thêm tin khách khi chỉ đổi nhãn theo dõi.

## Cần duyệt
Ngưỡng 20 / 30 / 45 ngày; phạm vi (chỉ đơn qua bot); backfill `last_seen_at`; lần thử nguồn; trần của Phương án A.
