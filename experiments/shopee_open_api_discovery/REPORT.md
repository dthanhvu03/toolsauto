# Shopee Affiliate Open API — discovery 2026-10-23

Nguồn bằng chứng được gắn nhãn riêng. Không có connector mới. Không sửa `experiments/shopee_conversion_v2/`. Không ghi `data/cashback.sqlite`.

## Môi trường

- Chrome profile POC: `C:\Users\Admin\chrome-profiles\shopee-affiliate-poc`. Lúc bắt đầu, process của profile này không chạy.
- Đã mở lại đúng profile, cổng debug chỉ `127.0.0.1:9222`. WSL không nối được cổng đó. Lệnh đọc trang chạy trên Windows.
- Trang `https://affiliate.shopee.vn/open_api/list` mở bằng session sẵn có. Không xuất cookie, không đọc file Cookies.
- Bundle tài liệu đang chạy: `https://deo.shopeemobile.com/shopee/shopee-affiliate-live-vn/static/js/app.df2c196d.js`.

## A. API Inventory

Một endpoint GraphQL cho mọi operation. Tài liệu không mô tả `conversionReportV2`. Chuỗi đó không có trong bundle trên.

| Nhóm | Operation | Loại | Endpoint | Auth | Việc lấy được, theo tài liệu đã render |
|---|---|---|---|---|---|
| Offer | `shopeeOfferV2` | Query | `POST https://open-api.affiliate.shopee.vn/graphql` | SHA256 header | Offer Shopee, `commissionRate`, link, phân trang `page` |
| Offer | `shopOfferV2` | Query | cùng endpoint | cùng auth | Trang `?type=brand_offer` render tiêu đề "Get Shop Offer List" và query này |
| Offer | `productOfferV2` | Query | cùng endpoint | cùng auth | Sản phẩm, `commissionRate`, `sellerCommissionRate`, giá, shop/item id. Phân trang `page` |
| Feed | `listItemFeeds` | Query | cùng endpoint | cùng auth | Danh sách file FULL/DELTA, `datafeedId` |
| Feed | `getItemFeedData` | Query | cùng endpoint | cùng auth | Dòng feed. Cột nằm trong chuỗi JSON `columns`. Tối đa 500 dòng, `offset` |
| Link | `generateShortLink` | Mutation | cùng endpoint | cùng auth | `originUrl` bắt buộc. `subIds` là mảng tối đa 5 chuỗi. Trả `shortLink` |
| Đơn | `conversionReport` | Query | cùng endpoint | cùng auth | Đơn affiliate, `utmContent`, hoa hồng, trạng thái đơn và fraud. Cửa sổ 3 tháng. `scrollId` |
| Đối soát | `validatedReport` | Query | cùng endpoint | cùng auth | Dòng theo `validationId`. Có `conversionId`, `orderId`, `utmContent`, hoa hồng. Không có field payout |

Rate limit ghi trên trang Overview: 8000 lần/giờ. Vượt thì từ chối, đợi cửa sổ sau. Mã `10030`.

`scrollId`: trang đầu không gửi cursor, tối đa 500 dòng, cursor sống 30 giây và dùng một lần. Query không cursor phải cách nhau hơn 30 giây.

Auth, trang Short Link render đúng mẫu header:

`Authorization: SHA256 Credential={AppId}, Signature={64 hex thường}, Timestamp={unix}`

Bước tính trong cùng bộ tài liệu:

1. Lấy nguyên body request.
2. Lấy timestamp. Lệch server quá 10 phút thì request hết hạn.
3. Ghép chuỗi `AppId + Timestamp + Payload + Secret`.
4. Băm ra hex thường.
5. Gắn header.

Ví dụ curl trên trang ghi thuật toán là `SHA256`. Bảng chuỗi trong bundle còn khóa `open_api_HMAC_SHA256_description` và `open_api_sha256_description`, cả hai đều nói "hiện chỉ hỗ trợ {code}". Trang đã render không điền HMAC. Chưa gọi thử chữ ký thật.

Explorer ghi trong tài liệu, chưa dùng: `https://open-api.affiliate.shopee.vn/explorer/v2`.

