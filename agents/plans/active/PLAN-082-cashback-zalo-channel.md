# PLAN-082 — Kênh Zalo cho bot hoàn tiền

| | |
|---|---|
| Executor | Claude Code (chủ bot giao trực tiếp 2026-10-24: "triển khai em viết em làm toàn như các báo cáo vừa làm hôm nay") |
| Nghiên cứu | `reports/CASHBACK_ZALO_BOT_RESEARCH.md` (mục 7: thử thật với token) |
| Trạng thái | Gate A: code + test + diễn tập. Triển khai sau khi chủ bot duyệt |

## Mục tiêu
Khách dùng Zalo gửi link Shopee, nhận link mua và số tiền hoàn dự kiến; xem đơn, hỗ trợ, thông báo đơn như bên Telegram. Lõi giá, `sub_id`, đồng bộ đơn, sổ ví, đối soát dùng chung. Bot Telegram không đổi hành vi.

## Thiết kế
1. **ID nội bộ âm.** Bảng `channel_identities(internal_user_id < 0, channel='zalo', external_id, display_name)`. Khách Zalo đi qua `CashbackService` như khách Telegram với ID âm. Không đổi bảng tiền, không đổi cột cũ.
2. **Tiến trình riêng** `python -m cashback_bot.zalo_bot`, khoá `/tmp/cashback_zalo.lock`. Chỉ nhận tin Zalo, trả lời, gửi thông báo cho khách Zalo. Không đồng bộ Shopee, không chạy việc định kỳ.
3. **Hộp thư bền** `zalo_inbox` (theo `message_id` Zalo): chống xử lý trùng. `-id` là `update_id` cho lõi nên không đụng số update Telegram. Lưu câu trả lời của bot để gửi lại khi lỗi mạng. Không lưu nội dung khách gửi (PLAN-077).
4. **Nút → số.** `zalo_render`:
   - bàn phím Telegram thành danh sách "1 · …";
   - khách gõ số thì chạy đúng callback `u:*` đó (lưu menu gần nhất 30 phút trong `bot_state`);
   - nút URL thành "nhãn: URL trần";
   - `<a href>` thành URL trần;
   - cắt tin 2000 ký tự.
5. **Lệnh gõ tắt:** `menu`, `hd`, `don`, `vi`, `hotro`, `cachtinh`, `dieukien`, `thongbao`; lệnh `/…` vẫn dùng được.
6. **Tin Zalo không hỗ trợ** (link bị Zalo biến thành thẻ xem trước) → hướng dẫn bấm ✕ hoặc bỏ `https://`. Tin đầu tiên: chào và báo đây là bot tự động, bot lưu dữ liệu gì (điều khoản Zalo III.6).
7. **Thông báo cho khách:** `Dispatcher` thêm `channel`:
   - Telegram chỉ lấy tin admin và tin khách có `chat_id > 0`;
   - Zalo chỉ lấy tin khách có `chat_id < 0`, gửi qua `ZaloSender`;
   - cùng cờ, cùng tuỳ chọn, cùng chống gửi trùng.
8. Admin thấy khách Zalo dạng `Zalo #N`.

## Scope (file)
- **Mới:** `cashback_bot/zalo_api.py`, `cashback_bot/zalo_render.py`, `cashback_bot/zalo_bot.py`, `tests/test_cashback_zalo.py`.
- **Sửa nhẹ:**
  - `db.py`: 2 bảng mới, lọc kênh khi lấy tin chờ;
  - `notify_dispatch.py`: tham số `channel`;
  - `config.py`: `ZALO_BOT_TOKEN` tuỳ chọn;
  - `admin_notify.py`: nhãn `Zalo #N`.

## Ngoài scope
Ví / rút tiền riêng cho Zalo (ví đang khoá cho mọi kênh), gộp tài khoản Telegram ↔ Zalo, webhook, đổi chính sách / tỷ lệ (dùng chung công thức Telegram).

## Kiểm thử bắt buộc
- Gửi link qua Zalo giả → `sub_id` gắn ID âm, link affiliate đúng, tin có URL trần.
- Zalo gửi lại cùng `message_id` → không tạo link mới.
- Gõ số chọn menu → chạy đúng callback; số ngoài menu → hướng dẫn.
- Tin không hỗ trợ → hướng dẫn bấm ✕.
- Tin khách Zalo không bao giờ đi qua Telegram, và ngược lại.
- Lỗi gửi Zalo → lưu để gửi lại, không xử lý lại.
- `gate_b_check` OK; toàn bộ test cũ đạt.

## Triển khai (sau khi duyệt)
1. Backup.
2. Merge, chạy test, push.
3. Chủ bot restart bot Telegram **trước** (bộ lọc kênh), rồi mới khởi động `cashback_bot.zalo_bot`.
4. Chủ bot nhắn thử trên Zalo; kiểm tra log và `gate_b_check`.

**Tắt:** dừng tiến trình Zalo. Dữ liệu khách Zalo vẫn nằm trong sổ chung.
