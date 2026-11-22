# PLAN-177 — Đối chiếu AddLiveTag, Shopee và Shopee Affiliate

> **Update Codex 19/11 17:17 VN:** Đã tìm thấy portal detail REST theo item_id, lấy 8 item exact shop/item gồm ±XTRA; mapped sure và giá khớp PD, 5 mẫu default-as-total overquote. Xem [PORTAL-DETAIL-POC-20261119.md](PORTAL-DETAIL-POC-20261119.md). Bảng 2/6 và kết luận thiếu native phía dưới là lịch sử của lượt list/name lookup, đã được bổ sung bởi detail POC. Gate 0.1 có technical proof; production/freshness/0.3 vẫn pending.

- Ngày: 2026-11-19 (VN)
- Mẫu: 6 item đã dùng trong `POC-GATE-B-native-quote.json`; bảng đánh số mẫu, không lặp ID/tên sản phẩm.
- Phạm vi: request đọc-only, dùng `ADDLIVETAG_API_KEY` trong memory; không ghi DB, không đổi Cashbot, không lưu key/cookie/raw payload.
- Mục đích: kiểm chứng nguồn và độ lệch, **không** phê duyệt quote live.

## AddLiveTag Product Data hiện tại

| Mẫu | HTTP/dataSource | Giá (₫) | HH raw (₫) | Seller (₫) | Shopee (₫) | rate | HH `sure_commission` (₫) | XTRA/cap |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 200 / db | 1,354,000 | 134,780 | 94,780 | 40,000 | 15% | 128,630 | yes / yes |
| 2 | 200 / api | 60,000 | 5,700 | 4,200 | 1,500 | 9.5% | 5,700 | yes / no |
| 3 | 200 / api | 138,475 | 9,693 | 0 | 9,693 | 7% | 3,461 | no / no |
| 4 | 200 / api | 167,500 | 25,125 | 13,400 | 11,725 | 15% | 17,587 | yes / no |
| 5 | 200 / db | 162,000 | 20,250 | 16,200 | 4,050 | 12.5% | 20,250 | yes / no |
| 6 | 200 / api | 284,000 | 36,920 | 17,040 | 19,880 | 13% | 24,140 | yes / no |

`sure_commission` là giá trị Cashbot dùng để tính quote: Seller commission cộng Shopee commission tối đa 2.5% giá món; không phải tổng raw commission trong mọi trường hợp. Giá trị history/offer phải map qua quy tắc này trước khi so số hoàn.

## AddLiveTag Offers và lịch sử hoa hồng

- `offers/product-offer.php` trả dữ liệu thành công 6/6 truy vấn, nhưng tìm đúng `itemId` chỉ **2/6** mẫu theo tên. Hai hàng khớp có `commissionRate=15%`: mẫu 1 trùng Product Data 15%; mẫu 2 lệch Product Data 9.5%. Vì vậy danh sách Product Offer chưa phải quote chính xác cho từng item nếu không khớp ID và chưa hiểu ngữ nghĩa rate.
- `price-tracking/history.php` với `type=both`, 6 item, 30 ngày trả **6/6** item và mốc 2026-11-19. History rate/split khớp Product Data hiện tại ở các mẫu được thử, nhưng request không có `base_rate`/`cap`; tài liệu AddLiveTag nói cần tier tài khoản để lịch sử hoa hồng được tính đúng. Không dùng chuỗi này làm chuẩn quote cho tới khi chốt tier.
- Mẫu 5 có latest price history **142,560₫**, trong khi Product Data hiện tại là **162,000₫** và commission `priceSnapshot=162,000₫`. Hai API không nhất quán về giá ở mẫu này; cần điều tra freshness/nguồn trước khi quote.
- So với dữ liệu AddLiveTag lưu trong POC cũ: `sure_commission` khớp ở 5/6 mẫu; mẫu 5 đổi từ 23,490₫ xuống 20,250₫. Rate hiển thị mẫu 4 đổi 16%→15% và mẫu 6 đổi 14%→13%, dù `sure_commission` không đổi. Điều này cho thấy tỷ lệ và tiền có thể thay đổi theo thời điểm/nguồn; POC cũ không đại diện mức hiện tại.

## Shopee thường và Shopee Affiliate

- Trang sản phẩm Shopee thường được thử bằng HTTP: trả 200 nhưng HTML không chứa ID sản phẩm hoặc metadata giá đọc được. Endpoint item JSON công khai trả HTTP 403 / mã 90309999. Vì vậy lượt này **không có giá Shopee thường độc lập** để đối chiếu; giá trong bảng vẫn lấy từ Product Data, không gán nhầm là giá Shopee đã xác minh trực tiếp.
- Shopee Affiliate portal POC đã có: `productOfferLinks` tạo short offer link **6/6**, nhưng `ProductOfferLink` chỉ có link, không có commission/rate/XTRA. `productOfferV2` không thuộc portal schema; gọi Open API thất bại `Failed to fetch`.
- **Cập nhật 19/11 chiều (live):** portal REST `GET /api/v3/offer/product/list` **có** giá + `max`/`seller`/`default_commission_rate` (string `%`, phẩy VN). Proof scrub: `CAPTURE-PORTAL-OFFER-COMMISSION-20261119.md` + `POC-PORTAL-LOOKUP-COMPARE-20261119.json`.

