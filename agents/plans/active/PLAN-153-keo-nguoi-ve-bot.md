# PLAN-153 — Kéo người xem / người đọc về 2 bot (cashback + shop AI)

- Status: Code + test xong (04/11) — chờ anh restart bot + nạp 8810
- Executor: Claude Code (anh 04/11: «anh muốn kéo traffic về 2 bot của anh» → chọn bot cashback + @aipass_shop_bot, nguồn: live Xe Tết + bài đăng)

## Hiện trạng
- @aipass_shop_bot đã nhận link `t.me/<bot>?start=buy_<id>` (vào thẳng món). Các mã start khác thì về trang chủ, không ghi lại là từ đâu tới.
- Bot cashback (Telegram + Zalo) không đọc mã start, nên không biết khách đến từ đâu.
- Live Xe Tết chưa có chỗ nào nhắc tới bot.
- Người xem live đang dùng điện thoại nên không quét được QR trên màn hình của chính mình. Lời mời cần là **tên bot dễ gõ** và **lơ xe đọc lên**, kèm link ở bio / bình luận ghim.

## Phạm vi

### 1. Đếm nguồn (làm trước, để biết cách nào có hiệu quả)
- Cả hai bot ghi `src` khi khách /start lần đầu: `?start=live`, `?start=video`, `?start=bio`, `?start=buy_<id>`.
  - Thêm một cột hoặc một khoá `bot_state`, không đổi luồng hiện có.
- Đặt link riêng cho từng nguồn, rồi báo số khách mới theo nguồn mỗi ngày trong tin báo admin đang có.

### 2. Live Xe Tết
- **Dải nhỏ ở góc màn hình**, cùng kiểu thẻ kính tối mới. Hai câu xoay vòng:
  - «💸 Mua Shopee hoàn tiền · Tele: <tên bot cashback>»
  - «🤖 Tài khoản AI giá rẻ · Tele: aipass_shop_bot»
  - Chữ và tên bot sửa được trên /control, không cần sửa code.
- **Lơ xe nhắc khéo** mỗi ~8–10 phút, gắn vào lúc trả khách hoặc lúc xe chạy, không chen ngang trận đấu:
  - «Ai hay mua Shopee thì ghé bot hoàn tiền của nhà xe, tên trên góc màn hình…»
  - Câu chữ theo luật: không «nha», không «!», tiếng Anh viết theo cách đọc.
- **Bình luận từ khoá** «hoàn tiền», «shopee», «AI», «chat gờ pê tê»: lơ xe trả lời riêng người đó và thẻ bật tên bot. Mỗi người tối đa 1 lần mỗi buổi.
- Không thêm phần thưởng trong game cho người vào bot (giai đoạn này chưa có cách khớp người xem TikTok với tài khoản Telegram).

### 3. Bài đăng / video
- Thêm dòng cuối cố định vào chú thích: tên bot + link có `?start=video`.
- Phần đăng bài (Buffer / video) đang do phiên khác làm. Em chỉ viết sẵn mẫu dòng cuối và link; phiên đăng bài gắn vào.

## Không làm
- Không đổi giá, kho, hay luồng hoàn tiền của hai bot.
- Không spam bình luận / nhắn tin người lạ.
- Không gửi QR trên live (người xem đang dùng chính điện thoại đó).

## Cần anh trả lời
1. Tên (username) bot cashback Telegram. Có muốn đưa thêm Zalo OA không?
2. Lơ xe nhắc bao lâu một lần: 8 phút hay 15 phút?
3. Bot nào ưu tiên trên live: cashback (khán giả đại trà) hay shop AI?

## Kiểm tra (khi làm)
- Test hai bot: /start kèm mã nguồn ghi đúng 1 lần cho khách mới; khách cũ không bị ghi đè; mã lạ không lỗi.
- 8811: chụp dải bot + lơ xe nhắc + trả lời từ khoá, 0 lỗi JS. Không nạp 8810 khi anh chưa bảo.
- Restart bot: anh tự chạy `systemctl restart cashback-bot cashback-zalo` / `store-bot store-api`.

## Anh đã chốt (04/11)
1. Bot hoàn tiền: @zt_shopee_bot (Telegram). 2. Lơ xe nhắc 8 phút. 3. Ưu tiên bot hoàn tiền.

## Thực tế khi làm
- Live đã có sẵn từ 03/11: biển ven đường, dòng gợi ý, lơ xe đọc quảng cáo 8 phút (cả hai bot). Chỉ thêm phần thiếu:
  bot 1 đọc 2/3 lượt; chip thường trực «💸 Tele @zt_shopee_bot» cạnh dòng đếm ngày; từ khoá bình luận (mục «Từ khoá» trên /control,
  quảng cáo lưu trước đó tự lấy từ khoá mặc định theo @tên bot).
- Người xem live gõ tên bot chứ không bấm link → khách từ live thường không có mã nguồn; dùng `?start=bio` cho link bio TikTok.
- Bài đăng/video: mẫu dòng cuối cho phiên đăng bài — `💸 Hoàn tiền Shopee: t.me/zt_shopee_bot?start=video`
  · `🤖 Tài khoản AI: t.me/aipass_shop_bot?start=video`.

## Proof (04/11)
- Bot: 1205 test cashback + store pass. 1 test lỗi sẵn có, không do thay đổi này: `test_b9_doi_tai_khoan_cho_7_ngay...` — màn ví admin
  lấy giờ thật thay vì giờ của test. Thêm test nguồn: chỉ khách mới, không ghi đè, mã lạ bỏ qua; `buy_<id>` → «kenh».
  Admin thấy nguồn ở tin «Người dùng mới» + bảng Phễu (cashback), «Thống kê» (shop). Ruff sạch.
- Xe Tết: pytest 217, ruff sạch, tsc sạch. Từ khoá: chỉ đúng bot, mỗi người 1 lần/bot, cả phòng 20 giây/lần. Hết lượt thì câu đó không
  chuyển cho AI: trên 8811, AI từng đáp sai «Không hoàn tiền đâu». 8811: chip dưới tên game + lơ xe «Bảo Ngọc ơi, …», 0 lỗi JS.

## Đổi hướng (04/11, sau khi nạp): live không nhắc sàn / app
- Anh: «live TikTok mà nói sàn khác thì cấm live». Research: TikTok ghi kéo người mua ngoài TikTok bị giảm hiển thị, cố lách
  hạn chế có thể bị khoá; blog người bán VN liệt kê Shopee, Lazada, Telegram, Zalo, Facebook, link bio, inbox, QR, nói lái.
- Anh chọn «giữ câu trung tính»: lơ xe + màn hình chỉ mời ghé trang cá nhân kênh, không tên sàn / app / bot. Tên bot để ở bio.
- `moderation.off_platform` chặn tên sàn / app / lời kéo người đi ở bong bóng chat + câu AI; mục quảng cáo có những chữ đó bị bỏ,
  bỏ hết thì dùng câu trung tính mặc định. AI có thêm luật không nói tên sàn / app. pytest 219.
