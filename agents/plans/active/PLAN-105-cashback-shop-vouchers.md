# PLAN-105 - Hiển thị mã giảm giá của Shop khi khách gửi link Shopee

- Trạng thái: Code xong, kiểm thử đầy đủ. Mặc định TẮT (`shop_voucher_enabled = "0"`).
- Yêu cầu: Khách dán link Shopee có thể xem nhanh các mã giảm giá của Shop (voucher của shop) để lưu trước khi đặt hàng.

## Nguyên tắc kỷ luật & an toàn
1. **Mặc định TẮT:** Tránh phá vỡ các contract thẻ link hiện có và chỉ kích hoạt khi admin chủ động bật.
2. **Không nghẽn bot (Non-blocking):** Gọi bridge service nội bộ với timeout ngắn (1.0s). Nếu bridge không phản hồi, bot vẫn trả thẻ link hoàn tiền tức thì.
3. **Báo cáo trung thực:** Khi bridge lỗi kết nối hoặc timeout, bot thông báo đúng thực tế: *"Tạm thời chưa kiểm tra được mã shop, bạn xem trực tiếp trên app Shopee nhé!"* chứ không được báo sai là *"Shop không có mã"*.
4. **Bảo vệ tài khoản Affiliate:** Dữ liệu mã shop được query qua cầu nối `shopee-mcp` (session riêng biệt với browser ẩn danh CloakBrowser), có cache 1 giờ bounded (_MAX_CACHE_SIZE=500), không spam request cào trang liên tục.
5. **Escape HTML:** Toàn bộ dữ liệu ngoài (mã code, tên shop) được escape trước khi gửi qua Telegram/Zalo.

## Dữ liệu & Cấu hình
- `bot_state`: key `shop_voucher_enabled` ("1" = bật, "0" hoặc vắng mặt = tắt).
- `link_requests`: lưu `shop_id` của sản phẩm để khi khách hoặc hệ thống gửi lại thẻ link cũ (replay), cấu trúc nút bấm vẫn đồng nhất 100%.

## Kiểm thử
- `tests/test_cashback_shop_voucher.py`: Đầy đủ test cho format số tiền, escape HTML, trạng thái lỗi, trạng thái không có mã, trạng thái có mã, và kiểm tra mặc định tắt.
