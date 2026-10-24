# Báo cáo triển khai — PLAN-076 Cashback Pricing & Policy Consistency V1

| | |
|---|---|
| Ngày triển khai | 24/10/2026, 11:52–11:57 giờ VN (04:52–04:57 UTC) |
| Người duyệt | Chủ bot ("Duyệt phát hành", kèm làm mục 2 và 3) |
| Người thực hiện | Claude Code (backup, merge, kiểm tra). Chủ bot chạy lệnh restart |
| Phiên bản | `main` `a9ff267` → **`810acc5`** (`bfce417` PLAN-076 + `810acc5` bổ sung; ADR-053) |
| Kết quả | **THÀNH CÔNG.** Công thức và số tiền không đổi; ví và chi trả vẫn khoá |

---

## 1. Tóm tắt

- Báo giá, sổ ví, màn admin và 🧮 Mô phỏng dùng **một công thức** (`pricing.cashback_for`).
- **Mỗi link có snapshot chính sách bất biến.** 31 link cũ đã được dựng lại có kiểm chứng: 31 backfilled, 0 unresolved.
- Đổi tỷ lệ, phí, thuế hay `.env` từ nay **chỉ tác động link tạo sau mốc hiệu lực**. Không áp dụng ngược thời gian được nữa.
- Mô phỏng mới:
  - so sánh V1.1 với V1.2;
  - nhập hoa hồng tự do;
  - hiện lịch hẹn và hạng (bản nháp).
- Huỷ được chính sách đã hẹn giờ, chỉ khi chưa tới mốc hiệu lực.
- «Admin còn» có một định nghĩa thống nhất trên mọi màn.
- **Số tiền khách thấy không đổi.** Chỉ đổi chữ ở `/cachtinh`, trang chủ và mô tả bot.

---

## 2. Các bước đã làm

| # | Bước | Giờ (UTC) | Kết quả |
|---|---|---|---|
| 1 | Kiểm tra trước: `main` sạch, HEAD `a9ff267`, PID 604968 | 04:52 | đạt |
| 2 | Backup trước triển khai | 04:52:17 | `cashback-20261024T045217Z.sqlite`, 0600. `verify_backup`: 27 bảng, 32 link |
| 3 | `git merge --ff-only cursor/cashback-plan076-pricing` | 04:53 | `main` = `810acc5` |
| 4 | Test trên `main` | 04:55 | **490 passed**, ruff sạch |
| 5 | `git push origin main` | 04:55 | `origin/main` = `810acc5` |
| 6 | Chủ bot restart | 04:56:23 | PID mới **612405** |
| 7 | Migration và backfill lúc khởi động | 04:56:24 | thêm `link_policy_snapshots`, `policy_cancellations`; log `backfilled=31 unresolved=0` |

---

## 3. Kiểm tra sau triển khai

DB đọc ở chế độ chỉ đọc. Các màn dựng trên bản sao DB (0600, xoá ngay). Không bấm trên bot thật, không gửi tin, không gọi Shopee.

| Kiểm tra | Kết quả |
|---|---|
| Bot chạy bản mới | ✅ PID 612405, cwd `/home/vu/toolsauto`, khởi động sau commit `810acc5` |
| Khởi động sạch | ✅ `setMyCommands`, `setMyDescription`, `setMyShortDescription`, `start db=…`; **0 ERROR/Traceback**; 0 chuỗi dạng token |
| Snapshot | ✅ 27 `v1.1:70` + 4 `v1.2-reserve-2026-10-23+r1`, tất cả `backfilled`; **0 lệch** giữa số đã báo và snapshot |
| Khoản pending | ✅ 12.157đ (phí 171, thuế 1.737) và 960đ (14, 138), `v1.1:70`, `pending`: giống hệt trước |
| Hoa hồng | ✅ 2 đơn PENDING / NOT_VERIFIED, 1 FRAUD: không đổi |
| Chính sách | ✅ `reserve_policies` #1 (0,98% / 10%), `share_policies` trống, 0 lệnh huỷ |
| Trigger | ✅ 4 `financial_lock_*`, 3 settlement, 2 snapshot, 2 huỷ lịch. 4 trigger chỉ-thêm của `share_policies` / `reserve_policies` được tạo ở lần đầu bot mở kết nối admin (lần báo giá hoặc /admin đầu tiên); đã xác nhận trên bản sao |
| Khoá tài chính | ✅ không có bảng mở khoá; `wallet_enabled=0`; 0 available; 0 payout. Trên bản sao: bật ví bị chặn "còn khoá tài chính" |
| Đối soát, cách ly update | ✅ 0 kỳ đối soát, 0 update bị cách ly |
| `quick_check` | ✅ ok |
| Màn 🧮 Mô phỏng | ✅ 100.000đ: V1.2 khách 62.314 · admin còn 26.706; V1.1 70.000 · 19.020. Nhập `1.372` ra cột V1.1 960đ, đúng đơn thật |
| Màn 📊 Lịch sử | ✅ phiên bản chính sách hiện "Mặc định cấu hình 70%", "#1 phí 0,98%, thuế 10% · ĐANG ÁP DỤNG"; "Link đã chốt chính sách: 31 · chưa xác định: 0" |
| Màn 💰 Chính sách | ✅ "Admin còn (sau dự phòng): 26.706đ" kèm định nghĩa. Chưa có lịch hẹn nên chưa có nút huỷ |
| `/cachtinh` | ✅ có "Mỗi link giữ cách tính lúc bot tạo link…" và "Ví hoàn tiền chưa mở, bot chưa chi trả." |

**Chủ bot nên tự xem trên Telegram:**
- /admin → 🧮 Mô phỏng: bấm ✏️ Nhập số khác, gõ thử `150k`;
- /admin → 📊 Lịch sử;
- gửi một link Shopee thử: số trên thẻ phải giống trước.

---

## 4. Quay lại bản cũ (nếu cần)

1. Chủ bot dừng bot.
2. `git revert 810acc5 bfce417` trên `main`, push, khởi động lại.
   - Hai bảng mới và các trigger chỉ-thêm để lại vô hại: code cũ không đọc, không sửa dòng chính sách.
   - Sổ ví sẽ quay về cách tra chính sách theo giờ như trước.
3. **Không restore DB** chỉ để quay lại code. Chỉ restore khi DB hỏng, từ `data/backups/cashback-20261024T045217Z.sqlite`, theo `cashback_bot/BACKUP.md`.

---

## 5. Việc tiếp theo

1. Mẫu chứng từ thật của một kỳ có tiền (báo cáo Thanh toán Shopee Affiliate, sao kê hoặc chứng từ ngân hàng, báo cáo Xác thực), cho parser và APPROVED có chứng từ.
2. Quyết định thuế người nhận và chính sách thu hồi.
3. Sau đó: nối đối soát vào khoá tài chính, mở ví có điều kiện.

Chi tiết kỹ thuật: `reports/CASHBACK_PLAN076_PRICING.md`, ADR-053.
