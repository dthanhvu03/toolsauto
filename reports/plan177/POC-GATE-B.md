# PLAN-177 Gate B POC — Native Shopee Affiliate quote

> Superseded for quote-schema/lookup: [Portal detail POC 19/11](PORTAL-DETAIL-POC-20261119.md) proves 8 exact-ID native quotes ±XTRA. This older GraphQL-only report is historical; Phase 2 remains gated.

- Thời điểm: 2026-11-19 (~05:10 VN) / UTC 2026-11-18T22:10Z
- Owner: ủy quyền Gate B («sao mình không làm gate B luôn»)
- Artifact JSON scrub: `POC-GATE-B-native-quote.json` (không cookie/CSRF/token/chữ ký)

## Kết luận ngắn

| Mục | Kết quả |
|---|---|
| Session portal qua bridge `:9224` | OK (`/health`, `batchCustomLink`, `productOfferLinks`) |
| ≥5 item tạo offer link native | **6/6 OK** |
| Lấy **giá + HH/rate/XTRA** native | **Chưa** — schema portal không trả commission trên `ProductOfferLink` |
| Open API `productOfferV2` | **Chưa chạy được** — không có App ID/Secret trong env; cookie REST `90309999`; fetch Open API từ page fail |

⇒ Gate B **0.0 approved**. Task **0.1 partial**: đủ proof session + link native; **thiếu quote số** → chưa đủ để Phase 2 báo hoàn từ native. Cần Owner cung cấp Open API credential **hoặc** capture DevTools query commission từ UI product offer.

## Chữ ký GraphQL portal đã chứng minh

```
productOfferLinks(
  productOfferLinkParams: [{ itemId, shopId }],
  sourceCaller: CUSTOM_LINK_CALLER
) { productOfferLink }
```

Endpoint: `POST https://affiliate.shopee.vn/api/v3/gql?q=productOfferLinks` (qua CloakBrowser session).

`productOfferV2` / `Int64` thuộc **Open API** (`open-api.affiliate.shopee.vn/graphql`) — khác schema portal; portal trả lỗi validation nếu gọi y như Open API.

## Bảng 6 item (scrub)

| shop/item | short (host+path) | DB commission (cũ, AddLiveTag) | Native HH fields |
|---|---|---:|---|
| 1206203638/42359593676 | s.shopee.vn/7VI4qQXVYn | 128630 (XTRA) | null |
| 462952014/47963173483 | s.shopee.vn/AUvgPwVIbz | 5700 (XTRA) | null |
| 1175585681/54321049804 | s.shopee.vn/70LoFVr4yo | 3461 | null |
| 994756706/40009234555 | s.shopee.vn/9V39E6s512 | 17587 (XTRA) | null |
| 1020571402/22485372686 | s.shopee.vn/20x8IKSkAz | 23490 | null |
| 15106804/56951779910 | s.shopee.vn/AAIq1L6Je5 | 24140 | null |

## Việc Owner cần chọn để hoàn tất 0.1 quote

1. **Open API**: cấp App ID + Secret (Shopee Affiliate Open API) → gọi `productOfferV2(shopId,itemId)` lấy `commissionRate` / `sellerCommissionRate` / `shopeeCommissionRate` / `commission` / giá.
2. **DevTools capture**: khi mở `affiliate.shopee.vn/offer/product_offer`, copy 1 request GraphQL/REST trả `% hoa hồng` (scrub cookie) → agent map schema portal.
3. **Tạm giữ**: Phase 1 degraded unquoted + số chỉ khi Product Data sống; native chỉ dùng tạo short (đã có `batchCustomLink`).

## An toàn

- Không lưu cookie/CSRF/Authorization/PII.
- Chỉ restart `shopee-mcp` (bridge); không restart cashback-bot.
- Endpoint POC `/api/product_offer` gắn tạm trên npm `shopee-mcp` build — cần đưa vào repo/patch có kiểm soát trước production Phase 2.
