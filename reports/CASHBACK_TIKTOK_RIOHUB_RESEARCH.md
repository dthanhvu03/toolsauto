# Nghiên cứu: thêm TikTok Shop qua RioHub API

| | |
|---|---|
| Ngày | 2026-10-25 |
| Người làm | Claude Code (chỉ đọc tài liệu công khai; không đăng ký, không gọi API RioHub, không viết code) |
| Yêu cầu | Chủ bot gửi bài giới thiệu RioHub ("từ 100.000 xuống 1.000 lượt gọi API") và đồng ý cho nghiên cứu |
| Cập nhật | 2026-10-25: bổ sung spec tích hợp RioHub (bản 09/10/2026) chủ bot gửi |
| Kết luận | **Về kỹ thuật làm được.** RioHub có đủ 3 thứ bot cần: tạo link có mã theo dõi, tra giá + hoa hồng, kéo đơn. Còn **3 điều phải hỏi rõ trước khi viết code**: (1) chủ bot có tài khoản TikTok đủ điều kiện affiliate chưa; (2) RioHub giữ lại bao nhiêu hoa hồng, tiền về ví RioHub như thế nào; (3) RioHub có cho dùng API để chạy bot hoàn tiền không |

## 1. Mẹo "1 link gốc" trong bài và bot mình

- **Shopee (đang chạy):** bot tự ghép link `an_redir` trên máy, gắn `sub_id` riêng cho từng khách (`affiliate.py`). Ghép link **không gọi API**. Mỗi link chỉ gọi AddLiveTag một lần để lấy giá + tỷ lệ hoa hồng. Bài RioHub không giúp gì thêm cho Shopee.
- **TikTok Shop qua RioHub:** áp dụng được đúng mẹo này.
  - Mỗi sản phẩm tạo **1 link gốc** (`/general-links`), lưu lại.
  - Mỗi khách: thay chữ `o_event_id` trong link bằng mã của bot (dùng chính `sub_id`), không gọi API.
  - Đơn trả về `trace_id` = mã đó, nên vẫn biết đơn của khách nào.
  - Nếu nhiều khách cùng gửi một sản phẩm, bot chỉ gọi tạo link một lần.

## 2. RioHub API: những gì đã xác minh (từ trang developer)

| Mục | Nội dung |
|---|---|
| Đăng nhập API | Khoá API trong header `X-Riohub-Api-Key`, tạo ở trang Developer; khoá chỉ hiện một lần. Không có OAuth |
| Điều kiện | Tài khoản RioHub (miễn phí) + **ít nhất 1 tài khoản TikTok creator đã kết nối**; API chỉ thao tác trên creator của chính tài khoản |
| Tạo link | `POST /partner/tiktok/affiliate/links` (có `sub_id`, 1–128 ký tự `[A-Za-z0-9_-]`); `/product-links` (link + thông tin sản phẩm trong một lần gọi); `/general-links` (link gốc, tối đa 50 sản phẩm, dùng `event_id`); `/links/batch` |
| Tra sản phẩm | `GET /products` (tối đa 100 ID, lưu đệm 24 giờ), `GET /products/search` |
| Sản phẩm không quảng bá được | `422 product_not_promotable` (không có hoa hồng, chưa duyệt, bị hạn chế) |
| Đơn hàng | `GET /orders`, lọc theo `trace_id` |
| Trạng thái đơn | `status` 1 chờ / 2 đã quyết toán / 3 huỷ-hoàn; `settlement_status` gốc TikTok; `fully_refunded`, số lượng hoàn / trả |
| Tiền | `est_commission` (ước tính, đã gồm thưởng và shop ads); `actual_commission` (thực nhận, rỗng tới khi đối soát); `pit` (thuế TNCN), phí thưởng; `settled_at` |
| Webhook | `order.created` / `updated` / `refunded`, ký HMAC-SHA256, cần **HTTPS công khai**, gửi lại tối đa 6 lần, có thể trùng và sai thứ tự |
| Giới hạn | 300 lượt/phút, 100.000 lượt/ngày mỗi khoá; TikTok còn giới hạn riêng theo creator (`429 tiktok_rate_limited`) |
| Dự phòng | 2 tên miền phụ (`riohub.riokupon.com`, `.me`), chỉ dùng khi lỗi mạng |

