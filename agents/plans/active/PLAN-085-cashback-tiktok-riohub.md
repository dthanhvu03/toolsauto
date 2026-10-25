# PLAN-085 — Thêm TikTok Shop qua RioHub API (NHÁP)

| | |
|---|---|
| Trạng thái | **Nháp, chưa được thực hiện.** Chờ chủ bot trả lời các điều kiện ở mục 0 và duyệt |
| Executor | Phần client / đơn / đối soát là backend → cần người làm backend (theo `CLAUDE.md`, không thuộc vai Claude Code). Claude Code làm câu chữ, UX, test diễn tập, báo cáo |
| Nghiên cứu | `reports/CASHBACK_TIKTOK_RIOHUB_RESEARCH.md` (đã bổ sung spec tích hợp 09/10/2026) |

## 0. Điều kiện trước khi viết code
1. Chủ bot có tài khoản TikTok đã bật TikTok Shop Affiliate, đã kết nối vào RioHub; biết `creator_username`.
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
