# Tài liệu tích hợp AffiPad API cho Cashbot

**Cập nhật:** 2026-11-17  
**Mục tiêu:** tạo link Shopee bằng Affiliate ID của chủ bot, gắn Sub ID theo từng khách và hỗ trợ tracking Facebook/Instagram.

> Đây là tài liệu nghiên cứu/tích hợp, chưa phải bằng chứng AffiPad được Shopee chứng nhận và chưa có request thật bằng API key của workspace. Không đưa API key, cookie hoặc token vào tài liệu này.

## 1. Kết luận nhanh

- API base URL: `https://api.affipad.com`.
- Xác thực API: `Authorization: Bearer YOUR_API_KEY`.
- Giới hạn tốc độ mặc định: **600 request/phút cho mỗi API key**. Gói trả phí có thể có giới hạn cao hơn.
- Đây là **rate limit**, khác với quota chuyển đổi theo tháng của workspace.
- Endpoint chính: `POST /v1/convert`.
- Lấy danh sách công cụ: `GET /v1/tools`.
- Kiểm tra quota tháng: `GET /v1/quota`.
- Lấy thông tin sản phẩm: `POST /v1/product-info`; mỗi lần gọi tiêu tốn 1 quota tháng.
- Không dùng đường dẫn cũ `/v1/fb-convert` cho tích hợp mới; tài liệu đánh dấu đường dẫn đó deprecated.

