# Nghiên cứu: chạy bot hoàn tiền song song trên Zalo

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code (nghiên cứu, chỉ đọc; không gọi API Zalo, không viết code) |
| Yêu cầu | Chủ bot: "nghiên cứu zalo bot, viết adapter hay interface để làm 2 bên bot; bên Zalo không cần chính sách rườm rà" |
| Kết luận | **Làm được** bằng Zalo Bot Platform chính thức. Vướng chính: gói miễn phí giới hạn **50 người dùng mỗi bot**; Zalo **không có nút bấm**. Nên làm bản Zalo gọn, dùng chung lõi giá / link / đơn |

## 1. Ba cách làm bot Zalo

| | Zalo Bot Platform | Zalo Official Account (OA) API | Thư viện tài khoản cá nhân (zca-js…) |
|---|---|---|---|
| Chính thức | Có (ra mắt 2025) | Có | **Không**, giả lập Zalo Web |
| Ai tạo được | Cá nhân từ 18 tuổi, hoặc tổ chức hợp pháp | Doanh nghiệp, OA đã xác thực | Bất kỳ tài khoản |
| API | Giống Telegram: `getUpdates`, `setWebhook`, `sendMessage`… | API riêng; tin tư vấn chỉ gửi trong 48 giờ sau lần khách tương tác | Không ổn định |
| Chi phí | Basic miễn phí; Pro 129.000đ/tháng (**sắp ra mắt**) | Có phí theo gói / tin, chưa thấy bảng giá 2026 chính thức | 0đ |
| Rủi ro | Zalo có quyền tạm ngưng không cần báo trước (điều khoản VII.2, VIII.3) | Thủ tục doanh nghiệp | **Tài khoản bị khoá hoặc cấm**; tác giả thư viện tự cảnh báo |

**Đề xuất:** dùng Zalo Bot Platform. Loại zca-js vì rủi ro khoá tài khoản và trái điều khoản. OA chỉ là đường nâng cấp khi đông khách; Zalo cũng tự giới thiệu Enterprise sang OA.

## 2. Zalo Bot Platform: những gì đã xác minh

**Tạo bot:**
1. Trong app Zalo, tìm OA **Zalo Bot Manager**, chọn "Tạo bot".
2. Đặt tên bắt đầu bằng "Bot" (ví dụ "Bot Hoàn Tiền").
3. Zalo gửi Bot Token qua tin nhắn. Token không hết hạn trừ khi reset.

**API** (`https://bot-api.zaloplatforms.com/bot<TOKEN>/<method>`):

| Nhóm | Phương thức | Ghi chú |
|---|---|---|
| Nhận tin | `getUpdates` (long polling, mặc định 30 giây) hoặc `setWebhook` (HTTPS + header `X-Bot-Api-Secret-Token`) | Không chạy hai cách cùng lúc. Bot mình đang dùng polling nên làm được ngay, không cần tên miền |
| Gửi | `sendMessage` (1–2000 ký tự), `sendPhoto` (ảnh bằng URL), `sendSticker`, `sendVoice`, `sendChatAction` (chỉ `typing`) | |
| Định dạng | `parse_mode` = `markdown` hoặc `html`: đậm, nghiêng, gạch, danh sách, màu | **Không có thẻ link `<a>`**: link affiliate phải để dạng URL trần |
| Sự kiện | `message.text.received`, `.image.`, `.sticker.`, `.voice.`, `.unsupported.` | `chat_id` dạng chuỗi, `chat_type` `PRIVATE` |

**Giới hạn gói Basic (miễn phí):**
- 3 bot;
- **50 người dùng mỗi bot**;
- **3.000 tin mỗi tháng**;
- 3 nhóm chat (beta).

Pro tăng "nhiều hơn" nhưng chưa có số và chưa mở bán.

**Chưa xác minh được (phải thử khi có token):**
- Không có nút bấm (inline keyboard): tài liệu `sendMessage` không có `reply_markup`. Tích hợp OpenClaw cũng ghi không hỗ trợ lệnh gốc.
- Bot có được **tự nhắn trước** cho khách không: cần cho thông báo đơn. Trang FAQ có câu hỏi này nhưng không ghi câu trả lời.
- Giới hạn tốc độ gửi.
- Khách tìm bot bằng cách nào (QR / link / tìm kiếm).

**Điều khoản bắt buộc (III.6), dù bản Zalo không cần chính sách rườm rà:**
- báo khách đây là bot tự động;
- báo bot có thu thập dữ liệu hay không.

Một câu chào ngắn là đủ, không cần màn đồng ý điều khoản.

## 3. Hiện trạng code: phần dùng chung được và phần gắn với Telegram

**Dùng chung được ngay** (không phụ thuộc Telegram):
- `shopee_url.py`: nhận link;
- `product_data.py`: AddLiveTag;
- `pricing.py`, `money.py`, `calculator.py`: tính tiền hoàn;
- `affiliate.py`: `sub_id` ngẫu nhiên mỗi link → gắn đơn về đúng người, kênh nào cũng được;
- `shopee_sync.py`, `sync_scheduler.py`: đồng bộ đơn, cũng tự khớp đơn Zalo qua `sub_id`.

**Gắn chặt với Telegram:**

