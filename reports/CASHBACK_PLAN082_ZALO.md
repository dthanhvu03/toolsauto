# PLAN-082 — Kênh Zalo: code, test, diễn tập

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code (chủ bot giao: "triển khai em viết em làm toàn như các báo cáo vừa làm hôm nay") |
| PLAN | `agents/plans/active/PLAN-082-cashback-zalo-channel.md` |
| Nghiên cứu | `reports/CASHBACK_ZALO_BOT_RESEARCH.md` |
| Nhánh | `cursor/cashback-zalo-bot` |

## Đã làm

| File | Nội dung |
|---|---|
| `cashback_bot/zalo_api.py` (mới) | `getUpdates`, `getMe`, `sendMessage` (chữ thuần + `text_styles`; Zalo từ chối định dạng thì gửi lại chữ thuần), `sendChatAction`. Lỗi phân loại như Telegram (`TelegramDeliveryError`) |
| `cashback_bot/zalo_render.py` (mới) | HTML Telegram → chữ thuần + style UTF-16; `<a>` → URL trần; nút Mua → "🛒 Mua trên Shopee: URL"; nút `u:*` → "Gõ số để chọn"; cắt tin 2000 ký tự. Câu chào, hướng dẫn thẻ xem trước |
| `cashback_bot/zalo_bot.py` (mới) | Tiến trình `python -m cashback_bot.zalo_bot`; ID nội bộ âm; hộp thư `zalo_inbox` chống trùng, lưu câu trả lời để gửi lại; gõ số chạy nút; lệnh tắt `menu` / `hd` / `don` / `vi` / `hotro`…; `ZaloSender` cho thông báo khách |
| `cashback_bot/db.py` | Bảng `channel_identities`, `zalo_inbox`. `list_pending_admin_events(channel=)`: Telegram lấy tin admin và tin khách ID dương; Zalo chỉ lấy tin khách ID âm |
| `cashback_bot/notify_dispatch.py` | `Dispatcher(channel=)` |
| `cashback_bot/config.py` | `ZALO_BOT_TOKEN` tuỳ chọn |
| `cashback_bot/admin_notify.py` | Admin thấy khách Zalo là `Zalo #N` |
| `tests/test_cashback_zalo.py` (mới) | 12 test |

**Không đổi:**
- bảng tiền, sổ ví, đối soát, chính sách và tỷ lệ (dùng chung công thức Telegram);
- luồng trả lời Telegram;
- khoá tài chính.

## Kiểm thử
- 12 test Zalo:
  - link gắn ID âm, URL trần;
  - Zalo gửi lại cùng tin → không tạo link mới;
  - hai khách → hai ID, chào một lần;
  - thẻ xem trước → hướng dẫn ✕;
  - gõ số đúng nút, số sai → báo hết hạn;
  - lỗi mạng → gửi lại câu đã lưu, không gọi lại nguồn giá;
  - lỗi vĩnh viễn → `failed`;
  - tin khách Zalo không đi qua Telegram và ngược lại;
  - style UTF-16 / `<a>` / cắt tin;
  - nhãn admin;
  - Zalo từ chối định dạng → gửi chữ thuần.
- Toàn bộ test cũ: xem mục Triển khai.
- **Diễn tập trên bản sao DB production** (quyền 0600, Zalo giả, nguồn giá giả, đã xoá sau khi chạy):
  - migrate tạo 2 bảng;
  - 6 tin (`hd`, `menu`, `1`, link, thẻ xem trước, `don`) đều `replied`;
  - link gắn ID −1, update −4;
  - +1 link, +1 người dùng; ví / đơn / lệnh chi +0;
  - tin chờ gửi của bot Telegram không đổi;
  - tin hỗ trợ cho khách Zalo chỉ có trong hàng Zalo;
  - `gate_b_check` OK.

## Giới hạn đã biết
- Gói Zalo BASIC: 50 người dùng, 3.000 tin/tháng.
- Bot tự nhắn trước (thông báo đơn khi khách lâu không nhắn) chưa thử thật. Zalo từ chối → tin thông báo `failed`, khách bị đánh dấu chặn cho tới khi nhắn lại (giống Telegram).
- Tin Zalo gửi lúc tiến trình tắt sẽ mất (Zalo không giữ).
- Trang hướng dẫn chung vẫn ghi "nút 🛒 Mua trên Shopee"; trên Zalo đó là dòng link.

## Triển khai
1. Backup.
2. Merge `--ff-only`, chạy test + ruff, push.
3. Chủ bot restart bot Telegram **trước** (bộ lọc kênh cho hàng thông báo).
4. Chủ bot khởi động tiến trình Zalo:
   `cd /home/vu/toolsauto && umask 077 && setsid nohup .venv/bin/python -m cashback_bot.zalo_bot >> logs/cashback_zalo.log 2>&1 &`
5. Kiểm tra:
   - log `zalo start bot=Bot Săn Hoàn Tiền`;
   - chủ bot nhắn `menu`, một link (bấm ✕), `don`;
   - `gate_b_check`.

**Tắt:** `kill -TERM <PID zalo>`. Khách Zalo vẫn nằm trong sổ chung.
