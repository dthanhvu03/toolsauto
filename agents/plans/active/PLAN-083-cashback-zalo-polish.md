# PLAN-083 — Hoàn thiện bot Zalo cho khách dùng

| | |
|---|---|
| Executor | Claude Code (chủ bot: "chỉnh cho chỉnh chu hoàn thiện, rà lại rồi làm 1 plan để hoàn thiện zalo bot cho user dùng") |
| Nền | PLAN-082 (kênh Zalo đang chạy từ 2026-10-24 15:26Z) |
| Báo cáo | `reports/CASHBACK_PLAN083_ZALO_POLISH.md` |

## Rà soát (những gì khách Zalo và admin đang thấy)

| # | Chỗ | Vấn đề |
|---|---|---|
| R1 | Tin admin Telegram | Khối chi tiết in `User -1`, `Update -5`: số kỹ thuật âm, khó hiểu |
| R2 | Câu chữ dùng chung với Telegram | "Gõ /huongdan", "Gửi yêu cầu tại /hotro", "Mở /dieukien": trên Zalo nên là lệnh gõ tắt (`hd`, `hotro`, `dieukien`) |
| R3 | Trang Cách dùng | Ghi "nút 🛒 Mua trên Shopee", "Bấm nút đó"; trên Zalo đó là dòng link. Chưa nói cách xử lý thẻ xem trước ngay trong các bước |
| R4 | Thẻ báo giá | Link affiliate dài 4–5 dòng, nằm cuối tin sau đoạn lưu ý → khó thấy, khó bấm |
| R5 | Danh sách số | "1 · ◀️ Trang chủ": mũi tên điều hướng thừa trên Zalo |
| R6 | Lỗi khi xử lý một tin | Khách không nhận được gì, admin không được báo; tin nằm mãi ở `received` |
| R7 | Tiến trình Zalo dừng | Không ai biết. Zalo không giữ tin gửi lúc bot tắt → mất tin khách |
| R8 | Gói BASIC 50 người | Không có cảnh báo trước khi chạm trần |
| R9 | Điều khoản đang công bố | Ghi "gắn với tài khoản Telegram"; khách Zalo đọc thấy chữ Telegram |
| R10 | Link dài | Rút gọn cần gọi dịch vụ ngoài (AddLiveTag short link hoặc Shopee) |
| R11 | Thông báo đơn chủ động | Chưa thử bot nhắn trước khi khách lâu không nhắn |

## Phần A — làm ngay (không cần quyết định chính sách)

| Việc | Cách làm | File |
|---|---|---|
| A1 (R1) | Khối chi tiết admin: `Zalo #1`, `Tin Zalo #5` | `admin_notify.py` |
| A2 (R2) | Đổi lệnh `/x` trong câu chữ thành "gõ **x**" khi gửi Zalo; có test canh câu gốc còn tồn tại | `zalo_render.py` |
| A3 (R3) | Trang Cách dùng riêng cho Zalo: 4 bước, có bấm ✕, "link" thay "nút" | `zalo_render.py`, `zalo_bot.py` |
| A4 (R4) | Link mua tách thành tin riêng, ngay sau thẻ báo giá: "👉 Bấm link dưới để mua trên Shopee" + URL | `zalo_render.py` |
| A5 (R5) | Bỏ mũi tên ◀️ ▶️ trong nhãn danh sách số | `zalo_render.py` |
| A6 (R6) | Lỗi xử lý → khách nhận câu xin lỗi, admin được báo (`zalo_update_failed`) | `zalo_bot.py` |
| A7 (R7) | Nhịp sống `zalo_heartbeat` (bot_state) mỗi vòng; bot Telegram kiểm tra mỗi 5 phút, quá 10 phút → báo admin "Bot Zalo đã dừng" (một lần), chạy lại → báo đã chạy lại | `zalo_bot.py`, `poller.py` |
| A8 (R8) | Khách Zalo thứ 40 và thứ 50 → báo admin sắp chạm / đã chạm trần gói BASIC | `zalo_bot.py` |
| A9 | Phát hiện khi diễn tập: trang điều khoản "Bấm từng mục… bấm nút cuối", cài đặt thông báo "Bấm để bật / tắt" → câu gõ số | `zalo_render.py` |
| A10 | Phát hiện khi diễn tập: khách Zalo đồng ý điều khoản bị ghi nguồn `telegram_button` → ghi `zalo_choice` (bằng chứng đúng kênh) | `customer_desk.py` |
| A11 | Phát hiện khi diễn tập: Zalo không có popup → câu xác nhận (toast) đặt lên đầu tin | `zalo_render.py` |

**Không đổi:** tiền, ví, tỷ lệ, chính sách, điều khoản, luồng Telegram cho khách.

## Phần B — chờ chủ bot quyết
1. **R9:** ra phiên bản điều khoản mới ghi "tài khoản Telegram hoặc Zalo". Nội dung bị khoá theo phiên bản; chủ bot duyệt câu chữ rồi công bố ở /admin.
2. **R10:** rút gọn link. Thử 1 lần AddLiveTag `short_link` (nguồn ghi phi thương mại) hoặc link rút gọn Shopee (cần duyệt gọi Shopee).
3. **R11:** khoảng 2026-10-26, thử 1 tin chủ động cho chủ bot sau ≥ 48 giờ không nhắn.
4. Ảnh đại diện và mô tả bot trong Zalo Bot Creator (chủ bot tự làm; câu mô tả đã đề xuất).
5. Lên gói Pro khi Zalo mở bán, nếu gần 50 người.

## Phần C — sau
Ví / rút tiền cho khách Zalo: chọn ngân hàng bằng số đã chạy được qua A5. Thử đủ luồng khi chủ bot mở ví.

## Kiểm thử
Test cho từng việc A1–A8. Toàn bộ test cũ đạt, ruff sạch. Diễn tập trên bản sao DB, `gate_b_check` OK.

## Triển khai
1. Backup.
2. Merge, chạy test, push.
3. Restart cả hai tiến trình: Telegram trước (A1, A7), rồi Zalo.
4. Chủ bot nhắn thử `hd`, một link, `don`.
