# PLAN-101 — Kỳ thanh toán Shopee tự động: bot tự lập kỳ, tự nhập báo cáo Shopee, chủ bot bấm xác nhận tiền về

- Executor: Claude Code. Ngày 29/10/2026, chủ bot hỏi «lần sau em tự động được không» sau khi em nhập tay kỳ
  17315920094261029 từ ảnh.
- Chủ bot duyệt (AskUserQuestion 29/10):
  - cho đọc thử trang thanh toán Shopee bằng cookie của bot (hai lượt, chỉ đọc);
  - tiền về ngân hàng: bot nhắn kèm nút «✅ Đã nhận đúng …», «⚠️ Số khác».
- Trạng thái: đang làm.

## Kết quả đọc thử (29/10)
- **Lượt 1:**
  - `POST /api/v3/gql?q=getPayoutList` và `?q=payoutDetail` (Lịch sử thanh toán, Chi tiết kỳ) trả **403**
    (error 90309999). Lý do: trang web dùng mã bảo mật trình duyệt mà bot không chạy. Không thử lách.
  - `GET /api/v3/report/validation_detail/v2` (Chi tiết chuyển đổi của một ngày) **đọc được**: đơn, hoa hồng từng
    món, giờ bấm, nguồn.
- **Lượt 2:** `GET /api/v3/payment/billing_list` (hoá đơn đối soát theo ngày) và `GET /api/v3/payment/billing_detail`
  đều **đọc được**. Mỗi hoá đơn ngày có:
  - `payout_id` (mã thanh toán) và `payout_created_time`;
  - `eligible_total_amount` (trước phí) và `bill_total_amount` (sau phí);
  - `payment_completed_time`;
  - khung giờ hoàn thành và khung giờ xác thực.
- **Không có ở REST:** thuế TNCN/VAT của kỳ và số sau thuế (chỉ có ở GraphQL bị chặn). Kỳ 29/10 khớp công thức
  5% TNCN + 5% VAT trên hoa hồng trước phí: 25.371đ → 1.269đ + 1.269đ.
- **Số thật thay số suy ra:** đơn 26/10 Shopee duyệt 1.373đ (bot ghi 1.372đ), ngày 27/08 trước phí 4.510đ. Đã thay
  chứng từ kỳ #1 (chứng từ #2 thay #1).

## Thiết kế
- **Đọc:** cuối mỗi lượt đồng bộ Shopee (240 phút), bot gọi 1 lệnh `billing_list` (120 ngày hoàn thành gần nhất) rồi
  gom hoá đơn ngày theo `payout_id`.
  - Lỗi ở phần này chỉ ghi log, không làm hỏng lượt đồng bộ đơn.
- **Kỳ mới** (chưa có kỳ cùng mã thanh toán):
  - bot đọc đơn của từng hoá đơn ngày (`validation_detail/v2`, chỉ khi có kỳ mới);
  - lập kỳ (tháng theo ngày khởi tạo, giờ VN) và nhập `shopee_payment_report`:
    - hoa hồng = Σ trước phí, phí = Σ (trước phí − sau phí);
    - thuế và số sau thuế để trống (Shopee chặn chỗ đọc), nên kỳ ở «Chờ chứng từ»;
    - mỗi đơn một khoản.
- **Báo admin, mỗi kỳ một lần:**
  - mã thanh toán, số sau phí, thuế tạm tính 10%, số dự kiến về tài khoản;
  - nút «✅ Đã nhận đúng X», «⚠️ Số khác», «🧾 Xem kỳ».
  - Thấy `payment_completed_time` (Shopee đã chuyển) mà chưa xác nhận thì nhắc thêm một lần.
- **Bấm ✅:**
  - bot tính lại X phía máy chủ; số trên nút khác X thì từ chối;
  - nhập `bank_statement` (nhận X);
  - thay báo cáo Shopee bằng bản có thuế = sau phí − X và sau thuế = X (ghi rõ nguồn là chủ bot xác nhận);
  - đối soát lại.
  - Ví khách vẫn khoá: đối soát không mở ví, không tạo lệnh rút, không gán APPROVED.
