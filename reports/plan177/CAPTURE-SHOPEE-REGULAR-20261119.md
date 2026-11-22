# Capture Shopee thường — 2026-11-19 (same-session new tab)

- Cách làm (đúng theo Owner): **giữ `shopee-mcp` / session Affiliate**, trong `withPage` mở **tab mới** → `https://shopee.vn/product/{shop}/{item}`, bắt XHR; không stop profile / không mở Cloak tay riêng.
- Bridge: online trước & sau; route tạm `/api/capture_regular_pdp` đã **gỡ**, `index.js` restore hash `9f8e47f0…`.
- Scrub: không lưu cookie/CSRF/token/raw body đầy đủ.

## Items

| shop_id | item_id | Ghi chú |
|---|---|---|
| 90751457 | 42252538115 | PetQ (link bot gần nhất) |
| 1206203638 | 42359593676 | Tủ KATA |

## Kết quả

### Mode
`same_session_new_tab` — tab mới trong context Cloak của bridge (session Affiliate đang có).

### `/api/v4/pdp/get_pc`
- HTTP 200
- **`error: 90309999`** = cổng anti-bot Shopee (cùng mã `SHOPEE_ANTIBOT_ERROR` trong `shopee-mcp` client)
- Không có field giá / hoa hồng / XTRA dùng được
- Keys response lỗi dạng sparse: `0,1,2,3,4,5,9,error`

### Khác bắt được
- `/api/v4/seo/pdp/relatedlink` — `error: 0`, có `data.related_links[].price` (SEO related), **không** phải commission affiliate

## Kết luận

1. Cách **mở tab trong session bridge** là đúng (Owner đúng; lần mở profile tay + stop bridge là thừa).
2. Session profile hiện tại **đủ cho Affiliate portal**, nhưng **chưa vượt anti-bot buyer PDP** (`get_pc` → 90309999). Cookie/login Affiliate ≠ phiên mua thường đã “sạch” cho `pdp/get_pc`.
3. **Chưa** lấy được quote native từ Shopee thường qua tab này.
4. Hướng tiếp (cần Owner chọn):
   - A) Login buyer trên cùng profile (1 lần, qua `shopee-mcp` login / tab `shopee.vn`) rồi bắt lại `get_pc`
   - B) Bám portal Affiliate (product offer list / DevTools) cho HH — Gate B partial như `POC-GATE-B.md`
   - C) Open API `productOfferV2` khi có App ID/Secret

## Không nằm trong phạm vi
- Không bật quote khách từ capture này
- Không giữ route tạm trên npm bridge
