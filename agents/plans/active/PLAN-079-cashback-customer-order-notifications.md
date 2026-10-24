# PLAN-079 — Customer Order Tracking & Notifications V1

| | |
|---|---|
| Trạng thái | **CODE READY (Gate A), CHỜ RELEASE REVIEW.** Gate B (bật thông báo đơn) NOT AUTHORIZED |
| Executor | Claude Code (chủ bot giao trực tiếp ngày 2026-10-24) |
| Đầu vào | `main@1b0d145` (production `c4b9b1a`), ADR-051/053/054/055 |
| Nhánh | `cursor/cashback-plan079-notifications`, worktree `/home/vu/toolsauto-cashback-notifications` |
| ADR | ADR-056 |

## Scope
`/donhang` (tổng quan, danh sách phân trang, chi tiết); `/thongbao` (tuỳ chọn từng khách); sự kiện đơn trong transaction ghi đơn; hàng đợi chung có thử lại; cờ `CUSTOMER_NOTIFICATIONS_ENABLED` mặc định tắt; màn admin 🔔 Thông báo khách; số tin khách trong tin kết quả đồng bộ.

**Không làm:** bật thông báo, gửi tin đơn lịch sử, tự đồng bộ Shopee, Membership, ví, payout.

## Proof — Claude Code, 2026-10-24
- Baseline 555 passed. Sau PLAN-079: **588 passed** (+33 `tests/test_cashback_order_notifications.py`; 5 test cũ và 1 helper cập nhật theo trạng thái gửi mới, menu lệnh và nút trang chủ), ruff sạch.
- Diễn tập trên bản sao DB production (0600, đã xoá): ghi lại y hệt 2 đơn → 0 tin; thêm bảng `customer_notification_prefs` và các cột; `/donhang` của 2 khách đúng số (960đ, 12.157đ); khách khác không xem được; ví khoá; integrity ok.
- Báo cáo: `reports/CASHBACK_PLAN079_CUSTOMER_NOTIFICATIONS.md`.
