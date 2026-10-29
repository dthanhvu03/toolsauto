# PLAN-103 — Theo dõi giá: khách bấm 🔔 trên thẻ link, có giảm là bot báo

- Executor: Claude Code. Ngày 29/10/2026, chủ bot hỏi tính năng «theo dõi sản phẩm này, biến động giảm giá thì báo».
- Chủ bot chốt: «cứ có giảm là thông báo». Cách kiểm giá theo đề xuất của em. Khách muốn thì điền giờ kiểm, không
  điền thì bot kiểm theo lượt chung.
- Trạng thái: xong code, chờ chủ bot restart.

## Khác báo giảm giá tự động có sẵn (`price_watch.py`)
- Chế độ có sẵn: bot tự chọn món khách từng tạo link, mỗi tối kiểm một lần, giảm từ 15% mới báo, tối đa 1 tin / 7 ngày.
- Tính năng mới: khách tự chọn món, có giảm là báo, mỗi món một tin. Món đang được khách theo dõi thì chế độ có sẵn
  bỏ qua để không nhắn trùng.

## Thiết kế
- **Bật:** thẻ link Shopee có nút **🔔 Báo khi giảm giá** (`u:pw:a:<sub_id>`).
  - Bấm thì bot theo dõi món đó 30 ngày. Mốc là giá trên thẻ.
  - Mỗi khách tối đa 10 món. Bấm lại món đang theo dõi thì mở màn món đó.
  - Thẻ link không bị sửa đè (khách vẫn bấm mua được).
- **Giờ kiểm:**
  - **Mặc định (không điền):** lượt chung mỗi giờ tròn 7:00–21:00 (cùng nhịp quét deal).
    - Đọc giá mới nhất ở lịch sử giá AddLiveTag (`history.php`, 50 món / lần).
    - Thấy rẻ hơn thì đọc giá thật (product-data) để chắc chắn và tính lại số hoàn.
    - Một món báo cách nhau ít nhất 6 giờ (giá flash sale nhảy lên xuống trong ngày).
  - **Giờ riêng:** khách chọn ⏰ Đặt giờ kiểm rồi gõ giờ, ví dụ `12h 20h30` hoặc `12:00`.
    - Tối đa 4 giờ, trong 6:00–23:00. Gõ «mặc định» để về lượt chung.
    - Tới giờ, bot đọc giá thật của món đó. Bot tắt quá 30 phút thì bỏ lượt đó, không kiểm bù.
  - Gõ giờ phải có `h` hoặc `:` để Zalo không hiểu nhầm thành số chọn mục.
- **Có giảm là báo:**
  - Giá thật thấp hơn giá lần trước bot thấy thì nhắn khách. Giá lần trước là giá trên thẻ, rồi cập nhật theo mỗi lần
    kiểm: giá lên thì ghi giá mới, nên lần giảm sau vẫn báo.
  - Tin: tên món, giá cũ → giá mới (−%), số hoàn dự kiến theo giá mới, hạn theo dõi.
  - Nút: 🛒 Mua trên Shopee (link cũ, cùng sub_id, đơn tính đúng khách) và 🔕 Ngừng theo dõi.
- **Quản lý:** lệnh `/theodoi` (Zalo `theodoi`) liệt kê món đang theo dõi. Mỗi món một màn: giá mốc, giá gần nhất, giờ
  kiểm, hạn; nút ⏰ Đặt giờ kiểm và 🔕 Ngừng theo dõi.
- **Tin đi qua hàng đợi chung:**
  - category `price_watch`, event `PRICE_WATCH`;
  - khách chặn bot thì không gửi;
  - không dính mục «nhắc» ở `/thongbao`, vì khách tự bật từng món và tắt bằng 🔕.
- **Admin:**
  - 📣 Nhắc mùa sale có dòng «🔔 Theo dõi giá»: số món đang theo dõi, số tin 7 ngày, lượt kiểm gần nhất;
  - nút bật / tắt (`bot_state.price_watch_list_enabled`, mặc định bật);
  - tắt thì thẻ link không hiện 🔔 và bot không kiểm.

## Dữ liệu
- Bảng mới `price_watches` (thêm vào `SCHEMA`, tự tạo lúc khởi động; không đổi bảng cũ):
  - khách, link, item / shop, tên món;
  - giá mốc, giá gần nhất, giờ kiểm riêng;
  - thời điểm tạo, hạn, ngừng, lần kiểm gần nhất, lượt giờ riêng gần nhất, lần báo gần nhất, số lần báo.
- Trạng thái chờ gõ giờ: `bot_state.price_watch_wait:<khách>` (10 phút).
- Backup DB trước khi restart (bảng mới, không ghi bảng cũ).

## Không đổi
- Không thêm `.env`. Không đổi cách tạo link, cách tính hoàn, đối soát, ví.
- Link TikTok, ShopeeFood chưa có 🔔.

## Kiểm
- Test (không gọi mạng):
  - bật từ thẻ, giới hạn 10 món, bấm lại;
  - lượt chung: giảm thì báo, không giảm / product-data không xác nhận thì không báo, giá lên rồi giảm lại thì báo,
    cách 6 giờ, ngoài 7–21 không kiểm, một lượt / giờ;
  - giờ riêng: đọc giờ (`12h`, `20h30`, `7:15`, quá 4 giờ, ngoài 6–23, «mặc định»), tới giờ thì kiểm, quá 30 phút bỏ;
  - ngừng, hết hạn, chặn bot;
  - `/theodoi`, Zalo (gõ giờ, chọn số);
  - chế độ có sẵn bỏ món đang theo dõi; admin bật / tắt.
- Toàn bộ `tests/test_cashback_*.py` + `ruff check cashback_bot`.

## Kết quả (29/10)
- Code:
  - `watchlist.py` (mới):
    - bật, ngừng, tối đa 10 món, 30 ngày;
    - lượt chung `run_default` (history.php rồi product-data), giờ riêng `run_slots`, `tick` (luồng nền);
    - đọc giờ `parse_times`; màn khách; tin báo.
  - `db.py`: bảng `price_watches` trong `SCHEMA`.
  - `service.py`:
    - 🔔 trên thẻ link Shopee (cả lúc Telegram gửi lại);
    - nút `u:pw:*`, thẻ không bị sửa đè;
    - `/theodoi`; chờ gõ giờ, dán link hay bấm nút khác thì bỏ chờ.
  - `poller.py`: `watchlist.tick` mỗi vòng.
  - `price_watch.py`: bỏ món khách đang theo dõi.
  - `admin_engagement.py`: dòng 🔔 Theo dõi giá, nút bật / tắt.
  - `messages.py`, `zalo_bot.py`, `zalo_render.py`: lệnh `theodoi`.
- Test `tests/test_cashback_watchlist.py` (11):
  - thẻ, bật, bấm lại, link của khách khác;
  - lượt chung giảm / không giảm / giá lên rồi giảm / cách 6 giờ / product-data không xác nhận;
  - tick 7–21, một lượt mỗi giờ, lỗi 429;
  - đọc giờ; giờ riêng tới giờ, trễ quá 30 phút thì bỏ;
  - dán link khi đang chờ;
  - ngừng, hết hạn, tối đa 10 món;
  - chế độ có sẵn bỏ món đang theo dõi; admin tắt;
  - Zalo (chọn số, gõ `12h 20h`, `theodoi`).
- Sửa test cũ theo nút mới: `test_cashback_plan060.py` (3), `test_cashback_bot.py` (lệnh bot).
- Toàn bộ: 930 qua, 1 hỏng có sẵn (`test_b9…`). Ruff sạch.