## B. Request Evidence

Ba nhóm không trộn.

### Nhóm 1 — trang đọc tài liệu

Mở từng URL tài liệu trả HTTP 200, nội dung nằm trong SPA. Không có XHR riêng kiểu "get API spec".

| URL | Status quan sát |
|---|---|
| `/open_api/list` | 200, title Shopee Affiliate Program |
| `/open_api/list?type=short_link` | trang render `generateShortLink` |
| `/open_api/list?type=conversion_report` | trang render `conversionReport` |
| `/open_api/list?type=validation_report` | trang render `validatedReport` |
| `/open_api/list?type=product_offer` | trang render `productOfferV2` |
| `/open_api/list?type=brand_offer` | trang render `shopOfferV2` |
| `/open_api/list?type=product_feed_offer` | trang render `listItemFeeds` |
| `/open_api/list?type=product_feed_offer_detail` | trang render `getItemFeedData` |
| `/open_api/document?type=overview` | GraphQL, rate limit, scroll, 3 tháng |
| `/open_api/home` | các bước chung, không có App ID |

### Nhóm 2 — API nội bộ website, khi trang Open API tải

| Method | URL | Status |
|---|---|---|
| GET | `/api/v3/config/website` | 200 |
| GET | `/api/v3/user/profile` | 200 |
| GET | `/api/v3/user/status` | 200 |
| GET | `/api/v3/user/check_program_permission?program_type=2` | 200 |
| GET | `/api/v3/offer/checkInAmsWhiteList` | 200 |

Đây không phải Open API. Không lưu body profile.

`GET /api/v3/user/status` trong session POC: HTTP 200, `code=0`, `allow_to_login=true`, `stop_commission_calculation=false`, `frozen_reason` rỗng, `review_status=1`, `status=1`, `program_type=1`. Không có field App ID, Secret, hay quyền Open API. Không ghi giá trị id.

`GET /api/v3/report/list` và `GET /api/v1/click_report/list` không được gọi lại trong phiên này. Schema của chúng là bằng chứng POC cũ, xem mục D.

### Nhóm 3 — Open API chính thức

`POST https://open-api.affiliate.shopee.vn/graphql`

Không gắn cookie Chrome, không gắn App ID.

- HTTP 200
- Body: `errors[0].extensions.code = 10020`, message `Invalid Authorization Header`

Khớp mã 10020 trong tài liệu. Không trả đơn.

## C. Account Access

`OPEN API ACCESS = NOT AVAILABLE / NOT VERIFIED`

Bằng chứng:

- `/open_api/home` của session này chỉ hiện quy trình: đăng ký affiliate, lấy AppID và Secret, chọn API, test, gọi online. Không hiện App ID, không hiện Secret, không có nút quản lý key.
- Route frontend quanh Open API chỉ có `/open_api`, `/home`, `/list`, `/document`. Không thấy màn hình credential.
- Project không có App ID hay Secret. Không tạo key, không gửi form xin quyền.
- Website affiliate đăng nhập được. Đó là quyền portal, không phải quyền GraphQL.
- Tài liệu có mã `10035`: tài khoản chưa được cấp Open API, phải liên hệ form `https://help.shopee.vn/portal/webform/c2d6ebc5a2d64dd1b26f8c871730cdbd`. Mã này chưa xuất hiện trên request của tài khoản này, vì chưa có chữ ký để gửi.

## D. Live Validation

| Việc | Nhãn |
|---|---|
| Danh sách operation, field, mã lỗi, rate limit, scroll, cửa sổ 3 tháng | Documentation verified. Đọc trên Chrome POC ngày 2026-10-23 |
| `POST /graphql` thiếu header trả 10020 | Live verified. Không có dữ liệu đơn |
| Hai đơn 22/08/2026 (hoa hồng ₫4.510) và 23/09/2026 (hoa hồng ₫0) có nằm trong Open API không | Unknown. Chưa gọi được `conversionReport` |
| Sub ID, order id, số tiền, trạng thái duyệt của hai đơn đó trên Open API | Unknown |
| Key website `GET /api/v3/report/list` trong `schema_map.py` | Fixture / POC trước. Không gọi lại hôm nay |
| Click report có sub id thật và giá trị `----` | Fixture verified. `fixtures/clicks_poc04_summary.json` |
| `conversionReportV2` | Không thấy trên trang và không thấy trong bundle. Không kết luận là có |

