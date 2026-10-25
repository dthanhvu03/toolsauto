# PLAN-085 — Thêm TikTok Shop qua RioHub API (NHÁP)

| | |
|---|---|
| Trạng thái | **Nháp.** A2 (client) đã viết theo lựa chọn của chủ bot 2026-10-25 ("Viết client, chưa nối bot"); phần còn lại chờ mục 0 |
| Executor | Phần client / đơn / đối soát là backend → cần người làm backend (theo `CLAUDE.md`, không thuộc vai Claude Code). Claude Code làm câu chữ, UX, test diễn tập, báo cáo |
| Nghiên cứu | `reports/CASHBACK_TIKTOK_RIOHUB_RESEARCH.md` (đã bổ sung spec tích hợp 09/10/2026) |

## 0. Điều kiện trước khi viết code
1. Chủ bot có tài khoản TikTok đã bật TikTok Shop Affiliate, đã kết nối vào RioHub; biết `creator_username`.
   **Thử thật 2026-10-25:** API đòi creator là **thành viên RioMCN đã được duyệt** (`403 mcn_membership_required`). Vào RioMCN nghĩa là MCN được chia hoa hồng (`shared_with_partner`), có thể có phí thành viên → phải biết tỷ lệ trước khi tính hoàn cho khách.
2. RioHub trả lời bằng văn bản: được dùng API cho bot hoàn tiền (chia lại hoa hồng cho người mua).
3. Chủ bot tự thêm vào `.env`: `RIOHUB_API_KEY`, `RIOHUB_CREATOR_USERNAME`. Không gửi khoá qua chat.
4. Chủ bot quyết hồ sơ phí / thuế cho TikTok: `actual_commission` đã trừ TNCN 10% và phần chia MCN, không trừ dự phòng thuế 10% lần nữa.

## 1. Giai đoạn A — link + báo giá (chưa ghi tiền)
| Việc | Cách làm |
|---|---|
| A1 | Nhận diện link TikTok Shop (`vt.tiktok.com/…`, `www.tiktok.com/t/…`, `shop.tiktok.com/view/product/<id>`); link khác giữ luồng Shopee |
| A2 | Client `riohub_client.py`: khoá từ `.env`; 3 tên miền, chỉ đổi khi lỗi kết nối / DNS / quá giờ; 429 đọc `Retry-After`; phân loại 401/403/404/422/424/502/503; log qua `redact` |
| A3 | Mỗi link khách: `POST /product-links` với `sub_id` của bot (không có dấu `-`) → link + tên + giá + hoa hồng trong 1 lượt. `422 product_not_promotable` → báo khách "sản phẩm không có hoa hồng", không thử lại |
| A4 | Tỷ lệ báo giá: `observed_commission.commission_rate`; không có thì `commission.rate + shop_ads_commission.rate`. Giá: `sales_price`, rỗng thì `original_price`; khoảng giá thì báo theo mức thấp |
| A5 | Ghi `link_requests` với cột nền tảng (`shopee` / `tiktok`), cùng bảng chia V1.2 + hồ sơ phí / thuế TikTok |
| A6 | Câu chữ khách Telegram + Zalo: thẻ báo giá TikTok, thời gian quyết toán TikTok |

## 2. Giai đoạn B — đồng bộ đơn + đối soát (ví vẫn khoá)
| Việc | Cách làm |
|---|---|
| B1 | Bảng `tiktok_orders`, khoá (`order_id`, `sku_id`); tiền lưu số nguyên đồng từ chuỗi decimal, không dùng float |
| B2 | Job định kỳ: `GET /orders` theo `update_time_start` = mốc lần trước − 10 phút, `update_time_end` = bây giờ, `page_size=200`, lặp hết trang; lưu mốc sau khi chạy xong |
| B3 | Không dùng webhook (bot không có HTTPS công khai) |
| B4 | `status` 1 → chờ; 2 → đã chốt (`actual_commission`); 3 → huỷ / hoàn. Ánh xạ vào `cashback_entries` như Shopee, giữ khoá tài chính |
| B5 | Thông báo đơn cho khách (Telegram / Zalo) dùng chung `order_notify` |
| B6 | `gate_b_check` thêm kiểm tra đơn TikTok |

