# PLAN-080 — Automatic Shopee Sync V1

| | |
|---|---|
| Trạng thái | **Gate A ĐÃ TRIỂN KHAI 2026-10-24** (`5232840`, PID 652982, cờ tắt). **Gate B ĐÃ BẬT 2026-10-24 10:34Z** (chủ bot, chu kỳ 240 phút, PID 654209; lượt tự động #11 thành công). Đang theo dõi 24–48 giờ. Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN080.md` |
| Executor | Claude Code (chủ bot giao trực tiếp ngày 2026-10-24, nội dung PLAN dán trong phiên) |
| Đầu vào | `main@4712c9a`, ADR-056 |
| Nhánh | `cursor/cashback-plan080-auto-sync`, worktree `/home/vu/toolsauto-cashback-notifications` |
| ADR | ADR-057 |

## Scope
Tự đồng bộ Shopee theo lịch, dùng lại đúng pipeline đồng bộ và thông báo hiện có:
- luồng nền duy nhất; khoá một lượt cho cả tay lẫn tự động;
- lịch bền; phân loại lỗi; NEEDS_AUTH; phát hiện trang bất thường (PARTIAL);
- sự cố và cảnh báo admin có chống trùng;
- màn ⏱ Tự động đồng bộ;
- cờ `SHOPEE_AUTO_SYNC_ENABLED` mặc định tắt.

**Không làm:** bật tự đồng bộ production, đổi cookie, đăng nhập Shopee, vượt CAPTCHA, gọi Shopee thật trong test, Membership, ví, payout, đổi Financial Lock, đổi ngưỡng hay mốc kích hoạt của PLAN-079.

## Proof — Claude Code, 2026-10-24
- **Test:** baseline 607 passed. Sau PLAN-080: **648 passed** (+41 `tests/test_cashback_auto_sync.py`; 2 test cũ trong `test_cashback_wallet.py` viết lại theo hành vi mới). Ruff sạch.
- **Diễn tập trên bản sao DB production** (0600, đã xoá):
  - migrate 2 lần không đổi dữ liệu nào (so bằng mã băm), `integrity_check` ok;
  - cờ tắt thì không có việc nào;
  - lượt tay qua Shopee giả phát lại 2 đơn thật: 0 mới, 0 đổi, 0 tin khách.
- **Tương thích ngược:** code `4712c9a` chạy được trên schema mới.
- **Báo cáo:** `reports/CASHBACK_PLAN080_AUTO_SYNC.md`.