Dừng thử đơn thật tại đây vì chưa có App ID và Secret.

## E. Conversion Mapping

Đề xuất. Không sửa parser. Không gán mã trạng thái số của website sang chữ của Open API.

| Việc cần | Website POC (`data.list[]`, snake_case) | Open API `conversionReport.nodes[]` | Ghi chú |
|---|---|---|---|
| Identity checkout | `checkout_id` | `conversionId` Int64. Tài liệu: trước đây gọi là Checkout id. `checkoutId` đánh dấu To Be Removed | Chưa có cặp response cùng một đơn |
| Identity đơn | `orders[].order_id`, có `order_sn` trong fixture đã khử | `orders[].orderId` String | Open API không mô tả `order_sn` |
| Sub ID | `utm_content`. Click report riêng có `sub_id` | `utmContent`. Tài liệu: giá trị sub-id trên link. Tạo link bằng `subIds` 5 phần tử | Chưa khớp với `RniJOPP8` / `QC2a50eT` |
| Click | `click_id`, `click_time` | `clickTime` Int. Không thấy field `clickId` trong schema đã render | |
| Mua | `purchase_time` | `purchaseTime` Int, unix | |
| Hoa hồng gộp cũ | `gross_commission`, `capped_commission`, `estimated_total_commission` | `grossCommission`, `cappedCommission`, `estimatedTotalCommission` đều To Be Removed | |
| Hoa hồng đang dùng | `affiliate_net_commission` | `netCommission` (New): sau trần và sau phí MCN. `totalCommission`: sau trần, trước phí MCN. `sellerCommission`, `shopeeCommissionCapped` | Tên gần, chưa chứng minh cùng một số |
| Hoa hồng item | `items[].item_commission` | `itemTotalCommission`, `itemSellerCommission`, `itemShopeeCommissionCapped`. `itemCommission` To Be Removed | |
| Đơn vị | Prototype ghi scale `100000` cho một đơn trên dashboard website | Tài liệu: chuỗi tiền tệ địa phương | Không chia Open API cho 100000 khi chưa có mẫu cặp |
| Trạng thái conversion | `conversion_status` giữ nguyên, fixture số | `conversionStatus` String PENDING / COMPLETED / CANCELLED, To Be Removed | Không map số sang chữ |
| Trạng thái đơn | `orders[].order_status` chữ, ví dụ COMPLETED | `orderStatus`: UNPAID, PENDING, COMPLETED, CANCELLED | Cùng chữ chưa chứng minh cùng nghĩa |
| Checkout text | `checkout_status` ví dụ "Waiting for payment" | Không có trong schema Open API đã render | |
| Fraud | Không nằm trong field map chính | `fraudStatus`: UNVERIFIED, VERIFIED, FRAUD. Item có `displayItemStatus`, `itemNotes` | |
| Cập nhật nhiều snapshot | Prototype tách theo checkout + order | Cùng `conversionId` + `orderId`, kéo lại bằng `purchaseTime` trong 3 tháng, hoặc `validatedReport` theo `validationId` | Chưa chạy |

Parser V2 đang tạo `conversion_id` dạng `inferred:{affiliate}:{checkout}:{order}` vì response website không có `conversion_id` top-level. Open API có `conversionId` riêng. Khi có mẫu thật, identity nên chuyển sang `conversionId` + `orderId`, không giữ khóa inferred.

## F. Commission và payment

Ba lớp khác nhau:

1. Trạng thái đơn: `orderStatus` UNPAID, PENDING, COMPLETED, CANCELLED.
2. Trạng thái kiểm tra hoa hồng: `fraudStatus` UNVERIFIED, VERIFIED, FRAUD. `displayItemStatus` là trạng thái gộp của order và fraud. `itemNotes` là chữ giải thích pending, cancel, fraud. `conversionStatus` PENDING/COMPLETED/CANCELLED đang bị đánh dấu To Be Removed.
3. Báo cáo đã validate: query `validatedReport`, lọc bằng `validationId` lấy từ Billing Information. Trả commission và order, không trả mã chuyển khoản, ngày tiền vào ví, hay số dư.