### Portal vs Product Data (cùng lúc fetch — bảng 0.2 một phần)

| Mẫu | Portal match `shop+item` | Giá portal | seller% / default% / max% | Hyp C → sure ước tính | PD sure | Δ | XTRA/cap (PD) |
|---:|---|---:|---|---:|---:|---:|---|
| 1 | yes (name→filter) | 1,354,000 | 7% / 9,5% / 0% | 128,630 | 128,630 | 0 | yes / yes |
| 2 | yes (name→filter) | 60,000 | 7% / 9,5% / 0% | 5,700 | 5,700 | 0 | yes / no |
| 3 | **no** (list rỗng) | — | — | — | 3,461 | — | no / no |
| 4 | **no** (fetch fail phiên) | — | — | — | 17,587 | — | yes / no |
| 5 | **no** (list rỗng) | — | — | — | 20,250 | — | yes / no |
| 6 | **no** (không attempts) | — | — | — | 24,140 | — | yes / no |

Ghi chú lookup:
- `keyword=item_id` / `shop_id+item_id` query → **list rỗng** trên 6 SKU POC.
- Match đúng ID chỉ khi `keyword` ≈ tên món rồi lọc `shop_id`+`item_id` trong `data.list`.
- Hypotheses: `A` default-as-total, `B` seller+2.5% cap default, `C` split default−seller — **cùng số** trên mẫu 1–2 (vì default% ≈ seller%+2.5%); `D` max-as-total **sai** (max=0%). Chưa đủ mẫu non-XTRA / lệch split để chốt 1 công thức.
- Gate B **0.1 vẫn partial**: chưa ≥5 item portal khớp ID có ±XTRA.

## Đường API, auth và ranh giới nguồn

| Endpoint | Cashbot gửi | Mục đích / dữ liệu | Trạng thái |
|---|---|---|---|
| `data.addlivetag.com/product-data/product-data.php` | GET `item_id` hoặc `url`; `X-API-Key` | Quote chi tiết một sản phẩm; Cashbot đang dùng trước khi tạo link | 6/6 trả quote được ở lượt kiểm tra |
| `data.addlivetag.com/offers/product-offer.php` | GET `keyword/page/limit`; `X-API-Key` | Danh sách offer theo từ khóa, gồm giá và `commissionRate` | 6 truy vấn 200; chỉ 2 match đúng item ID |
| `data.addlivetag.com/price-tracking/history.php` | POST `item_ids/type/days`; `X-API-Key` | Chuỗi giá/rate/Seller/Shopee/XTRA | 6/6; tier `base_rate/cap` chưa chốt |
| `data.addlivetag.com/search/market.php` | GET `q/sort/limit/price_min`; `X-API-Key` | Tìm candidate cho deal; Cashbot vẫn gọi Product Data để tính hoàn | Có code; không gọi live trong lượt này |
| `addlivetag.com/api/v1/conversions.php` | GET `type/source/from/to/page/page_size`; `X-API-Key` | Cross-check đơn/click và fallback thông báo | Không phải sổ đơn/ví chính; thiếu `order_id`/`is_fraud` |
| `api.addlivetag.com/v1/shopee-link.php` | GET `url/sub_id`; Bearer API key | Tạo link tracking/short, không quote | Feature flag mặc định tắt; không gọi live lượt này |

Trong code Cashbot, Product Data / Offers / History / conversion client gửi API key AddLiveTag; không gửi Shopee cookie của bot. PLAN-098 ghi conversion service lấy dữ liệu từ tài khoản Affiliate đã gắn trên AddLiveTag. Chưa có bằng chứng Product Data dùng chính cookie đó; docs mô tả nguồn `api`/`db`/cache và tier `base_rate`/`cap`.

## Kết luận

1. AddLiveTag hiện là nguồn duy nhất trong phép thử trả đủ quote cho 6 mẫu, nhưng có stale/cache source, một lệch giá History, và độ lệch so với snapshot cũ.
2. AddLiveTag Offers là bộ khám phá danh sách; không được coi `commissionRate` trên kết quả tìm gần đúng là quote của item nếu không match chính xác.
3. Shopee thường: giá chưa lấy được qua đường HTTP hiện tại. Shopee Affiliate: link native đã chứng minh, commission native chưa.
4. Chưa promote native hay thay công thức quote; `sure_commission` vẫn cần dữ liệu split + tier/freshness đã kiểm chứng.
5. Tài liệu AddLiveTag công khai hiện ghi API miễn phí cho nghiên cứu/công cụ nội bộ và không dùng cho mục đích thương mại; PLAN-064 cũng lưu `nonCommercialOnly=True` / `apiUnofficial=True`. Cần cân nhắc giới hạn này trước khi xem API đó là nguồn production lâu dài.

## Nguồn và proof

- Code: `cashback_bot/product_data.py`, `price_watch.py`, `deals.py`, `addlivetag_orders.py`, `alt_shopee_link.py`, `config.py`.
- Live AddLiveTag outputs: scrubbed, in-memory; không ghi ID/tên sản phẩm, key, cookie hoặc response thô vào báo cáo.
- Shopee Affiliate: `reports/plan177/POC-GATE-B.md` + `POC-GATE-B-native-quote.json`.
- AddLiveTag docs: `https://data.addlivetag.com/shopee/` (Product Data / Offers / Market) và `https://data.addlivetag.com/` (Price & Commission History).
