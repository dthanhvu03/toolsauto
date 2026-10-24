# PLAN-081 Gate B — Theo dõi đơn đang chờ khi ra khỏi khung 30 ngày (Phương án B)

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Duyệt | Chủ bot: "anh duyệt" sau Gate A. Áp dụng các đề xuất mục 21 của `reports/CASHBACK_PLAN081_GATE_A_AUDIT.md` |
| Nhánh | `cursor/cashback-plan081-reconciliation`, tách từ `main@4a52f82` |
| ADR | ADR-058 (Accepted cho Phương án B) |
| Trạng thái | **CODE READY**, chưa merge, chưa triển khai. Phương án A (thử nguồn > 30 ngày): **chưa làm**, cần chủ bot xác nhận riêng vì phải gọi Shopee thật |

## Quyết định đã áp dụng
- **Phương án B:** chỉ đọc DB, không gọi Shopee.
- **Ngưỡng:** "sắp ra khung" khi tuổi ≥ 20 ngày; "ngoài khung" khi ≥ 30 ngày (đúng 30×86400 giây); "cần đối soát" khi ≥ 45 ngày, **hoặc** vắng ≥ 2 lượt thành công liên tiếp dù còn trong khung, **hoặc** thiếu giờ mua.
- **Phạm vi:** đơn qua bot (`matched_link_id`) có `validation_status` PENDING / UNKNOWN / NEEDS_REVIEW.
- **"Lần cuối thấy" của dòng cũ:** lấy từ `updated_at`, gắn `last_seen_source='backfill_updated_at'`; màn admin ghi "(suy ra)".
- **Báo admin:**
  - tin tổng hợp tối đa 1 lần / ngày (theo giờ VN), chỉ khi danh sách đổi;
  - tin riêng một lần khi đơn chuyển "cần đối soát", và khi đơn từng ngoài khung được đối soát.

## Thay đổi
| File | Nội dung |
|---|---|
| `cashback_bot/db.py` | Cột `shopee_conversions.last_seen_at / last_seen_run_id / last_seen_source` (chỉ ghi ở đường đồng bộ có mã lượt); backfill có đánh dấu; bảng `conversion_reconciliation`; bảng `conversion_reconciliation_events` chỉ thêm (trigger chặn sửa / xoá) |
| `cashback_bot/reconciliation.py` (mới) | `evaluate()`: nhãn theo tuổi và lượt vắng, sự kiện khi đổi nhãn, cảnh báo admin có chống trùng; `backlog()` cho màn admin |
| `cashback_bot/sync_scheduler.py` | Gọi `evaluate()` sau mỗi lượt (lượt không thành công không tính là vắng); lỗi không làm hỏng lượt |
| `cashback_bot/poller.py` | `_check_reconciliation` mỗi giờ: cập nhật nhãn theo tuổi kể cả khi không có lượt; không gọi Shopee |
| `cashback_bot/admin_reconciliation.py` (mới), `admin_policy.py`, `admin_ui.py` | Màn 🧾 Đơn cần đối soát (chỉ đọc), nút cạnh ⏱ ở 🔗 Shopee Affiliate |
| `tests/test_cashback_reconciliation.py` (mới) | 17 test |

**Không đổi:** `validation_status`, `settlement_status`, sổ ví, payout, Financial Lock, công thức, snapshot, gán Sub ID, ngưỡng / mốc PLAN-079, chu kỳ và khung PLAN-080. Ví, payout và đối soát thanh toán không đọc bảng theo dõi (có test quét mã nguồn).

## Bằng chứng
- **Test:** 666 passed (649 + 17); ruff sạch.

  | Nhóm test matrix Gate A | Test |
  |---|---|
  | 1–7, 23 | biên 19 ngày 23 giờ / 20 / 30 ngày − 1 giây / 30 / 31 / 35 / 45 / 60 / 90 |
  | 8 | mua cũ, Shopee báo muộn |
  | 13–15 | PARTIAL và lỗi không tính vắng |
  | 19 | đánh giá lại cùng lượt không đếm hai lần |
  | 21 | thiếu giờ mua |
  | 22 | backfill có đánh dấu; ghi tay không phải "thấy trong nguồn" |
  | 24–25 | vắng 2 lượt thì cần đối soát; thấy lại thì về bình thường |
  | 9–12 | đơn ngoài khung có dữ liệu thật thì đối soát, báo admin một lần |
  | 26 | tin tổng hợp tối đa mỗi ngày theo giờ VN; cần đối soát báo riêng một lần |
  | 27–31 | không đổi tiền, không tin khách, không available, không payout, lịch PLAN-080 không đổi |
  | khác | sự kiện chỉ thêm; màn admin chỉ đọc, sai quyền, nút giả, trống |

  Các ca chỉ thuộc Phương án A (16–18 khi đọc khung hẹp, 20) chưa áp dụng.
