# PLAN-064 — Lưu thêm dữ liệu sản phẩm AddLiveTag cho thống kê

| | |
|---|---|
| Trạng thái | **APPROVED (user, 2026-10-23)** — code xong, chờ restart; `base_rate`/`cap` chờ user |
| Executor | Claude Code (user trực tiếp giao) |
| Bối cảnh | User không đăng ký được Shopee Open API App ID/Secret → tiếp tục AddLiveTag, tìm nguồn dự phòng sau |
| Phạm vi | `cashback_bot/` + test cashback |

## Rủi ro đã báo user
AddLiveTag tự ghi `nonCommercialOnly=True`, `apiUnofficial=True`. Bot là dùng thương mại → có thể bị khoá key. Cần nguồn dự phòng; ranh giới thay nguồn là `ProductDataClient.fetch()` + `quote_from_payload()`.

## Việc làm
- Thêm cột cho phép NULL vào `link_requests` (qua `_add_column` trong `migrate()`): `cat_name`, `shop_name`, `seller_commission_vnd`, `shopee_commission_vnd`, `commission_rate_bps`, `is_xtra`, `is_capped`.
- `quote_from_payload` đọc các trường đó một cách lỏng: thiếu hay sai thì để NULL, **không** từ chối báo giá.
- Màn 📈 Thống kê: hoa hồng người bán vs Shopee/Xtra, tỷ lệ trung bình, số link Xtra / chạm trần, top ngành hàng, top shop. Ghi rõ số link có dữ liệu (link cũ không có).

## Chưa làm (chờ user)
- `base_rate` / `cap` theo hạng tài khoản: cần user đưa số từ trang Shopee Affiliate.

## Tiêu chí xong
- [x] Link mới lưu đủ các trường khi API có; thiếu trường vẫn tạo link bình thường.
- [x] Thống kê hiện các mục mới; DB cũ chưa có cột không vỡ.
- [x] Migration thử trên bản sao DB; pytest cashback xanh.

## Proof / Log thực thi

### Claude Code — 2026-10-23

- Gọi thật 1 lần `product-data.php` (item 50768320759): xác nhận tên trường `catName`, `shopName`, `sellerComFinal`, `shopeeComFinal`, `totalRatePercent`, `isXtra`, `isCapped` (giá trị dạng chuỗi). Response có `legalNotice.nonCommercialOnly=True`, `apiUnofficial=True`. Tài liệu `data.addlivetag.com` và `/shopee/`: không có endpoint đơn, click hay thống kê tài khoản; có `base_rate`/`cap` cho hạng tài khoản.
- `product_data.py`: `ProductQuote` thêm 7 trường mặc định None; `_text`, `_flag`, `_rate_bps` đọc lỏng, không chặn báo giá.
- `db.py`: `PRODUCT_INSIGHT_COLUMNS` thêm qua `_add_column` trong `migrate()`; `_insert` chỉ ghi cột có trong DB và trong fields.
- `admin_stats.py` + `admin_ui.py`: mục "🏷️ Hoa hồng theo nguồn" (n/tổng link có dữ liệu, người bán vs Shopee/Xtra, tỷ lệ TB, Xtra, chạm trần, top 3 ngành, top 3 shop); DB chưa có cột thì ẩn.
- Thử trên bản sao `data/backups/cashback-20261023T104207Z.sqlite`: thêm đủ 7 cột, chạy 2 lần, 27 dòng giữ nguyên, `integrity_check` ok; thống kê hiện "0/27 link có dữ liệu".
- Test `tests/test_cashback_insight.py` (6 test). Proof: **171 passed**.
