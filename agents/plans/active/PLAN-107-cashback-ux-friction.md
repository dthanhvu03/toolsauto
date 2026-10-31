# PLAN-107 — Cashback: giảm ma sát cho khách (thẻ link, báo mã, chờ đơn, tiến trình)

- Executor: Claude Code (UX / messages / voucher.py của PLAN-104)
- Người duyệt: chủ bot
- Trạng thái: ĐÃ LÀM (chủ bot duyệt 2026-10-31: «triển khai hết… theo em đề xuất») — chờ chủ bot restart
- Nguồn: bài phân tích «5 điểm bất tiện của End-User» chủ bot gửi 2026-10-31, đã đối chiếu dữ liệu thật bên dưới.

## 0. Đối chiếu bài phân tích với dữ liệu thật (DB đọc `mode=ro`, 2026-10-31)

| Ý trong bài | Thực tế | Kết luận |
|---|---|---|
| 1. Thẻ link dài | `_render_card` (messages.py) ra ~14 dòng: tiêu đề, món, số hoàn, dòng «thận trọng», câu 🔒, khối «Để được hoàn» 4 gạch, dòng món giá cao, chữ nhỏ ⓘ, lời bấm nút. Nút 🛡️ Lưu ý **đã có** (`u:tip`). | Đúng. Làm. |
| 2. Quên xoá món trong giỏ | Câu nhắc giỏ đã có trên thẻ, nhưng nằm ở gạch thứ 3 trong khối dài nên dễ trôi. | Đúng. Giữ đúng 1 câu này trên thẻ, đưa lên cao. |
| 3. «Shopee nhả đơn sau 15–30 phút» | 6 đơn gần nhất: bot thấy đơn sau **7,8–34,5 giờ** (trung bình 21,6 giờ), vì cookie đồng bộ khoảng 1 lần/ngày, AddLiveTag dự phòng chỉ chạy khi cookie hỏng. Tin «🛒 Có đơn mới» **đã có** (`order_new_notice`, CUSTOMER_NOTIFICATIONS_ENABLED=1). | Vấn đề đúng nhưng **con số sai**. Không được hứa «15–30 phút». Báo đúng: «thường khoảng 1 ngày». |
| 4. Chờ 15–30 ngày, rút tối thiểu 50k | Ví **chưa mở** (`wallet_enabled=0`), giữ tiền 15 ngày, rút tối thiểu **10.000đ** (không phải 50k). Tin trạng thái đơn đã có (mới → hoàn thành → vào ví). | Thanh tiến trình: làm. Thưởng đơn đầu: **chính sách tiền**, chủ bot quyết. |
| 5. Báo mã làm phiền | `voucher_audience=all` từ tối 30/10: 3 tin mã gửi 17 khách lúc **23:20–00:02 giờ VN** (SALEHOT100K, VCXBHH1030, VCXBH1030; hai mã sau cách nhau 18 giây). Không giới hạn là theo lựa chọn của chủ bot ngày 30/10. | Đúng và **đang xảy ra**. Ưu tiên số 1. Cần chủ bot đổi lại quyết định «không giới hạn». |

Mốc đo trước khi sửa (14 ngày đến 31/10): 91 link tạo cho 17 khách → 6 link có đơn (~6,6%). Đo lại sau 14 ngày.

## 1. Phạm vi theo thứ tự ưu tiên

### B1 — Báo mã không làm phiền (voucher.py, test_cashback_voucher.py)
1. **Giờ yên lặng 22:00–08:00 giờ VN:** mã đến trong giờ này xếp hàng, 08:00 gửi một tin gộp các mã **còn sống** (bỏ mã đã HẾT).
2. **Gộp mã đến gần nhau:** các mã đến trong 10 phút gửi chung một tin (một nút mỗi mã, tối đa 5 nút).
3. **Không gửi lại cùng mã trong 24 giờ** cho cùng khách (AddLiveTag đăng lại/cập nhật mã cũ).
4. **Trần mỗi khách: N tin mã/ngày** (đề xuất 2). Quá trần thì không gửi; mã vẫn hiện ở /magiam.
5. Tin đầu tiên khách nhận có dòng «Không muốn nhận? Bấm 🔕 Tắt báo mã» (nút đã có).
6. Admin vẫn nhận ngay, không bị giờ yên lặng/trần (để kiểm tra).
- Tuỳ chọn B1b (chờ chủ bot): mở kênh «ZT báo mã» công khai cho người săn mã 24/7. Chat 1-1 chỉ nhận theo trần ở trên.

