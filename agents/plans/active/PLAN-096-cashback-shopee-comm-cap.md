# PLAN-096 — Báo hoàn theo Shopee Comm tối đa 2,5%

| | |
|---|---|
| Executor | Claude Code (chủ bot duyệt 2026-10-27: chọn cách A) |
| Trạng thái | ✅ Đã merge vào main 2026-10-27, chờ chủ bot restart |
| Không đổi | Không đổi cấu trúc DB. Không đổi cách tính hoa hồng thật của đơn. Link cũ giữ nguyên số đã báo |

## Vì sao

Đối chiếu AMS ngày 2026-10-27: cả 3 đơn thật đều chỉ được Shopee Comm 2,5%.
- Link 55 (mô hình xe F1): AddLiveTag báo 8%, khách thấy hoàn 23.678đ; thực tế 10.391đ hoa hồng, hoàn 6.474đ.
- Trong 30 link Shopee gần đây, 14 link được báo Shopee Comm 4–8%.

## Cách làm

- `product_data.SHOPEE_BASE_BPS = 250` và `ProductQuote.sure_commission_vnd`:
  - hoa hồng dùng để báo hoàn = min(Shopee Comm, 2,5% giá) + XTRA;
  - thiếu phần tách shop / Shopee thì giữ nguyên tổng như trước.
- `service`:
  - báo hoàn và snapshot chính sách tính theo `sure_commission_vnd`, ghi vào `estimated_commission`;
  - `shopee_commission_vnd` vẫn lưu số gốc AddLiveTag báo.
- Thẻ link (Telegram và Zalo) thêm dòng "➕ Có thể được thêm tới Xđ nếu Shopee áp mức hoa hồng cao hơn", với X = hoàn tính theo tổng hoa hồng AddLiveTag − hoàn chắc chắn.
- Tin admin khi khách tạo link:
  - tỷ lệ HH và dòng "· từ Shopee" theo số đã tính;
  - thêm ghi chú "AddLiveTag báo Shopee Comm …; bot chỉ tính tối đa 2,5%".

## Còn lại (chủ bot chưa duyệt)

- Thẻ link thêm câu "Mua đúng sản phẩm này để được hoàn như trên". Đơn 261027N7MJJKFV mất 12% XTRA vì khách mua ở shop khác.
- Tin báo đơn giải thích khi hoàn thực thấp hơn hẳn số dự kiến.

## Proof

- `test_shopee_comm_tren_2_5_chi_ghi_co_the_duoc_them` (số thật link F1) và `test_xtra_va_shopee_2_5_giu_nguyen` (số thật link Cúp pha lê).
- Toàn bộ test cashback: 841 passed. ruff sạch.
