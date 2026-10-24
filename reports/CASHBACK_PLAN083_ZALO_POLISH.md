# PLAN-083 — Hoàn thiện bot Zalo: rà soát, sửa, diễn tập

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| PLAN | `agents/plans/active/PLAN-083-cashback-zalo-polish.md` |
| Nhánh | `cursor/cashback-zalo-polish` |

## Đã làm (phần A)

| Việc | Trước | Sau |
|---|---|---|
| A1 Tin admin | `User -1`, `Update -5` | `Zalo #1`, `Tin Zalo #5` |
| A2 Lệnh trong câu chữ | "Gửi yêu cầu tại /hotro", "Gõ /huongdan" | "Gửi yêu cầu bằng cách gõ **hotro**", "Gõ **hd**" (không đụng URL) |
| A3 Cách dùng | Chữ "nút", mẹo ✕ nằm cuối | Trang riêng "Cách dùng trên Zalo": 4 bước, có bấm ✕, "link 🛒 Mua trên Shopee" |
| A4 Thẻ báo giá | Link dài nằm cuối thẻ, sau đoạn lưu ý | Thẻ một tin; link mua một tin riêng ngay sau: "👉 Bấm link dưới để mua trên Shopee:" + URL, danh sách số ở cuối |
| A5 Danh sách số | "1 · ◀️ Trang chủ" | "1 · Trang chủ" |
| A6 Lỗi xử lý | Khách không nhận gì | Câu xin lỗi + gợi ý `hotro`; admin nhận "Lỗi bot · zalo_update_failed" |
| A7 Bot Zalo dừng | Không ai biết | Bot Telegram kiểm tra mỗi 5 phút; Zalo im > 10 phút → "🔴 Bot Zalo không hoạt động" kèm lệnh khởi động lại (một lần); chạy lại → "🟢 Bot Zalo hoạt động lại" |
| A8 Trần 50 người | Không cảnh báo | Khách thứ 40: "🟡 sắp chạm trần"; thứ 50: "🔴 đã chạm trần" |
| A9 Điều khoản, thông báo | "Bấm từng mục…", "Bấm để bật / tắt" | "Gõ số của từng mục…", "Gõ số để bật / tắt" |
| A10 Đồng ý điều khoản | Khách Zalo ghi nguồn `telegram_button` | Ghi `zalo_choice` |
| A11 Câu xác nhận | Mất (Zalo không có popup) | Đặt lên đầu tin, ví dụ "Đã ghi nhận bạn đồng ý điều khoản." |

**File:**
- `zalo_render.py`, `zalo_bot.py`;
- `admin_notify.py` (dòng chi tiết, 2 tin mới);
- `poller.py` (`_check_zalo_health`);
- `customer_desk.py` (nguồn đồng ý).

**Không đổi:** tiền, ví, tỷ lệ, điều khoản, luồng Telegram của khách.

## Kiểm thử
- `tests/test_cashback_zalo.py`: 20 test (thêm 8 test cho A1–A11, kèm 1 test canh câu gốc Telegram còn tồn tại).
- Toàn bộ: **697 passed**, ruff sạch.
- **Diễn tập trên bản sao DB production** (Zalo giả, nguồn giá giả, đã xoá sau khi chạy), đi 20 bước:
  - menu → điều khoản → mục Dữ liệu;
  - cách tính, ví, hạng, thông báo (bật / tắt bằng số);
  - hỗ trợ → chọn loại → gửi nội dung → tạo yêu cầu #1;
  - đơn, link (tên có `&` `<`), lưu ý trước khi mua;
  - chữ thường, link ShopeeFood, số sai, sticker, thẻ xem trước.
  
  Mọi trang hiển thị đúng; A9–A11 là lỗi tìm ra ở lượt này.

## Phần B — chờ chủ bot quyết
1. **Điều khoản V1** (đang công bố) mục Dữ liệu ghi "Mã tài khoản Telegram"; mục Ghi nhận ghi "gắn với tài khoản Telegram". Đề xuất ra V2: "tài khoản Telegram hoặc Zalo". Nội dung khoá theo phiên bản; chủ bot duyệt câu chữ rồi công bố ở /admin.
2. **Rút gọn link mua:** thử 1 lần AddLiveTag `short_link`, hoặc link rút gọn Shopee (cần duyệt).
3. **Khoảng 2026-10-26:** thử 1 tin chủ động cho chủ bot sau ≥ 48 giờ không nhắn.
4. Ảnh đại diện và mô tả bot trong Zalo Bot Creator.
5. Lên gói Pro khi gần 50 người.

## Phần B — chủ bot quyết theo đề xuất (2026-10-24: "anh quyết theo đề xuất của em nhé triển khai luôn")

| Việc | Kết quả |
|---|---|
| B1 Điều khoản V2 | Mẫu `terms_content.py` lên **V2**. Đã đối chiếu: mẫu cũ trùng hash bản V1 đang công bố (`63c0d16d…`). V2 chỉ đổi 2 câu: "gắn với tài khoản Telegram **hoặc Zalo** đã gửi link", "Mã tài khoản Telegram **hoặc Zalo**, tên người dùng **hoặc tên hiển thị**". Không đổi quyền lợi, cách tính, trạng thái chi trả. **Chủ bot công bố:** /admin → 📋 Điều khoản → "📝 Tạo bản nháp V2 từ mẫu" → xem → Công bố → xác nhận. Cờ bắt buộc đồng ý đang tắt nên khách không bị chặn |
| B2 Rút gọn link | **Không làm.** Trang "short link" của AddLiveTag là tài liệu Shopee Open API `generateShortLink` (cần App ID + chữ ký, mình không có). Rút gọn qua phiên cookie Shopee thì mỗi link khách gọi Shopee một lần → rủi ro phiên bị kiểm tra, hỏng đồng bộ đơn. Giữ link `s.shopee.vn/an_redir…` ở tin riêng (A4) |
| B3 Tin chủ động | Hẹn khoảng 2026-10-26 (sau ≥ 48 giờ chủ bot không nhắn bot Zalo) |
| B4 Ảnh, mô tả | Chủ bot tự làm trong Zalo Bot Creator (câu mô tả đã đề xuất trong phiên) |
| B5 Gói Pro | Khi có cảnh báo khách thứ 40 (A8) |