**Đã rõ nhờ spec tích hợp (bản 09/10/2026, chủ bot gửi):**
- `actual_commission` = `actual_standard_commission + actual_bonus_commission + actual_shop_ads_commission + shared_with_partner + pit + actual_creator_commission_reward_fee`. 3 khoản cuối **đã mang dấu âm**: phần chia MCN, **thuế TNCN 10%**, phí reward. Tức là `actual_commission` đã trừ hết, không trừ thêm.
- **Tỷ lệ để báo giá:** `commission.rate` chỉ là tỷ lệ chuẩn, không gồm thưởng. Dùng `observed_commission.commission_rate` (tỷ lệ tổng lấy từ đơn gần nhất; `scope` = creator hoặc global). Không có thì dùng `commission.rate` + `shop_ads_commission.rate`. `rate` thô ÷ 100 = %.
- **Giá:** `sales_price` có thể rỗng → dùng `original_price`; giá và hoa hồng có thể là khoảng "min - max".
- **Link riêng từng khách:** `/links` (1 lượt mỗi khách) hoặc `/links/batch` (tối đa 50 `sub_id` một lượt, mỗi `sub_id` vẫn tính 1 lượt quota). Đơn mang `trace_type = SPECIFIC`, `trace_id` = `sub_id`. `/product-links` trả link + giá + hoa hồng trong 1 lượt, hợp nhất cho bot.
- **`sub_id` tách 4 phần bằng dấu `-`:** `sub_id` của bot không được chứa `-`.
- **Đồng bộ đơn:** lọc `update_time_start` / `update_time_end`, `page_size` tối đa 200. Khoá đơn là (`order_id`, `sku_id`) vì một đơn có nhiều SKU.
- **`settled_at`:** về `null` khi đơn chuyển huỷ / hoàn; chốt lại thì nhận mốc mới. Lệch TikTok tối đa khoảng 3 giờ (nhịp đồng bộ của RioHub).
- **Lỗi riêng:** `424 creator_token_invalid` (token TikTok của creator hỏng, không phải khoá API sai), `503 tiktok_scope_unavailable` (thử lại không giúp), `502 tiktok_shop_error` (thử lại có giãn cách).

**Hệ quả với chính sách V1.2 của bot:** báo giá hiện trừ "dự phòng thuế 10%" trên hoa hồng gộp. Với TikTok, TNCN 10% và phần chia MCN đã bị trừ trong `actual_commission`. Nếu đem công thức Shopee áp nguyên thì **trừ thuế hai lần**. Cần một hồ sơ phí / thuế riêng cho TikTok (chủ bot quyết mức).

## 3. Điều khoản RioHub (trang /terms)

| Điểm | Nội dung | Ảnh hưởng tới bot |
|---|---|---|
| Công ty | Công ty TNHH Thiết Kế Quản Lý Và Quảng Cáo Dimaco (DIMACO), hỗ trợ `hotro@riohub.vn`. Trang không ghi địa chỉ, mã số thuế | Cần biết pháp nhân để đối soát, xuất chứng từ |
| Hoa hồng | Số liệu do TikTok Shop cung cấp; RioHub đối soát; **rút tiền qua Ví RioHub**. Không ghi tỷ lệ RioHub giữ lại | Phải biết phần chủ bot thực nhận thì mới tính được tỷ lệ hoàn cho khách |
| Cấm | "Dùng bot, script, hoặc truy cập API ngoài phạm vi được cấp phép"; "Tạo đơn hàng ảo, **tự mua qua link của mình** để trục lợi hoa hồng" | Bot hoàn tiền là khách mua qua link của chủ bot rồi được chia lại. Câu này có thể bị hiểu là cấm → **phải hỏi RioHub bằng văn bản** |
| Hoàn tiền / cashback | Không nhắc tới | Chưa rõ được phép hay không |
| Chế tài | Giữ hoặc thu hồi hoa hồng khi có gian lận; khoá tài khoản | Rủi ro mất hoa hồng đã ghi cho khách |
| Trách nhiệm | Tối đa bằng hoa hồng đã trả trong 6 tháng; không chịu trách nhiệm khi TikTok đổi chính sách / API | Như các nguồn bên thứ ba khác |

## 4. Điều kiện TikTok Shop Affiliate

- Theo các bài hướng dẫn (không phải trang chính thức của TikTok): tài khoản cá nhân **từ 1.000 người theo dõi**, chủ tài khoản từ 18 tuổi.
- Hoa hồng do nhà bán đặt, tính trên giá thanh toán thực tế; hoàn hàng hoặc huỷ đơn thì giảm hoặc về 0.
- Chưa tìm thấy quy định chính thức của TikTok về chia lại hoa hồng (cashback) cho người mua. Phải đọc chính sách creator trên TikTok Shop Academy / Creator Center.

