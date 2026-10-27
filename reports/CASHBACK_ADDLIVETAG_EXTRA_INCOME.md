# AddLiveTag: kiếm thêm ngoài link affiliate

| | |
|---|---|
| Ngày | 2026-10-27 |
| Yêu cầu | Chủ bot: xem AddLiveTag có gì để kiếm thêm; làm mục 1 (kênh deal) và mục 2 (ShopeeFood) |
| Trạng thái | Mục 2A đã làm (2026-10-27, `price_watch.py`, **mặc định tắt**). 2B và ShopeeFood chưa làm |

## 1. AddLiveTag có gì

- addlivetag.com: công cụ cho người làm affiliate (live, video AI, voucher, deal, bot nhóm Zalo…). **Không có chương trình giới thiệu / đại lý trả hoa hồng.**
- "Shopee Affiliate API DEV" trên addlivetag.com là tài liệu **Open API của Shopee**, cần App ID / Secret. Chủ bot không đăng ký được, nên hướng này bị chặn.
- **data.addlivetag.com** (máy chủ bot đang dùng cho `product-data.php`, khoá `ADDLIVETAG_API_KEY` bắt buộc từ 01/10/2026) có thêm:

| API | Đường dẫn | Dùng được cho |
|---|---|---|
| Product Offer | `/offers/product-offer.php?keyword=&sortType=&page=&limit≤50` | Sản phẩm có hoa hồng: giá, lượt bán, đánh giá, `commissionRate`. **Không có % giảm giá** |
| Shopee Offer | `/offers/shopee-offer.php` | Chiến dịch hoa hồng (tên, tỷ lệ, thời gian) |
| Shop Offer / Shop Products | `/offers/shop-offer.php`, `/offers/shop-products.php?shopId=` | Shop có hoa hồng, sản phẩm của một shop |
| Market Search | `/search/market.php?q=&sort=sales\|comm_rate\|growth…&commission_min=` | Top sản phẩm theo từ khoá; không tốn quota nguồn, cache 6 giờ |
| **Price & Commission History** | `/price-tracking/history.php?item_ids=(≤50)&type=both&days=` | **Lịch sử giá và hoa hồng từng sản phẩm**; 600 sản phẩm / phút / IP |
| ShopeeFood Store | `/shopeefood/store.php?restaurant_id=` | Tên quán, địa chỉ, giờ mở cửa, link đặt. Không có hoa hồng |
| ShopeeFood Orders | `/shopeefood/orders.php` (cookie ShopeeFood) | Đơn ShopeeFood: món, giá, `item_commission`, `checkout_cap` |
| Lazada Product Feed | `/lazada/` | Sàn thứ ba |

Nguồn: [data.addlivetag.com](https://data.addlivetag.com/), [/shopee/](https://data.addlivetag.com/shopee/), [/shopeefood/](https://data.addlivetag.com/shopeefood/), [aff-link](https://data.addlivetag.com/shopee/aff-link.html), [addlivetag.com](https://addlivetag.com/), [deal.html](https://addlivetag.com/deal.html).

✅ Trang ShopeeFood ghi API "không dùng cho mục đích thương mại", nhưng chủ bot xác nhận 2026-10-27: AddLiveTag cho dùng với bot hoàn tiền (nhiều người đang dùng công khai trên mạng xã hội).

## 2. Mục 1: kênh deal

Không có API "deal / % giảm giá" trực tiếp. Hai cách làm được:

**A. Báo giảm giá món khách từng xem (đề xuất làm trước)**
- Món khách đã tạo link trong 30 ngày mà chưa mua: mỗi ngày kiểm lịch sử giá (`history.php`, 50 món / lần).
- Giá hiện tại thấp hơn giá lúc tạo link từ 15% trở lên thì nhắn:
  > 📉 Món **[tên]** bạn xem hôm trước đang giảm còn **[giá mới]** (−X%) nè! Chốt qua link bot vẫn được hoàn nha 😎
- Hợp với khách nhất: đúng món họ đang muốn mua, đúng lúc rẻ. Không phải tin đại trà.
- Dùng chung mục 🛒 Nhắc ở /thongbao và ngân sách 1 tin / 7 ngày với nhắc link chưa dùng.

**B. "Top món bán chạy, hoàn cao" mỗi tuần**
- Lấy từ Market Search / Product Offer (sắp theo lượt bán, lọc hoa hồng cao).
- Danh sách tự động có thể lẫn món kém chất lượng, nên phải để admin xem trước và duyệt như nhắc sale.
- Khách tự bật nhận. Làm sau A.

## 3. Mục 2: ShopeeFood

| Việc | Tình trạng |
|---|---|
| Tạo link affiliate ShopeeFood có sub_id | AddLiveTag **không công bố cách tạo**. Chỉ ghi sub_id nằm trong `utm_content` (`sub_id1-…-sub_id5`). Bot nhóm Zalo của họ làm được, nên có cách |
| Đọc đơn ShopeeFood | Có API `orders.php` qua cookie ShopeeFood, hoặc báo cáo affiliate.shopee.vn có thể đã gồm ShopeeFood: chưa kiểm |
| Mức hoa hồng VN | Chưa biết. Indonesia: 12–40%, trần khoảng 13.000đ / đơn (tham khảo) |

**Cần chủ bot cung cấp trước khi thiết kế:**
1. Ảnh chụp mức hoa hồng ShopeeFood trong app Shopee Tiếp thị liên kết.
2. Một link affiliate ShopeeFood tạo từ trang affiliate (Custom Link). Che `affiliate_id` cũng được, chỉ cần thấy định dạng.
3. Trong affiliate.shopee.vn → Báo cáo chuyển đổi, đơn ShopeeFood có nằm chung với đơn Shopee không.

## 4. Đã làm: báo giảm giá (2A)

- `price_watch.py`: mỗi tối một lượt (19:00–21:30, luồng nền), kiểm tối đa 200 món, 50 món mỗi lần gọi `history.php` (`type=price`, 7 ngày).
- Báo khi giá mới ≤ 85% giá lúc tạo link và còn hàng. Mỗi khách 1 món giảm sâu nhất; mỗi link 1 lần.
- Dùng chung giới hạn 1 tin / 7 ngày với nhắc link chưa dùng; nhường tối có nhắc sale.
- Lỗi AddLiveTag: ghi trạng thái, báo admin, tối mai thử lại.
- Câu:
  > 📉 **Món [tên] bạn xem hôm trước đang giảm còn 200.000đ (−20%) nè!**
  > (⚡ Đang flash sale, nhanh tay kẻo hết nha.)
  > Chốt qua link bot vẫn được hoàn nha 😎
  > 👉 Bấm **🛒 Mua trên Shopee** bên dưới rồi đặt hàng.
- Bật ở ⚙️ Cài đặt → 📣 Nhắc mùa sale → 🟢 Bật báo giảm giá.
- Lần bật đầu tiên là lần đầu bot gọi `history.php` thật: định dạng phản hồi mới đọc theo tài liệu, chưa thử với dữ liệu thật.
