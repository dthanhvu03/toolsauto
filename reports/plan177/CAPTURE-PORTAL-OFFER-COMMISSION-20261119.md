# Capture portal product_offer — commission schema (2026-11-19)

- Cách: session Affiliate `shopee-mcp` (như shortlink) → trang `affiliate.shopee.vn/offer/product_offer` → `fetch` in-page `credentials:include` + CSRF.
- Không lưu cookie/CSRF/token. Bridge npm đã restore hash `9f8e47f0…`; `/health` + shortlink OK sau cleanup.

## Endpoint (portal REST, không phải Open API)

```
GET https://affiliate.shopee.vn/api/v3/offer/product/list
  ?list_type=0&sort_type=1&page_offset=0&page_limit=10&client_type=1
  &keyword={query}
```

Envelope: `{ code: 0, msg: "success", data: { list, page_offset, page_limit, total_count, trace } }`

## Field quote trên mỗi phần tử `data.list[]` (đã chứng minh)

| Field | Type thực tế | Ví dụ scrubbed |
|---|---|---|
| `max_commission_rate` | string `%` | `"0%"` |
| `seller_commission_rate` | string `%` | `"2%"` |
| `default_commission_rate` | string `%` (dấu phẩy VN) | `"4,5%"` |
| `invited_campaign_offer_card.shop_commission_rate` | string | `""` (có thể trống) |
| `batch_item_for_item_card_full.price` / `price_min` / `price_max` | string số scale Shopee | `"10190000000"` → ÷100000 = VND |
| `batch_item_for_item_card_full.shopid` / `itemid` | string/number | map shop/item |
| `item_id` | string | |

Proof: keyword `kem` → `list_len=10`, lấy đủ 3 rate + price trên sample 5 item.

## So với shortlink

| | Shortlink | Quote HH (mới map) |
|---|---|---|
| Origin | `affiliate.shopee.vn` | cùng |
| Cách gọi | `withPage` + `fetch` GraphQL `batchCustomLink` | `withPage` + `fetch` REST `offer/product/list` |
| Session | Cookie portal | cùng |
| Output | `shortLink` | `%` string + price string |

## Lưu ý triển khai Phase 2

1. Parse `%`: bỏ `%`, đổi `,` → `.` rồi `float` (vd `"4,5%"` → `4.5`).
2. Giá: `int(price)/100_000` → VND (cùng scale sync Shopee).
3. Chọn rate nào cho khách: cần chốt business (`max` vs `seller` vs `default` / XTRA). Sample thấy `max` thường `"0%"` trong lúc `default` có số — **không** mặc định lấy `max`.
4. Tra cứu đúng 1 món: `keyword=item_id` lần này `list_len=0`; cần thử thêm query `shop_id`/`item_id` hoặc keyword tên/link — chưa chốt.
5. Không đụng `shopee.vn` buyer PDP (`90309999`); không cần Open API cho path này.

## Lookup đúng món (live follow-up)

- `keyword=item_id` → rỗng (xác nhận GPT).
- `keyword` tên món → lọc `shop_id`+`item_id`: **2/6** POC khớp (mẫu 1 capped XTRA, mẫu 2 XTRA); mẫu 3 non-XTRA không có trong list; 4–6 miss/fail phiên.
- JSON scrub: `POC-PORTAL-LOOKUP-COMPARE-20261119.json`. Đối chiếu bảng: `SOURCE-COMPARISON-20261119.md`.

## Kết luận Gate B 0.1

- **Schema quote portal đã có** qua `offer/product/list` (cùng kiểu session shortlink).
- **0.1 vẫn partial:** chưa đủ ≥5 item portal khớp ID ± XTRA.
- Còn lại: lookup ổn định theo link khách (không phụ thuộc đoán tên), chốt mapping rate→`sure_commission` (Decimal/bps; **không** dùng `max` khi =0%), đủ mẫu non-XTRA + wire bridge repo-owned.