## 5. Hiện trạng code: phần dùng lại được, phần phải viết mới

| Dùng lại được | Phải viết mới (Backend, theo `CLAUDE.md` không phải việc của Claude Code) |
|---|---|
| Kênh Telegram + Zalo, menu, hỗ trợ, điều khoản, thông báo | Nhận diện link TikTok Shop (`vt.tiktok.com`, `shop.tiktok.com/view/product/<id>`…) |
| Bảng tỷ lệ chia (V1.2), công thức hoàn, khoá tài chính | Client RioHub: tạo link gốc, ghép `event_id`, tra giá, kéo đơn, phân loại lỗi |
| Ví, đối soát chung, gate kiểm an toàn | Bảng đơn TikTok (hiện có `shopee_conversions`, `shopee_sync_runs`; 35 file có chữ `shopee`) |
| | Đồng bộ đơn định kỳ (không có HTTPS công khai nên dùng `GET /orders`, không dùng webhook) |
| | Ánh xạ trạng thái 1/2/3 sang luồng ghi nhận / huỷ / quyết toán hiện có |
| | Câu chữ khách (thời gian quyết toán TikTok khác Shopee) và điều khoản V3 ghi thêm TikTok Shop |

Ước lượng: một PLAN cỡ PLAN-082, chủ yếu là việc backend. Nên làm theo từng bước: link + giá trước, đơn + đối soát sau, ví sau cùng.

## 6. Rủi ro

1. **Điều khoản:** câu cấm "tự mua qua link của mình" và cấm bot ngoài phạm vi. Nếu RioHub coi bot hoàn tiền là vi phạm thì có thể giữ hoa hồng hoặc khoá tài khoản.
2. **Trung gian:** tiền đi TikTok → RioHub → chủ bot. Thêm một bên có thể chậm hoặc giữ tiền; tỷ lệ RioHub giữ lại chưa rõ.
3. **Số liệu tiền:** `actual_commission` đã trừ TNCN 10% + phần chia MCN, dễ trừ thuế hai lần nếu dùng chung công thức Shopee; `settled_at` rỗng với đơn quyết toán sau 60 ngày. Vẫn phải đối chiếu bằng đơn thật.
4. **Phụ thuộc tài khoản TikTok của chủ bot:** API chỉ chạy trên creator đã kết nối. Tài khoản TikTok bị hạn chế thì toàn bộ kênh dừng.
5. **Giới hạn TikTok theo creator:** lúc đông khách có thể gặp `tiktok_rate_limited`, cần thông báo khách thử lại.

## 7. Chủ bot cần quyết / làm

1. Có tài khoản TikTok đã bật TikTok Shop Affiliate chưa (≥ 1.000 người theo dõi)?
2. Nếu có: tự đăng ký RioHub, kết nối tài khoản TikTok, tạo khoá API, rồi tự thêm `RIOHUB_API_KEY` vào `.env`. Em không đăng ký thay, không cần xem khoá.
3. Gửi email `hotro@riohub.vn`, hỏi 4 câu:
   - dùng API để chạy bot hoàn tiền (chia lại một phần hoa hồng cho người mua) có được phép không;
   - phần `shared_with_partner` (chia MCN) thường là bao nhiêu phần trăm, phí rút tiền, thời gian về ví;
   - TNCN 10% đã khấu trừ có chứng từ cho chủ bot không;
   - pháp nhân, mã số thuế, chứng từ khi rút tiền.
4. Sau khi có trả lời: em viết PLAN và thử 1 lần trên tài khoản thật (cần chủ bot duyệt): tạo 1 link gốc, ghép `event_id`, tra 1 sản phẩm, kéo đơn. Không tạo khách, không ghi tiền.

## Nguồn

- RioHub TikTok Shop Developer: https://riohub.vn/tiktok-shop-developer
- RioHub trang chủ: https://riohub.vn/
- RioHub điều khoản: https://riohub.vn/terms
- Điều kiện TikTok Affiliate (bài bên thứ ba): https://www.misaeshop.vn/26891/affiliate-tiktok-la-gi/ , https://viettelstore.vn/tin-tuc/tiktok-affiliate-la-gi-cach-hoat-dong-kiem-tien-tu-a-z-2026
- Chính sách đánh giá TikTok Shop (bài bên thứ ba, chỉ áp dụng nhà bán ở Mỹ): https://ppc.land/tiktok-shop-bars-paid-reviews-and-sets-60-day-negative-review-rate-window/
