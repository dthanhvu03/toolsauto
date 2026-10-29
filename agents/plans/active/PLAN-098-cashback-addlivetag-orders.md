# PLAN-098 — Đơn Shopee qua API AddLiveTag: đối soát chéo, nguồn dự phòng, chuẩn bị ShopeeFood

- Executor: Claude Code. Ngày 28/10/2026, chủ bot chọn "mục 2" (API AddLiveTag không chính thống) và chọn cả ba việc.
- Trạng thái: chủ bot duyệt 28/10. Bước A, B xong (chờ restart); C đã khảo sát, chờ chủ bot quyết thử nghiệm.

## Bối cảnh (đã kiểm 28/10)
- API: `GET https://addlivetag.com/api/v1/conversions.php` với header `X-API-Key`, tối đa 60 lệnh/phút.
  - Tham số: `type=items|orders|clicks`, `source=shopee|food`, `from`/`to`, `page`/`page_size`.
  - AddLiveTag lấy dữ liệu từ tài khoản affiliate mà chủ bot đã gắn cookie trên AddLiveTag.
- Khoá: bot dùng `ADDLIVETAG_API_KEY` đang có (đúng dạng 48 hex). Không thêm biến `.env`.
- Gọi thử 2 lệnh, chỉ đọc (items và orders, 20–28/10). Được 4 dòng, cả 4 khớp đơn bot: sub_id, order_sn và checkout_id đều trùng, hoa hồng lệch nhiều nhất 1đ.
- AddLiveTag chậm hơn bot: 2 đơn ngày 26–27/10 bot đã có, AddLiveTag chưa có.
- `commission_status` "Chờ trả hoa hồng" chính là `checkout_status` "Waiting for payment" mà bot đã có. AddLiveTag **không** cho thêm bằng chứng duyệt hay đã trả.
- Dòng items có các trường: checkout_id, order_sn, item_id, shop_id, item_name, qty, price, order_value, commission, mcn_fee, status, status_code, commission_status, purchase_time, click_time, complete_time, utm, sub_id1, affiliate.
  - Thiếu `order_id`: bot đang lấy order_id làm conversion_id.
  - Thiếu `is_fraud`, `attribution_type`, `validation_month`.

## Nguyên tắc (không đổi)
- Nguồn cookie Shopee vẫn là nguồn chính. AddLiveTag **không bao giờ ghi** vào `shopee_conversions` hay `cashback_entries`, và không đổi trạng thái hay số tiền của đơn đã có.
  - Lý do: thiếu order_id thì không tạo được đúng khoá đơn. Ghi vào sẽ có nguy cơ một đơn thành hai dòng và hoàn tiền hai lần.
  - Thiếu `is_fraud` thì không đánh giá được gian lận.
- Không gán APPROVED hay SETTLED. Không gỡ khoá tài chính.
- Không log khoá API. Dữ liệu AddLiveTag chỉ giữ trong RAM của lượt chạy, cộng kết quả tóm tắt trong `bot_state`.
- Không sửa schema DB (không migration). Trạng thái lưu trong `bot_state`.

## Bước A — Đối soát chéo hằng ngày (chỉ đọc)
- **Module mới `cashback_bot/addlivetag_orders.py`:**
  - Client: `fetch_items(from, to)` đi hết các trang `page_size=50`, timeout 20 giây, nghỉ ≥ 1 giây giữa hai trang.
  - Hàm so sánh thuần, theo `order_sn`, chỉ xét dòng có sub_id là link bot.
- **Thời điểm chạy:** mỗi ngày một lần lúc 09:00 giờ VN, khung 30 ngày. Gắn vào vòng `_periodic` ở `poller.py`. Khoá ngày ghi ở `bot_state alt_crosscheck:<ngày>` để không chạy hai lần.
- **Các loại lệch:**
  1. AddLiveTag có đơn qua link bot nhưng bot chưa có. Chỉ báo khi giờ mua đã quá 6 giờ.
  2. Lệch huỷ: một bên huỷ, bên kia không.
  3. Lệch hoa hồng: chênh từ 100đ và từ 2% trở lên.
  4. Bot có đơn mua đã quá 3 ngày mà AddLiveTag chưa có. Chỉ ghi số lượng, không báo, vì AddLiveTag vốn chậm.
- **Báo admin:** chỉ gửi khi có lệch loại 1, 2 hoặc 3. Tin ghi tối đa 5 đơn, khoá `alt_crosscheck:<ngày>`.
  - Màn /admin → 🔗 Shopee Affiliate thêm một dòng: «🔁 Đối soát AddLiveTag 28/10: khớp 6/6».
  - Lỗi API (401, 429, mạng) chỉ ghi vào dòng trạng thái, không báo mỗi ngày.

