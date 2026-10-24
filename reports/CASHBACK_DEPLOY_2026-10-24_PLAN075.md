# Báo cáo triển khai — PLAN-075 Shopee Settlement & Fund Reconciliation V1

| | |
|---|---|
| Ngày triển khai | 24/10/2026, 10:54–10:58 giờ VN (03:54–03:58 UTC) |
| Người duyệt | Chủ bot (giao PLAN-075, cho phép triển khai phần an toàn) |
| Người thực hiện | Claude Code (backup, merge, kiểm tra). Chủ bot chạy lệnh restart |
| Phiên bản | `main` `5bf2796` → **`6dc2dd1`** (PLAN-075, ADR-052) |
| Kết quả | **THÀNH CÔNG.** Phần ghi chứng cứ và đối soát đã chạy; ví và chi trả vẫn khoá |

---

## 1. Tóm tắt

- Bot đã có **khung đối soát tiền Shopee thật**: ghi nhận kỳ thanh toán, lưu chứng từ có chống trùng, đối chiếu báo cáo Shopee ↔ số học kỳ ↔ tiền ngân hàng, tách tiền đơn qua bot khỏi tiền ngoài bot, ghi điều chỉnh khi Shopee thu hồi hoa hồng.
- Màn mới: /admin → 🔗 Shopee Affiliate → **🧾 Đối soát thanh toán**.
- **Chưa có chứng từ thật nào**, nên mọi số tiền trên màn hiện "Chưa xác minh".
- **APPROVED vẫn bị chặn**, **ví và chi trả vẫn khoá**.
- Công thức báo giá không đổi.

---

## 2. Các bước đã làm

| # | Bước | Giờ (UTC) | Kết quả |
|---|---|---|---|
| 1 | Kiểm tra trước: `main` sạch, HEAD `5bf2796` | 03:54 | đạt |
| 2 | Backup trước triển khai | 03:54:56 | `cashback-20261024T035456Z.sqlite`, 0600. `verify_backup`: 22 bảng, 32 link, integrity ok |
| 3 | `git merge --ff-only cursor/cashback-plan075-settlement` | 03:55 | `main` = `6dc2dd1` |
| 4 | Test trên `main` | 03:56 | **412 passed**, ruff sạch |
| 5 | `git push origin main` | 03:56 | `origin/main` = `6dc2dd1` |
| 6 | Chủ bot restart (`kill -TERM 601747`, `umask 077`, `setsid nohup …`) | 03:57:20 | PID mới **604968** |
| 7 | Migration tự chạy lúc khởi động | 03:57:25 | thêm 5 bảng `settlement_*` và 3 trigger chỉ-thêm |

---

## 3. Kiểm tra sau triển khai

| Kiểm tra | Kết quả |
|---|---|
| Bot chạy bản mới | ✅ PID 604968 khởi động 03:57:20, sau commit `6dc2dd1` |
| Khởi động sạch | ✅ `setMyCommands ok` … `start db=…`; **0 ERROR/Traceback** từ sau restart |
| Schema | ✅ đủ 5 bảng `settlement_adjustments/audit/batches/evidence/items` (đang trống); trigger `settlement_audit_no_update`, `settlement_audit_no_delete`, `settlement_evidence_no_delete`; `quick_check` = ok |
| Khoá tài chính | ✅ 4 trigger `financial_lock_*` còn nguyên; **không có** `shopee_settlements` / `payout_tax_policies`; `wallet_enabled=0`. Trên bản sao: nút bật ví bị từ chối "còn khoá tài chính" |
| Không tạo nghĩa vụ chi | ✅ 0 khoản `available`, 0 yêu cầu rút |
| Dữ liệu cũ | ✅ 32 link; 2 đơn bot PENDING / NOT_VERIFIED (18.740đ); đơn 23/09 FRAUD; sổ ví 2 khoản `pending` (13.117đ); 0 update bị cách ly |
| Màn 🧾 Đối soát thanh toán | ✅ trên bản sao DB vừa chạy: "Chưa có kỳ thanh toán nào được nhập", mọi số tiền "Chưa xác minh" (không hiện 0đ), có hướng dẫn nhập chứng từ |
| Màn 🧾 Duyệt hoa hồng (PLAN-074) | ✅ vẫn hoạt động (2 chờ xác minh) |
| Log không lộ bí mật | ✅ 0 chuỗi dạng token |

Các kiểm tra màn hình và khoá ví chạy trên bản sao DB (0600, đã xoá ngay), không bấm trên bot thật, không gửi tin Telegram, không gọi Shopee. Thư mục chứng cứ `data/settlement_evidence/` sẽ được tạo (0700) ở lần nhập chứng từ đầu tiên.

**Chủ bot nên tự xem trên Telegram:** /admin → 🔗 Shopee Affiliate → 🧾 Đối soát thanh toán. Bấm 🔄 Đồng bộ như thường lệ cũng được: đồng bộ giờ còn tự quét điều chỉnh, hiện chưa có kỳ nào nên không phát sinh gì.

---

## 4. Trạng thái các phần

| Phần | Trạng thái |
|---|---|
| **Đã code và test** | schema 5 bảng, engine đối soát, phân bổ quỹ, điều chỉnh, công cụ nhập `settlement_import`, màn admin (412 test) |
| **Đã triển khai production** | tất cả phần trên, tại `6dc2dd1` |
| **Chưa xác minh được** | định dạng thật của báo cáo Shopee và sao kê; quy tắc thuế người nhận |
| **Đang bị chặn bởi nguồn chứng cứ** | APPROVED; parser đọc file Shopee thật |
| **Không được phép** | bật ví, chi trả |

---

## 5. Quay lại bản cũ (nếu cần)

1. Chủ bot dừng bot.
2. `git revert 6dc2dd1` trên `main`, push, rồi khởi động lại. Năm bảng mới để lại không ảnh hưởng code cũ; trigger khoá không bị đụng.
3. **Không restore DB** chỉ để quay lại code (sẽ mất link và dữ liệu mới). Chỉ restore khi DB hỏng, từ `data/backups/cashback-20261024T035456Z.sqlite` theo `cashback_bot/BACKUP.md`.

---

## 6. Việc tiếp theo

1. **Chủ bot gửi chứng từ thật** của một kỳ đã có tiền: báo cáo Thanh toán Shopee Affiliate, sao kê/chứng từ ngân hàng của khoản Shopee chuyển, và nếu có, báo cáo Xác thực hoa hồng. Có thể che số tài khoản.
2. Từ mẫu đó: **PLAN-076/077**, gồm parser đọc file thật và cơ chế APPROVED có chứng từ.
3. Chủ bot quyết định thuế người nhận và chính sách khi Shopee thu hồi hoa hồng đã chi.
4. **PLAN-078**: nối đối soát vào khoá tài chính, mở ví có điều kiện.

Chi tiết kỹ thuật: `reports/CASHBACK_PLAN075_SETTLEMENT.md`.
