# Chính sách tính cashback V1.2

Hồ sơ cá nhân, cá nhân kinh doanh và hộ kinh doanh nằm ở `cashback_bot/TAX_PROFILES.md`. Cùng một công thức. Nhãn tài khoản không chọn thuế suất.

Chưa phát hành cho khách. `CASHBACK_ESTIMATE_POLICY` mặc định `v1.1`. Bot đang chạy không được restart trong lần soạn chính sách này.

## Estimated

Dùng khi khách gửi link và hoa hồng AddLiveTag là một số nguyên VND tin cậy. Trường `commission` là một tổng. Không cộng thêm hoa hồng Shopee và Xtra lên trên tổng đó.

```
fee = ceil(gross × phí dự phòng)
tax = ceil(gross × dự phòng rủi ro thuế)
distributable = max(0, gross - fee - tax - khoản khác)
estimated = floor(distributable × tỷ lệ chia, đơn vị làm tròn)
```

Cấu hình thử, đơn vị basis point trên 10.000:

| Khoản | Mặc định | Ý nghĩa |
|---|---|---|
| `CASHBACK_RATE_PERCENT` | 70 | Tỷ lệ chia trên phần còn lại |
| `CASHBACK_ESTIMATE_FEE_BPS` | 98 | 0,98% dự phòng phí dịch vụ |
| `CASHBACK_ESTIMATE_TAX_RESERVE_BPS` | 1000 | 10% dự phòng rủi ro, không phải thuế luật định |
| `CASHBACK_ESTIMATE_OTHER_RESERVE_VND` | 0 | Khoản khác, chỉ khi có căn cứ |
| `CASHBACK_ESTIMATE_ROUNDING_UNIT` | 1 | Làm tròn xuống từng đồng |

Mã phiên bản lưu khi đã có cột `estimate_policy`: `v1.2-reserve-2026-10-23`.

Dòng cũ không bị tính lại. Cột chưa có thì bot giữ công thức V1.1 dù biến môi trường đặt `v1.2`.

## Đổi mức dự phòng không cần sửa `.env` (ADR-047)

`/admin` → Thuế & phí → Đổi mức áp dụng: chọn loại hình, phí dự phòng, thuế dự phòng (0–50%), ngày hiệu lực, xem trước, áp dụng. Mức lưu ở bảng `reserve_policies` (chỉ thêm dòng). Mỗi báo giá đọc dòng mới nhất đã tới hiệu lực; chưa có dòng nào thì dùng `CASHBACK_ESTIMATE_FEE_BPS` và `CASHBACK_ESTIMATE_TAX_RESERVE_BPS`. Link mới ghi mã `v1.2-reserve-2026-10-23+r{id}`. Tỷ lệ chia vẫn chỉ đổi qua `CASHBACK_RATE_PERCENT`.

## Final

Chỉ là phép tính offline. `payable_vnd` luôn `None`. `authorize_payable` không trả số tiền.

Phí và thuế thực tế chỉ trừ khi chưa nằm trong hoa hồng đầu vào. Phí 44 đồng của đơn tháng 8 đã gồm VAT 3 đồng. Không trừ thêm 3 đồng và không áp thêm 0,98% ở bước final.

Thuế 10% của bước ước tính không được ghi thành thuế đã nộp.

Phí chuyển tiền được xét sau khi chia. Nếu phí đó lớn hơn phần người vận hành còn giữ, phép tính bị chặn và không lập nghĩa vụ.

## Kỳ thanh toán

Phân bổ phí, thuế và điều chỉnh theo tỷ lệ hoa hồng, phần dư theo thứ tự xác định, sao cho tổng phần phân bổ bằng chứng từ. Thiếu trọng số thì trạng thái `reconciliation_required`, không ép cân.

## Bật cho khách

1. Duyệt bảng chênh lệch ở báo cáo phiên này. Số hiển thị thấp hơn 70% của hoa hồng gộp.
2. Sao lưu `data/cashback.sqlite`.
3. Chạy `cashback_bot/migrations/001_estimate_policy.sql` trên bản sao, kiểm tra, rồi mới tới file thật.
4. Đặt `CASHBACK_ESTIMATE_POLICY=v1.2`.
5. Restart bot sau bước trên, không làm trong lúc soạn chính sách.