## Bước B — Nguồn dự phòng khi cookie Shopee lỗi
- **Khi nào chạy:** có sự cố đồng bộ đang mở (`shopee_sync_incidents.resolved_at IS NULL`), hoặc lần đồng bộ thành công gần nhất đã quá 6 giờ.
  - Trong thời gian đó, cứ 60 phút đọc AddLiveTag 3 ngày gần nhất.
  - Cookie chạy lại thì dừng.
- **Đơn qua link bot mà `order_sn` chưa có trong DB:**
  - Báo admin «🛟 Đơn mới (nguồn dự phòng AddLiveTag)», kèm món, hoa hồng và khách.
  - Báo khách tin «đã ghi nhận giao dịch» như đơn bình thường, có thêm câu «số tiền cập nhật khi đồng bộ Shopee chạy lại».
  - Ghi `bot_state alt_order:<order_sn>` với giờ đã báo.
- **Khi cookie chạy lại**, đồng bộ chính ghi đơn như cũ, kèm hai việc:
  - Không gửi lại tin «đã ghi nhận giao dịch» nếu `alt_order:<order_sn>` đã báo khách.
  - Ví và sổ hoàn tiền chỉ có khoản này sau khi đồng bộ chính ghi đơn.
- **Đơn đã có trong DB:** không làm gì. Đổi trạng thái chờ cookie.
- **File sửa:** `addlivetag_orders.py` (mới), `poller.py` (gắn lịch), `order_notify.py` (chặn tin trùng theo order_sn).

## Bước C — ShopeeFood (chỉ khảo sát, chưa code)
- Kiểm tài liệu và 1 lệnh đọc `source=food` khung 30 ngày, để xem đơn Food có sub_id hay utm không.
- Tìm cách tạo link affiliate ShopeeFood có sub_id: Shopee custom link với shopeefood.vn, hoặc `short_link` của AddLiveTag.
- Ra một ghi chú khảo sát và PLAN riêng để chủ bot duyệt: link, giá, tỉ lệ hoàn, khách có hiểu đúng không.
- Hiện bot vẫn từ chối link Food (`food_link`). Bước này không đổi điều đó.

## Không làm
- Không gọi API chính thức của Shopee. Không lưu cookie hay token của AddLiveTag. Không đổi `.env`.
- Không chạy thử trên DB production. Thử bằng bản sao trong scratchpad.

## Thứ tự và proof
1. A: test với dữ liệu giả (khớp, thiếu, lệch huỷ, lệch tiền, AddLiveTag chậm), chạy trên bản sao DB và API thật đúng 1 lượt.
2. B: test cookie lỗi (đơn mới → báo đúng 1 lần), cookie chạy lại (không báo lại), đơn đã có (không làm gì).
3. C: ghi chú khảo sát.
- Mỗi bước: toàn bộ test qua, ruff sạch, ghi proof vào file này, cập nhật current-status. Chủ bot restart.

## Proof bước A (28/10)
- `cashback_bot/addlivetag_orders.py` mới; gắn vào `poller._loop` (`alt_crosscheck`), `admin_notify.notify_alt_crosscheck`, dòng 🔁 trên màn 🔗 Shopee Affiliate (`admin_policy`, `admin_ui.shopee_text`).
- `tests/test_cashback_addlivetag_orders.py` 7 test: khớp nhiều món trừ MCN, lệch tiền, lệch huỷ, bot thiếu, mới mua chưa báo, ngoài link bot bỏ qua, AddLiveTag chậm, lệch dưới ngưỡng, 9:00 mỗi ngày 1 lần, không lệch không nhắn, lỗi API chỉ ghi trạng thái, chia trang + map lỗi, không ghi sổ đơn.
- Toàn bộ 905 test qua, ruff sạch.
- Chạy thật 1 lượt (bản sao DB, API thật, 09:22Z): so 4 đơn, khớp 4/4, không lệch. Đã xoá bản sao.

