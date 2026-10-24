# Triển khai PLAN-080 Gate A — Tự đồng bộ Shopee (code), cờ TẮT

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code (merge, kiểm tra); chủ bot (restart, bấm 🔄) |
| Duyệt | Chủ bot: "oke anh duyệt nhé" |
| Code | `main@5232840` |
| Báo cáo PLAN | `reports/CASHBACK_PLAN080_AUTO_SYNC.md`, ADR-057 |
| Kết quả | **Gate A đã triển khai.** Tự đồng bộ **TẮT** (không có `SHOPEE_AUTO_SYNC_*` trong `.env`). Gate B: NOT AUTHORIZED |

## Diễn biến

| Bước | Giờ (UTC) | Nội dung | Kết quả |
|---|---|---|---|
| Backup | 10:21:26 | `data/backups/cashback-20261024T102126Z.sqlite`, quyền 0600 | `verify_backup`: 41 bảng, 35 link |
| Merge | 10:22 | `main` fast-forward `4712c9a` → `5232840` | 648 passed, ruff sạch, đã push |
| Restart | 10:26:34 | Chủ bot restart, PID 652982 | Log: `[ShopeeAutoSync] cấu hình: bật=False chu kỳ=120 phút`, `shopee auto sync enabled=False interval_min=120`. 0 lỗi, 0 `database is locked`, 0 token / cookie trong log. Tiến trình có 2 luồng (poll + đồng bộ) |
| Bấm 🔄 | 10:27:11 | Lượt #10, chạy qua luồng nền | `manual · success`, 2 trang (0 trang lỗi), 2 đơn: 0 mới · 0 đổi · 2 không đổi, 0 tin khách. Khung 2026-09-24 → 2026-10-24. Khoá đã nhả. Tin kết quả cho admin gửi lúc 10:27:13 |

## Trạng thái sau triển khai

- **`shopee_sync_state`:**
  - `enabled=0`, `next_due_at` trống;
  - `last_result=success`, `last_run_id=10`, `consecutive_failures=0`;
  - không có khoá đang giữ.
- **Sự cố:** 0. Không có lượt `auto` mới (lượt `auto` duy nhất là #1 ngày 2026-10-23, khi kết nối cookie lần đầu).
- **Màn ⏱ Tự động đồng bộ** (ảnh chủ bot gửi): "TẮT (chủ bot bật bằng SHOPEE_AUTO_SYNC_ENABLED trong .env)"; phiên Shopee bình thường; lần chạy gần nhất #10, thủ công, thành công, 1 giây, "2 đơn · 0 mới · 0 đổi · tin khách 0"; lỗi liên tiếp 0. Không có nút bật.
- **`gate_b_check` OK:** 2 khoản pending 12.157đ / 960đ; ví 0, available 0, payout 0; trigger 6/6; `quick_check` ok.

## Gate B (chờ duyệt riêng)

1. Bấm 🔄 kiểm tra nguồn ngay trước khi bật.
2. Thêm `SHOPEE_AUTO_SYNC_ENABLED=1` vào `.env`, rồi restart. Lượt tự động đầu tiên chạy sau 5 phút, sau đó mỗi 120 phút.
3. Lượt đầu có thể gửi tin cập nhật thật cho khách nếu Shopee đã có thay đổi so với lượt #10.
4. Theo dõi 24–48 giờ trước khi chốt chu kỳ.

**Tắt:**
- tạm dừng nóng: /admin → 🔗 → ⏱ → ⏸️ Tạm dừng;
- tắt hẳn: xoá dòng `SHOPEE_AUTO_SYNC_ENABLED`, rồi restart.

---

## Gate B — Bật tự đồng bộ (2026-10-24)

Chủ bot tự thêm cấu hình vào `.env` và restart.

| Bước | Giờ (UTC) | Nội dung | Kết quả |
|---|---|---|---|
| Thử lần 1 | 10:31 | `.env` gõ thiếu chữ (`SHOPEE_AUTO_SYNC_ENABL`) | Bot bỏ qua biến lạ; tự đồng bộ vẫn tắt |
| Restart lỗi | 10:33:28 | Lệnh khởi động chạy khi bot cũ chưa dừng | Khoá một tiến trình chặn lại: «another cashback bot process is already running»; bot cũ chạy tiếp |
| Restart đúng | 10:34:28 | `.env`: `SHOPEE_AUTO_SYNC_ENABLED=1`, `SHOPEE_AUTO_SYNC_INTERVAL_MINUTES=240` (chủ bot chọn 4 giờ). PID 654209 | Log: `cấu hình: bật=True chu kỳ=240 phút`; lượt đầu hẹn 10:39:32Z; 0 lỗi |
| Lượt tự động đầu | 10:39:32 | Lượt #11 `auto` | `success`, 1 giây, 2 trang, 0 trang lỗi, 2 đơn: 0 mới · 0 đổi · 2 không đổi, **0 tin khách**, 0 sự cố, khoá đã nhả. Không nhắn admin (đúng thiết kế). Lượt kế: 14:39:33Z (21:39 giờ VN) |

Sau lượt đầu, `gate_b_check` OK: 12.157đ / 960đ, ví 0 / available 0 / payout 0, trigger 6/6. Log 0 lỗi, 0 token / cookie.

**Theo dõi tiếp (24–48 giờ):** tỷ lệ lượt thành công, thời lượng, số tin khách, lỗi phiên, `database is locked`, poll Telegram. Sau đó quyết định giữ 240 phút hay hạ xuống 120.
