# Kỳ báo cáo & chênh lệch đang “rối” — giải thích từ DB thật

Thời điểm: 20/11/2026 · Chỉ đọc · `evaluate()` không ghi DB.

## Vì sao anh thấy rối

Hệ thống đang trộn **3 sổ khác nhau**, cộng thêm **3 kỳ cùng nhãn tháng `2026-11`**:

| Sổ | Ý nghĩa | Anh hay nhìn |
|---|---|---|
| A. `settlement_batches` | Từng **lần Shopee chi tiền** (mỗi `payment_ref` = 1 kỳ) | “Kỳ 10 / 11” |
| B. `cashback_entries` | Hoàn khách trên ví bot (`holding` / `available` / `pending`) | “Khách được bao nhiêu” |
| C. `shopee_conversions.settlement_status` | Đơn đã `SETTLED` **chỉ khi** nằm trong kỳ batch **MATCHED** | “Đơn đã đối soát chưa” |

→ Cùng một đơn có thể: item kỳ = MATCHED, nhưng batch = PARTIALLY / EVIDENCE_PENDING → conversion vẫn `NOT_VERIFIED`, entry vẫn `holding`. Trông như “lộn” nhưng đúng rule code.

## Bản đồ 4 kỳ hiện có

| Batch | Nhãn `period` | Payment ref (đuôi) | Status | HH báo cáo | NH nhận | Vì sao status đó |
|---|---|---|---|---:|---:|---|
| **#1** | 2026-10 | …261029 | **MATCHED** | 25.371 | 22.585 | Khớp đủ; có 1đ làm tròn đã gắn adjustment |
| **#2** | 2026-11 | …261102 | **MATCHED** | 18.415 | 16.392 | Khớp đủ |
| **#3** | 2026-11 | …261116 | **PARTIALLY_MATCHED** | 43.413 | 38.646 | Lệch phân bổ **+1 đ** (`UNALLOCATED`) |
| **#4** | 2026-11 | …261119 | **EVIDENCE_PENDING** | 10.655 | *(null)* | Chưa chứng từ NH (`NO_BANK` + `TOTALS_INCOMPLETE`) |

Công thức tiền kỳ (đã kiểm):
`reported − fee − tax = shopee_payout` → **#1 #2 #3 đều đúng số học với ngân hàng**.

## Chênh lệch cụ thể (không phải “mất tiền lớn”)

### Kỳ #3 — rối chính

- 6 đơn item đều `match_status=MATCHED`, tổng `settled` = **43.412**
- `reported_commission` = **43.413**
- → `unallocated = 1` đ → engine gắn **PARTIALLY_MATCHED**
- Hệ quả: `eligible_fund = null`; 6 conversion vẫn `NOT_VERIFIED`; 6 entry vẫn **`holding`** (~24.768 đ hoàn khách bị kẹt vì **1 đ** báo cáo)

Đây là lệch làm tròn / 1đ trên bảng kê, không phải thiếu cả chục nghìn.

### Kỳ #4 — chưa xong hồ sơ

- Đã có statement items (2 đơn, 10.655)
- Chưa có `bank_received` / tax/payout đủ → **EVIDENCE_PENDING**
- Entry vẫn `holding` cho đến khi gắn sao kê NH và kỳ về MATCHED

### Kỳ #1 — đã êm

- Có 1 đơn `adjustment_vnd=1` (1373 duyệt → 1372 settled); allocate tính cả adjustment → unallocated 0 → MATCHED

## Đơn hoàn **không** nằm kỳ nào (8 dòng)

| Loại | Ví dụ | Ý |
|---|---|---|
| HH = 0 | 2 đơn 07/11 | Không có tiền để vào kỳ |
| Chưa vào bảng kê | `2611112QNG7H2A` HH **93.195** / hoàn **49.776** | Đơn lớn đang holding, **chưa** gán batch |
| TikTok `tt:…` | 2 dòng | Không đi settlement Shopee |
| Pending mới | 14/11, 18/11 | Chưa đủ điều kiện / chưa kỳ |

## Liên hệ với báo cáo tiền sáng nay

| Con số anh thấy | Thuộc sổ | Ghi chú |
|---|---|---|
| NH nhận ~77.623 | Kỳ #1+#2+#3 đã có bank | Đúng tiền vào TK |
| Hoàn khách 120.903 | Toàn bộ entry | Gồm holding + available + pending |
| Available 25.910 | Chỉ entry `available` | ≈ đơn thuộc kỳ **#1+#2 MATCHED** |
| Holding ~84.909 | Entry chưa mở ví | Chủ yếu kỳ **#3/#4** + đơn chưa vào kỳ (+ đơn lớn 49.776) |

## Cách đọc cho đỡ rối (đề xuất vận hành)

1. **Đừng nhóm theo `period` tháng** — nhóm theo `batch_id` + đuôi `payment_ref`.
2. Một tháng có thể có **nhiều lần chi** Shopee (#2, #3, #4 đều “2026-11”).
3. `PARTIALLY_MATCHED` vì **1đ** vẫn chặn mở `SETTLED`/holding → cần xử lý lệch 1đ (ghi adjustment / chỉnh reported) rồi `reconcile` lại.
4. `EVIDENCE_PENDING`: thiếu sao kê ngân hàng, chưa phải lệch số đơn.

## Việc có thể làm tiếp (khi anh cho phép — chưa làm)

1. Kỳ #3: ghi nhận lệch **1đ** (adjustment / làm tròn) → `reconcile` → kỳ MATCHED → sync conversion SETTLED → entry holding→available (theo rule ví).
2. Kỳ #4: upload/gắn bank evidence → hoàn tất totals → MATCHED.
3. Đơn lớn `2611112QNG7H2A` (93k HH): theo dõi kỳ Shopee nào sẽ chứa nó.
4. UI/admin: hiện `batch_id` + `payment_ref` thay vì chỉ “Tháng 11”. → **đã làm 20/11 ~10:15** (`_batch_label` trên màn Kỳ thanh toán + Tiền & ví).

## Đánh giá

- Độ tin cậy: **Cao** (evaluate trên DB thật).
- Không sửa dữ liệu trong lượt này.
