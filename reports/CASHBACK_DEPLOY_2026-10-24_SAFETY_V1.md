# Báo cáo triển khai — Cashback Bot Production Safety Hardening V1

| | |
|---|---|
| Ngày triển khai | 24/10/2026, 09:57–10:00 giờ VN (02:57–03:00 UTC) |
| Người duyệt | Chủ bot ("oke em triển khai tiếp đi") |
| Người thực hiện | Claude Code (backup, merge, kiểm tra). Chủ bot chạy lệnh restart |
| Phiên bản | `main` `eca64fd` → **`a9bb42a`** (PLAN-073, ADR-050) |
| Kết quả | **THÀNH CÔNG.** Bot chạy bản mới, mọi kiểm tra sau triển khai đều đạt |

---

## 1. Tóm tắt

Bot cashback đã được nâng cấp an toàn, không gián đoạn chức năng đang có:

1. **Một tin nhắn lỗi không còn làm cả bot ngừng trả lời.** Tin lỗi được ghi lại để kiểm tra, rồi bot xử lý tiếp tin sau.
2. **Token bot và cookie Shopee không còn có thể lọt vào file log.**
3. **Bot tự sao lưu DB mỗi ngày**, kiểm tra bản sao khôi phục được, báo admin nếu lỗi. Lần đầu đã chạy thành công lúc 09:59.
4. **Khoá chi trả:**
   - Ví khách không bật được, khách không tạo được yêu cầu rút, admin không xác nhận được "đã chuyển", cho tới khi có bằng chứng Shopee đã trả tiền và chính sách thuế đã duyệt.
   - Có thêm chặn ở tầng DB.

Khách vẫn dùng bình thường: tạo link, xem số hoàn dự kiến, đơn vẫn được ghi nhận. Công thức báo giá không đổi.

---

## 2. Các bước đã làm

| # | Bước | Giờ (UTC) | Kết quả |
|---|---|---|---|
| 1 | Kiểm tra trước: `main` sạch, HEAD `eca64fd` | 02:57 | đạt |
| 2 | Backup trước triển khai: `python -m cashback_bot.backup` | 02:57:15 | `cashback-20261024T025715Z.sqlite`, quyền 0600. `verify_backup`: 20 bảng, 29 link, integrity ok |
| 3 | `git merge --ff-only cursor/cashback-safety-hardening` | 02:58 | `main` = `a9bb42a` |
| 4 | Chạy lại test trên `main` | 02:58 | **334 passed**, ruff sạch |
| 5 | `git push origin main` | 02:58 | `origin/main` = `a9bb42a` |
| 6 | Chủ bot restart (`kill -TERM 590993`, `umask 077`, `chmod 600` log và backup cũ, `setsid nohup …`) | 02:58:43 | PID mới **597550** |
| 7 | Migration tự chạy lúc khởi động | 02:58:48 | thêm bảng `failed_updates` và 4 trigger `financial_lock_*` |
| 8 | Backup tự động lần đầu | 02:59:19 | `backup ok file=cashback-20261024T025919Z.sqlite tables=21 links=29` |

---

## 3. Kiểm tra sau triển khai

