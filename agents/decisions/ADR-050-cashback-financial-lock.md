# ADR-050 — Khoá tài chính cho ví hoàn tiền

| | |
|---|---|
| Trạng thái | Accepted (PLAN-073), chưa triển khai |
| Ngày | 2026-10-24 |
| Liên quan | ADR-049 (sổ cái ví), `reports/CASHBACK_FULL_AUDIT.md` P0-1, P0-2, P0-3 |

## Bối cảnh
ADR-049 cho khoản vào ví theo `COMPLETED + N ngày`. Audit cho thấy mốc này không chứng minh Shopee đã duyệt hay đã trả. Đơn 23/09 trong DB: `COMPLETED` nhưng `is_fraud=1`, hoa hồng 0. Bật ví khi đó có thể chi tiền Shopee không bao giờ trả.

## Quyết định
1. Tách công tắc giao diện (`wallet_enabled`) khỏi điều kiện tài chính. Ví chỉ có hiệu lực khi cả hai đạt.
2. Điều kiện tài chính dựa trên **bằng chứng trong DB**, không dựa trên cấu hình:
   - kỳ Shopee đã trả (`shopee_settlements`), có mã chứng từ;
   - chính sách thuế người nhận đã duyệt (`payout_tax_policies`).
   Chưa có thì khoá. Không có nút hay biến môi trường nào để bỏ qua.
3. Một khoản chỉ `available` khi đủ ngày giữ, không gian lận, có tháng duyệt, và tháng đó đã có kỳ Shopee trả.
4. Tổng đã chi + đang yêu cầu ≤ tổng Shopee đã trả.
5. Trigger SQLite chặn ghi `available`, yêu cầu rút mới, `paid` khi chưa có bảng bằng chứng. Đây là lớp cuối cho trường hợp gọi SQL trực tiếp.
6. DDL hai bảng chỉ là nháp (`migrations/007_settlement_evidence.DRAFT.sql`). Tạo trên production cần PLAN đối soát riêng, có luồng nhập chứng từ và người chịu trách nhiệm.

## Hệ quả
- Ví khách không bật được cho tới khi có PLAN đối soát. Bot vẫn tạo link, đồng bộ đơn, ghi tiền chờ duyệt.
- Khoản `holding` không còn "ngày vào ví" cố định; chữ báo khách đổi thành "khi Shopee duyệt và thanh toán".
- Còn mở: điều chỉnh âm khi hoa hồng giảm sau khi đã `available` (phải làm trước khi mở khoá).
