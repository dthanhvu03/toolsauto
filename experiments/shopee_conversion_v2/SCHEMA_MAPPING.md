# Schema mapping — Conversion Sync V2

Prototype này tách ba lớp dữ liệu. Không tự dịch mã trạng thái thành “đã duyệt hoa hồng”.

## Mức xác minh

| Mức | Ý nghĩa |
|---|---|
| VERIFIED | Đã thấy tên field hoặc giá trị trong POC Click/Conversion report |
| INFERRED | Có trong tài liệu nhiệm vụ hoặc API tương tự, chưa có raw response lưu lại |
| SYNTHETIC | Fixture tự tạo để test parser. Không phải validation live |

Envelope JSON `code / message / data.list` dùng trong fixture là **SYNTHETIC**. POC xác nhận list nằm ở `data.list`, nhưng không còn file raw response để khóa cấu trúc lồng nhau.

## Conversion

| Raw field | Canonical | Bắt buộc | Mức | Ghi chú |
|---|---|---|---|---|
| conversion_id | conversion_id | có | VERIFIED | Khóa nghiệp vụ cùng `source`, không dùng `order_id` |
| checkout_id | checkout_id | không | VERIFIED | Có thể khác conversion |
| order_id | order_id | không | VERIFIED | Chưa chứng minh duy nhất |
| order_sn | order_sn | không | VERIFIED | Dashboard gọi đây là Order id. Không dùng làm khóa |
| affiliate_transaction_id | affiliate_transaction_id | không | VERIFIED | Có trên order. Chưa chứng minh duy nhất giữa nhiều tài khoản |
| sub_id | sub_id | không | VERIFIED | Key đối chiếu. `----` là placeholder đã thấy ở click cũ |
| click_id | click_id | không | INFERRED | Có ở conversion mẫu POC, chưa khóa vị trí lồng nhau |
| purchase_time | purchase_time | không | VERIFIED | Epoch hoặc ISO. Có TZ thì đổi về UTC |
| click_time | click_time | không | INFERRED | Có ở Click Report |
| conversion_status | conversion_status_raw | có | VERIFIED | Giữ mã thô. `internal_status` luôn `unknown` |
| checkout_status | checkout_status_raw | không | VERIFIED | Giữ mã thô |
| order_status | order_status_raw | không | VERIFIED | `COMPLETED` không có nghĩa đã trả cashback |
| gross_commission | gross_commission | không | VERIFIED | Cột lưu số API. Một đơn thật: đây là phần Shopee, không phải tổng |
| capped_commission | capped_commission | không | VERIFIED | Bằng gross trên đơn đã đối chiếu |
| estimated_total_commission | estimated_total_commission | không | VERIFIED | Phần Shopee + phần brand trên đơn đã đối chiếu |
| affiliate_net_commission | affiliate_net_commission | không | VERIFIED | Chuỗi số. Bằng estimated trên đơn đã đối chiếu. Không phải tiền đã nhận |
| item_commission | item_commission | không | VERIFIED | Cấp item. Trùng gross khi đơn một item. Không cộng thêm vào gross |
| item_id / shop_id / item_name / item_price | cùng tên | không | INFERRED | Fixture có; POC chưa lưu mẫu item |
| source_updated_at | source_updated_at | không | INFERRED | Chưa thấy field này |

## Click

| Raw field | Canonical | Mức |
|---|---|---|
| click_id | click_id | INFERRED |
| sub_id | sub_id | VERIFIED |
| click_time | click_time | VERIFIED |
| click_region | click_region | VERIFIED |
| device_type | device_type | INFERRED |
| utm_content | utm_content | INFERRED — không dùng làm filter Click Report |

## Live shape đã đọc ngày 22/10/2026

`GET /api/v3/report/list` trả `code`, `msg`, `data.list`, `data.total_count`, `data.page_num`, `data.page_size`.

Không có `conversion_id` ở cấp checkout. Tracking nằm ở `utm_content`. Đơn nằm ở `orders[]`, với `order_id`, `order_sn`, `affiliate_transaction_id`, `order_status`. Sản phẩm nằm ở `orders[].items[]`, với `item_commission`, `item_price`, `qty`, `model_id`.

Parser tạo khóa nội bộ `inferred:{affiliate_id}:{checkout_id}:{order_id}`. Đây không phải ID do Shopee công bố. Thiếu một trong ba phần, hoặc trùng khóa trong cùng response, thì bản ghi vào `conversion_quarantine` và không ghi đè `conversions`.

Ngày 22/10/2026, một đơn trên cùng màn Conversion Report khớp hệ số `100000`:

- Giá API `8200000000` = ₫82.000
- `item_commission` và `gross_commission` `205000000` = ₫2.050, đúng phần “Hoa hồng từ Shopee (2,5%)”
- `total_brand_commission` `246000000` = ₫2.460, đúng phần “Hoa hồng Xtra (3%)”
- `estimated_total_commission` và `affiliate_net_commission` `451000000` = ₫4.510

Bốn field đó là các phần của cùng một khoản. Cột canonical vẫn lưu số API. Bản VND nằm ở metadata và không được dùng để chi trả. `internal_status` vẫn là `unknown`.

Click Report thật dùng `code`, `msg`, `data.list`, `data.total_count`. Mỗi click có `sub_id` ở cấp dòng. Không có `utm_content` trong click row đã đọc.

## Khóa và lịch sử

- Unique conversion: `(source, conversion_id)`.
- Import lại cùng payload: `unchanged`, không tạo dòng mới.
- Đổi trạng thái hoặc hoa hồng: cập nhật dòng cũ và thêm `conversion_status_history`.
- Báo cáo mới không chứa conversion cũ: dòng cũ được giữ.
- Attribution ghi đè theo `conversion_db_id`, không cộng dồn.
