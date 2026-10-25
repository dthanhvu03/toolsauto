# ADR-059 — Chính sách chi trả ví cashback (NHÁP, chờ chủ bot duyệt lần cuối)

| | |
|---|---|
| Trạng thái | **Nháp.** Chủ bot trả lời 2026-10-25; chưa ghi vào `payout_policy_decisions` (bảng chỉ thêm, không sửa / xoá được) |
| Liên quan | ADR-052 (đối soát kỳ), ADR-055 (vòng đời payout), PLAN-078 (điều kiện mở ví) |
| Không đổi | Khoá tài chính vẫn giữ; ADR này không mở ví, không tạo payout |

## Quyết định của chủ bot (2026-10-25)

| Chủ đề (`topic`) | Quyết định |
|---|---|
| `tax` | **A1 chưa trả lời** (khấu trừ TNCN trên tiền hoàn cho khách): chờ kế toán. A2: **giữ dự phòng thuế 10%** trên hoa hồng như hiện tại |
| `clawback` | Shopee thu hồi sau khi đã trả khách: **trừ vào tiền hoàn sau này của khách, khoá rút đến khi bù đủ**. Không đòi lại ngoài bot |
| (cài đặt ví) | Giữ tiền **mặc định 15 ngày** sau khi đơn hoàn thành (admin chỉnh được 0 / 7 / 15 / 30 / 45); vẫn phải có kỳ Shopee đã trả |
| `payout_terms` | **Soạn điều khoản V3** gồm các mục trong bảng này; chủ bot duyệt rồi công bố |
| `bank_verification` | Tên chủ tài khoản trùng tên khách khai; admin kiểm tra tên người nhận trên app ngân hàng. **Đổi tài khoản thì chờ 7 ngày**, admin xác minh được thì cho rút ngay tuỳ trường hợp |
| `payment_limits` | Tối thiểu **20.000đ** / lần · tối đa **500.000đ** / lần · **2.000.000đ** / ngày · **10.000.000đ** / tháng |
| `manual_payment` | Chuyển từ **tài khoản cá nhân** của chủ bot; xử lý trong **3–7 ngày làm việc**; chứng từ: **mã giao dịch ngân hàng** nhập vào bot |

## Báo cáo thanh toán Shopee thật (ảnh chủ bot gửi 2026-10-25)

- Lịch sử thanh toán: 5 lần gần nhất 10/02 → 23/07/2026, lần cuối 72.777đ (Mã thanh toán `…260720`, ID tham chiếu ngân hàng, VCB `******4544`). Chưa có lần trả nào cho đơn qua bot (bot chạy từ 10/2026).
- Chi tiết 1 lần trả: "Tổng thanh toán sau thuế" **=** "Tổng doanh thu hợp lệ" (72.777đ) → lần trả 07/2026 **Shopee không khấu trừ thuế**. Cần xem lần trả đầu sau 01/10/2026.
- Chi tiết gom theo **ngày hoa hồng hoàn thành** (ví dụ "18-07-2026 · 72.777đ"), **không theo từng đơn**.
- Shopee đổi sang **hoá đơn theo ngày, trả thứ Ba và thứ Năm** khi tổng chờ trả ≥ 10.000đ.

## Việc phải làm trước khi mở ví (ngoài quyết định trên)

| Việc | Ai | Ghi chú |
|---|---|---|
| A1 thuế khi chi cho khách | Chủ bot hỏi kế toán | Hai câu: tiền hoàn là giảm giá hay thu nhập của người mua; có phải khấu trừ TNCN, từ mức nào |
| Đọc báo cáo thanh toán Shopee vào đối soát | Backend, cần PLAN | ADR-052 đòi "tổng theo đơn = tổng kỳ"; Shopee chỉ cho tổng theo ngày hoàn thành → ghép bằng tổng hoa hồng các đơn hoàn thành cùng ngày (báo cáo chuyển đổi). Kỳ là hoá đơn theo ngày, không phải tháng |
| Chờ 7 ngày khi đổi tài khoản + admin cho rút ngay | Backend, cần PLAN | Code hiện chỉ đưa tài khoản mới về `UNVERIFIED`, chưa có mốc 7 ngày |
| Thu hồi: trừ tiền sau + khoá rút | Backend, cần PLAN | ADR-052 mục 7 hiện "không thu hồi tiền, không đổi sổ ví" → phải sửa |
| Điều khoản V3 | Claude Code soạn, chủ bot duyệt | Sau khi có A1 |
| Ghi 6 quyết định + bảng hạn mức vào bot | Sau khi chủ bot duyệt bản này | Bảng chỉ thêm; ghi sai phải thêm dòng `REVOKED` |
| Kỳ Shopee đầu tiên khớp (báo cáo + sao kê ngân hàng) | Chờ Shopee trả đơn qua bot | Điều kiện cuối của khoá tài chính |
