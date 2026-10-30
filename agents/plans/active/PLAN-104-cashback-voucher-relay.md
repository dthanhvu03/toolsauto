# PLAN-104 — Báo mã giảm giá Shopee trong bot hoàn tiền (AddLiveTag Theo dõi Voucher qua kênh trung gian)

- Executor: Claude Code. Ngày 30/10/2026, chủ bot gửi trang AddLiveTag «Theo dõi Voucher» và chọn hướng 2: báo mã
  ngay trong bot. Chủ bot chốt cách A: «oke vậy em triển khai». Lý do: khách muốn «all in one».
- Trạng thái: xong code, chờ chủ bot restart và làm các bước «Chủ bot làm sau khi restart».

## Khảo sát (30/10, qua Chrome của chủ bot, chủ bot đăng nhập)
- Trang `addlivetag.com/tool/voucher-monitor/` gọi API nội bộ `api/portal/voucher-*.php`. API xác thực bằng phiên đăng nhập
  Google trên web, không có bản dùng API key.
- AddLiveTag tự kiểm mã mỗi phút. Có mã thì gửi tin vào kênh Telegram / Zalo bằng **bot của người dùng** (dán token).
  Hết mã thì sửa lại chính tin đó, có thể gửi thêm tin «hết mã».
- Mỗi tài khoản: 1 kênh, 3 link mã (thêm link: 1.000 điểm / link). Kho mã dùng chung lúc khảo sát có 1 mã, đã hết.
- Mẫu tin mặc định: `{icon} <b>{gio}: {ten} {ma} đã dùng {dadung}% - Giảm {giam}% - Tối đa {toida} - Đơn tối thiểu {toithieu}</b>`,
  tin hết mã: `🔴 <b>HẾT MÃ — {ten} ({ma})</b> …`. Chủ bot sửa được mẫu.
- Đã xoá file ghi mạng, mã nguồn trang và profile tạm sau khảo sát.

## Vì sao không dùng token bot hoàn tiền
- AddLiveTag «Lấy danh sách chat» phải gọi `getUpdates`: tranh tin khách với bot (lỗi 409, mất tin).
- Ai giữ token thì điều khiển được bot hoàn tiền.
- Telegram không gửi cho bot tin do chính bot đăng: bot hoàn tiền không đọc được tin AddLiveTag nếu dùng chung token.

## Thiết kế
- **Đường đi:** AddLiveTag → bot chuyển tin (chủ bot tạo mới qua @BotFather) → kênh Telegram riêng tư → bot hoàn tiền
  (quản trị kênh) đọc `channel_post` → soạn lại → gửi khách đã bật (Telegram + Zalo) qua hàng đợi chung.
- **Gắn kênh:** bot chỉ đọc tin của **một** kênh đã gắn (`bot_state.voucher_channel`).
  - Kênh lạ đăng tin: bot chỉ ghi tên + id kênh gần nhất (`voucher_seen_channel`), không làm gì khác.
  - /admin → 📣 Nhắc mùa sale → 🎟 Báo mã: nút «✅ Dùng kênh …» để gắn, «Gỡ kênh» để gỡ. Ghi 📊 Lịch sử.
- **Đọc tin:** nhận mẫu mặc định của AddLiveTag (không cần sửa mẫu) và mẫu có nhãn dòng (`Mã:`, `Giảm:`…).
  - Link lưu mã: lấy link Shopee trong tin (chữ, link gắn chữ, nút). Không có link thì tin khách chỉ có mã.
  - Tin không đọc được: bỏ qua, admin thấy số tin bỏ qua.
  - Chủ bot tự đăng tin đúng mẫu vào kênh cũng được (báo mã tay).
- **Gửi khách:**
  - Khách tự bật: `/magiam` (Zalo `magiam`), nút 🎟 Mã giảm giá ở trang chủ (khi đã gắn kênh), nút trong tin báo mã.
    Mặc định tắt.
  - Tin mới có mã: gửi ngay trong 8:00–22:00; ngoài giờ chỉ lưu, khách mở `/magiam` vẫn thấy.
  - Một mã gửi lại cách ít nhất 12 giờ. Mỗi khách tối đa 3 tin báo mã / ngày. Khách chặn bot thì không gửi.
  - Tin: tên, mã, giảm / tối đa / đơn từ, % đã dùng; nút 🎟 Lưu mã (nếu có link), 🔕 Tắt báo mã.
    Nhắc: lưu mã xong dán link món vào bot để mua có hoàn; dùng mã thì số hoàn tính trên giá sau giảm.
  - AddLiveTag sửa tin (% đã dùng) hoặc báo hết mã: bot cập nhật, `/magiam` không hiện mã đã hết.
- **`/magiam`:** mã còn (bot thấy trong 24 giờ, chưa hết), trạng thái bật / tắt, nút bật / tắt.
- **Admin:** 🎟 Báo mã: kênh đã gắn, số khách bật, mã 7 ngày, tin 7 ngày, tin bỏ qua; bật / tắt cả tính năng.

## Dữ liệu
- Bảng mới `voucher_posts` (trong `SCHEMA`, tự tạo lúc khởi động): kênh, message_id, mã, tên, giảm, tối đa, đơn từ, % đã dùng,
  link, trạng thái (live / out), thời điểm, số tin đã xếp hàng.
- `bot_state`: `voucher_enabled` (vắng = bật), `voucher_channel`, `voucher_seen_channel`, `voucher_skipped`,
  `voucher_on:<khách>`.

## Không đổi
- Không thêm `.env`, không gọi AddLiveTag hay Shopee. Không đổi cách tạo link, tính hoàn, ví.
- `getUpdates` thêm `channel_post`, `edited_channel_post`; update khác như cũ.

