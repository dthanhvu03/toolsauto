# Nhắc mùa sale — nghiên cứu lịch, giờ gửi, câu chữ

| | |
|---|---|
| Ngày | 2026-10-27 |
| Yêu cầu | Chủ bot: nghiên cứu câu từ, ngữ nghĩa; tham khảo lịch sale cố định (ngày đôi, giữa tháng, cuối tháng) để tự thiết lập; nghiên cứu thời gian gửi phù hợp |
| Code | `sale_calendar.py` (lịch, hàm thuần) · `engagement.py` (chạy định kỳ) · `admin_engagement.py` (màn duyệt) |
| Trạng thái | Đã làm. **Mặc định tắt.** Mỗi lượt phải được chủ bot duyệt mới gửi |

## 1. Lịch sale của Shopee VN

Shopee không công bố bảng phân cấp chính thức. "Siêu sale" là tên Shopee dùng cho các đợt lớn cuối năm; "mini" là cách các trang săn sale gọi đợt nhỏ (15, 25). Bot chia 4 cấp:

| Cấp | Dịp | Nhắc | Ghi chú nguồn |
|---|---|---|---|
| **Đỉnh** | 11.11, 12.12 | 20:30 tối hôm trước + 11:30 trong ngày | 11.11 giảm sâu nhất năm; 12.12 là siêu sale sinh nhật Shopee |
| **Siêu sale** | 9.9, 10.10, Black Friday (thứ Sáu cuối tháng 11; 2026 là 27/11) | 20:30 tối hôm trước | 9.9 mở màn mùa sale cuối năm |
| Ngày đôi thường | 1.1 … 8.8 | 20:30 tối hôm trước | Mỗi tháng một lần, mở lúc 0h |
| Mini | 15 (giữa tháng), 25 (cuối tháng / "lương về") | 20:30 tối hôm trước | Một nguồn ghi cuối tháng là 25 hoặc 27 |

**Không nhắc:**
- Flash sale hằng ngày (khung 0h · 9h · 12h · 15h · 18h · 21h): ngày nào cũng có, nhắc thì thành tin rác.
- Dịp lễ có ngày thay đổi hoặc không chắc Shopee có sale riêng: Tết, 8/3, 30/4–1/5, 1/6, 20/10, Giáng sinh. Có thể thêm sau, khi có lịch chính thức.

