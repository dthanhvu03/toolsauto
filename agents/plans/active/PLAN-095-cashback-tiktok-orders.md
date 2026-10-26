# PLAN-095 — Đồng bộ đơn TikTok Shop (PLAN-085 giai đoạn B)

| | |
|---|---|
| Executor | Claude Code (chủ bot duyệt 2026-10-26: kéo mỗi 2 giờ, báo đơn cho khách như Shopee) |
| Trạng thái | ✅ Đã merge vào main 2026-10-26, chờ chủ bot restart |
| Không đổi | Không đổi cấu trúc DB. Không gán APPROVED / SETTLED. Ví vẫn khoá. Chỉ đọc RioHub (`GET /orders`), không gọi Shopee |

## Cách làm

- `cashback_bot/tiktok_sync.py`:
  - Mỗi dòng RioHub (khoá `order_id` + `sku_id`) thành một dòng `shopee_conversions` mã `tt:<order>:<sku>`, đi qua `record_conversion_snapshot` như đơn Shopee.
  - Ánh xạ: status 1 → PENDING; 2 → COMPLETED (hoa hồng `actual_commission`, `complete_time` = `settled_at_iso`, `time_delivered_iso` hoặc lúc đồng bộ); 3 hoặc `fully_refunded` → CANCELLED (đánh giá REJECTED / order_cancelled).
  - Đánh giá luôn là PENDING (`tiktok_pending` / `tiktok_settled_unverified`), không bao giờ APPROVED. `pit` giữ trong raw_json.
- Chạy trong luồng nền của bot Telegram (`maybe_start` gọi mỗi vòng poll).
  - Mỗi 2 giờ; lỗi thì thử lại sau 15 phút.
  - Mốc lưu ở `bot_state.tiktok_sync_last_end`, chồng lấn 10 phút. Lần đầu kéo 7 ngày.
  - Lỗi RioHub: báo admin `tiktok_sync_<kind>` (chống spam theo loại lỗi sẵn có).
- Dùng chung với Shopee: sổ ví (`refresh_wallet`), thông báo đơn cho khách (`order_notify`), 📦 Đơn hàng của tôi, dashboard, 🎯, 🔍.
- Chữ: `messages.source_text` đổi "Shopee" thành "TikTok" trong tin và màn của đơn `tt:`. Dòng đầu 📦 Đơn hàng đổi thành "Đã ghi nhận N đơn" (bỏ chữ Shopee).
- Đối soát Shopee (`reconciliation.evaluate`) bỏ qua đơn `tt:`, vì đơn TikTok không có trong báo cáo Shopee nên sẽ bị báo vắng giả.
- 🎵 TikTok Shop: số đơn đã ghi và trạng thái đồng bộ gần nhất.

## Còn lại

- Nguồn đối soát tiền TikTok thật (Ví RioHub), để có ngày ví mở cho TikTok.
- Đơn có `pit` khác 0: cách tính hiện trừ dự phòng thuế như Shopee. Nếu gặp đơn có `pit` âm thì xem lại chuyện trừ hai lần.
- Kiểm `sub_id` của bot về đúng trong đơn thật (cần một đơn mua qua link bot).

## Proof

- `pytest tests/test_cashback_*.py`: 820 passed. `ruff check`: sạch.
- `tests/test_cashback_tiktok.py`, thêm 5 test:
  - ghi sổ như Shopee, khớp khách, số hoàn bằng báo giá, tin "TikTok vừa ghi nhận", 📦 "chờ TikTok xác minh";
  - chốt rồi huỷ, không gán SETTLED, ví giữ;
  - lỗi RioHub giữ mốc và thử lại sau 15 phút;
  - chạy nền mỗi 2 giờ;
  - đối soát Shopee bỏ qua đơn TikTok.
