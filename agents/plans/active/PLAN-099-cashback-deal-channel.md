# PLAN-099 — Kênh Telegram deal hời: đăng deal mỗi lượt, nút mở bot để khách nhận link riêng

- Executor: Claude Code. Ngày 28/10/2026 chủ bot duyệt («oke em, triển khai đi em») sau khi xem trang chủ AddLiveTag
  (hạ giá mạnh, deal khung giờ, nhóm Telegram báo giảm giá).
- Mục tiêu: khách nhớ tới bot khi định mua. Kênh đưa deal vào luồng Telegram khách lướt hằng ngày, khách chuyển tiếp
  cho bạn bè được.
- Trạng thái: đang làm.

## Bối cảnh (đã kiểm 28/10)
- Deal hời (deals.py) soạn 10:30 / 17:30, gửi riêng 12:08 / 20:08 cho khách đã chọn danh mục hoặc bot đoán gu.
  Chỉ soạn danh mục có người nhận. Chuẩn «hời thật» theo lịch sử giá 30 ngày, không tin % giảm shop tự ghi.
- Bot nhận update `message` và `callback_query` (getUpdates `allowed_updates`). Bot chưa biết username của mình.
- Hàng đợi `admin_notifications`: bot Telegram lấy tin `audience='admin'` (mọi chat_id) và tin khách ID dương; bot
  Zalo lấy tin khách ID âm. ID kênh Telegram là số âm (-100…).

## Nguyên tắc
- Link trong kênh dùng chung cho mọi người nên **không** gắn mã khách. Mỗi món là nút URL
  `https://t.me/<bot>?start=dl_<shop>_<item>`: khách bấm thì mở bot, bot tạo link riêng như nút 🛒 trong tin deal
  (cùng thẻ, cùng cách tính, đơn tính đúng người, cùng giới hạn tạo link, cùng cổng điều khoản).
- Không tạo sẵn link affiliate hàng loạt. Không đổi schema DB, không thêm biến `.env`. Trạng thái ở `bot_state`.
- Kênh tắt mặc định. Chỉ đăng khi admin đã gắn kênh và bấm bật. Không đăng gì cho khách riêng ngoài luồng đang có.

## Phạm vi
1. **Gắn kênh** (admin): thêm bot làm quản trị kênh (quyền đăng bài), rồi chuyển tiếp một bài bất kỳ của kênh vào
   chat với bot. Bot hỏi «Dùng kênh … làm kênh deal?» → ✅ thì lưu `deals_channel` = {id, title, username}.
   Chỉ admin; người khác chuyển tiếp thì xử lý như tin thường.
2. **Username bot**: lúc khởi động gọi `getMe`, lưu `bot_username`. Thiếu thì không đăng kênh, màn admin báo rõ.
3. **Soạn**: kênh bật thì lượt soạn chạy cả khi chưa ai chọn danh mục, và soạn thêm mọi danh mục.
4. **Đăng**: lúc gửi lượt (12:08 / 20:08), xếp một bài vào hàng đợi cho kênh (`audience='admin'`, `event_type
   DEALS_CHANNEL`, khoá `deals_channel:<ngày>[:trua]`). Tối đa 8 món tốt nhất (sắp theo % rẻ hơn thường ngày), tối đa
   2 món / danh mục, bỏ món admin đã bỏ. Nút cuối «🤖 Mở bot hoàn tiền». Lượt bị bỏ, lỡ giờ, nhường nhắc sale thì
   kênh cũng không đăng.
5. **Deep link**: `/start dl_<shop>_<item>` → như bấm 🛒 trong tin deal.
6. **Màn admin 🔥 Deal hời**: dòng trạng thái kênh, hướng dẫn gắn kênh, nút 🟢 Bật / ⚪ Tắt đăng kênh,
   📤 Đăng bài giới thiệu (để ghim đầu kênh), 🗑 Bỏ kênh. Ghi 📊 Lịch sử.

## Ngoài phạm vi
- Deal khung giờ (flash sale): chưa biết AddLiveTag có API; xem tài liệu sau nếu chủ bot muốn.
- Kênh Zalo. Thống kê lượt bấm từ kênh (link tạo từ kênh vẫn ghi như link thường).

## Kiểm
- Test: gắn kênh qua tin chuyển tiếp (admin / không phải admin), soạn khi chỉ có kênh, bài kênh (số món, nút URL,
  bỏ món admin bỏ, không đăng khi tắt / thiếu username), deep link tạo link, màn admin bật / tắt / giới thiệu / bỏ.
- Toàn bộ `tests/test_cashback_*.py` + `ruff check cashback_bot`.
- Không gọi Telegram thật để thử. Chủ bot restart rồi tự gắn kênh và bấm 📤 Đăng bài giới thiệu.

## Kết quả (28/10)
- Code:
  - `deals.py`: phần «Kênh Telegram», gồm `channel_post`, `intro_post`, `post_channel`, `post_intro`, `start_deal`
    và `forwarded_channel`. `build` và `tick` soạn mọi danh mục khi kênh bật. `send` xếp bài kênh.
  - `admin_deals.py`: `offer`, nút `c:dl:ch:*`, phần kênh trên màn 🔥 Deal hời, 📊 Lịch sử.
  - `admin_policy.py`: `deals_channel_offer`.
  - `service.py`: nhận tin admin chuyển tiếp từ kênh và `/start dl_<shop>_<item>`.
  - `telegram_api.py`: `get_username` (getMe). `poller.py`: lưu `bot_username` lúc khởi động.
- Test mới `tests/test_cashback_deal_channel.py`, 6 test:
  - gắn kênh: admin, khách, Bot API cũ, nhóm;
  - màn admin: giới thiệu, bật, bỏ, lịch sử;
  - bài 8 món, mỗi danh mục 2, bỏ món admin bỏ, không lặp món;
  - soạn đủ danh mục và đăng lúc gửi;
  - không đăng khi tắt hoặc thiếu username;
  - deep link ra thẻ link của người bấm.
- Xem trước bằng bản nháp deal thật tối 28/10 (chỉ đọc DB): 7 món, nút `t.me/<bot>?start=dl_…`.
- Lưu ý:
  - Khi bật kênh, lượt soạn tìm cả 10 danh mục (50 lệnh Market Search và khoảng 1.500 món lịch sử giá mỗi lượt), nên
    soạn lâu hơn vài phút.
  - Admin chuyển tiếp bài từ kênh nào vào bot thì luôn nhận câu hỏi gắn kênh, không tạo link từ tin đó.
