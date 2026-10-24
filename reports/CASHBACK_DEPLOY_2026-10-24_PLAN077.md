# Báo cáo triển khai — PLAN-077 Customer Terms, Support & Payout Readiness V1

| | |
|---|---|
| Ngày triển khai | 24/10/2026, 13:03–13:06 giờ VN (06:03–06:06 UTC) |
| Người duyệt | Chủ bot ("phát hành đi em") |
| Người thực hiện | Claude Code (backup, merge, kiểm tra). Chủ bot chạy lệnh restart |
| Phiên bản | `main` `cca8f8c` → **`5a14fc1`** (PLAN-077, ADR-054) |
| Kết quả | **THÀNH CÔNG.** Ví và chi trả vẫn khoá; điều khoản V1 chưa công bố |

---

## 1. Tóm tắt

- Khách có thêm **📩 Hỗ trợ** ở trang chủ và lệnh **`/hotro`**: 6 loại yêu cầu, có mã và trạng thái.
- Admin có thêm 3 màn: **📩 Hỗ trợ**, **📋 Điều khoản**, **⚖️ Sẵn sàng chi trả** (chỉ đọc).
- Hệ thống điều khoản theo phiên bản đã chạy, nhưng **chưa có bản nào được công bố**: khách vẫn thấy `/dieukien` cũ. Cờ bắt buộc đồng ý vẫn **tắt**.
- Cổng chi trả chặn link không chứng minh được chính sách. Hiện 33/33 link chứng minh được.
- Dữ liệu tối thiểu: tin không phải link chỉ lưu độ dài; màn admin xem khách che số tài khoản.
- Không đổi công thức tiền hay 2 khoản pending. Không gửi tin cho khách.

---

## 2. Các bước đã làm

| # | Bước | Giờ (UTC) | Kết quả |
|---|---|---|---|
| 1 | Kiểm tra trước: `main` sạch, HEAD `cca8f8c`, PID 615042 | 06:03 | đạt |
| 2 | Backup trước triển khai | 06:03:20 | `cashback-20261024T060320Z.sqlite`, 0600. `verify_backup`: 29 bảng, 34 dòng link |
| 3 | `git merge --ff-only cursor/cashback-plan077-terms` | 06:03 | `main` = `5a14fc1` |
| 4 | Test trên `main` | 06:05 | **521 passed**, ruff sạch |
| 5 | `git push origin main` | 06:05 | `origin/main` = `5a14fc1` |
| 6 | Chủ bot restart | 06:05:53 | PID mới **620902** |
| 7 | Migration lúc khởi động | 06:05:55 | thêm 5 bảng, 13 trigger chỉ-thêm / đóng băng |

---

## 3. Kiểm tra sau triển khai

DB đọc ở chế độ chỉ đọc. Các màn dựng trên bản sao DB (0600, xoá ngay). Không bấm trên bot thật, không gửi tin.

| Kiểm tra | Kết quả |
|---|---|
| Bot chạy bản mới | ✅ PID 612405 → **620902**, cwd `/home/vu/toolsauto` |
| Khởi động sạch | ✅ `setMyCommands` (có `/hotro`), `setMyDescription`, `start db=…`; **0 ERROR**; 0 chuỗi dạng token |
| Bảng mới | ✅ `customer_terms_versions`, `customer_terms_acceptances`, `link_terms_context`, `support_tickets`, `support_ticket_events`: đều **0 dòng** |
| Trigger | ✅ 4 `financial_lock_*` còn nguyên; thêm `terms_*` (đóng băng bản công bố, trạng thái chỉ tiến), `terms_acceptances_*`, `link_terms_context_*`, `support_*` (chỉ thêm, không xoá) |
| Không có bảng mở khoá | ✅ không có `shopee_settlements`, `payout_tax_policies`, `tax_policy_decisions` |
| Link, snapshot | ✅ 33 link (31 backfilled + 2 captured), 0 chưa chứng minh chính sách |
| Khoản pending | ✅ 12.157đ (171 / 1.737) và 960đ (14 / 138), `v1.1:70`, `pending` |
| Hoa hồng | ✅ 2 PENDING / NOT_VERIFIED, 1 FRAUD: không đổi |
| Ví | ✅ `wallet_enabled=0`, 0 available, 0 payout |
| Tin gửi đi từ lúc restart | ✅ 0 (không gửi tin hàng loạt) |
| `quick_check` | ✅ ok |
| Màn khách (bản sao) | ✅ trang chủ có `u:p:support`; `/dieukien` vẫn là trang cũ «Để đơn được ghi nhận»; `/hotro` có 6 danh mục; `terms_required = False` |
| Màn admin (bản sao) | ✅ menu có 📩 Hỗ trợ, 📋 Điều khoản, ⚖️ Sẵn sàng chi trả; mỗi màn mở được |

**Chủ bot nên tự xem trên Telegram:**
- trang chủ bot → 📩 Hỗ trợ (có thể mở thử một yêu cầu, rồi đóng trong /admin → 📩 Hỗ trợ);
- /admin → 📋 Điều khoản → 📝 Tạo bản nháp V1 → đọc từng mục. **Chỉ bấm công bố khi đã duyệt nội dung.**

---

## 4. Quay lại bản cũ (nếu cần)

1. Chủ bot dừng bot.
2. `git revert 5a14fc1` trên `main`, push, khởi động lại. 5 bảng mới để lại vô hại.
3. **Không restore DB** chỉ để quay lại code. Chỉ restore khi DB hỏng, từ `data/backups/cashback-20261024T060320Z.sqlite`, theo `cashback_bot/BACKUP.md`.

---

## 5. Việc tiếp theo (chờ chủ bot)

1. Duyệt nội dung điều khoản V1, rồi tự công bố.
2. Có bật bắt buộc đồng ý không (`CASHBACK_TERMS_REQUIRED`).
3. Thời hạn xử lý hỗ trợ; thời gian lưu dữ liệu; xoay vòng log.
4. Gửi 14 câu hỏi thuế cho kế toán (báo cáo PLAN-077 mục 10.3); xem lại dự phòng 10%.
5. Chính sách khi hoa hồng đã chi bị thu hồi.
6. Chứng từ Shopee thật (thanh toán, sao kê, xác thực).

Chi tiết kỹ thuật: `reports/CASHBACK_PLAN077_TERMS_POLICY.md`, ADR-054.
