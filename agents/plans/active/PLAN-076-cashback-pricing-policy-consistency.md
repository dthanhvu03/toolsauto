# PLAN-076 — Cashback Pricing & Policy Consistency V1

| | |
|---|---|
| Trạng thái | **CHỦ BOT DUYỆT PHÁT HÀNH 2026-10-24**, kèm «Admin còn», nhập số tự do ở Mô phỏng, huỷ lịch hẹn (đã làm) |
| Executor | Claude Code (chủ bot giao trực tiếp ngày 2026-10-24) |
| Đầu vào | PLAN-073/074/075, `main@a9ff267` (code production `6dc2dd1`), ADR-045/047/048 |
| Nhánh | `cursor/cashback-plan076-pricing`, worktree `/home/vu/toolsauto-cashback-pricing` |
| ADR | ADR-053 |

## Scope
- Một công thức tiền (`pricing.cashback_for`) cho báo giá, sổ ví, màn admin và mô phỏng.
- Snapshot chính sách bất biến cho từng link; backfill link cũ có kiểm chứng.
- Chọn chính sách theo thời điểm hiệu lực, không hồi tố, không lệch quote ↔ snapshot ở mốc chuyển.
- 🧮 Mô phỏng dùng đúng engine, so sánh V1.1/V1.2, hiện lịch hẹn và hạng (bản nháp).
- `/cachtinh` và trang chủ giải thích đúng; 📊 Lịch sử hiện phiên bản chính sách.

**Không làm:** ví, payout, membership, settlement. Không đổi 70%, 0,98%, 10%. Không đổi công thức V1.1 hay V1.2.

## Ràng buộc
Không sửa production, không restart, không đổi `.env`, không gọi Shopee/Telegram thật, không merge/deploy khi chưa được duyệt riêng.

## Proof — Claude Code, 2026-10-24
- Baseline `main@a9ff267`: 412 passed.
- Sau PLAN-076: **456 passed** (412 + 44 trong `tests/test_cashback_pricing_policy.py`), ruff sạch trên phần thay đổi.
- Diễn tập trên bản sao DB production (0600, đã xoá):
  - 31/31 link cũ backfilled (27 V1.1, 4 V1.2 `+r1`), 0 unresolved, 0 lệch quote ↔ snapshot;
  - 2 khoản pending giữ nguyên số (12.157đ và 960đ);
  - chỉ thêm bảng `link_policy_snapshots`;
  - khoá tài chính còn nguyên; `integrity_check` = ok.
- Báo cáo: `reports/CASHBACK_PLAN076_PRICING.md`.

## Bổ sung sau khi duyệt — 2026-10-24
- «Admin còn» một định nghĩa trên mọi màn; nhập hoa hồng tự do ở Mô phỏng (RAM, 10 phút, không ghi DB); huỷ chính sách đã hẹn giờ chỉ trước mốc (`policy_cancellations` chỉ thêm, CHECK chặn hồi tố).
- **490 passed**. Diễn tập lại trên bản sao DB production đạt (mục 21 báo cáo).