Nguồn: [Shopee blog](https://shopee.vn/blog/khi-nao-shopee-sale/), [FPT Shop](https://fptshop.com.vn/tin-tuc/danh-gia/khi-nao-shopee-sale-191538), [GHN: khung giờ](https://ghn.vn/blogs/tip-ban-hang/cap-nhat-khung-gio-san-sale-shopee), [GHN: các ngày sale](https://ghn.vn/blogs/tip-ban-hang/cac-ngay-sale-shopee), [magiamgiashopee.vn](https://magiamgiashopee.vn/lich-sale-shopee/), [khuyenmaidacbiet.com: tháng 11/2026](https://khuyenmaidacbiet.com/landing-page/lich-sale-shopee-thang-11-2026), [bloggiamgia.vn](https://bloggiamgia.vn/lich-san-sale), [VnEconomy: 9.9](https://vneconomy.vn/shopee-mo-man-mua-sale-voi-su-kien-9-9.htm), [Viettablet](https://www.viettablet.com/cac-ngay-sale-lon-2026-cua-shopee).
Đây đều là trang tổng hợp, không phải lịch chính thức. Ngày có thể đổi theo năm, nên màn admin cho **bỏ qua** từng lượt.

## 2. Giờ gửi

Bằng chứng:
- Người Việt mua online nhiều nhất buổi trưa và buổi tối (báo cáo Shopee 2019, theo [Brands Vietnam](https://www.brandsvietnam.com/18832-Nguoi-Viet-hay-mua-online-vao-giua-tuan-tim-kiem-nhieu-nhat-son-moi-giay-ba-lo)). Đây là dữ liệu cũ nhất quán duy nhất tìm được.
- Các bài về thông báo đẩy (blog nhà cung cấp, không phải nghiên cứu): giờ cao điểm 12–13h và 18–20h; tránh nhắn khuya; tối đa 2–3 tin khuyến mãi mỗi tuần ([Pushwoosh](https://www.pushwoosh.com/blog/push-notifications-e-commerce), [FOMO](https://fomo.com/blog/push-notification-engagement)).
- Không tìm thấy nghiên cứu nào đo "gửi trước giờ sale bao lâu là tốt nhất".

Lựa chọn và lý do:

| Lượt | Giờ (VN) | Lý do |
|---|---|---|
| Tối hôm trước mọi dịp | **20:30** | Trong khung tối, khách đang lướt điện thoại; còn hơn 3 giờ trước 0h để mở link qua bot và gom giỏ. Không nhắn sau 22h |
| Trưa ngày đôi lớn (11.11, 12.12) | **11:30** | Trước khung 12h; người không thức tới 0h vẫn kịp |
| Không gửi | 0h | Đúng lúc săn nhưng là nửa đêm, dễ bị coi là làm phiền |

Giới hạn tần suất: hai dịp cách nhau dưới 5 ngày thì chỉ giữ dịp cấp cao hơn. Như vậy mỗi khách nhận tối đa khoảng 2 tin mỗi tuần, 3–4 tin mỗi tháng. Với Zalo (3.000 tin / tháng / bot, ≤ 50 khách) là khoảng 200 tin, an toàn.

Lịch cuối năm 2026:

| Ngày gửi | Dịp | Cấp |
|---|---|---|
| 10/11 20:30 | 11.11 (tối hôm trước) | Đỉnh |
| 11/11 11:30 | 11.11 (trưa) | Đỉnh |
| 26/11 20:30 | Black Friday 27/11 | Siêu sale |
| 11/12 20:30 | 12.12 (tối hôm trước) | Đỉnh |
| 12/12 11:30 | 12.12 (trưa) | Đỉnh |
| 24/12 20:30 | 25/12 | Mini |
| 31/12 20:30 | 1.1 | Ngày đôi |

Bị bỏ vì sát dịp cấp cao hơn (dưới 5 ngày): 15/11, 25/11, 15/12.

## 3. Câu chữ

Nguyên tắc:
1. **Mốc thời gian lên đầu, in đậm**: "Mai 11.11 rồi", "0h đêm nay 11.11 mở sale". Khách hiểu ngay đây là tin gì.
2. **Một việc cần làm**: gửi link qua bot *trước khi chốt đơn*.
3. **Nhắc chuyện giỏ hàng.** Ngày sale khách hay gom giỏ từ trước rồi mua thẳng từ giỏ, nên không qua link và mất hoàn. Đây là lý do mất hoàn lớn nhất của ngày sale.
4. **Không hứa số tiền, không phóng đại** ("hoàn tận…", 🤑): quanh chuyện tiền, giọng càng "trend" càng giống lừa đảo.
5. **Giọng bạn bè** (*nha, nhé, giỏ hàng sẵn chưa, lương về rồi*), không dùng từ lóng ngắn hạn.
6. **Ngắn**: 2–3 dòng, dưới 260 ký tự, đọc được trên màn hình khoá.
7. **Cách tắt ở cuối**: "gõ /thongbao để tắt". Trên Zalo tự đổi thành "gõ thongbao".
8. Mỗi loại có **2 câu**, luân phiên theo ngày để các dịp liền nhau không trùng câu. Siêu sale / đỉnh có câu riêng nhấn mạnh "giỏ hàng full chưa", vì khách gom giỏ nhiều ngày trước.

Câu đang dùng: `messages.SALE_REMINDERS`.

## 4. Cách chạy

- Admin bật ở /admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale. Màn này có lịch 45 ngày tới, trạng thái từng lượt, số khách sẽ nhận.
- Trước giờ gửi 48 giờ: bot báo admin "📣 Nhắc sale 11.11 chờ anh duyệt".
- Admin bấm 👁 để xem đúng tin khách sẽ nhận, rồi bấm **✅ Duyệt gửi** hoặc **⏭ Bỏ qua**. Đã duyệt thì còn **↩️ Huỷ duyệt** được tới trước giờ gửi.
- Tới giờ, nếu đã duyệt: đưa vào hàng đợi chung, gửi qua Telegram và Zalo như tin báo đơn.
  - Người nhận là khách đã tạo link, chưa chặn bot và chưa tắt "🛒 Nhắc mùa sale" ở /thongbao.
- Bot sập hay quá 60 phút sau giờ gửi thì **bỏ lượt**, không gửi muộn (tin "mai 11.11" gửi lúc 2h sáng là sai).
- Mọi thao tác bật / tắt / duyệt / bỏ qua ghi vào 📊 Lịch sử cấu hình.

## 5. Còn mở

- Zalo: tin chủ động tới chủ bot ngày 27/10 **gửi được** (1 giờ sau lần chủ bot nhắn cuối). Chưa kiểm sau 48 giờ im lặng; khách Zalo lâu không nhắn có thể không nhận được.
- Lượt đầu tiên là 10/11 20:30 (11.11), không có lượt nào sớm hơn để thử. Tin nhắc dùng chung đường gửi với tin báo đơn, mà đường này đã chạy thật trên Telegram.
- Đo hiệu quả: số khách tạo link trong 24 giờ sau tin nhắc. Chưa làm.