### B2 — Thẻ link gọn (messages.py, zalo_render.py, test liên quan)
Thẻ mới, mục tiêu ≤ 6 dòng chữ:
```
✅ Đã tạo link hoàn tiền
🛍️ <tên món> · 250.000đ
💰 Hoàn dự kiến: khoảng 8.000đ
🛒 Món có sẵn trong giỏ: xoá đi rồi mở lại bằng nút bên dưới.
👉 Bấm 🛒 Mua trên Shopee rồi đặt hàng.
[🛒 Mua trên Shopee]
[🛡️ Lưu ý trước khi mua]   [🎟 Mã giảm giá]
```
- Món giá cao (capped): thêm 1 dòng «Món giá cao: thanh toán riêng, mỗi lần 1 cái». Dòng này giữ trên thẻ vì nó đổi số tiền.
- Chuyển sang popup 🛡️ Lưu ý: dòng «thận trọng», câu 🔒, các gạch «mua qua link / đúng món / voucher làm giảm», chữ nhỏ ⓘ «chưa phải tiền rút».
- Thêm vào popup: «Shopee báo đơn cho bot sau khoảng 1 ngày; bot tự nhắn khi thấy đơn».
- Không đổi số, không đổi link, không đổi cách tính. TikTok dùng cùng khung.
- Thẻ Telegram và thẻ Zalo phải cùng nội dung. Test canh văn bản (test_cashback_bot, plan060, zalo…) sửa theo.

### B3 — Trấn an sau khi đặt (messages.py)
- /donhang khi chưa có đơn, hoặc link mới tạo dưới 2 ngày chưa thấy đơn: «Đơn mới thường hiện sau khoảng 1 ngày. Đặt rồi thì bạn cứ yên tâm, bot sẽ tự nhắn.»
- **Không** gửi thêm tin chủ động sau khi tạo link: bot không biết khách có mua hay không, gửi là thành spam.

### B4 — Thanh tiến trình trong /donhang (messages.py: `order_detail_reply`, danh sách đơn)
`🛒 Đã mua ➔ 📦 Hoàn thành ➔ ⏳ Chờ sàn trả ➔ 💰 Vào ví`, tô đậm bước hiện tại, lấy từ trạng thái sẵn có (order_status / entry_status). Đơn huỷ hoặc không hợp lệ: hiện «❌ Không được hoàn», không hiện thanh. Ví chưa mở thì bước cuối ghi «Vào ví (khi mở rút)», không hứa ngày.

### B5 — Bớt bước dán link (messages.py: trang hướng dẫn)
Hướng dẫn «Chia sẻ → chọn Telegram/Zalo → chọn bot» thay vì sao chép rồi mở app dán. Chỉ đổi chữ ở trang hướng dẫn và tin chào.

### Ngoài phạm vi (cần chủ bot quyết chính sách trước, plan riêng)
- Thưởng đơn đầu / mốc thưởng: tốn tiền thật, chạm ví đang khoá. Bot không tự đặt mức.
- Hạ trần giữ tiền 15 ngày hay mức rút 10.000đ: chính sách ví.

## 2. Chủ bot cần quyết trước khi làm
1. B1: đồng ý bỏ «không giới hạn» ngày 30/10, chuyển sang giờ yên lặng 22–8 và trần **2 tin mã/ngày/khách**? (số trần, giờ tuỳ anh)
2. B2: duyệt thẻ mẫu ở trên, nhất là việc đưa câu ⓘ «chưa phải tiền có thể rút» vào popup. Nếu câu này phải luôn hiện trên thẻ (điều khoản) thì giữ, rút gọn còn 1 dòng.
3. B1b: có mở kênh công khai cho người săn mã không?

## 3. Kiểm tra
- `ruff check cashback_bot`; bộ test `tests/test_cashback_*.py` (chạy nền, timeout 900); test_b9 lỗi sẵn có, chỉ báo.
- Thêm test: giờ yên lặng xếp hàng rồi gửi 08:00 bỏ mã hết; gộp 10 phút; không lặp mã 24h; trần/ngày; admin không bị chặn; thẻ ≤ 6 dòng chữ; Telegram = Zalo; thanh tiến trình theo từng trạng thái.
- Không gọi Telegram/Shopee thật. Chủ bot tự restart: `systemctl restart cashback-bot cashback-zalo`.

## 4. Kết quả (2026-10-31)

Chủ bot chọn «theo em đề xuất»: giờ yên lặng 22h–8h, trần 2 tin/ngày; B1b (kênh công khai) chưa làm, chỉ là việc
chủ bot đổi kênh «ZT báo mã» sang công khai nếu muốn, không cần code.

