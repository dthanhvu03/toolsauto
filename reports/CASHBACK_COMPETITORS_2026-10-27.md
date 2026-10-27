# So sánh các bot / app hoàn tiền Shopee ở VN

| | |
|---|---|
| Ngày | 2026-10-27 |
| Cách làm | Đọc trang công khai của từng bên. **Chưa dùng thử bot nào**, nên mọi con số là lời quảng cáo của chính họ, chưa kiểm chứng |

## 1. Các bên

| Bên | Kênh | Hoàn cho khách (họ tự ghi) | Rút tiền | Ghi chú |
|---|---|---|---|---|
| [DealHup](https://dealhup.io.vn/) | Zalo | "đến **80%** hoa hồng" | "bất cứ lúc nào, không giới hạn", sau 7–15 ngày đổi trả | Không ghi tính trên hoa hồng trước hay sau thuế; không ghi ai vận hành |
| [HoanTien365](https://hoantien365.io.vn/) | Telegram / Zalo | "lên đến **80%**"; bảng theo ngành: thời trang 15%, điện tử 12%… (nhiều khả năng là tỷ lệ hoa hồng, không phải phần khách) | "không giới hạn số tiền rút", về ngân hàng | Không ghi đơn vị vận hành |
| [hoantiensp.com](https://hoantiensp.com/bot-guide) | Telegram @hoantiensp_bot + Zalo | Ví dụ "15.000đ (7.5%)" trên giá | Không ghi | Có giới thiệu, nhiệm vụ, bảng xếp hạng |
| [Mai mèo](https://www.maimeo.io.vn/) | Web / Zalo | "lên đến **50%**" | Không ghi | — |
| [Bot DealHoanTien](https://zalo.me/3845599028583046324) | Zalo | Không ghi | — | — |
| [ZaloBot Hoàn Tiền (AddLiveTag)](https://zalobot.addlivetag.com/) | Bot trong **nhóm Zalo** | Chủ nhóm tự đặt; nhóm mẫu tên "Hoàn Tiền **85%**" | Không có | Bán cho chủ nhóm, dùng thử 30 ngày; **dùng API Zalo không chính thức**, có rủi ro bị khoá |
| [ShopBack](https://www.goshopback.vn/) | App | 2–10% giá đơn tuỳ ngành (theo trang tổng hợp) | Từ 20.000đ, về ngân hàng | Thương hiệu lớn, ghi nhận sau 48 giờ |

Nguồn khác: [taobothoantien.com](https://taobothoantien.com/) (dịch vụ tạo bot hoàn tiền Zalo), [mualoi.com](https://mualoi.com/blog/so-sanh-cashback-shopee-lazada-tiktok-shop-tiki), [Tinhte](https://tinhte.vn/thread/top-3-web-hoan-tien-mua-sam-tot-nhat-hien-nay.4178499/), [Vinymart](https://vinymart.com/app-hoan-tien-shopee).
Cảnh báo lừa đảo cùng thời điểm: [Báo Pháp Luật: AI Livestream](https://baophapluat.vn/triet-pha-duong-day-lua-dao-nup-bong-ai-livestream.html), [Gia đình & Xã hội: xem phim nhận hoa hồng](https://giadinh.suckhoedoisong.vn/xem-phim-ngan-nhan-hoa-hong-nguy-co-mat-thong-tin-ca-nhan-bi-cai-dat-phan-mem-doc-hai-172261026145836836.htm).

## 2. Bot mình đang ở đâu

Chính sách V1.2: trừ dự phòng phí 0,98% và dự phòng thuế 10% (khớp mức Shopee đã khấu trừ), rồi chia 70% cho khách.

| Phần khách | Trên hoa hồng gốc | Biên của bot |
|---|---|---|
| **70% quỹ (đang chạy)** | **62,3%** | 26,7% |
| 75% quỹ | 66,8% | 22,3% |
| 80% quỹ | 71,2% | 17,8% |
| 85% quỹ | 75,7% | 13,4% |

- Nếu "80%" của đối thủ tính trên hoa hồng **sau thuế** (tức tiền Shopee thực trả), thì họ đưa khách khoảng 72% hoa hồng gốc, **cao hơn mình khoảng 10 điểm**.
- Nếu tính trên hoa hồng gốc mà không trừ thuế, họ chỉ còn khoảng 10% biên sau khi Shopee khấu trừ 10%. Khó trụ, hoặc họ không thực trả đủ như quảng cáo.

**Bất lợi về cách trình bày:** các bên ghi "đến 80%", "hoàn 15%". Mình ghi số tiền thật, đã tính thận trọng: "khoảng 7.399đ". Khách so hai thẻ cạnh nhau sẽ tưởng mình thấp hơn nhiều, dù thực nhận có thể bằng nhau.

## 3. Mình hơn ở đâu, kém ở đâu

| | Bot mình | Đối thủ (theo quảng cáo) |
|---|---|---|
| Số hoàn báo trước | Số tiền cụ thể, tính thận trọng (Shopee Comm tối đa 2,5%) | "Lên đến X%", không rõ cơ sở |
| Báo đơn | Có: đơn mới, thay đổi, lý do khi hoàn thấp hơn | Phần lớn không nói |
| Kênh | Zalo **API chính thức** + Telegram | Có bên dùng API Zalo không chính thức (rủi ro khoá) |
| Minh bạch | Điều khoản có phiên bản, hỗ trợ có mã yêu cầu | Phần lớn không ghi ai vận hành |
| **Rút tiền** | **Chưa mở** | "Rút bất cứ lúc nào" |
| Tỷ lệ | 62% hoa hồng gốc | Quảng cáo 50–85% |

**Điểm yếu lớn nhất không phải tỷ lệ mà là chưa rút được tiền.** Khách so "rút bất cứ lúc nào" với "chưa mở ví" thì gần như chắc chắn chọn bên kia, dù tỷ lệ bằng nhau.

## 4. Đề xuất

1. **Không đua tỷ lệ lúc này.** Nâng lên 80% quỹ thì biên còn 17,8%; mức hoà vốn tăng từ khoảng 400 lên khoảng 600 đơn / tháng. Đổi tỷ lệ là chính sách, chủ bot quyết.
2. **Thử thực tế các bot đối thủ** (chủ bot làm, vì cần tài khoản Zalo / Telegram): dán **cùng một link Shopee** vào DealHup, @hoantiensp_bot và bot mình, chụp số hoàn mỗi bên báo. Đây là dữ liệu thật duy nhất có được, vì không ai công bố cách tính.
3. **Cạnh tranh bằng lòng tin**, trong lúc thị trường đầy cảnh báo lừa đảo:
   - giữ số báo trước thận trọng và giải thích khi hoàn thấp hơn;
   - khi mở ví, hiện công khai "Bot đã hoàn X đồng cho Y người".
4. **Ưu tiên mở ví.** Đây là khoảng cách lớn nhất với đối thủ.
5. Cân nhắc **hiện thêm tỷ lệ** cạnh số tiền trên thẻ link (ví dụ "≈ 1,6% giá"). Hiện % theo giá thì nhỏ hơn % theo hoa hồng mà đối thủ hay dùng, nên cần chủ bot quyết cách ghi.
