# ADR-062 — Khoá tài chính đọc kỳ đối soát thật

| | |
|---|---|
| Trạng thái | Accepted (chủ bot yêu cầu 2026-11-03), chờ merge + restart |
| Ngày | 2026-11-03 |
| Thay | ADR-050 §2, §3, §5, §6; ADR-052 §1 (câu «đối soát MATCHED không thể mở ví») |
| Liên quan | ADR-050, ADR-052, ADR-055, ADR-059, PLAN-075, PLAN-078, PLAN-088, PLAN-101 |

## Bối cảnh
- Khoá cũ (ADR-050) đòi hai bảng `shopee_settlements` / `payout_tax_policies`. DDL của hai bảng chỉ là nháp (migration 007) và không bao giờ chạy, nên ví khoá vĩnh viễn.
- Từ PLAN-075 / PLAN-101 bot đã có đối soát thật: báo cáo Shopee (đọc tự động), chứng từ ngân hàng do chủ bot xác nhận, kỳ `MATCHED` khi hai nguồn khớp tới từng đơn. Từ PLAN-078 có quyết định thuế người nhận (`payout_policy_decisions`). Trigger `financial_lock_v2_*` (PLAN-088) đã khoá theo đúng dữ liệu này.
- Báo cáo đơn Shopee không có trường nào chứng minh «đã duyệt» (commission_validation.py), nên `validation_status = APPROVED` không bao giờ được gán và không đơn nào vào được ví.
- 2026-11-03: kỳ #1 (2026-10) khớp hoàn toàn; chủ bot yêu cầu mở khoá.

## Quyết định
1. Điều kiện hệ thống: ít nhất một kỳ `settlement_batches.status = 'MATCHED'` **và** quyết định thuế mới nhất `APPROVED`, cộng các điều kiện PLAN-078 (`payout_readiness.system_conditions`). Không có công tắc bỏ qua.
2. Năm trigger `financial_lock_*` giữ tên, đổi điều kiện sang (1). `TrackingRepository._migrate` xoá bản cũ (thân trigger còn nhắc `shopee_settlements`) để SCHEMA tạo lại. Khoản `available` số âm (dòng thu hồi) không bị chặn, như `financial_lock_v2_*`.
3. Bằng chứng duyệt của một đơn = đơn nằm trong kỳ `MATCHED` (`settlement_status = 'SETTLED'`): Shopee chỉ đưa vào hoá đơn đối soát đơn đã duyệt, và tiền kỳ đó đã về ngân hàng. Đơn `FRAUD` / `REJECTED` không bao giờ vào ví. Bỏ điều kiện `validation_month`.
4. Quỹ chi (`payout_headroom`) = `payouts.fund_position`: phần đơn bot của các kỳ `MATCHED` trừ phí, thuế của cả kỳ − đang giữ − đã chi. Đơn ngoài bot, không rõ đơn không vào quỹ.
5. Shopee giảm hoặc huỷ hoa hồng sau khi đã vào ví: trừ vào ví khách, số dư được âm, đơn sau bù trước (giữ ADR-059 / PLAN-088; chủ bot chọn lại 2026-11-03). Mục «còn mở» của ADR-050 coi như đã xong.

## Hệ quả
- Sau khi merge và restart, chủ bot bật được ví trong /admin. Đơn kỳ #1 vào ví sau 15 ngày giữ tính từ ngày hoàn thành (khoảng 10–11/11/2026); đơn kỳ #2 vào khi kỳ #2 khớp.
- Bảng nháp `shopee_settlements` / `payout_tax_policies` và migration 007 không còn vai trò; giữ file nháp cho lịch sử.
- Xác nhận ngân hàng là chốt chặn chính: bấm nhầm «Đã nhận đúng …» có thể mở khoá sai. Cần nút gỡ xác nhận ngân hàng trong /admin (việc tiếp theo, chưa làm).