- **Diễn tập trên bản sao DB production** (0600, đã xoá):
  - `migrate()` 2 lần không đổi dữ liệu khác; `integrity_check` ok; 3 đơn có `last_seen_at` từ `updated_at`, nguồn `backfill_updated_at`.
  - Mô phỏng thời gian cho 2 đơn qua bot:

    | Mốc | Nhãn | Tin admin |
    |---|---|---|
    | bây giờ | Đang theo dõi | 0 |
    | 12/11 | Sắp ra khung | 1 tin tổng hợp |
    | 22/11 | Ngoài khung, chưa xác minh | 1 tin tổng hợp |
    | 08/12 | Cần đối soát | 2 tin riêng + 1 tin tổng hợp |

  - Đơn …7156 (không qua bot) không vào danh sách. Tiền, hàng đợi khách, lịch đồng bộ, mốc PLAN-079: không đổi.

## Triển khai (cần chủ bot duyệt)
1. Backup và verify.
2. Merge, test, push.
3. Chủ bot restart.
4. Kiểm tra:
   - log sạch;
   - 🧾 Đơn cần đối soát hiện 2 đơn "Đang theo dõi";
   - sau lượt tự đồng bộ kế tiếp, "lần cuối thấy" hết nhãn "(suy ra)";
   - `gate_b_check` OK.

## Rollback
- Thay đổi chỉ đọc và chỉ thêm. `git revert` rồi restart.
- Cột và bảng mới để lại vô hại; không sửa dữ liệu tiền; không restore DB.

## Còn lại
- Phương án A cần một lần thử nguồn được chủ bot xác nhận riêng.
- Đối soát tay dựa vào chứng từ PLAN-075 (🧾 Đối soát thanh toán). Chưa biết portal xuất chứng từ theo đơn được không.

---

## Phương án A — tra khung hẹp cho đơn đã ra khung (2026-10-24)

**Duyệt:** chủ bot: "có em cho phép thực thi phương án A luôn".

### Lần thử nguồn (1 yêu cầu thật, chỉ đọc, không ghi DB)
- Đơn …7156: mua 2026-09-23 13:43:37Z, **30,91 ngày tuổi** lúc thử.
- Gọi `report/list` với `purchase_time_s/e` = giờ mua ± 60 giây, trang 1, 100 dòng.
- Kết quả:
  - `code=0`, `total_count=1`, 1 checkout;
  - đơn khớp đúng mã (`order_status=COMPLETED`, `is_fraud=1` ở cả 3 món, `conversion_status=3`);
  - không in cookie hay header.
- **Kết luận:** website endpoint nhận khung giờ mua cũ hơn 30 ngày, ít nhất ~31 ngày. 45 / 60 / 90 ngày **chưa chứng minh**; code ghi kết quả từng lần tra nên đơn không bị mất dấu nếu Shopee không trả.

### Thiết kế đã làm
- **Cờ:** `SHOPEE_RECONCILE_LOOKUP_ENABLED` (mặc định **tắt**) và `SHOPEE_RECONCILE_LOOKUP_MAX` (mặc định 10, trong khoảng 1–50).
- **Chạy ở đâu:** trong cùng lượt của `SyncCoordinator` (cùng khoá, heartbeat, `MAX_RUNTIME`), sau phần quét 30 ngày.
- **Mỗi đơn cần tra** (đơn qua bot đang chờ, tuổi 30–180 ngày, chưa tra hôm nay theo giờ VN): 1 yêu cầu `report/list` với giờ mua ± 60 giây. Chỉ ghi đúng đơn đó, qua `record_conversion_snapshot` với `last_seen_source='report_list_narrow'`.
- **Kết quả từng lần tra:** `seen` / `not_returned` / `error:<loại>`, ghi vào `conversion_reconciliation.last_attempt_*` và vào sự kiện chỉ thêm.
- **Lỗi:** lỗi phiên hoặc 429 dừng lượt như phần quét chính (NEEDS_AUTH / lùi lịch).
- **Nhãn:** đơn ngoài khung nhưng tra được trong 48 giờ → `OBSERVED_RECENTLY` ("ngoài khung 30 ngày nhưng bot vẫn tra được trên Shopee"). Shopee có kết luận thật → `RECONCILED`; khách nhận tin cập nhật qua đúng luồng PLAN-079, một lần.
- **Màn 🧾:** hiện "lần tra Shopee gần nhất" và kết quả; câu ghi chú đổi theo cờ.
- **Chi phí:** tối đa N yêu cầu / lượt và 1 yêu cầu / đơn / ngày. Hiện 0 đơn cần tra; từ 2026-11-23 có 2 đơn.

### Bằng chứng
- **Test:** 676 passed (666 + 10 `tests/test_cashback_reconciliation_lookup.py`):
  - cờ tắt thì không tra;
  - tra đúng khung ± 60 giây;
  - 1 lần / ngày;
  - kết luận thật → `RECONCILED`, 1 tin khách qua PLAN-079;
  - Shopee không trả → ghi `not_returned`, không đổi gì;
  - trần N;
  - lỗi phiên dừng lượt và ghi lần tra;
  - đơn trong khung hoặc > 180 ngày không tra;
  - không đổi tiền, không available, không payout;
  - màn admin.

  Ruff sạch.
- **Bản sao DB** (đã xoá): migrate thêm 2 cột, `integrity_check` ok; hôm nay 0 đơn cần tra; ngày 23/11 cần tra đúng 2 đơn qua bot.
