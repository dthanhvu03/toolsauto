# Báo cáo triển khai — PLAN-079 Customer Order Tracking & Notifications V1 (Gate A)

| | |
|---|---|
| Ngày triển khai | 24/10/2026, 15:06–15:11 giờ VN (08:06–08:11 UTC) |
| Người duyệt | Chủ bot ("Có em phát hành đi em") |
| Người thực hiện | Claude Code (backup, merge, kiểm tra). Chủ bot chạy lệnh restart |
| Phiên bản | `main` `1b0d145` → **`0deb060`** (PLAN-079, ADR-056) |
| Kết quả | **THÀNH CÔNG (Gate A).** Thông báo đơn tự động TẮT; không gửi thêm tin cho khách |

---

## 1. Tóm tắt

- Khách có thêm:
  - **📦 Đơn hàng của tôi** (`/donhang`): tổng quan, danh sách, chi tiết đơn của chính mình;
  - **`/thongbao`**: tự bật hoặc tắt từng loại tin.
- Hàng đợi tin dùng chung cho admin và khách, với bộ gửi mới: thử lại có giãn cách, theo `retry_after`, biết khách chặn bot, không tự gửi lại khi không rõ kết quả.
- Sự kiện thông báo đơn đã có nhưng **cờ `CUSTOMER_NOTIFICATIONS_ENABLED` tắt** và mốc kích hoạt chưa đặt. Đồng bộ 🔄 không gửi tin đơn cho khách.
- Admin có màn **🔔 Thông báo khách**.

---

## 2. Các bước đã làm

| # | Bước | Giờ (UTC) | Kết quả |
|---|---|---|---|
| 1 | Kiểm tra trước: `main` sạch, HEAD `1b0d145`, PID 631959; `.env` không đặt `CUSTOMER_NOTIFICATIONS_ENABLED`; hàng đợi 42 dòng, tất cả `sent` | 08:06 | đạt |
| 2 | Backup trước triển khai | 08:06:56 | `cashback-20261024T080656Z.sqlite`, 0600. `verify_backup`: 40 bảng, 35 dòng link |
| 3 | `git merge --ff-only cursor/cashback-plan079-notifications` | 08:07 | `main` = `0deb060` |
| 4 | Test trên `main` | 08:10 | **588 passed**, ruff sạch |
| 5 | `git push origin main` | 08:10 | `origin/main` = `0deb060` |
| 6 | Chủ bot restart | 08:10:45 | PID mới **636239** |
| 7 | Migration lúc khởi động | 08:10:47 | 6 cột cho `admin_notifications` + index; bảng `customer_notification_prefs`; cột `telegram_users.notify_blocked_at` |

---

## 3. Kiểm tra sau triển khai

DB đọc ở chế độ chỉ đọc. Các màn dựng trên bản sao DB (0600, xoá ngay). Không bấm trên bot thật.

| Kiểm tra | Kết quả |
|---|---|
| Bot chạy bản mới | ✅ PID 631959 → **636239** |
| Khởi động sạch | ✅ `setMyCommands` (thêm `/donhang`, `/thongbao`), 0 ERROR, 0 chuỗi dạng token |
| Schema | ✅ cột `audience`, `category`, `next_retry_at`, `telegram_message_id`, `reply_markup_json`, `source_ref`; bảng tuỳ chọn (0 dòng); cột đánh dấu chặn bot |
| Hàng đợi | ✅ 42 dòng cũ, tất cả `audience=admin`, `sent`; **0 tin mới** |
| Cờ thông báo đơn | ✅ tắt; mốc kích hoạt chưa đặt |
| Khoản pending | ✅ 12.157đ và 960đ, `pending` |
| Ví và khoá | ✅ ví tắt, 0 available, 0 payout, 6 trigger khoá |
| `quick_check` | ✅ ok |
| Menu và trang chủ (bản sao) | ✅ lệnh `start, huongdan, dieukien, cachtinh, donhang, hotro, thongbao, help`; trang chủ có 📦 Đơn hàng của tôi |
| `/donhang` của 2 khách có đơn (bản sao) | ✅ khách …966: 1 đơn, hoàn tạm tính 960đ, "Người mua đã thanh toán đơn · Hoa hồng đang chờ Shopee xác minh"; khách …420: 1 đơn, 12.157đ, "Người mua chưa thanh toán đơn · Hoa hồng đang chờ Shopee xác minh" |
| Màn 🔔 Thông báo khách (bản sao) | ✅ "Thông báo đơn hàng tự động: TẮT (cờ CUSTOMER_NOTIFICATIONS_ENABLED, chờ chủ bot duyệt)" |

**Chủ bot nên tự xem trên Telegram:** gõ `/donhang` và `/thongbao` bằng tài khoản của mình; /admin → 🔔 Thông báo khách → 👁 Xem mẫu tin.

---

## 4. Quay lại bản cũ (nếu cần)

1. **Trước khi revert:** code cũ gửi mọi dòng `status != 'sent'`. Nếu đã có dòng `suppressed` / `unknown` / `failed`, đánh dấu `sent` trước (sửa DB, chỉ khi chủ bot duyệt):
   `UPDATE admin_notifications SET status = 'sent' WHERE status IN ('suppressed', 'unknown', 'failed')`.
   Hiện chưa có dòng nào như vậy.
2. `git revert 0deb060`, push, khởi động lại. Cột và bảng mới để lại vô hại.
3. **Không restore DB** chỉ để quay lại code. Backup: `data/backups/cashback-20261024T080656Z.sqlite`.

---

## 5. Việc tiếp theo

1. **Gate B, bật thông báo đơn:**
   - chủ bot duyệt câu chữ (🔔 → Xem mẫu tin) và ngưỡng 500đ / 10%;
   - thử với tài khoản test;
   - thêm `CUSTOMER_NOTIFICATIONS_ENABLED=1` vào `.env`, restart.
   Mốc kích hoạt được đặt lúc khởi động. Tắt nhanh: bỏ cờ và restart.
2. Nếu muốn tin gần thời gian thực: PLAN riêng cho tự đồng bộ Shopee.

Chi tiết kỹ thuật: `reports/CASHBACK_PLAN079_CUSTOMER_NOTIFICATIONS.md`, ADR-056.