**B1 — voucher.py, admin_engagement.py, poller.py**
- Chế độ «mọi khách»: `handle_post` gửi admin ngay, đánh dấu tin `sent = -1` (QUEUED). `voucher.tick` chạy mỗi vòng
  poller: ngoài 22h–8h, khi mã mới nhất đã chờ 2 phút (mã đầu chờ tối đa 10 phút) thì gửi mỗi khách một tin gộp
  ≤ 5 mã còn sống (bỏ mã hết, quá 24 giờ), bỏ mã khách đã nhận trong 24 giờ, khách đã nhận 2 tin trong ngày (giờ VN)
  thì bỏ. Tin mã đầu tiên của khách có dòng chỉ cách tắt. Không thêm bảng/cột, không ghi bot_state.
- Chế độ thử (chỉ admin) giữ như cũ: gửi ngay, có nhãn 🧪.
- /magiam ghi «tối đa 2 tin mã mỗi ngày và không nhắn từ 22h đến 8h»; bỏ chữ «nhắn liền».
- Màn admin 🎟 Báo mã: bỏ «gửi ngay mọi giờ, không giới hạn», thêm luật mới và «Đang chờ gửi khách: N mã».

**B2 — messages.py**: thẻ link 17 → 10 dòng (kể cả dòng trống). Trên thẻ: số hoàn (+ «có thể cao hơn» khi bot báo
mức thận trọng), ⚠️ mua thẳng trong app, 🛒 món trong giỏ, 🎟 voucher, 💎 món giá cao (nếu có), ⓘ chữ nhỏ, 👉 nút.
- Lệch so với plan, có lý do:
  - Popup 🛡️ Lưu ý là popup Telegram, tối đa 200 ký tự. Câu ⓘ «sau dự phòng phí và thuế… Chưa phải tiền có thể rút»
    là câu công bố của V1.2 (test canh) nên giữ trên thẻ, không đưa vào popup.
  - Dòng voucher giữ trên thẻ: quyết định 2026-10-27 (nhận số thấp mà không biết vì sao thì tưởng bị bớt).
  - Bỏ câu 🔒 «Link mở thẳng Shopee…»; popup có «Bot không thu tiền».
- Popup mới (193 ký tự): mua đúng món qua link bot · không bấm sang quảng cáo/livestream · mỗi lần lấy link mới ·
  bot không thu tiền · sàn báo đơn sau khoảng 1 ngày. Zalo dùng cùng chữ thẻ.

**B3**: /donhang trống: «Đơn mới thường hiện ở đây sau khoảng 1 ngày, vì Shopee báo đơn chậm…»; danh sách đơn
có thêm «Đơn mới thường hiện sau khoảng 1 ngày.» Không gửi tin chủ động.

**B4**: mỗi đơn trong danh sách /donhang có `✅ Đã mua › ⏳ Hoàn thành › ⚪ Sàn duyệt › ⚪ Vào ví` (đơn huỷ/không hợp
lệ không có). Bỏ chữ «⏳ chờ Shopee xác minh» lặp với thanh. Màn chi tiết đơn vốn đã có 6 bước tiến trình, giữ nguyên.

**B5**: /huongdan Telegram: «Chia sẻ → chọn Telegram rồi chọn bot này», còn cách sao chép. Hướng dẫn Zalo giữ nguyên:
chia sẻ sang Zalo gửi thẻ xem trước, bot có thể không đọc được (hướng dẫn hiện đã dặn bấm ✕).

**Kiểm tra**: xem mục 5.

## 5. Kiểm tra (2026-10-31)
- `ruff check cashback_bot`: sạch.
- Bộ `tests/test_cashback_*.py` ở worktree tách từ origin/main: 945 passed, 3 failed. Sau khi sửa: 2 test canh chữ cũ
  (tiktok danh sách đơn, wallet dòng voucher) đã cập nhật và chạy lại 180 passed (tiktok, wallet, pricing, plan107, bot).
  Còn `test_b9_doi_tai_khoan_cho_7_ngay_admin_xac_minh_thi_rut_ngay`: lỗi có sẵn từ trước, không liên quan.
- Test mới: `test_cashback_voucher.py` (giờ yên lặng / gộp / không lặp mã / trần / admin ngay / chờ tối đa 10 phút),
  `test_cashback_plan107.py` (thanh tiến trình, câu 1 ngày, thẻ TikTok + Zalo, hướng dẫn chia sẻ).
- Không gọi Telegram, Shopee, AddLiveTag thật. Không ghi DB production.