Nguồn chính: [API Reference](https://docs.affipad.com/api), [Authentication](https://docs.affipad.com/authentication), [Rate Limits](https://docs.affipad.com/rate-limits).

## 2. Phân biệt ba loại thông tin xác thực

| Thông tin | Dùng ở đâu | Quyền/rủi ro |
|---|---|---|
| Shopee Affiliate ID | Cấu hình Affiliate trên workspace | Định danh nguồn hoa hồng |
| Shopee cookie hoặc `shopee_token` | Bước onboarding/dashboard của AffiPad nếu chọn cách này | Là thông tin phiên Shopee, cần coi như bí mật |
| AffiPad API key | Gọi `api.affipad.com` | Có thể truy cập toàn workspace; tài liệu yêu cầu không chia sẻ/commit |

Cookie Shopee không thay cho AffiPad API key khi gọi API. API key không được ghi vào git, log, Telegram hoặc chat.

## 3. Chuẩn bị một lần

1. Hoàn tất workspace và Affiliate ID trên AffiPad.
2. Tạo công cụ chuyển link trong dashboard, ví dụ `fb-voucher`.
3. Vào **Settings → API Keys → Generate New Key**.
4. Lưu API key trong secret manager hoặc biến môi trường:

```bash
export AFFIPAD_API_KEY='...'
export AFFIPAD_TOOL_ID='...'
```

5. Lấy `toolId` thật từ API, không đoán theo slug:

```bash
curl -sS https://api.affipad.com/v1/tools \
  -H "Authorization: Bearer $AFFIPAD_API_KEY"
```

Response có dạng `data.tools[]`; lấy trường `id` của công cụ thuộc workspace mình.

## 4. Luồng đề xuất cho Cashbot

```text
Khách gửi link Shopee
  -> chuẩn hóa/resolve sản phẩm
  -> tạo Sub ID riêng cho khách
  -> POST /v1/convert với Affiliate ID của tool
  -> nhận link đã ký
  -> lưu link và Sub ID khớp nhau
  -> trả nguyên link cho khách
```

Cashbot hiện sinh Sub ID **8 ký tự chữ/số**. Nên tiếp tục dùng định dạng này để đối soát đơn, dù AffiPad cho phép `subId` dài hơn.

Không đưa output đã ký qua bước làm sạch hoặc rút gọn lại của luồng cũ. Việc đổi query sau khi ký có thể làm chữ ký không còn hợp lệ.

## 5. Chế độ chuyển đổi thường — khuyến nghị cho POC

Dùng khi muốn AffiPad tạo link affiliate bằng Affiliate ID đã cấu hình trong tool:

```bash
curl -sS -X POST https://api.affipad.com/v1/convert \
  -H "Authorization: Bearer $AFFIPAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://shopee.vn/product/123456/789",
    "toolId": "YOUR_TOOL_ID",
    "useCache": false,
    "useShortLink": false,
    "subId": "Ab12Cd34",
    "tracking": {"preset": "fb_reels"}
  }'
```

Ý nghĩa chính:

- `url`: link sản phẩm/shop Shopee.
- `toolId`: ID công cụ trong workspace.
- `subId`: mã theo khách/campaign; ký tự cho phép `a-z`, `A-Z`, `0-9`, `-`, `_`, tối đa 200 ký tự.
- `subIds`: mảng tối đa 5 chuỗi chữ/số; không dùng đồng thời với `subId`. Nếu gửi cả hai, `subId` được ưu tiên.
- Gửi `subId` hoặc `subIds` sẽ tắt cache cho request đó.
- `useShortLink=false` giúp POC dễ kiểm tra query và Sub ID; sau khi xác minh mới cân nhắc short link.
- `resolveRedirect=true` trả link đích trực tiếp nhưng tài liệu cảnh báo link chỉ dùng được trong thời gian ngắn.

Response thành công nằm ở `data.results[]`. Cần lưu `link`, `affiliateId`, `shopId`, `itemId` và mã Sub ID nội bộ; không log payload/chữ ký nhạy cảm.

## 6. Tracking Facebook/Instagram

Tài liệu công bố hai preset:

- `fb_reels` → `channel_type=fb`, `content_source=fb`, `content_type=REELS`.
- `ig_reels` → `channel_type=ig`, `content_source=ig`, `content_type=REELS`.

Có thể gửi cặp tham số Meta nếu đã có:

```json
{
  "tracking": {
    "preset": "fb_reels",
    "fbContentId": "META_CONTENT_ID",
    "encryptedPayload": "META_ENCRYPTED_PAYLOAD"
  }
}
```

`fbContentId` và `encryptedPayload` phải gửi cùng nhau. Tài liệu ghi AffiPad tự tạo và ký `fbclid`, `cts`, `sm_sig_id`; không tự sửa những trường này sau response.

Tài liệu hiện chỉ mô tả `fb_reels` và `ig_reels`; chưa có preset YouTube trong API reference đã kiểm tra.

## 7. `trackingOnly`: chỉ dùng khi đã có link affiliate của mình

Chế độ này **không tạo hoặc thay Affiliate ID**. API chỉ thêm bộ tracking Meta và ký lại URL mà mình gửi:

```bash
curl -sS -X POST https://api.affipad.com/v1/convert \
  -H "Authorization: Bearer $AFFIPAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://shopee.vn/product/123456/789?affiliate_id=YOUR_AFFILIATE_ID&sub_id=Ab12Cd34",
    "toolId": "YOUR_TOOL_ID",
    "trackingOnly": true,
    "useShortLink": false,
    "tracking": {"preset": "fb_reels"}
  }'
```

Quy tắc cần giữ:

- `affiliate_id`, `sub_id`, `utm_*` có sẵn trong input được giữ lại và nằm trong phạm vi chữ ký.
- Các trường Meta cũ được thay bằng bộ mới và ký lại.
- `subId`, `subIds`, `resolveRedirect`, `useCache` bị **bỏ qua âm thầm** trong chế độ này.
- Mỗi request thành công vẫn tiêu tốn 1 quota.
- Ưu tiên full URL Shopee; short link có thể làm mất query khi redirect.
- Chỉ nhận HTTPS trên `shopee.vn`, `shp.ee`, `shope.ee` và subdomain; tối đa 4096 ký tự; không có credential/port.

Vì vậy không được truyền link của người khác vào `trackingOnly` rồi kỳ vọng API đổi sang Affiliate ID của anh.

## 8. Giới hạn 600 request/phút

AffiPad ghi rate limit **theo từng API key**, cửa sổ theo phút:

- `X-RateLimit-Limit`: mức tối đa của cửa sổ hiện tại.
- `X-RateLimit-Remaining`: số lượt còn lại.
- `X-RateLimit-Reset`: Unix timestamp lúc cửa sổ reset.

Khi vượt giới hạn, response là HTTP `429` với mã `RATE_LIMITED` và cần xem `Retry-After` nếu server trả header đó. Tài liệu cảnh báo gọi dồn dập có thể bị throttling theo IP.

Thiết kế vận hành nên giữ mức nội bộ thấp hơn trần, ví dụ **540 request/phút (90%)**, để chừa khoảng cho retry và các endpoint quản trị. Không dùng 600 request/phút làm mục tiêu liên tục.

Pseudo-code retry:

```python
# minh họa; chưa nối vào Cashbot
for attempt in range(3):
    response = request()
    if response.status_code != 429:
        return response
    delay = min(1.0 * (2 ** attempt) + random_jitter(), 30.0)
    sleep(delay)
raise RateLimitError()
```

Retry chỉ áp dụng cho lỗi tạm thời. Không retry vô hạn, không retry `401`, `400`, `404` hoặc `QUOTA_EXCEEDED`.

## 9. Quota tháng khác rate limit

`GET /v1/quota` trả plan, `limit`, `used`, `remaining`, `overage` và ngày bắt đầu chu kỳ. Cần gọi định kỳ ở admin/monitoring, không gọi cho mỗi khách.

Các request có thể tiêu quota theo tài liệu:

- `/v1/convert`: mỗi conversion thành công; `trackingOnly` thành công cũng tính 1.
- `/v1/product-info`: mỗi request tính 1.
- `trackingOnly` không dùng cache; mỗi request là request mới.
- Lỗi nội bộ 500 được hoàn quota; hành vi 404/402/429 theo tài liệu endpoint.

Do đó với Cashbot nên bỏ qua `/v1/product-info` ở request đầu nếu chưa cần hiển thị tên/giá; link conversion là đủ cho POC.

## 10. Mã lỗi cần xử lý

| HTTP | Mã | Xử lý |
|---:|---|---|
| 400 | `INVALID_REQUEST` | Sửa JSON/tham số; không retry |
| 400 | `INVALID_URL` | Chuẩn hóa lại link Shopee |
| 401 | `UNAUTHORIZED` | Kiểm tra/revoke API key; không retry liên tục |
| 404 | `TOOL_NOT_FOUND` | Lấy lại `/v1/tools`, kiểm workspace |
| 429 | `RATE_LIMITED` | Đọc `Retry-After`, backoff có jitter |
| 429 | `QUOTA_EXCEEDED` | Dừng conversion, báo admin kiểm quota/gói |
| 503 | `NO_AFFILIATES` | Retry giới hạn |
| 503 | `SHOPEE_BLOCKED` | Backoff; không bão request |
| 503 | `RESOLVE_FAILED` | Retry giới hạn, giữ link gốc |

## 11. Checklist POC một sản phẩm

- [ ] Có Affiliate ID đúng tài khoản.
- [ ] Tool `fb-voucher` đã tạo và lấy được `toolId` thật.
- [ ] API key lưu ngoài repo và không xuất hiện trong log.
- [ ] Gọi `useShortLink=false`, `trackingOnly=false` ở lượt đầu.
- [ ] Gửi Sub ID mới, duy nhất, đối chiếu đúng từng ký tự.
- [ ] Kiểm tra link trả về mở đúng shop/item.
- [ ] Kiểm tra Affiliate ID/Sub ID trong đích đến bằng log đã che bí mật.
- [ ] Kiểm tra voucher tại checkout bằng tài khoản chủ bot.
- [ ] Chỉ sau khi POC đạt mới nối vào Cashbot; chưa đổi luồng tiền, schema hoặc dùng Sub ID `VOUCHERS` cho khách.

## 12. Khoảng trống cần xác minh

Tài liệu API không chứng minh:

- Bot Săn Sale đang dùng AffiPad.
- Shopee sẽ chấp nhận mọi bộ Meta tracking do bên thứ ba ký.
- Voucher chắc chắn còn lượt hoặc được áp dụng khi checkout.
- Đơn hợp lệ sẽ ghi nhận đúng commission/Sub ID.
- Có preset YouTube tương đương.

Các điểm này cần một POC có kiểm soát và một đơn hợp lệ do chủ tài khoản thực hiện.
