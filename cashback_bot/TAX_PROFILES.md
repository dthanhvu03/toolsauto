# Hồ sơ thuế nhiều loại hình

Calculator dùng chung cho PERSONAL, INDIVIDUAL_BUSINESS và HOUSEHOLD_BUSINESS. Nhãn tài khoản không chọn thuế suất. Chưa bật trên bot đang chạy. Không có migration và không có payout.

## Hồ sơ có phiên bản

Mỗi lần đổi loại hình là một `TaxProfileVersion` mới, gắn vào `PolicyHistory`. Bản cũ không bị sửa.

Một phiên bản ghi:

| Mục | Cách dùng |
|---|---|
| Loại hình và `shopee_status` | `confirmed` chỉ khi Shopee đã chấp thuận. `pending` hoặc `unverified` không được dùng để miễn thuế |
| `effective_from` | Ngày bắt đầu. Đơn lấy phiên bản có hiệu lực đúng ngày đơn |
| `shopee_accepted_on` | Bắt buộc trùng ngày hiệu lực khi đổi loại hình |
| Phương thức khấu trừ | Shopee khấu trừ, tự kê khai, kết hợp, hoặc chưa xác minh |
| Thuế đã khấu trừ | Số trên chứng từ. Khác với dự phòng |
| Thuế tự phải nộp | Nghĩa vụ đã biết nhưng chưa nộp |
| Dự phòng | Khoản admin nhập khi nghĩa vụ chưa chốt |
| Doanh thu năm | Admin khai từ các nguồn. Không tự miễn thuế |
| Nguồn chứng từ và ngày xác nhận | Thiếu thì chặn xác nhận chi |
| `legal_rule_id` | Trỏ tới `TaxRule` có ngày hiệu lực, nguồn và trạng thái `verified` hoặc `unverified` |

`TaxRule` không chứa thuế suất sẵn. Muốn có số thì admin ghi vào hồ sơ sau khi đối chiếu chứng từ.

## Công thức chung

```
Gross
− phí Shopee chưa nằm trong gross
− thuế đã khấu trừ chưa nằm trong gross
− thuế tự nộp chưa nộp
− dự phòng chưa nằm trong gross
− chi phí hợp lệ khác
= Distributable
× tỷ lệ chia, làm tròn xuống
= Cashback
```

`payable_vnd` và `available_fund_vnd` luôn là null. Tiền Shopee chưa trả không vào quỹ. Sổ `fund_after_shopee` chỉ là thử nghiệm: không giữ chỗ nếu số hoàn lớn hơn tiền đã nhận.

## Mô phỏng chuyển loại hình

Đơn tháng 8, hoa hồng 4.510đ, phí 44đ. Ba nhãn tài khoản cho cùng một kết quả nếu các số thuế admin nhập giống nhau: còn 4.466đ, 70% là 3.126đ, payable null.

Cá nhân từ 01/01/2026, chuyển cá nhân kinh doanh từ 01/07/2026:

- Đơn tháng 3 vẫn gắn `personal-2026`.
- Nếu khách đã được báo 2.809đ, số đã cam kết giữ nguyên khi hồ sơ mới xuất hiện.
- Đơn từ 01/07 dùng phiên bản mới.
- Điều chỉnh đơn cũ không nhảy sang thuế suất của phiên bản mới.

Cá nhân kinh doanh sang hộ kinh doanh làm cùng một bước append. Thiếu ngày Shopee chấp thuận thì không tạo được phiên bản mới.

## Ma trận kiểm thử

