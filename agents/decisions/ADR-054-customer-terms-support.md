# ADR-054 — Điều khoản khách theo phiên bản, hỗ trợ khách, cổng chính sách chưa chứng minh

| | |
|---|---|
| Trạng thái | Accepted (PLAN-077), chưa triển khai production |
| Ngày | 2026-10-24 |
| Liên quan | ADR-050 (khoá tài chính), ADR-053 (snapshot chính sách link) |

## Bối cảnh
- `/dieukien` là chữ cố định: không có phiên bản, ngày hiệu lực, lịch sử hay bằng chứng khách đã đồng ý.
- Khách không có kênh khiếu nại có lịch sử.
- Đường dự phòng của PLAN-076 vẫn tính được tiền cho link `unresolved`, và chưa có gì chặn khoản đó vào ví.

## Quyết định
1. **`customer_terms_versions`:**
   - trạng thái chỉ đi DRAFT → PUBLISHED → SUPERSEDED;
   - mỗi lúc chỉ một bản PUBLISHED (unique index một phần);
   - trigger đóng băng nội dung, ngày hiệu lực và người duyệt khi đã rời DRAFT, và chặn xoá bản đã công bố;
   - công bố phải khớp hash nội dung admin vừa xem.
2. **`customer_terms_acceptances`:**
   - chỉ ghi khi khách bấm đồng ý đúng bản đang công bố, trong chat riêng của chính khách;
   - lưu kèm hash nội dung đã thấy;
   - một dòng mỗi (khách, phiên bản), chỉ thêm;
   - không chuyển chấp thuận sang bản mới, không ghi thay khách.
3. **`link_terms_context`:**
   - tách khỏi snapshot tiền: bản điều khoản đang công bố lúc tạo link và lần chấp thuận của người tạo (nếu có);
   - link trước PLAN-077 không có dòng (LEGACY_NOT_RECORDED), không backfill.
4. **Cờ `CASHBACK_TERMS_REQUIRED`** (mặc định tắt): chặn tạo link mới cho tới khi khách đồng ý. Không chặn xem lịch sử, `/hotro` hay `/dieukien`.
5. **`support_tickets` và `support_ticket_events`:**
   - events chỉ thêm; ticket không xoá được;
   - chặn trùng theo `source_update_id`;
   - bảng chuyển trạng thái cố định; kết luận và chờ Shopee phải có lý do;
   - không có hẹn giờ tự đóng;
   - nội dung che token, cookie và số giống số thẻ, tối đa 1.000 ký tự;
   - chỉ gắn link hay đơn của chính khách;
   - không có đường nào đổi hoa hồng, trạng thái duyệt/đối soát, sổ ví hay payout.
6. **`payout_gate.entry_payable`** thêm điều kiện: link phải có snapshot `captured` hoặc `backfilled`. `unresolved` hoặc thiếu snapshot thì không bao giờ payable.
7. **Thuế:**
   - sổ quyết định chỉ là DDL nháp (`009_tax_decisions.DRAFT.sql`), không chạy;
   - cố ý không đặt tên `payout_tax_policies`, không nối vào khoá tài chính.
8. **Dữ liệu tối thiểu:**
   - tin không phải link chỉ lưu độ dài, không lưu nội dung;
   - màn admin xem khách che số tài khoản. Số đầy đủ chỉ còn ở màn yêu cầu rút, nơi cần để chuyển khoản; màn này hiện không dùng vì ví khoá.

## Hệ quả
- Nội dung điều khoản là quyết định của chủ bot: code chỉ có mẫu V1 và quy trình công bố.
- Thay nội dung điều khoản thì phải tạo phiên bản mới. V1 chưa có trình sửa bản nháp trong bot.
