# Báo cáo triển khai — PLAN-074 Shopee Validation & Commission V1

| | |
|---|---|
| Ngày triển khai | 24/10/2026, 10:28–10:31 giờ VN (03:28–03:31 UTC) |
| Người duyệt | Chủ bot ("duyệt 074") |
| Người thực hiện | Claude Code (backup, merge, kiểm tra). Chủ bot chạy lệnh restart |
| Phiên bản | `main` `539e3d9` → **`cef3467`** (PLAN-074, ADR-051) |
| Kết quả | **THÀNH CÔNG.** Mọi kiểm tra sau triển khai đều đạt |

---

## 1. Tóm tắt

Từ bản này, bot theo dõi riêng **trạng thái duyệt hoa hồng** của từng đơn Shopee, tách khỏi trạng thái đơn hàng và trạng thái tiền Shopee đã trả:

- Hai đơn thật qua bot đang **chờ Shopee duyệt hoa hồng**. Đơn ngoài bot ngày 23/09 được nhận ra là **gian lận**.
- **Chưa đơn nào được ghi là "Shopee đã duyệt"**, vì Shopee hiện chưa cung cấp field nào chứng minh điều này.
- Từ lần bấm 🔄 kế tiếp, mỗi khi Shopee đổi hoa hồng hay trạng thái, bot ghi lịch sử (giá trị trước và sau) và báo admin một tin.
- Màn mới: /admin → 🔗 Shopee Affiliate → **🧾 Duyệt hoa hồng**.
- Ví khách và chi trả **vẫn khoá** như PLAN-073. Công thức báo giá không đổi.

---

## 2. Các bước đã làm

| # | Bước | Giờ (UTC) | Kết quả |
|---|---|---|---|
| 1 | Kiểm tra trước: `main` sạch, HEAD `539e3d9` | 03:28 | đạt |
| 2 | Backup trước triển khai | 03:28:35 | `cashback-20261024T032835Z.sqlite`, 0600. `verify_backup`: 21 bảng, 31 link, integrity ok |
| 3 | `git merge --ff-only cursor/cashback-plan074-validation` | 03:29 | `main` = `cef3467` |
| 4 | Test trên `main` | 03:29 | **368 passed**, ruff sạch |
| 5 | `git push origin main` | 03:29 | `origin/main` = `cef3467` |
| 6 | Chủ bot restart (`kill -TERM 597550`, `umask 077`, `setsid nohup …`) | 03:30:51 | PID mới **601747** |
| 7 | Migration tự chạy lúc khởi động | 03:30:56 | thêm bảng `shopee_conversion_changes` và 13 cột; điền trạng thái cho dòng cũ |

---

## 3. Kiểm tra sau triển khai

| Kiểm tra | Kết quả |
|---|---|
| Bot chạy bản mới | ✅ PID 601747 khởi động 03:30:51, sau commit `cef3467` |
| Khởi động sạch | ✅ `setMyCommands ok` … `start db=… public=True`; **0 ERROR/Traceback** từ sau restart |
| Migration | ✅ đủ 13/13 cột mới; bảng `shopee_conversion_changes` có, 0 dòng; `quick_check` = ok |
| Trạng thái 3 đơn (DB chỉ đọc) | ✅ xem bảng dưới |
| Không suy diễn | ✅ 0 đơn APPROVED; cả 3 `settlement_status = NOT_VERIFIED` |
| Khoá tài chính | ✅ 4 trigger `financial_lock_*` còn nguyên; không có bảng bằng chứng; `wallet_enabled=0`; bản sao: nút bật ví bị từ chối "còn khoá tài chính", công tắc vẫn 0 |
| Dữ liệu cũ | ✅ sổ ví vẫn 2 khoản `pending` (12.157đ, 960đ); 0 yêu cầu rút; 0 update bị cách ly |
| Màn 🧾 Duyệt hoa hồng | ✅ dựng trên bản sao DB vừa chạy: "Đơn qua bot: 2 · Chờ xác minh 2 · Shopee đã duyệt 0", kèm "⚠️ Chưa có dữ liệu đủ điều kiện xác nhận hoa hồng đã được Shopee duyệt." và đủ 7 nút |
| Log không lộ bí mật | ✅ 0 chuỗi dạng token |

