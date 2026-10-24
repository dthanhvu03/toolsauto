# ADR-051 — Trạng thái duyệt hoa hồng tách khỏi trạng thái đơn và settlement

| | |
|---|---|
| Trạng thái | Accepted (PLAN-074), chưa triển khai |
| Ngày | 2026-10-24 |
| Liên quan | ADR-049 (sổ ví), ADR-050 (khoá tài chính) |

## Bối cảnh
Đơn Shopee "hoàn thành" không có nghĩa hoa hồng affiliate được duyệt; hoa hồng được duyệt không có nghĩa Shopee đã trả tiền. Khảo sát 3 response thật cho thấy báo cáo conversion không có field nào chứng minh "đã duyệt"; chỉ có cờ gian lận kèm lý do bằng chữ.

## Quyết định
1. Ba cột độc lập trên `shopee_conversions`: `order_status` (có sẵn), `validation_status` (UNKNOWN/PENDING/APPROVED/REJECTED/FRAUD/NEEDS_REVIEW), `settlement_status` (NOT_VERIFIED; PLAN-075 mới được đổi).
2. `validation_status` chỉ suy từ bằng chứng: FRAUD khi `is_fraud=1` hoặc có `fraud_reason`; REJECTED khi đơn huỷ; giá trị lạ, mâu thuẫn, hoa hồng 0 không lý do → NEEDS_REVIEW; còn lại PENDING. **Không có quy tắc nào ra APPROVED** cho tới khi có field đã xác minh hoặc quy trình duyệt thủ công có chứng từ được quyết định riêng.
3. Lịch sử trong `shopee_conversion_changes`, chỉ thêm. Giá trị thiếu không ghi đè; trạng thái lùi từ FRAUD/REJECTED → NEEDS_REVIEW; người được ghi nhận theo Sub ID giữ theo lần gắn đầu.
4. Sổ ví: FRAUD/REJECTED → `cancelled`. Cổng khoá yêu cầu APPROVED ngoài các điều kiện ADR-050.

## Hệ quả
- Không khoản nào vào ví được cho tới khi có nguồn APPROVED **và** settlement (PLAN-075).
- Shopee đổi mã trạng thái thì bot báo cần kiểm tra thay vì đoán.
