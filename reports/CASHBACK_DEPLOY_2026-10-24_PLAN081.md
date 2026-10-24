# Triển khai PLAN-081 (Phương án B + A) và sửa link ShopeeFood

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code (merge, kiểm tra); chủ bot (restart) |
| Duyệt | Chủ bot: "triển khai pa B đi em, có em cho phép thực thi phương án A luôn"; link ShopeeFood: "lỗi này em" |
| Code | `main@8de3bd3` (`ea1359c` Phương án B, `c31368f` Phương án A, `8de3bd3` ShopeeFood) |
| Báo cáo PLAN | `reports/CASHBACK_PLAN081_GATE_B.md`, ADR-058 (Accepted) |
| Kết quả | **Đã triển khai.** Theo dõi đơn quá 30 ngày đang chạy. Phương án A **TẮT** (không có `SHOPEE_RECONCILE_LOOKUP_ENABLED` trong `.env`) |

## Diễn biến

| Bước | Giờ (UTC) | Nội dung | Kết quả |
|---|---|---|---|
| Backup | 11:26:13 | `data/backups/cashback-20261024T112613Z.sqlite`, quyền 0600 | `verify_backup`: 43 bảng, 37 link |
| Merge B | 11:21 | `ea1359c` | 666 passed, ruff sạch, đã push |
| Thử nguồn | ~11:30 | 1 yêu cầu `report/list`, giờ mua ± 60 giây của đơn …7156 (30,91 ngày) | `code=0`, 1 dòng khớp. Không ghi DB, không in cookie |
| Merge A | 11:40 | `c31368f` | 676 passed, ruff sạch, đã push |
| Merge ShopeeFood | 11:51 | `8de3bd3` | 677 passed, ruff sạch, đã push |
| Restart | 13:56:22 | Chủ bot restart, PID 675442 | Log: `shopee auto sync enabled=True interval_min=240 reconcile_lookup=False max=10`. 0 lỗi sau khởi động |
| Đánh giá đầu | ~13:57 | `_check_reconciliation` ở vòng lặp đầu | 2 đơn qua bot → `OBSERVED_RECENTLY` (`seen`), 2 sự kiện. 0 tin admin (đúng: chưa có đơn cần chú ý) |

Lưu ý: bản backup có trước lúc migrate 2,5 giờ. Trong khoảng đó, bot bản cũ vẫn ghi dữ liệu.

## Trạng thái sau triển khai

- **Bảng mới:** `conversion_reconciliation` và `conversion_reconciliation_events` đã có, 2 trigger chặn sửa / xoá sự kiện.
- **Đơn theo dõi:**
  - …0309 và …0025: mua ngày 23/10;
  - `last_seen_source=backfill_updated_at` (màn 🧾 ghi "(suy ra)"), sẽ hết nhãn này sau lượt tự đồng bộ kế tiếp (`next_due_at` 14:39:33Z).
- **`gate_b_check` OK:**
  - 2 khoản pending 12.157đ / 960đ;
  - ví 0, available 0, payout 0;
  - trigger khoá 6/6;
  - `quick_check` ok.
- **Tiền và ví:** không đổi. Không có tin khách mới.

## Còn chờ

1. Chủ bot gửi lại link `spf.shopee.vn`, phải nhận tin "🍜 Đây là link ShopeeFood".
2. Sau lượt tự đồng bộ 14:39Z, "lần cuối bot thấy" hết nhãn "(suy ra)" (nguồn `report_list_30d`).
3. **Mốc:**
   - 2026-11-12: 2 đơn chuyển "🟡 Sắp ra khung";
   - 2026-11-22: 2 đơn chuyển "🟠 Ngoài khung";
   - từ 2026-11-23, Phương án A (nếu bật) bắt đầu tra lại.

## Bật / tắt Phương án A

- **Bật:** thêm `SHOPEE_RECONCILE_LOOKUP_ENABLED=1` vào `.env`, rồi restart. Trước 2026-11-22, bật cũng không thêm yêu cầu nào tới Shopee.
- **Tắt:** xoá dòng đó, rồi restart. Theo dõi (Phương án B) vẫn chạy.