- **Bấm ⚠️:** không ghi gì. Bot dặn gửi ảnh trang «Đối soát vào ngày …» cùng số tài khoản nhận để nhập tay.
- **Màn kỳ** (🧾 Đối soát thanh toán → kỳ) có hai nút xác nhận khi kỳ chưa có chứng từ ngân hàng.

## Không đổi
- Không đổi schema, không thêm `.env`.
- Không đọc, không lưu số tài khoản hay thông tin thuế cá nhân. Hai lệnh đọc mới chỉ lấy hoá đơn và đơn.
- Kỳ đã nhập tay (cùng mã thanh toán) không bị lập lại. Bot chỉ báo nút xác nhận.

## Kiểm
- Test (không gọi mạng):
  - lập kỳ mới, khoản theo đơn khớp, không lập trùng, kỳ nhập tay không lập lại;
  - báo một lần, nhắc khi Shopee đã chuyển;
  - ✅ đúng số thì nhập ngân hàng và thay báo cáo; số cũ trên nút bị từ chối; bấm lần hai bị từ chối;
  - ⚠️ không ghi; ví không đổi;
  - lỗi đọc kỳ không làm hỏng lượt đồng bộ.
- Toàn bộ `tests/test_cashback_*.py` + `ruff check cashback_bot`.

## Kết quả (29/10)
- Code:
  - `shopee_client.py`: `fetch_billing_list`, `fetch_bill_orders` (header `Affiliate-Program-Type: 1` như web).
  - `shopee_payout.py` (mới):
    - `poll` gom hoá đơn theo mã thanh toán, chỉ kỳ khởi tạo trong 14 ngày;
    - lập kỳ và nhập báo cáo; hoa hồng từng đơn tính cùng cách `shopee_sync`;
    - báo admin `SHOPEE_PAYOUT` kèm nút;
    - `confirm_bank`; `expected_tax`.
  - `shopee_sync.py`: bước 4c gọi `poll` cuối lượt. Lỗi chỉ ghi log.
  - `admin_settlement.py`: nút `c:sm:bok:<kỳ>:<số>` / `c:sm:box:<kỳ>`; màn kỳ hiện hai nút khi chưa có chứng từ
    ngân hàng.
- Test `tests/test_cashback_shopee_payout.py` (6):
  - lập kỳ, khoản theo đơn, bỏ kỳ tháng 7 và hoá đơn chưa vào kỳ, không đọc lại, không báo lại;
  - nhắc khi Shopee đã chuyển;
  - kỳ nhập tay không lập lại;
  - ✅ / ⚠️ / số cũ / bấm lần hai / không phải admin; ví không đổi;
  - lỗi 403 không hỏng lượt đồng bộ; thuế tạm tính.
- Sau restart, lượt đồng bộ Shopee kế tiếp thấy kỳ 17315920094261029 (kỳ #1 đã nhập tay) nên không lập lại. Bot báo
  admin kèm nút «✅ Đã nhận đúng 22.585đ».
  - Bấm nút thì kỳ thành «Khớp một phần»: còn 4.510đ ngày 27/08 chưa có mã đơn, đơn 26/10 lệch 1đ.

## Sửa sau tin đầu tiên (29/10, 10:56)
- Chủ bot nhận tin kỳ 17315920094261029: «em phải kiểm tra trạng thái rồi mới báo chứ em». Tin chưa ghi trạng thái
  Shopee mà đã có nút «✅ Đã nhận đúng …» trong khi Shopee còn «Đang xử lý».
- Sửa `shopee_payout.py`:
  - đọc `payout_status` của hoá đơn (kỳ 29/10 web ghi «Đang xử lý» thì API trả 2; mã khác hiện số kèm «bot chưa biết
    nghĩa») và `payment_completed_time`;
  - tin có dòng «Trạng thái Shopee: …» (đã chuyển thì ghi giờ chuyển);
  - Shopee chưa chuyển: tin chỉ có «🧾 Xem kỳ», dặn bot sẽ báo lại. Shopee ghi đã chuyển: tin thứ hai có nút
    «✅ Đã nhận đúng …» / «⚠️ Số khác».
  - Màn kỳ (🧾 Đối soát thanh toán) vẫn có hai nút để chủ bot tự xác nhận khi cần.
- Test thêm: trạng thái trong tin, tin «chưa chuyển» không có nút xác nhận, tin «đã chuyển» có nút, mã trạng thái lạ.
