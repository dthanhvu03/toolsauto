# PLAN-177 — Thử lại sau Owner xác nhận phiên (19/11/2026)

## Kết luận

Sau Owner báo **«xong»** (đã kiểm tra UI Affiliate, không logout/login lại): **một request chi tiết hoa hồng thành công** + shortlink tạo được. Cầu nối cũ đã phục hồi. **Chưa bật nguồn native cho khách.**

## Bằng chứng

| Phép đo | Kết quả |
|---|---|
| Shortlink trước probe (`1175585681/54321049804`) | HTTP 200, `success=true`, host `s.shopee.vn` |
| Portal detail `GET /api/v3/offer/product?item_id=54321049804` | HTTP **200**, `code=0`, `ids_exact=true` (shop `1175585681`) |
| Thời điểm detail | `2026-11-19T15:58:19.574Z` (~22:58 VN) |
| Tỉ lệ (scrub) | seller `0%`, shopee/default `7%`, cap raw có |
| Health + shortlink sau restore bridge | health 200; shortlink `success=true` |

Lượt GPT trước đó (`403` / `90309999`) **không tái hiện** ở request giới hạn này.

## Artifact

- `post-xong-detail-20261119.jsonl` (fields số/%, không cookie/tên SP đầy đủ trong summary)
- `post-xong-retry-summary-20261119.json`

## Ranh giới

- Không đổi `.env`, không bật `PRODUCT_QUOTE_PRIMARY=native`, không restart Cashbot/Zalo.
- Hash npm legacy giữ nguyên; chỉ stop/start PM2 `shopee-mcp` để probe.
- Bước tiếp: Claude verify / Gate production bridge / Owner duyệt bật nguồn — vẫn pending.