| # | Tình huống | Kết quả mã kiểm tra |
|---|---|---|
| 1 | Cá nhân chuyển CNKD giữa năm | Đơn cũ giữ phiên bản và số đã cam kết |
| 2 | CNKD chuyển HKD | Đúng phiên bản theo ngày |
| 3 | Shopee đã khấu trừ 200đ | Trừ một lần, còn 4.266đ |
| 4 | Tự khai 300đ chưa nộp | Trừ 300đ, không trừ thêm 10% |
| 5 | Xác minh không phải giữ thuế | Còn 4.466đ. Xin miễn vì doanh thu nhỏ bị từ chối. Payable vẫn null |
| 6 | Nhiều kỳ, nhiều chính sách | Mỗi kỳ một phiên bản |
| 7 | Một kỳ nhiều đơn | Phí 44đ phân bổ đủ, tổng còn 4.466đ |
| 8 | Khấu trừ rồi điều chỉnh thêm 30đ | Phần đã nằm trong gross không trừ lại |
| 9 | Thiếu phí, thiếu chứng từ, phương thức chưa rõ | Không ra số chia, payable null |
| 10 | Tiền Shopee chưa về hoặc nhỏ hơn phần chia | Không lập quỹ và không chi |

## Đã có trên bot (ADR-047)

Admin khai loại hình kèm mức phí và thuế dự phòng cho báo giá V1.2 trong `/admin` → Thuế & phí. Loại hình ở đó chỉ là nhãn; hồ sơ thuế đầy đủ cho đối soát bên dưới vẫn chưa nối.

## Giao diện đề xuất

Admin, chưa xây trong lần này:

- Chọn loại hình và ngày Shopee chấp thuận. Không sửa dòng cũ.
- Ô thuế đã khấu trừ, thuế tự nộp, dự phòng. Ba ô riêng.
- Quỹ tối đa chỉ hiện khi có số Shopee đã trả. Không có chứng từ thì để trống, không hiện 0.
- Phần còn lại sau phí, thuế và sau khi trừ cashback dự kiến.
- Cảnh báo khi thiếu chứng từ, quy tắc chưa verified, hoặc phương thức khấu trừ chưa rõ.
- Lịch sử phiên bản: mã, ngày, loại hình, người xác nhận.

Telegram:

- "Cashback dự kiến: Xđ".
- "Số này đã trừ khoản dự phòng. Số cuối cùng có thể đổi sau khi Shopee đối soát."
- Không có số dư, không có nút rút.
- Khách không sửa được thuế suất.

## Giả định pháp lý cần xác minh

Các mục dưới đây chưa được đưa vào thuế suất của code.

| Giả định | Trạng thái |
|---|---|
| Nghị định 68/2026/NĐ-CP và 141/2026/NĐ-CP áp dụng thế nào cho affiliate | Chưa đối chiếu điều khoản trong phiên này |
| Cá nhân, cá nhân kinh doanh, hộ kinh doanh có cùng hay khác cách tính trên hoa hồng Shopee | Chưa xác minh |
| Shopee đang khấu trừ hộ, để tự kê khai, hay tùy kỳ | Chưa có điều khoản hợp đồng trong repo |
| Doanh thu Shopee thấp thì được miễn | Không dùng. Code từ chối suy ra miễn thuế từ doanh thu |
| 10% trong ước tính V1.2 là thuế luật định | Không phải. Đó là dự phòng cấu hình của bước ước tính link |
| Kỳ tháng 8 không bị khấu trừ TNCN nên mọi kỳ sau cũng vậy | Không đủ. Kỳ đó chỉ chứng minh VAT của phí dịch vụ |

## Rủi ro trước khi bật

Bật hồ sơ khi quy tắc vẫn `unverified` thì số có thể tính được nhưng payable vẫn null. Rủi ro là admin nhìn số minh họa rồi chi tay. Màn admin cần ghi "không phải số được chi" cạnh mọi dòng chưa verified.

Đổi loại hình mà quên ngày Shopee chấp thuận bị chặn. Rủi ro còn lại là gắn nhầm phiên bản vào đơn mới. Đơn lưu `profile_version_id` tại thời điểm ghi nhận, không lấy hồ sơ mới nhất khi đối soát lại.

Chưa triển khai production.
