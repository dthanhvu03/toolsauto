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

## Thẻ link mới (chủ bot yêu cầu 2026-10-27: làm lại UI, làm nổi phần đáng chú ý)

- Thứ tự: tiêu đề + sản phẩm → **💰 Hoàn dự kiến** (cả dòng đậm) → ➕ có thể được thêm → khối **⚠️ Để được hoàn** (3 gạch đầu dòng) → chữ nhỏ in nghiêng → 👉 lời bấm nút ở cuối, sát nút.
- Khối "Để được hoàn" có thêm ý "Mua đúng món này. Mua món khác thì số hoàn sẽ khác." (đơn 261027N7MJJKFV mất 12% XTRA vì khách mua ở shop khác).
- Zalo dùng chung chữ; thẻ `<i>` / `<b>` đổi sang style của Zalo.

## Đợt 3: câu chữ theo tâm lý khách (chủ bot duyệt 2026-10-27)

- Dòng ➕ bỏ số tiền ("Có thể được thêm nếu Shopee áp mức cao hơn"): ghi "thêm tới Xđ" thì khách cộng lại và lấy tổng làm mốc.
- Thêm dòng 🔒 "Link mở thẳng Shopee. Bạn thanh toán trên Shopee như bình thường, bot không thu tiền gì." (TikTok có câu riêng).
- Câu voucher chuyển từ chữ nhỏ thành gạch đầu dòng thứ 4 trong khối "Để được hoàn".
- Tin "📦 Có đơn mới qua link của bạn": khi hoàn thấp hơn hẳn số báo lúc tạo link (ngưỡng như tin thay đổi: ≥500đ hoặc ≥10%), thêm "Lúc tạo link bot báo khoảng X. Số thấp hơn vì:" kèm từng lý do lấy từ dữ liệu đơn:
  - mua món khác món trong link (item_id trong raw_json);
  - trả ít hơn giá tham khảo (gmv_vnd);
  - Shopee tính mức thấp hơn (đã trừ phần do giá trả mà vẫn thấp hơn hẳn).
  - Đơn huỷ / không đủ điều kiện thì không thêm.

## Còn lại

- Thẻ link nói thời điểm tiền vào ví: chờ chủ bot chốt chính sách thời gian.
- `entry_notice` (tin khi ví mở) vẫn chỉ nói lý do giá trả; nên dùng `why_lower` khi mở ví.

## Proof

- `test_shopee_comm_tren_2_5_chi_ghi_co_the_duoc_them` (số thật link F1) và `test_xtra_va_shopee_2_5_giu_nguyen` (số thật link Cúp pha lê).
- Toàn bộ test cashback: 843 passed (đợt 3). ruff sạch trên file đã sửa.