`netCommission` là hoa hồng sau trần và sau phí MCN. Tài liệu không nói số này đã được thanh toán.

Portal có route `/payment/billing` và `/payment/payout_record`. Đó là website nội bộ. Không nằm trong danh sách Open API đã render. Chưa gọi.

## G. Recommended Architecture

Khi đã có App ID và Secret, nguồn lâu dài là GraphQL chính thức. Job đọc, không dùng Chrome.

```
AppId + Secret (ngoài git)
        |
        v
POST /graphql
  conversionReport(purchaseTime, scrollId)  -> đơn + utmContent + hoa hồng ước tính
  validatedReport(validationId, scrollId)   -> dòng đã vào một kỳ validate
        |
        v
bảng snapshot riêng, khóa conversionId + orderId
        |
        v
đối chiếu sub id với SQLite cashback (chỉ đọc)
```

Website `/api/v3/report/list` giữ vai trò đã dùng để kiểm chứng POC. Không dùng làm sync đêm, vì nó phụ thuộc session Chrome.

AddLiveTag vẫn là nguồn giá và hoa hồng ước tính lúc tạo link. `productOfferV2` có tỷ lệ hoa hồng và giá. Product feed có file FULL/DELTA nhưng cột thật nằm trong JSON `columns`, schema cột chưa được tài liệu liệt kê. Chưa đủ để thay AddLiveTag.

## H. Gate Decision

| Cổng | Kết luận |
|---|---|
| Open API Documentation | GO |
| Account API Access | NOT VERIFIED |
| Conversion API | CONDITIONAL |
| Sub ID Attribution | CONDITIONAL |
| Financial Accuracy | NO-GO |
| Commission Approval Data | CONDITIONAL |
| Long-term Sync Feasibility | CONDITIONAL |

## I. Next Action

1. Tìm trên portal chỗ cấp App ID và Secret. Trang `/open_api/home` của session này không có. Nếu không có chỗ cấp, dùng form trong mã lỗi 10035. Không tự gửi form trong task này.
2. Lưu App ID và Secret ngoài git. Gọi một `conversionReport` cho 01/08/2026–20/10/2026, giới hạn nhỏ, có `scrollId` nếu còn trang.
3. Đối chiếu hai đơn đã biết: order id, `utmContent`, số tiền, `orderStatus`, `fraudStatus`. Chưa khớp thì không đổi parser.
4. Nếu `validatedReport` cần `validationId`, lấy id đó từ Billing trên portal rồi gọi một trang. Không coi kết quả là tiền đã về ví nếu response không có field thanh toán.

## So sánh ba hướng

| | AddLiveTag | Website session | Open API |
|---|---|---|---|
| Quyền hiện tại | Đang dùng cho giá sản phẩm | Session POC đăng nhập được | Chưa có App ID/Secret |
| Ổn định | Phụ thuộc bên thứ ba | UI và `/api/v3` đổi là gãy | GraphQL có version note, field cũ đánh dấu To Be Removed |
| Chi phí | Đang có key | $0, tốn session | Tài liệu không ghi phí |
| Tự động | Có, không cần Chrome | Cần session | Có, nếu được cấp key |
| Sub ID | Không phải nguồn đơn | Click report đã thấy sub id | Tài liệu có `subIds` và `utmContent`, chưa gọi được |
| Cập nhật đơn | Không | Report list đã thấy đơn | `conversionReport` trong 3 tháng, cộng `validatedReport` |
| Trạng thái hoa hồng | Không | Field website, mã số chưa map | Fraud + order status + validated report. Không có payout |
| Bảo mật | Một API key | Cookie session | Secret ngang mật khẩu, để ngoài git |
| Lâu dài | Bổ sung giá/offer | Không chọn làm sync đêm | Chọn sau khi cổng Account Access thành GO |