**Trạng thái 3 đơn sau triển khai:**

| Đơn | Qua bot | Trạng thái đơn | Hoa hồng (ban đầu = hiện tại) | Duyệt hoa hồng | Tiền Shopee trả |
|---|---|---|---|---|---|
| …0309 DOPI kem nền | có | Chưa thanh toán | 17.368đ | ⏳ Chờ Shopee duyệt | Chưa xác minh |
| …0025 Bộ cọ trang điểm | có | Đã thanh toán | 1.372đ | ⏳ Chờ Shopee duyệt | Chưa xác minh |
| …7156 (23/09) | không | Đã hoàn thành | 0đ | 🚨 Gian lận (Shopee gắn cờ) | Chưa xác minh |

Các kiểm tra màn hình và khoá ví chạy trên bản sao DB (0600, đã xoá ngay), không bấm trên bot thật, không gửi tin Telegram, không gọi Shopee.

**Chủ bot nên tự xem trên Telegram:** /admin → 🔗 Shopee Affiliate → 🧾 Duyệt hoa hồng → bấm "📋 Chờ xác minh" → bấm một đơn để xem chi tiết.

---

## 4. Từ giờ bot làm gì khác

- **Mỗi lần bấm 🔄:**
  - mỗi đơn được đánh giá lại;
  - có thay đổi thật thì ghi lịch sử, đồng bộ lại y hệt thì không ghi gì;
  - tin kết quả đồng bộ có thêm "N thay đổi hoa hồng/trạng thái đã ghi lịch sử".
- **Hoa hồng giảm từ 1.000đ / 10%, về 0, xuất hiện gian lận, đơn huỷ, Sub ID trỏ sang link khác:** đơn chuyển "🔎 Cần kiểm tra" và admin nhận **một** tin "🔔 Hoa hồng Shopee thay đổi" cho mỗi lần đồng bộ.
- **Shopee trả thiếu dữ liệu:** bot giữ số cũ, không ghi đè thành 0 hay rỗng.
- **Người được ghi nhận** theo Sub ID giữ theo lần gắn đầu tiên.
- **Đơn gian lận hoặc bị huỷ:** sổ ví ghi không phải trả.

---

## 5. Cách quay lại bản cũ (nếu cần)

1. Chủ bot dừng bot.
2. `git revert cef3467` trên `main`, push, rồi khởi động lại.
3. Bảng và cột mới để lại không ảnh hưởng code cũ. Trigger khoá không bị đụng.
4. DB hỏng: khôi phục từ `data/backups/cashback-20261024T032835Z.sqlite` theo `cashback_bot/BACKUP.md`.

---

## 6. Việc còn lại

**Để mở được trạng thái "Shopee đã duyệt"** (chủ bot chọn một trong hai):
- đợi Shopee duyệt kỳ tháng 10, rồi bấm 🔄 một lần để bot lưu dữ liệu đơn đã duyệt; hoặc
- xuất báo cáo "Xác thực" / "Thanh toán" (CSV) từ trang Shopee Affiliate gửi em.

**PLAN-075 — Settlement & đối chiếu quỹ** (trước khi chi tiền thật):
1. Nguồn bằng chứng Shopee đã trả: trang Thanh toán Shopee Affiliate hay sao kê ngân hàng (chủ bot chọn).
2. Luồng ghi bằng chứng có kiểm soát và audit.
3. Đối chiếu đơn với kỳ thanh toán.
4. Điều chỉnh âm khi hoa hồng giảm sau khi đã vào ví.
5. Quyết định thuế người nhận; quét QR thật; trần rút mỗi tháng.

Chi tiết kỹ thuật: `reports/CASHBACK_PLAN074_VALIDATION.md`.
