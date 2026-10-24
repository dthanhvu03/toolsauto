# ADR-052 — Đối soát thanh toán Shopee tách khỏi khoá chi trả

| | |
|---|---|
| Trạng thái | Accepted (PLAN-075) |
| Ngày | 2026-10-24 |
| Liên quan | ADR-050 (khoá tài chính), ADR-051 (trạng thái duyệt hoa hồng) |

## Bối cảnh
Cần ghi nhận và đối chiếu tiền Shopee thực trả (báo cáo thanh toán ↔ số học kỳ ↔ tiền ngân hàng), tách tiền đơn qua bot khỏi tiền ngoài bot, ghi điều chỉnh về sau. Chưa có mẫu báo cáo Xác thực/Thanh toán Shopee hay sao kê thật.

## Quyết định
1. Năm bảng mới `settlement_batches`, `settlement_evidence`, `settlement_items`, `settlement_adjustments`, `settlement_audit`. **Không** dùng tên `shopee_settlements` / `payout_tax_policies` (điều kiện mở khoá của `payout_gate`, ADR-050): đối soát MATCHED không thể mở ví. Nối đối soát vào khoá là việc của PLAN-078.
2. Chứng từ vào bằng **định dạng chuẩn nội bộ** `cashback_settlement_v1` qua công cụ quản trị trên máy chủ (`python -m cashback_bot.settlement_import`), không qua Telegram. Không viết parser đoán cột CSV Shopee; parser thật chuyển về định dạng này khi có mẫu.
3. Chứng cứ chỉ thêm: chống trùng theo sha256 và (loại, mã chứng từ); thay chứng từ = dòng mới + SUPERSEDED; bản gốc lưu theo tên sha256 trong thư mục 0700, file 0600; trigger chặn xoá chứng cứ, chặn sửa/xoá audit.
4. Kỳ MATCHED chỉ khi đủ hai nguồn độc lập (báo cáo thanh toán + ngân hàng), số học kỳ đúng (phí đã gồm VAT không trừ VAT lần nữa), ngân hàng = Shopee báo, tổng theo đơn = tổng kỳ, không khoản nào lệch/không rõ/trùng. Còn lại: EVIDENCE_PENDING / PARTIALLY_MATCHED / DISPUTED; REVERSED khi đảo.
5. Phân bổ: chỉ tiền đơn qua bot đã khớp vào "quỹ có chứng từ"; ngoài bot, không rõ đơn, cần kiểm tra tách riêng; phí/thuế không có chi tiết theo đơn thì để chưa phân bổ, không chia tỷ lệ.
6. `settlement_status` của đơn = SETTLED chỉ khi đơn có khoản khớp trong một kỳ MATCHED; kỳ đảo/lệch thì về NOT_VERIFIED. Báo cáo xác thực chỉ lưu số "Shopee báo duyệt", **không** đổi `validation_status` (APPROVED vẫn BLOCKED).
7. Điều chỉnh sau khi đã vào kỳ: một dòng OPEN cho mỗi sự kiện (khoá theo lần đồng bộ), không thu hồi tiền, không đổi sổ ví.

## Hệ quả
- Admin xem được đối soát; ví và chi trả vẫn khoá hoàn toàn.
- Khi có mẫu báo cáo Shopee thật: thêm parser chuyển về `cashback_settlement_v1`, không đổi engine.