| Chỗ | Mức độ |
|---|---|
| DB: cột `telegram_user_id INTEGER` (62 chỗ trong `db.py`, 19 file); ID Zalo là chuỗi | Cao: cần cột / bảng theo kênh, phải migration |
| `CashbackService.handle_update` đọc cấu trúc update Telegram (`callback_query`, `from.id` kiểu int) | Trung bình |
| `BotReply` có `inline_keyboard`, `edit_message_id`, `callback_query_id`, `toast`; 149 callback `c:…`; 14 file dùng nút | Cao về UX: Zalo không có nút, không sửa được tin cũ |
| `messages.py` viết bằng HTML Telegram, có `<a href>` | Trung bình: cần bản chữ cho Zalo |
| Hàng đợi thông báo khách (`chat_id INTEGER`, gửi qua `TelegramApi`) | Trung bình |
| Toàn bộ màn admin | Giữ trên Telegram, không đưa sang Zalo |

## 4. Kiến trúc đề xuất

```
                     ┌─ TelegramAdapter (đang có: nút, HTML, sửa tin)
lõi dùng chung ──────┤
(nhận link, giá,     └─ ZaloAdapter (mới: chữ + markdown, lệnh gõ tay, URL trần)
 link affiliate, đơn)
```

**Bước 1 — Bot Zalo gọn (tiến trình riêng `cashback_zalo`), không đụng luồng Telegram:**
- **Gửi link Shopee** → trả số tiền hoàn ước tính + link mua (URL trần), dùng lại lõi giá / affiliate.
- **Gõ `don`** → danh sách đơn của khách: chờ duyệt / đã duyệt / bị huỷ.
- **Gõ `hd`** → hướng dẫn 3 dòng. Câu chào đầu tiên ghi rõ là bot tự động.
- **Không có:** ví, rút tiền, hạng, màn điều khoản, nút bấm, admin.
- **DB:** bảng mới `zalo_users` và cột kênh trên `links`, hoặc bảng `zalo_links` riêng. Migration do Codex làm.
- Khi Zalo cho phép bot nhắn trước, bước sau sẽ thêm thông báo đơn qua hàng đợi theo kênh.

**Bước 2 — tách lõi:** gom phần nhận tin / trả lời của `CashbackService` thành giao diện kênh dùng chung, khi bản Zalo đã chạy ổn. Làm ngay từ đầu thì phải sửa rất nhiều file của luồng Telegram đang chạy thật, rủi ro cao mà chưa cần.

## 5. Rủi ro

1. **Trần 50 người / bot** (gói miễn phí): đủ cho thử nghiệm, chưa đủ cho "ai cũng dùng Zalo". Pro chưa mở bán; muốn lớn hơn thì phải chuyển sang OA (doanh nghiệp, có phí).
2. **AddLiveTag ghi "phi thương mại".** Thêm kênh Zalo làm tăng lượng gọi và rủi ro bị chặn. Vẫn cần nguồn giá dự phòng (đã ghi từ trước).
3. Zalo có quyền khoá bot không báo trước. Không có nút → trải nghiệm kém hơn Telegram.
4. Một khách dùng cả hai kênh sẽ có hai danh tính riêng. Bước 1 không gộp tài khoản.

## 6. Chủ bot cần quyết

1. Làm bước 1 không? Nếu làm: anh tạo bot qua **Zalo Bot Manager**, tự thêm `ZALO_BOT_TOKEN=...` vào `.env` (em không đụng `.env`).
2. **Tỷ lệ hoàn bên Zalo:** dùng chung công thức với Telegram (đề xuất, để số tiền khớp đơn), hay một tỷ lệ cố định đơn giản?
3. **Khách Zalo nhận tiền thế nào** khi mở ví? Hiện ví đang khoá cho cả hai kênh, nên bước 1 chỉ báo số dự kiến và theo dõi đơn.
4. Cho phép một lần thử thật với token (`getMe`, gửi 1 tin cho chính anh) để xác minh nút bấm, tự nhắn trước, và cách khách tìm bot.

Theo `CLAUDE.md`, adapter và migration là việc backend. Sau khi anh duyệt, Anti viết PLAN, Codex làm phần backend, Claude Code làm nội dung tin nhắn và UX bên Zalo.

## Nguồn

- Zalo Bot Platform: [trang chủ và bảng giá](https://bot.zaloplatforms.com/en/), [tài liệu](https://bot.zaloplatforms.com/docs/), [tạo bot](https://bot.zaloplatforms.com/docs/create-bot/), [sendMessage](https://bot.zaloplatforms.com/docs/apis/sendMessage/), [điều khoản](https://bot.zaloplatforms.com/docs/terms/)
- Bản tổng hợp API: [context7](https://context7.com/websites/bot_zaloplatforms/llms.txt?tokens=10000)
- Tích hợp tham khảo: [OpenClaw Zalo](https://docs.openclaw.ai/channels/zalo), [OpenClaw Zalo cá nhân](https://docs.openclaw.ai/channels/zalouser)
- zca-js: [npm (cảnh báo khoá tài khoản)](https://npmjs.com/package/zca-js)
- OA: [tin tư vấn 48 giờ](https://unpkg.com/@warriorteam/redai-zalo-sdk@1.11.1/docs/CONSULTATION_SERVICE.md), [Zenify: Zalo OA](https://zenify.vn/blog/what-is-zalo-oa)
