# PLAN-100 — Deal hời tự động: quét mỗi giờ, có món mới hời thật là gửi (bỏ lượt cố định 12:08 / 20:08)

- Executor: Claude Code. Ngày 28/10/2026, chủ bot yêu cầu: «bot tự động gửi deal hời cho khách, tự update tự gửi, cứ
  có là gửi không quan trọng giờ, 1 deal cũng gửi mà 2–3 deal cũng gửi».
- Chủ bot chọn (AskUserQuestion 28/10):
  - quét mỗi 60 phút;
  - mỗi khách tối đa 4 tin / ngày;
  - chỉ gửi 8:00–22:00;
  - bỏ hai lượt cố định.
- Trạng thái: đang làm.

## Bối cảnh
- AddLiveTag không có API «vừa hạ giá». Trang Open API chỉ có offer, short link, báo cáo đơn và click. Mục «Vừa hạ giá
  mạnh» trên web của họ dùng % giảm do shop tự ghi.
- Bot dùng lại nguồn đang có: Market Search (món bán chạy) và lịch sử giá 30 ngày. Chuẩn «hời thật» không đổi.

## Thiết kế
- **Quét:** mỗi giờ tròn từ 7:00 tới 21:00 giờ VN (15 lượt / ngày), luồng nền, một lượt mỗi giờ.
  - Lượt giờ chẵn dùng 5 từ khoá đầu của danh mục, giờ lẻ dùng phần còn lại.
  - Mỗi lượt quét đủ 10 danh mục.
  - Trạng thái lượt ghi ở `bot_state.deals_scan`.
- **Kho deal** (`bot_state.deals_pool`): món đạt chuẩn, mỗi món có thời điểm thấy lần đầu (`first`) và lần gần nhất
  còn hời (`seen`).
  - Lượt quét thấy lại món thì cập nhật giá và `seen`.
  - Món 24 giờ không thấy lại thì bỏ khỏi kho.
- **Gửi:** sau mỗi lượt quét, nếu đang trong 8:00–22:00 và không có tin nhắc sale trong 3 giờ tới.
  - Chỉ dùng món thấy lại trong 2 giờ 30 phút gần nhất (hai nửa từ khoá chạy xen kẽ).
  - Món khách chưa nhận trong 3 ngày qua là món mới với khách đó.
  - Có từ 1 món là gửi. Mỗi tin tối đa 3 món, chia đều theo danh mục khách chọn.
  - Mỗi khách tối đa 4 tin / ngày, hai tin cách nhau ít nhất 2 giờ. Món của khách đang bị giới hạn để lượt sau.
  - Khách bot đoán gu giữ luật cũ: tối đa 2 tin / tuần, món rẻ ≥ 12%, nhận 3 tin không tạo link thì dừng.
- **Không còn duyệt từng lượt** (chủ bot muốn tự gửi). Admin vẫn có:
  - tắt / bật deal hời, tắt / bật đoán gu;
  - **❌ Bỏ món** trong kho: không gửi, không hiện ở 🔥 Deal hôm nay (`bot_state.deals_removed`).
- **🔥 Deal hôm nay** (PLAN-099): hiện món trong kho thấy lại trong 12 giờ qua (ban đêm vẫn còn deal của lượt 21:00).
- **Bỏ:** lượt trưa / tối, bản nháp, bỏ lượt, tin báo admin «đã soạn» (`notify_deals_ready`).
  - Nút cũ trong tin admin cũ trả «không còn hiệu lực».
  - 📊 Lịch sử cũ vẫn đọc được.

## Chi phí
- 15 lượt / ngày thay vì 2. Mỗi lượt khoảng 50 lệnh Market Search, khoảng 1.500 món lịch sử giá (giãn nhịp 500 món /
  phút, khoảng 3 phút) và tối đa 50 lệnh product-data.
- Chưa biết AddLiveTag có giới hạn theo ngày không. Lỗi 429 thì lượt đó ghi «lỗi», giờ sau quét lại.

## Không đổi
- Không đổi schema, không thêm `.env`.
- Hàng đợi chung (`event_type` DEALS, category `deal`), nên chặn bot, tắt thông báo và Zalo giữ như cũ.
- Bấm món vẫn tạo link như khách tự dán.

## Kiểm
- Test: lịch quét (giờ, một lượt / giờ, xen kẽ từ khoá), kho (thêm, cập nhật, bỏ sau 24 giờ), gửi (1 món cũng gửi,
  không lặp món, tối đa 4 tin / ngày, cách 2 giờ, ngoài 8–22 không gửi, nhường nhắc sale, bỏ món admin bỏ), đoán gu,
  màn admin, 🔥 Deal hôm nay.
- Toàn bộ `tests/test_cashback_*.py` + `ruff check cashback_bot`.

## Kết quả (28/10)
- Code:
  - `deals.py`: bỏ Slot trưa / tối; thêm kho deal (`merge`, `current_deals`, bỏ món), `send_round` (giới hạn 4 tin /
    ngày, cách 2 giờ, 8–22, nhường nhắc sale), `scan` và `tick` (mỗi giờ 7–21, xen kẽ từ khoá).
    🔥 Deal hôm nay đọc kho (`feed_for`, 12 giờ).
  - `admin_deals.py`: màn mới (lượt quét gần nhất, số tin hôm nay, món đang hời, ❌ Bỏ / ↩️ Lấy lại).
    Nút cũ trả «không còn hiệu lực», 📊 Lịch sử cũ vẫn đọc được.
  - `admin_notify.py`: bỏ `notify_deals_ready`.
  - `messages.py`: đổi chữ «12:08 / 20:08» trong màn chọn danh mục và nút mời.
- Test (`test_cashback_deals.py`, `test_cashback_deal_feed.py`):
  - quét mỗi giờ: tắt thì không quét, một lượt / giờ, từ khoá giờ chẵn / lẻ, ngoài 7–21 không quét;
  - 1 món cũng gửi, tối đa 4 tin / ngày, cách 2 giờ, món để dành lượt sau, không lặp món, sang ngày đếm lại, sau 22:00
    không gửi;
  - kho: cập nhật, bỏ sau 24 giờ, độ mới, admin bỏ món;
  - nhường nhắc sale, đoán gu, màn admin, 🔥 Deal hôm nay.
- Toàn bộ `tests/test_cashback_*.py`: 911 passed. `ruff check cashback_bot` sạch.
- Xem trước tin mới bằng deal thật tối 28/10 (chỉ đọc DB): 3 món, chia theo danh mục của khách.
- Sau restart, lượt quét đầu chạy ở giờ tròn kế tiếp trong 7:00–21:00. Khách đã nhận deal 20:08 tối 28/10 thì tính 1
  tin của ngày đó và phải cách 2 giờ, nên tin tự động đầu tiên là từ 8:00 sáng 29/10.
