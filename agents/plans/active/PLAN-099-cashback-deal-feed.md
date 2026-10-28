# PLAN-099 — 🔥 Deal hôm nay ngay trong bot (thay cho kênh Telegram riêng)

- Executor: Claude Code. Ngày 28/10/2026.
- Lịch sử:
  - Chủ bot duyệt làm kênh Telegram đăng deal, bản đó lên main ở `21fd968`.
  - Sau đó chủ bot đổi ý: «dùng chung 1 con bot hiện tại luôn không cần tạo kênh», «làm kênh deal ngay trong kênh
    bot chứ em gắn kênh nào nữa».
  - Bản này gỡ phần kênh (revert `21fd968`) và làm mục deal xem ngay trong bot.
- Mục tiêu: khách nhớ tới bot khi định mua. Mở bot là có deal để lướt, không phải chờ 12:08 / 20:08.
- Trạng thái: xong code, chờ restart.

## Phạm vi
1. **Lối vào:** nút trang chủ «🔥 Deal hôm nay» (`u:dh`), đặt cạnh «🛍️ Danh mục deal» (thay nút «🛍️ Deal hời của
   tôi»). Thêm lệnh `/deal` vào menu lệnh, và từ `deal` cho Zalo. Deal hời tắt thì không có nút; gõ `/deal` thì về trang
   chủ.
2. **Nội dung:** lấy lượt gần nhất đã tới giờ gửi (trạng thái sent / sale / missed) của hôm nay hoặc hôm qua.
   - Bản nháp chưa tới giờ gửi thì không hiện, vì admin còn đang duyệt.
   - Lượt admin bỏ thì không hiện. Món admin bỏ cũng không hiện.
3. **Tin:** tối đa 8 món, mỗi danh mục 2, sắp theo % rẻ hơn thường ngày.
   - Danh mục khách đã chọn xếp trước.
   - Mỗi món một nút 🛒 (`u:dl:<shop>:<item>`): bot tạo link như khi khách tự dán link. Thẻ link là tin mới, danh sách
     vẫn giữ.
   - Có nút lọc theo danh mục (`u:dh:<danh mục>`, sửa tin tại chỗ), «🔥 Tất cả», «⚙️ Chọn danh mục nhận tin», trang chủ.
4. **Soạn:** khi deal hời bật, mỗi lượt soạn đủ 10 danh mục, kể cả khi chưa ai chọn danh mục. Gửi riêng cho khách vẫn
   như cũ.

## Không đổi
- Không đổi schema, không thêm `.env`, không gửi thêm tin cho khách.
- Chuẩn «hời thật» và lịch gửi riêng giữ như cũ.

## Chi phí
- Lượt soạn tìm 10 danh mục thay vì chỉ danh mục có người chọn (tối 28/10 là 5): mỗi lượt 50 lệnh Market Search và
  khoảng 1.500 món lịch sử giá. Lượt soạn lâu hơn vài phút, vẫn xong trước giờ gửi.

## Kiểm (28/10)
- Test mới `tests/test_cashback_deal_feed.py`, 3 test:
  - chỉ hiện lượt đã tới giờ, không hiện lượt bị bỏ, lượt mới nhất trước;
  - tin 8 món: mỗi danh mục 2, bỏ món admin bỏ, không lặp món, danh mục khách trước, lọc danh mục, hôm qua, rỗng;
  - trang chủ, `/deal`, lọc sửa tại chỗ, bấm món ra thẻ link mới.
- Sửa test cũ theo hành vi mới: soạn đủ danh mục, nút trang chủ, menu lệnh có `deal`.
- Xem trước bằng bản deal thật tối 28/10 (chỉ đọc DB): 7 món, danh mục của chủ bot lên trước, 5 nút danh mục.
