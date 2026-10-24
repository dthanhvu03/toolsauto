# Báo cáo triển khai — PLAN-078 Wallet & Payout Readiness V1 (Gate A)

| | |
|---|---|
| Ngày triển khai | 24/10/2026, 14:15–14:19 giờ VN (07:15–07:19 UTC) |
| Người duyệt | Chủ bot ("có phát hành") |
| Người thực hiện | Claude Code (backup, merge, kiểm tra). Chủ bot chạy lệnh restart |
| Phiên bản | `main` `88ebf63` → **`e50afeb`** (PLAN-078, ADR-055) |
| Kết quả | **THÀNH CÔNG (Gate A: code).** Ví và chi trả vẫn khoá. Gate B (mở ví, chi tiền) NOT AUTHORIZED |

---

## 1. Tóm tắt

- Đã có trên production:
  - vòng đời yêu cầu rút 11 bước, có lịch sử chỉ thêm;
  - phân bổ từng đồng về đúng đơn;
  - quỹ có chứng từ (lấy từ kỳ đối soát khớp);
  - lịch sử và xác minh tài khoản ngân hàng;
  - điều kiện chi trả nhiều cấp, trigger mới cho các trạng thái chi tiền.
- **Không có gì được mở.** Production thiếu cả 2 điều kiện cũ lẫn 8/9 điều kiện mới (chỉ đạt điều kiện backup), nên mọi đường rút và chi vẫn bị chặn.
- Khách chỉ thấy câu thông báo ví đóng mới khi mở `/vi`.

---

## 2. Các bước đã làm

| # | Bước | Giờ (UTC) | Kết quả |
|---|---|---|---|
| 1 | Kiểm tra trước: `main` sạch, HEAD `88ebf63`, PID 620902 | 07:15 | đạt |
| 2 | Backup trước triển khai | 07:15:47 | `cashback-20261024T071547Z.sqlite`, 0600. `verify_backup`: 34 bảng, 35 dòng link |
| 3 | `git merge --ff-only cursor/cashback-plan078-payout` | 07:16 | `main` = `e50afeb` |
| 4 | Test trên `main` | 07:18 | **554 passed**, ruff sạch |
| 5 | `git push origin main` | 07:18 | `origin/main` = `e50afeb` |
| 6 | Chủ bot restart | 07:18:41 | PID mới **629793** |
| 7 | Migration lúc khởi động | 07:18:43 | 6 bảng mới, 3 cột, 2 index unique, các trigger; ghi 1 dòng lịch sử tài khoản |

---

## 3. Kiểm tra sau triển khai

DB đọc ở chế độ chỉ đọc. Các màn dựng trên bản sao DB (0600, xoá ngay). Không bấm trên bot thật, không gửi tin.

| Kiểm tra | Kết quả |
|---|---|
| Bot chạy bản mới | ✅ PID 620902 → **629793**, cwd `/home/vu/toolsauto` |
| Khởi động sạch | ✅ 0 ERROR; 0 chuỗi dạng token; 0 dãy số dài giống số tài khoản trong log |
| Bảng mới | ✅ `payout_allocations`, `payout_events`, `bank_account_verifications`, `payout_policy_decisions`, `payout_limit_policies`: 0 dòng; `bank_account_history`: 1 dòng (VCB, 4 số cuối `4544`, `add`) cho tài khoản thử của chủ bot |
| `cashback_payouts` | ✅ thêm cột `version`, `idempotency_key`, `account_sha`; index `uq_payout_idempotency`, `uq_payout_one_open`; 0 yêu cầu |
| Trigger | ✅ 4 `financial_lock_*` cũ còn nguyên; thêm `financial_lock_payout_progress` và `payout_paid_needs_evidence` |
| Không có bảng mở khoá | ✅ không có `shopee_settlements`, `payout_tax_policies` |
| Khoản pending | ✅ 12.157đ (171 / 1.737) và 960đ (14 / 138), `v1.1:70`, `pending` |
| Hoa hồng | ✅ 2 PENDING / NOT_VERIFIED, 1 FRAUD: không đổi |
| Ví | ✅ `wallet_enabled=0`, 0 available, 0 payout. Trên bản sao: bật ví bị chặn; tạo yêu cầu rút trả `locked` |
| Kiểm tra sổ | ✅ không vi phạm bất biến nào |
| Tin gửi đi từ lúc restart | ✅ 0 |
| `quick_check` | ✅ ok |
| Màn 👛 Ví khách (bản sao) | ✅ 2 lý do khoá gốc + "Còn 8 điều kiện chi trả PLAN-078 chưa đạt"; quỹ có chứng từ "Chưa xác minh"; không có nút chi tiền |
| Màn ⚖️ Sẵn sàng chi trả (bản sao) | ✅ ma trận điều kiện: 8 ❌, chỉ backup ✅; quỹ "Chưa xác minh"; kiểm tra sổ "ổn" |
| `/vi` của khách (bản sao) | ✅ "Ví hoàn tiền chưa mở. Các khoản được ghi nhận đang chờ Shopee xác minh và đối soát; chưa thể yêu cầu rút." |

**Chủ bot nên tự xem trên Telegram:** /admin → 👛 Ví khách, và /admin → ⚖️ Sẵn sàng chi trả.

---

## 4. Quay lại bản cũ (nếu cần)

1. Chủ bot dừng bot.
2. `git revert e50afeb` trên `main`, push, khởi động lại. Bảng, cột, index và trigger mới để lại vô hại (trigger chỉ khiến khoá chặt hơn).
3. **Không restore DB** chỉ để quay lại code. Chỉ restore khi DB hỏng, từ `data/backups/cashback-20261024T071547Z.sqlite`, theo `cashback_bot/BACKUP.md`.

---

## 5. Việc tiếp theo (Gate B, chưa được phép)

1. Một kỳ Shopee có báo cáo Thanh toán và sao kê khớp (MATCHED), kèm bằng chứng Shopee duyệt hoa hồng theo đơn.
2. Quyết định của chủ bot về:
   - thuế người nhận (sau khi có câu trả lời của kế toán);
   - chính sách thu hồi;
   - điều khoản chi trả (một phiên bản điều khoản mới);
   - hạn mức;
   - cách xác minh tài khoản;
   - quy trình chuyển khoản và chứng từ cần lưu.
3. Một bước phát hành riêng để ghi các quyết định và mở khoá cũ.
4. Một đợt thử với 1–2 khách, số tiền nhỏ.

Chi tiết kỹ thuật: `reports/CASHBACK_PLAN078_WALLET_PAYOUT.md`, ADR-055.