## Chủ bot làm sau khi restart
1. @BotFather → `/newbot` → lấy token bot chuyển tin.
2. Tạo kênh Telegram riêng tư. Thêm bot chuyển tin và bot hoàn tiền làm quản trị.
3. AddLiveTag → Kênh nhận tin: nền tảng Telegram, dán token **bot chuyển tin**, chọn kênh, lưu. Thêm link mã, chọn kênh.
4. Đăng một tin bất kỳ vào kênh → /admin → 📣 Nhắc mùa sale → 🎟 Báo mã → ✅ Dùng kênh.
5. Bấm «Gửi thử» trên AddLiveTag, kiểm tra bot đọc đúng (admin thấy mã mới).

## Kiểm
- Test (không gọi mạng): đọc mẫu mặc định / mẫu nhãn / tin hết mã / tin lạ; link từ chữ, link gắn chữ, nút; kênh lạ chỉ ghi
  tên; gắn / gỡ kênh; gửi khách đã bật, không gửi khách tắt / chặn, ngoài giờ, trùng mã 12 giờ, tối đa 3 / ngày; sửa tin
  cập nhật % / hết mã; `/magiam`, bật / tắt, Zalo `magiam`; trang chủ có nút khi đã gắn kênh; admin.
- Toàn bộ `tests/test_cashback_*.py` + `ruff check cashback_bot`.

## Kết quả (30/10)
- Code:
  - `voucher.py` (mới): đọc tin (mẫu mặc định, mẫu nhãn, tin hết mã), lấy link Shopee, gắn kênh, gửi khách, `/magiam`,
    số liệu admin.
  - `db.py`: bảng `voucher_posts`. `telegram_api.py`: thêm `channel_post`, `edited_channel_post`.
  - `service.py`: tin kênh → `voucher.handle_post` (không trả lời); nút `u:vc:*`; `/magiam`; 🎟 ở trang chủ khi đã gắn kênh.
  - `messages.py`: lệnh `magiam`, `home_keyboard(show_voucher)`. `zalo_bot.py`, `zalo_render.py`: Zalo `magiam`.
  - `admin_engagement.py`: nút 🎟 Báo mã, màn gắn / gỡ kênh, bật / tắt, số liệu; ghi 📊 Lịch sử.
- Test `tests/test_cashback_voucher.py` (8). Sửa danh sách lệnh trong `test_cashback_bot.py`, `test_cashback_plan060.py`.
- Toàn bộ: 940 qua, 1 hỏng có sẵn (`test_b9…`). Ruff sạch.

## Bỏ giới hạn, gửi mọi khách (30/10, chủ bot: «cứ có mã là báo, không cần giới hạn gì hết»)
- Chủ bot chọn: gửi **mọi khách đã tạo link** (khách tự bật cũng nhận), ai không muốn thì 🔕 Tắt báo mã / `/magiam`
  (`voucher_on:<id>` = "0"); mã nạp lúc 0h **nhắn ngay**.
- Bỏ: khung 8:00–22:00, một mã cách 12 giờ, tối đa 3 tin / khách / ngày. Giữ: tin AddLiveTag sửa lại (% đã dùng) không gửi
  lại; khách chặn bot không gửi.
- Admin: «N khách nhận báo mã» đếm theo luật mới.
- Thử thật 30/10: mã tay `TEST123` đăng vào kênh → bot gửi chủ bot sau 1 giây; chủ bot bảo gỡ → backup
  `cashback-manual-20261030T060926Z.sqlite`, đặt `TEST123` = out.
- AddLiveTag đang theo dõi `METAPARIGDOCT2211` (Instagram giảm 22%, tối đa 300K, đơn từ 50K, hiệu lực tới 2038).

## Link lưu mã gắn affiliate (30/10, chủ bot: «đăng tay thì gắn được mã aff không» → «em thử xem»)
- Thử 1 lần trên Chrome chủ bot: `s.shopee.vn/an_redir?origin_link=<trang mã VCXBHH1030>&affiliate_id=…&sub_id=VOUCHER`
  mở đúng trang mã, URL đích có `promotionId` và `utm_medium=affiliates`.
- Mức 1 (sub_id chung `VOUCHERS`, 8 ký tự như sub_id link): link trang mã `https://shopee.vn/…` trong tin kênh (AddLiveTag hay
  đăng tay) được bọc an_redir trước khi lưu và gửi khách. Link rút gọn / không phải shopee.vn giữ nguyên.
- Đơn sub_id `VOUCHERS` không khớp link bot nên không gắn khách, không thành tiền hoàn; chủ bot có hoa hồng. Khách dán link món
  vào bot sau đó thì lượt bấm mới (sub_id của khách) được tính như thường.
- `affiliate.build_voucher_redir`, `voucher.handle_post(..., affiliate_id)`. Test `test_link_luu_ma_gan_affiliate_sub_id_chung`.

## Chế độ thử: chỉ admin (30/10, chủ bot: «cần test trước cho admin đã»)
- `bot_state.voucher_audience`: vắng / "test" = chỉ gửi admin (`CASHBACK_ADMIN_USER_IDS`), đầu tin có dòng 🧪 Tin thử;
  "all" = mọi khách theo luật trên. Mặc định là thử.
- /admin → 📣 Nhắc mùa sale → 🎟 Báo mã: 📣 Bật gửi khách / 🧪 Về chế độ thử, màn ghi số khách sẽ nhận; ghi 📊 Lịch sử.
- Test `test_che_do_thu_mac_dinh_chi_gui_admin`. Toàn bộ (trước chế độ thử) 941 qua, 1 hỏng có sẵn (`test_b9…`);
  sau chế độ thử chạy lại 9 file liên quan: 144 qua. Ruff sạch.