## 3. Giai đoạn C — sau
Điều khoản V3 ghi thêm TikTok Shop; ví / rút tiền dùng chung khi chủ bot mở ví.

## 4. Thử thật (mỗi lần phải được chủ bot duyệt)
1. 1 lượt `/product-links` với 1 sản phẩm chủ bot chọn, `sub_id` thử; không tạo khách.
2. 1 lượt `GET /orders` 7 ngày gần nhất, chỉ đọc.
3. Đối chiếu `actual_commission` với số trong Ví RioHub ở 1 đơn thật trước khi bật ghi tiền.

## 5. Không làm
Không đăng ký thay chủ bot; không gọi RioHub khi chưa duyệt; không bật ví; không đổi công thức Shopee.

## Đã làm (2026-10-25)
Chủ bot dán spec đủ 8 phần và chọn "Viết client, chưa nối bot". Không làm `/general-links` + `event_id`, trang chuyển hướng `/go/…`, webhook, tìm theo tên, báo cáo (cần HTTPS công khai hoặc bot không dùng).

| File | Nội dung |
|---|---|
| `cashback_bot/riohub_client.py` (mới) | `RioHubClient`: `create_link`, `create_product_link`, `get_products` (gom 100 id), `iter_orders` (200 / trang, lặp hết). Đổi tên miền chỉ khi lỗi mạng; 429 chờ `Retry-After` (tối đa 30 giây, thử lại 1 lần); `RioHubError.kind` phân loại 401 / 403 / 404 / 422 / 424 / 429 / 503 / 5xx. Hàm đọc phòng thủ: `commission_rate_bps` (observed trước), `price_range_vnd`, `parse_order` (Decimal → đồng, làm tròn xuống), `sync_window` (chồng lấn 10 phút). CLI `products` / `link` / `orders` để chủ bot thử tay |
| `cashback_bot/config.py` | `RIOHUB_API_KEY`, `RIOHUB_CREATOR_USERNAME` (tuỳ chọn) |
| `.env.example` | Thêm `ZALO_BOT_TOKEN`, 2 biến RioHub |
| `tests/test_cashback_riohub.py` (mới) | 24 test, phản hồi giả theo ví dụ trong spec, không gọi mạng |

**Chưa chắc theo spec:** tên field mã lỗi trong thân phản hồi lỗi (đọc `error` rồi `code`); `update_time` và `settled_at_iso` có trong mô tả nhưng không có trong ví dụ phản hồi `orders`.

**Kiểm thử:** 24 test mới đạt; toàn bộ 727 test có 1 hỏng có từ trước: `test_cashback_auto_sync.py::test_14_bam_tay_khi_tu_dong_dang_chay` (giờ giả `T0 = 2026-10-25 02:00Z`, màn admin dùng giờ thật nên từ 02:00Z hôm nay lượt giả bị coi là hết hạn). Hỏng cả khi bỏ bản này. Ruff sạch.

## Thử thật lần 1 (2026-10-25, chủ bot duyệt "Đúng, thử thêm 1 link")
- `.env` có `RIOHUB_API_KEY` (52 ký tự, file quyền 600), `RIOHUB_CREATOR_USERNAME=twot283` (chủ bot xác nhận đúng tài khoản).
- `python -m cashback_bot.riohub_client orders --days 7` (chỉ đọc) → `http=403`, `{"error": {"code": "mcn_membership_required", "message": "Creator 'twot283' chưa là thành viên RioMCN (chưa được duyệt) nên chưa thể dùng chức năng này."}}`. Khoá hợp lệ (không phải 401).
- Sửa client: đọc lỗi dạng lồng `error.code` / `error.message`; CLI in một dòng thay vì traceback; +1 test (25).
- **Chưa tạo link thử:** tài khoản chưa vào RioMCN thì gần như chắc cũng bị chặn; chờ duyệt RioMCN.