| Kiểm tra | Cách kiểm | Kết quả |
|---|---|---|
| Bot chạy bản mới | `ps`: PID 597550 khởi động 02:58:43, sau commit `a9bb42a` | ✅ |
| Khởi động sạch | Log: `setMyCommands ok`, `start db=… public=True …`; không ERROR hay Traceback từ sau restart | ✅ |
| Migration | DB (chỉ đọc): có `failed_updates` (0 dòng), có đủ 4 trigger; `quick_check` = ok | ✅ |
| Dữ liệu cũ nguyên vẹn | 29 link, 6 người dùng, 2 khoản `pending` (12.157đ và 960đ), 0 yêu cầu rút | ✅ |
| Backup tự động | File mới 0600, thư mục 0700; `bot_state.backup_last_ok` đã ghi | ✅ |
| Quyền file | `logs/cashback_bot.log` 0600; mọi `cashback-*.sqlite` 0600 | ✅ |
| Khoá tài chính, giao diện | Trên bản sao của backup mới: màn 👛 hiện "🔒 KHOÁ TÀI CHÍNH" và 2 lý do; nút "🔒 Bật ví (đang khoá)" | ✅ |
| Khoá tài chính, nút cũ | `c:wl:on:ok` → "Chưa bật được ví: còn khoá tài chính"; công tắc vẫn 0 | ✅ |
| Khoá tài chính, gọi hàm | `set_enabled(True)` → bị chặn; `request_payout` → `locked` | ✅ |
| Khoá tài chính, SQL trực tiếp | `UPDATE … 'available'` và `INSERT cashback_payouts` → `financial_lock: no settlement evidence` | ✅ |
| Không lộ bí mật | Log: 0 chuỗi dạng token Telegram, 0 giá trị cookie `SPC_*` | ✅ |
| Báo giá không đổi | Không sửa `pricing.py`, `calculator.py`, `money.py`; test V1.1 (70%) và V1.2 pass | ✅ |

Các kiểm tra khoá tài chính chạy trên bản sao (0600, đã xoá ngay), không bấm trên bot thật và không gửi tin Telegram.

**Việc chủ bot nên tự thử thêm trên Telegram:**
- Gửi một link Shopee: bot trả link và số hoàn như trước.
- /admin → 👛 Ví khách: thấy khoá và lý do.
- /admin → 📈 Thống kê vẫn hiển thị bình thường.

---

## 4. Trạng thái hiện tại

| Mảng | Trạng thái |
|---|---|
| Cô lập update lỗi | **ĐANG CHẠY** |
| Log an toàn | **ĐANG CHẠY**; quyền log 0600 |
| Backup tự động | **ĐANG CHẠY**, 24 giờ/lần. Lần kế tiếp khoảng 03:00 UTC 25/10 |
| Backup ngoài máy | **CHƯA CẤU HÌNH** (`OFFSITE_BACKUP = NOT CONFIGURED`) |
| Khoá tài chính | **ĐANG KHOÁ**. Ví tắt, không thể rút hay chi |
| Ví khách / chi trả | **CHƯA ĐƯỢC PHÉP**, và về kỹ thuật cũng không bật được |

---

## 5. Cách quay lại bản cũ (nếu cần)

1. Dừng bot (chủ bot chạy `kill -TERM <PID>`).
2. Trả code: `git revert a9bb42a` trên `main`, push, rồi khởi động lại bot.
3. Bảng `failed_updates` và các trigger để lại không ảnh hưởng code cũ; trigger vẫn tiếp tục chặn chi trả. Gỡ trigger cần chủ bot duyệt riêng.
4. Nếu DB hỏng: khôi phục từ `data/backups/cashback-20261024T025715Z.sqlite` (bản trước triển khai) theo `cashback_bot/BACKUP.md`.

---

## 6. Việc còn lại

**Chủ bot quyết:**
1. Nơi lưu backup ngoài máy, có mã hoá.
2. Giữ bot công khai hay chỉ cho người được mời.

**Trước khi được chi tiền hoàn thật (cần PLAN riêng):**
1. Luồng ghi bằng chứng kỳ Shopee đã trả: chứng từ, người nhập, đối chiếu sao kê.
2. Điều chỉnh âm khi hoa hồng giảm hoặc bị gắn gian lận sau khi tiền đã vào ví.
3. Quyết định thuế người nhận (kế toán, ghi ADR).
4. Quét QR bằng app ngân hàng thật; trần rút mỗi tháng; ghi audit chi trả.

Chi tiết kỹ thuật: `reports/CASHBACK_SAFETY_HARDENING_V1.md`. Audit gốc: `reports/CASHBACK_FULL_AUDIT.md`.