## Proof bước B (28/10)
- `addlivetag_orders.py`: `cookie_down`, `run_fallback`, `maybe_fallback` (luồng nền, 60 phút/lượt, 3 ngày). Gắn `poller._loop` (`alt_fallback`, NotifyConfig theo cờ CUSTOMER_NOTIFICATIONS_*), `admin_notify.notify_alt_fallback_orders`.
- `order_notify`: `ALT_NOTIFIED_KEY`; hook thấy `alt_order:<order_sn>` đã "queued" → tin «có đơn mới» ghi `suppressed` lý do `alt_notified` (nhãn ở `admin_customer_notify.REASON_LABELS`).
- Tin khách dự phòng: `order_new_notice` + «Số tiền sẽ cập nhật khi bot đồng bộ lại với Shopee», nút 📦 Đơn hàng của tôi / 📩 Hỗ trợ; qua `customer_block_reason` + mốc kích hoạt như tin đơn thường.
- Test thêm 4: khi nào coi cookie lỗi; báo đơn mới 1 lần, bỏ đơn đã có / huỷ / ngoài link, không ghi sổ, cookie chạy lại không báo lần hai; cờ tắt thì đồng bộ chính vẫn báo; lịch 60 phút, lỗi API không nhắn admin. Toàn bộ 909 test qua, ruff sạch.
- Chạy thật trên bản sao DB (API thật): cookie đang ổn → dự phòng không chạy; gọi thẳng run_fallback ra 0 đơn thiếu. Đã xoá bản sao.

## Khảo sát bước C — ShopeeFood (28/10)
- 1 lệnh đọc `source=food` khung 30 ngày: 0 đơn Food (`total: 0`). Chưa có mẫu để biết đơn Food có sub_id / utm hay không.
- Tài liệu `generateShortLink` (Open API chính thức, cần AppID/Secret) chỉ có ví dụ link shopee.vn, không nói gì về Food.
- Blog bên thứ ba (Sapo, Ecomobi; chưa có tài liệu chính thức Shopee VN): link Food lấy trong app (Tôi → Shopee Tiếp Thị Liên Kết → ShopeeFood), mỗi lần chép ra một link rút gọn khác. Không thấy cách gắn sub_id. Ở Indonesia, hoa hồng Food chỉ tính cho click từ link Food Affiliate.
- Bot tạo link bằng `an_redir` (affiliate_id + 1 sub_id). Chưa biết `an_redir` có nhận đích `shopeefood.vn` / `spf.shopee.vn` không.
- AddLiveTag product-data không có giá / hoa hồng món Food, nên bot không báo được số hoàn trước khi mua.
- Kết luận: chưa thể làm hoàn tiền Food theo từng khách. Cần một lần thử thật để biết hai điều: (1) link `an_redir` tới quán Food có sub_id có mở đúng quán không; (2) đơn đặt qua link đó có ra trong báo cáo Food kèm sub_id không.
  - Việc thử cần chủ bot tự đặt 1 đơn nhỏ, rồi hôm sau đọc lại `source=food`.
  - Chủ bot chưa duyệt thì không làm.

## Thử ShopeeFood (chủ bot duyệt 28/10)
- Link quán chủ bot gửi: `spf.shopee.vn/906KKy82bs`. Ghép tay `s.shopee.vn/an_redir?origin_link=<link>&affiliate_id=<id>&sub_id=FOODTEST`, không đổi code bot.
- ~17:15 28/10: link mở đúng món trong app (Chè dừa dầm thốt nốt 28.490đ, An Vy, Bàu Cát; món thuộc «ShopeeFood Trùm Deal»). Chủ bot đã đặt 1 đơn qua link.
- 28/10 sau khi đặt, 1 lệnh đọc `type=clicks&source=food` 2 ngày: chưa có FOODTEST. Lượt bấm mới nhất AddLiveTag có là 27/10, nghĩa là báo cáo trễ.
- **Next:** 29–30/10 đọc lại `source=food` (items + clicks), tìm FOODTEST. Kết luận theo 3 trường hợp: có mã / có đơn không mã / không có đơn.
- 29/10 13:40 chủ bot gửi ảnh app Shopee (Tiếp thị liên kết → ShopeeFood → Hiệu quả tiếp thị, ngày 28/10): **1 lượt click, 0 đơn, 0đ**. Trang web affiliate.shopee.vn không có mục Food; số liệu Food chỉ xem được trong app.
  - Lượt click Food có ghi vào tài khoản affiliate của bot, nên link `an_redir` tới quán Food được Shopee nhận. App không hiện sub_id, nên chưa biết lượt click này có mang FOODTEST không.
  - Đơn đặt ~17:15 28/10 chưa thành đơn chuyển đổi. Có thể do báo cáo trễ, do Food chỉ tính đơn khi đã giao xong, hoặc do Shopee không tính đơn tự mua qua link của chính mình. Chưa đủ dữ liệu để kết luận.
  - Vẫn chờ: chủ bot xem tab «Đơn chuyển đổi» trong app, và bot đọc `source=food` của AddLiveTag 30/10 (cần chủ bot nói «kiểm FOODTEST»).
