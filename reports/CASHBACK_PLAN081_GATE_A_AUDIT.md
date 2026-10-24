# PLAN-081 Gate A — Đối soát vòng đời đơn Shopee quá 30 ngày: Audit

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Loại | Gate A: audit đọc code, truy vấn DB chỉ đọc (`mode=ro`), đọc tài liệu có sẵn trong repo. **Không** sửa code, không migration, không gọi Shopee, không đổi `.env`, không restart |
| ADR | ADR-058 (DRAFT, chưa duyệt) |
| Kết luận | **Gate A: GO** (audit xong). **Gate B: NOT AUTHORIZED**, chờ chủ bot chọn phương án (mục 21) |

Nhãn bằng chứng dùng trong báo cáo:

| Nhãn | Nghĩa |
|---|---|
| **[CODE]** | chứng minh bằng mã nguồn |
| **[PROD]** | truy vấn DB / log production chỉ đọc |
| **[DOC]** | tài liệu Shopee đã đọc và ghi trong repo |
| **[CHƯA XÁC MINH]** | chưa có bằng chứng |

---

## 1. Executive Summary

- **Bot chỉ quét đơn mua trong 30 ngày gần nhất [CODE].**
  - Mỗi lượt đồng bộ (tay và tự động) gọi `/api/v3/report/list` với `purchase_time_s = bây giờ − 30×86400` và `purchase_time_e = bây giờ`;
  - `days_back=30` cố định, bộ lập lịch PLAN-080 không truyền giá trị khác.
- **Đơn ra ngoài khung thì không bao giờ được đọc lại, và không có gì đánh dấu việc này. Production đã có ví dụ thật [PROD]:**
  - đơn …7156 (không qua bot, Shopee gắn gian lận) mua 2026-09-23 13:43 UTC;
  - lần cuối bot thấy đơn này là lượt #3 (2026-10-23 11:45 UTC); từ lượt #4 tới #11 đơn không còn trong kết quả;
  - DB vẫn giữ đơn với trạng thái cũ, không có dấu hiệu nào cho biết bot đã "mất dấu" nó.
- **Hai đơn qua bot (12.157đ và 960đ) sẽ ra khỏi khung vào 2026-11-22**, khoảng 08:48 và 10:29 giờ Việt Nam [PROD]. Shopee chưa trả tháng dự kiến xác minh cho hai đơn này: `estimate_validation_month` đang rỗng.
- **Chưa có bằng chứng** website endpoint chấp nhận khung > 30 ngày, hay có cách tra theo mã đơn [CHƯA XÁC MINH].
  - Bot chưa từng gọi khung khác 30 ngày.
  - Response không có trường thời gian cập nhật, nên không lọc được theo ngày cập nhật.
  - Open API của Shopee có `conversionReport` với khung 3 tháng và `validatedReport` theo `validationId` [DOC], nhưng dự án **không có App ID / Secret**, nên không dùng được.
- **Khuyến nghị:**
  1. Làm **Phương án B (theo dõi và đối soát có kiểm soát)** trước ngày **2026-11-12**, khi hai đơn bắt đầu "sắp ra khung" theo đề xuất ngưỡng 20 ngày.
  2. Song song, xin chủ bot duyệt **một lần thử nguồn có kiểm soát** (mục 5.4) để biết Phương án A có khả thi không.
  3. Không tự mở rộng khung quét.

---

## 2. Production Baseline (xác minh lại 2026-10-24 ~11:00 UTC)

| Mục | Giá trị | Nguồn |
|---|---|---|
| Git | `main@4f4a701` (sửa nhãn lịch sử, sau `5232840`); working tree sạch | [PROD] |
| Bot | PID 656347, khởi động 10:50:30 UTC; log `shopee auto sync enabled=True interval_min=240` | [PROD] |
| `.env` (chỉ tên biến) | `CUSTOMER_NOTIFICATIONS_ENABLED`, `SHOPEE_AUTO_SYNC_ENABLED`, `SHOPEE_AUTO_SYNC_INTERVAL_MINUTES` | [PROD] |
| Lịch tự đồng bộ | bật, 240 phút, lượt kế 14:39:33Z, `last_result=success`, 0 lỗi liên tiếp, 0 sự cố | [PROD] |
| Lượt gần nhất | #10 thủ công, #11 tự động: success, 2 trang, 2 đơn không đổi, 0 tin khách; khung 2026-09-24 → 2026-10-24 | [PROD] |
| Đơn trong DB | 3 (2 qua bot, 1 không qua bot) | [PROD] |
| Sổ ví | 2 `pending`: 12.157đ, 960đ; 0 available; 0 payout; ví tắt; 6 trigger khoá | [PROD] |
| Lịch sử thay đổi đơn | 0 dòng `shopee_conversion_changes` | [PROD] |
| Đối soát thanh toán | chưa có kỳ nào | [PROD] |

---

## 3. Current Shopee Sync Architecture

```
SyncWorker (luồng nền, PLAN-080)
→ SyncCoordinator.run(trigger)          sync_scheduler.py:291–318   (khoá DB, không truyền days_back)
→ ShopeeSyncEngine.sync(days_back=30)   shopee_sync.py:229–232
   → khung giờ mua: [now − 30 ngày, now] shopee_sync.py:291–292
   → _paged(fetch_conversions)          shopee_sync.py:110         (PAGE_SIZE 100, MAX_PAGES 20)
   → _process_order_item                shopee_sync.py:486
   → record_conversion_snapshot         db.py:1550                 (updated_at = now; evidence_ref = sync_run:<id>)
      → hook PLAN-079 (thông báo khách) trong cùng transaction
→ _finish (đóng lượt, lịch, nhả khoá)    sync_scheduler.py:329
```

---

## 4. 30-Day Query Window Audit (A1–A10)

| # | Câu hỏi | Trả lời | Bằng chứng |
|---|---|---|---|
| A1 | Khung thời gian lấy dữ liệu? | 30 ngày tính tới thời điểm chạy, cho cả click lẫn đơn | [CODE] `shopee_sync.py:232` (`days_back: int = 30`), `:291–292`. Bộ điều phối không truyền `days_back`: `sync_scheduler.py:302` |
| A2 | Theo trường nào? | **`purchase_time`** (giờ mua) cho đơn; `click_time` cho click | [CODE] `shopee_client.py:239–240` (`purchase_time_s/e`), `:223` (`click_time_s`). [DOC] PLAN-065 mục kiểm thật 2026-10-23 |
| A3 | Đầu và cuối khung tính thế nào? | `end = int(now)` (unix giây, UTC); `start = end − 30×86400`. Mốc lăn theo từng giây: đơn mua lúc T rơi khỏi khung khi now > T + 30 ngày | [CODE] `shopee_sync.py:291–292`; khung lưu ở `shopee_sync_runs.window_start/end` |
| A4 | 30 ngày là giới hạn API hay lựa chọn của code? | **Lựa chọn của code.** Không có tài liệu nào về giới hạn khung của website endpoint | [CODE] giá trị mặc định; [CHƯA XÁC MINH] giới hạn thật của `/api/v3/report/list` |
| A5 | Cùng endpoint có truy vấn quá 30 ngày được không? | **Chưa biết.** Bot và các POC trước chưa từng gọi khung khác | [CHƯA XÁC MINH] |
| A6 | Có endpoint tra theo Order ID / Conversion ID không? | Website: không biết có. Response chỉ có `checkout_id`, `orders[].order_id/order_sn`, không thấy tham số lọc theo mã. Open API: `validatedReport(validationId)` lọc theo **mã kỳ xác minh**, không theo mã đơn; `conversionReport` lọc theo `purchaseTime` trong 3 tháng | [DOC] `experiments/shopee_open_api_discovery/REPORT.md:24–29, 140`. Không có App ID / Secret: cùng file `:100–105`, và memory dự án |
| A7 | Có lưu lần cuối thấy đơn không? | **Không có cột riêng.** Có hai giá trị gần nghĩa: `shopee_conversions.updated_at` (ghi mỗi lần lượt đồng bộ thấy đơn, kể cả không đổi) và `evidence_ref = sync_run:<id>` (mã lượt gần nhất thấy đơn). Không đường ghi nào khác đụng `updated_at`, nhưng tên cột không nói đúng nghĩa, và `evidence_ref` cũng là trường chứng cứ | [CODE] `db.py:1645` (`"updated_at": now`), `:1655` (`evidence_ref`); các đường ghi khác không đụng `updated_at`: `settlement.py:479`, `db.py:746, 1711` |
| A8 | Phân biệt "không xuất hiện" với "Shopee huỷ"? | Không có logic nào đánh dấu đơn vắng mặt. Đơn vắng mặt **giữ nguyên trạng thái cũ** (không bị đổi thành huỷ), nhưng cũng không có tín hiệu "mất dấu" | [CODE] engine chỉ ghi đơn có trong response; [PROD] đơn …7156 |
| A9 | PARTIAL có đánh dấu sai đơn cũ không? | Không. PARTIAL chỉ ghi vào lượt (`shopee_sync_runs`) và lịch; không sửa đơn nào | [CODE] `sync_scheduler.py:329–370`; test PLAN-080 `test_33_34_36` |
| A10 | Shopee cập nhật đơn sau ngày thứ 35, bot có thấy không? | **Không**, với code hiện tại: đơn mua trước now − 30 ngày không nằm trong response | [CODE] A1–A3; [PROD] …7156 vắng từ lượt #4 |

**Thêm: `data.total_count` có trong response nhưng code không dùng** [DOC] `experiments/shopee_conversion_v2/SCHEMA_MAPPING.md:52`; [CODE] không có `total_count` trong `cashback_bot/`. Nếu dùng được, có thể đối chiếu số dòng đọc được với tổng Shopee báo.

---

## 5. Shopee Source Capability

### 5.1 Hiện trạng nguồn

| Nguồn | Quyền | Khung / lọc | Tra theo mã | Trạng thái |
|---|---|---|---|---|
| Website `/api/v3/report/list` (cookie) | Có, đang dùng | `purchase_time_s/e`; giới hạn tối đa chưa biết | Không biết có | 30 ngày: [PROD] đã chạy 11 lượt. > 30 ngày: [CHƯA XÁC MINH] |
| Open API `conversionReport` | **Không** (thiếu App ID / Secret) | `purchaseTime`, khung 3 tháng, `scrollId` | Không | [DOC], không dùng được |
| Open API `validatedReport` | **Không** | `validationId` (từ Billing) | Theo kỳ xác minh | [DOC], không dùng được |
| Màn Conversion Report trên portal (người dùng xem tay) | Có (chủ bot đăng nhập) | Theo giao diện; khung tối đa chưa biết | Tìm theo mã trên giao diện: chưa biết | [CHƯA XÁC MINH] |
| Xuất file từ portal / màn Billing | Có thể có | — | — | [CHƯA XÁC MINH] định dạng |

### 5.2 Phương án A — mở rộng khung truy vấn
- **Chưa được phép mặc định.** Không có tài liệu về giới hạn khung của website endpoint.
- **Nếu Shopee chấp nhận,** cách ít tốn yêu cầu nhất là **khung hẹp quanh giờ mua của từng đơn còn chờ**, thay vì quét lại cả 60–90 ngày. Ví dụ `[purchase_time − 60 giây, purchase_time + 60 giây]` cho mỗi đơn qua bot đang chờ mà đã ngoài 30 ngày.
  - Mỗi đơn tốn 1 yêu cầu, tối đa 1 lần/ngày.
  - Đây vẫn là cùng endpoint, cùng tham số, chỉ đổi giá trị. Không đoán endpoint mới.
- **Quét lại cả khung 60–90 ngày** thì số trang tăng theo tổng đơn của tài khoản (kể cả đơn không qua bot), và tốn thời gian của lượt.

### 5.3 Phương án B — tra cứu từng đơn
- Không có cơ chế tra theo mã nào đã được chứng minh trên website. Không thử endpoint không có căn cứ.
- Khung hẹp theo giờ mua (5.2) là cách gần nhất với "tra một đơn" mà vẫn dùng đúng endpoint đã biết.

### 5.4 Đề xuất kiểm chứng nguồn (cần chủ bot duyệt, không làm ở Gate A)
- **Một lần thử chỉ đọc**, qua client hiện có:
  - gọi `report/list` với khung hẹp quanh giờ mua của đơn …7156 (mua 2026-09-23, hiện 31 ngày tuổi), 1 trang, `page_size` 100;
  - không ghi DB, không qua engine, không gửi tin.
- **Kết quả cho biết:**
  - Shopee có chấp nhận khung cũ hơn 30 ngày không: trả đơn, hay trả lỗi / danh sách rỗng;
  - dữ liệu trả về có đủ trường để xác minh không.
- **Lưu ý:** lần thử là 1 yêu cầu thật tới Shopee, có tính vào giới hạn tần suất. Kết quả của một lần thử không chứng minh cho mọi khung tuổi (45, 60, 90 ngày).

### 5.5 Phương án C — đối soát qua báo cáo Shopee
- Hạ tầng sẵn có: PLAN-075 đã có `settlement_evidence` / `settlement_batches` / `settlement_items` để nhập chứng từ kỳ thanh toán, đối chiếu theo đơn và có trigger chỉ thêm.
- Chưa biết portal xuất được file theo đơn với trạng thái xác minh hay không [CHƯA XÁC MINH].
- Nếu có, nhập theo đúng luồng PLAN-075: có chứng từ, có hash, có người duyệt. **Không** gán APPROVED chỉ vì file ghi "hoàn thành".

### 5.6 Phương án D — cảnh báo, chưa điều chỉnh
Phương án an toàn tối thiểu, gộp trong Phương án B (mục 12).

---

## 6. Database Fields Audit [PROD]

| Cần | Có trong DB? | Cột / ghi chú |
|---|---|---|
| Conversion ID | Có | `shopee_conversions.conversion_id` (PK) |
| Shopee Order ID / SN | Có | `order_sn`; `order_id` chỉ trong `raw_json` |
| Matched Link ID | Có | `matched_link_id` |
| Sub ID | Có | `sub_id` |
| Purchase Time | Có | `purchase_time` (ISO UTC) |
| First Seen | Gần nghĩa | `created_at` = lần đầu bot ghi đơn |
| Last Seen | **Không có cột riêng** | Gần nghĩa: `updated_at` (ghi mỗi lần lượt đồng bộ thấy đơn), `evidence_ref = sync_run:<id>`. Không dùng thay `last_seen_at` khi chưa được duyệt (mục 9) |
| Last Snapshot | Có | `raw_json` (bản gần nhất) |
| Order Status | Có | `order_status`, `checkout_status` |
| Validation Status | Có | `validation_status`, `validation_reason`, `validation_source`, `validation_confidence` |
| Settlement Status | Có | `settlement_status` (chỉ PLAN-075 ghi) |
| Commission | Có | `gross_commission_vnd`, `net_commission_vnd`, `first_commission_vnd` |
| Tháng dự kiến xác minh | Có cột, đang rỗng | `validation_month`; trong `raw_json`: `report_payment_validation_info` (validation_cycle 0, estimate_validation_month "", period_start/end 0) cho cả 3 đơn |
| Cashback Snapshot | Có | `link_policy_snapshots` (PLAN-076); số trong sổ ví `cashback_entries.cashback_vnd` |
| Conversion Change History | Có | `shopee_conversion_changes` (0 dòng) |
| Last reconciliation attempt | **Không có** | — |

---

## 7. Pending Orders Aging Report [PROD]

Mốc tính tuổi: 2026-10-24 11:00 UTC, theo `purchase_time`.

| Tuổi đơn theo ngày mua | Tổng đơn | Qua bot | Đang chờ xác minh HH | Đã có kết luận HH | Không rõ |
|---|---:|---:|---:|---:|---:|
| 0–20 ngày | 2 | 2 | 2 | 0 | 0 |
| 21–29 ngày | 0 | 0 | 0 | 0 | 0 |
| 30–44 ngày | 1 | 0 | 0 | 1 (FRAUD) | 0 |
| 45–59 ngày | 0 | 0 | 0 | 0 | 0 |
| Từ 60 ngày | 0 | 0 | 0 | 0 | 0 |

**Ba chiều tách riêng:**

| Đơn (4 số cuối) | Qua bot | Trạng thái đơn | Xác minh hoa hồng | Shopee thanh toán | Sổ ví | Tuổi |
|---|---|---|---|---|---|---|
| …0309 | có | UNPAID | PENDING | NOT_VERIFIED | pending 12.157đ | 1 ngày |
| …0025 | có | PAID | PENDING | NOT_VERIFIED | pending 960đ | 1 ngày |
| …7156 | không | COMPLETED | FRAUD | NOT_VERIFIED | — | 30 ngày |

| Chỉ số | Giá trị |
|---|---|
| `pending_total` (xác minh HH đang chờ, qua bot) | 2 |
| `pending_age_ge_20d` / `ge_30d` / `ge_45d` / `ge_60d` | 0 / 0 / 0 / 0 |
| `stale_pending` (đơn chờ, không được thấy trong lượt thành công gần nhất) | 0 |
| `unresolved` (đơn chờ đã ngoài khung) | 0 |
| `last_observed_at` của 2 đơn qua bot (theo `updated_at`) | 2026-10-24T10:39:33Z (lượt #11) |
| `last_reconcile_attempt_at` | không có cơ chế |

**Lịch dự kiến của hai đơn qua bot** (nếu Shopee chưa đổi trạng thái):

| Đơn | Sắp ra khung (tuổi 20 ngày, đề xuất) | Ra khung 30 ngày |
|---|---|---|
| …0025 | 2026-11-12 | 2026-11-22 01:48 UTC (08:48 giờ VN) |
| …0309 | 2026-11-12 | 2026-11-22 03:29 UTC (10:29 giờ VN) |

Không tạo số liệu giả. Các khung 21–29 / 45+ hiện bằng 0 trên production; chúng được thiết kế cho test Gate B (mục 18).

---

## 8. Last Seen vs Purchase Time [PROD]

| Đơn | Mua | Lần đầu ghi (`created_at`) | Lần cuối thấy (`updated_at`) | Mã lượt gần nhất (`evidence_ref`) | Ghi chú |
|---|---|---|---|---|---|
| …7156 | 2026-09-23 13:43 | 2026-10-23 11:45 (lượt #3) | **2026-10-23 11:45** | trống (code lúc đó chưa ghi) | Khung lượt #4 bắt đầu 2026-09-24 01:44 > giờ mua, nên **vắng từ lượt #4 tới #11** |
| …0025 | 2026-10-23 01:48 | 2026-10-24 01:44 (lượt #4) | 2026-10-24 10:39 | `sync_run:11` | Thấy ở mọi lượt |
| …0309 | 2026-10-23 03:29 | 2026-10-24 01:44 (lượt #4) | 2026-10-24 10:39 | `sync_run:11` | Thấy ở mọi lượt |

Cách nhận ra đơn "mất dấu" bằng dữ liệu hiện có (chỉ để audit, chưa đề xuất dùng làm nguồn chính thức):

```
lượt thành công gần nhất có window_start > purchase_time
và updated_at < last_success_at
```

---

## 9. Missing Data & Observability Gaps

1. **Không có `last_seen_at` / `last_seen_run_id` riêng.** `updated_at` đang mang nghĩa đó do cách code ghi, nhưng sau này bất kỳ thay đổi nào ghi `updated_at` (ví dụ admin sửa một trường) sẽ làm sai "lần cuối thấy". `evidence_ref` lẫn với nghĩa "chứng cứ".
2. **Không có trạng thái theo dõi** (sắp ra khung, đã ra khung, cần đối soát, đã đối soát).
3. **Không có lần thử đối soát** (thời điểm, kết quả, lý do).
4. **Không dùng `total_count`** để đối chiếu đủ / thiếu dòng.
5. **`days_back` cố định 30,** không cấu hình được và không ghi lý do.
6. **Tháng dự kiến xác minh rỗng** ở cả 3 đơn, nên chưa ước được bao giờ Shopee duyệt.
7. **Màn admin không cảnh báo** đơn đang chờ mà sắp hoặc đã ra khung quét.

---

## 10. Reconciliation Backlog Proposal (đặc tả, chưa tạo bảng)

**Nguyên tắc:** lớp theo dõi **tách riêng**, không ghi vào `validation_status`, `settlement_status` hay `cashback_entries.status`.

**Trường quan sát** (ghi bởi `record_conversion_snapshot`, chỉ ở đường đồng bộ):

| Trường | Nghĩa |
|---|---|
| `last_seen_at` | lần cuối đơn có trong response của một lượt |
| `last_seen_run_id` | mã lượt đó |
| `last_seen_source` | `report_list_30d` / `report_list_narrow` / `evidence_import` |

**Bảng `conversion_reconciliation`**, mỗi đơn qua bot đang chờ một dòng hiện tại:

| Trường | Nghĩa |
|---|---|
| `conversion_id`, `order_ref_masked` | đơn (mã che 4 số cuối) |
| `purchase_time`, `age_days` | tính khi đọc |
| `last_seen_at`, `last_attempt_at`, `last_attempt_result` | `seen` / `not_returned` / `error:<category>` / `skipped` |
| `order_status`, `validation_status`, `settlement_status`, `last_commission_vnd` | bản sao để hiển thị, không phải nguồn |
| `provenance` | nguồn của lần thấy gần nhất |
| `tracking_status` | `OBSERVED_RECENTLY` / `APPROACHING_WINDOW` / `OUTSIDE_WINDOW_UNVERIFIED` / `RECONCILIATION_REQUIRED` / `RECONCILED` |
| `reason`, `next_action`, `evidence_ref` | lý do, việc cần làm, chứng từ |

**Bảng `conversion_reconciliation_events`**: chỉ thêm, ghi mỗi lần đổi `tracking_status` hoặc mỗi lần thử, có trigger chặn sửa / xoá như các bảng chứng cứ khác.

**Quy tắc chuyển trạng thái** (ngưỡng **đề xuất**, chờ duyệt):

| Điều kiện | `tracking_status` |
|---|---|
| Thấy trong lượt thành công gần nhất và tuổi < 20 ngày | `OBSERVED_RECENTLY` |
| Thấy và 20 ≤ tuổi < 30 ngày | `APPROACHING_WINDOW` |
| Tuổi ≥ 30 ngày, chưa có nguồn đọc được | `OUTSIDE_WINDOW_UNVERIFIED` |
| Tuổi ≥ 45 ngày và chưa kết luận, **hoặc** đơn trong khung mà vắng ở ≥ 2 lượt thành công liên tiếp | `RECONCILIATION_REQUIRED` |
| Có kết luận từ nguồn đáng tin (response thật hoặc chứng từ PLAN-075) | `RECONCILED` |

- Ra khỏi theo dõi khi hoa hồng có kết luận (REJECTED / FRAUD, hoặc APPROVED kèm SETTLED có chứng từ), hoặc đơn huỷ có dữ liệu thật.
- **Ví dụ:** đơn PENDING, mua 35 ngày trước, lần cuối thấy 7 ngày trước → `OUTSIDE_WINDOW_UNVERIFIED`, "Cần kiểm tra lại dữ liệu Shopee". **Không bao giờ** suy ra "Shopee đã từ chối".

---

## 11. Automatic Reconciliation Option (Phương án A)

- **Điều kiện bắt buộc:** lần thử nguồn (5.4) cho thấy website endpoint trả đúng đơn cũ hơn 30 ngày, với đủ trường xác minh.
- **Thiết kế** (nếu đủ điều kiện):
  - trong **cùng một lượt** của `SyncCoordinator` (không có scheduler riêng), sau phần quét 30 ngày, đọc khung hẹp cho từng đơn `OUTSIDE_WINDOW_UNVERIFIED` / `RECONCILIATION_REQUIRED`;
  - tối đa N đơn mỗi lượt và mỗi đơn tối đa 1 lần/ngày (N đề xuất 10, chờ duyệt);
  - kết quả đi qua `record_conversion_snapshot`, nên lịch sử thay đổi, snapshot tiền, hook PLAN-079 và khoá chống trùng dùng lại nguyên;
  - đơn không có trong khung hẹp → `last_attempt_result=not_returned`, **không** đổi trạng thái tiền.
- **Chi phí:** với 2 đơn hiện tại, thêm tối đa 2 yêu cầu/ngày. Một lượt đang có khoảng 3 yêu cầu, 6 lượt/ngày.
- **Rủi ro:**
  - Shopee đổi cách lọc;
  - khung hẹp trả nhiều checkout cùng giây; xử lý bằng cách khớp `checkout_id` + `order_id`;
  - phụ thuộc cookie như hiện nay.
- **Rollback:** cờ cấu hình tắt phần đọc bổ sung; dữ liệu đã ghi giữ nguyên.

---

## 12. Manual / Evidence-Based Option (Phương án B)

- **Không cần nguồn mới:**
  - thêm trường quan sát và bảng theo dõi (mục 10);
  - mỗi lượt cập nhật `tracking_status` từ dữ liệu bot đã có;
  - màn admin "🧾 Đơn cần đối soát" có danh sách, lý do, lần cuối thấy và việc cần làm;
  - báo admin dạng tổng hợp (mục 13).
- **Khi admin có chứng cứ:** nhập qua luồng chứng từ PLAN-075 (file kỳ thanh toán, hash, người duyệt). Đơn được đối soát chuyển `RECONCILED`; `settlement_status` chỉ đổi theo đúng quy tắc PLAN-075.
- **Chưa có chứng cứ:** đơn giữ nguyên `pending` trong sổ ví, không đổi số tiền, không báo khách.
- **Chi phí:** không thêm yêu cầu tới Shopee; admin xử lý tay khi có đơn trong backlog (hiện 0, sau 2026-11-22 có thể là 2).

---

## 13. Admin Alerts (đề xuất, ngưỡng chờ duyệt)

- **Một tin tổng hợp**, tối đa 1 lần/ngày, và chỉ khi danh sách thay đổi so với tin trước. Khoá chống trùng theo nội dung tập đơn: `recon_digest:<ngày>:<hash tập đơn + trạng thái>`.
- **Nội dung:**
  ```
  ⚠️ ĐƠN CẦN ĐỐI SOÁT
  Có 2 đơn cashback đang chờ Shopee xác minh:
  • 2 đơn sắp ra khỏi khung đồng bộ 30 ngày (từ 22/11).
  Vui lòng xem /admin → 🔗 Shopee Affiliate → 🧾 Đơn cần đối soát.
  ```
- **Báo riêng một lần:**
  - đơn chuyển `RECONCILIATION_REQUIRED`;
  - đơn đã từng ngoài khung nay `RECONCILED` (báo phục hồi).
- **Chỉ gửi admin.** Khách chỉ nhận tin khi Shopee có thay đổi thật theo đúng quy tắc PLAN-079.

---

## 14. PLAN-079 Integration

- Dữ liệu thật từ Shopee (cả khung hẹp, nếu Phương án A được duyệt) đi qua `record_conversion_snapshot`, nên tự có:
  - lịch sử thay đổi, snapshot tiền của link, người nhận theo Sub ID;
  - khoá `conversion:<id>:changes:<id thay đổi>`: không trùng tin; không đổi thì không có tin.
- Đơn chỉ quá 30 ngày (không có dữ liệu mới) → **không** tin khách, không đổi cashback.
- Không tin "Shopee đã duyệt" khi thiếu APPROVED thật (quy tắc PLAN-079 giữ nguyên).
- Mốc kích hoạt PLAN-079 không liên quan.

---

## 15. PLAN-080 Integration

- **Không có scheduler Shopee thứ hai.**
  - Phương án B chỉ đọc DB sau mỗi lượt, trong cùng luồng nền; không gọi Shopee.
  - Phương án A nếu được duyệt chạy trong lượt của `SyncCoordinator`, dưới cùng khoá, cùng heartbeat và `MAX_RUNTIME`.
- **Giữ nguyên:** chu kỳ 240 phút, khung 30 ngày.
- **Phương án A:** thêm yêu cầu có trần (N đơn/lượt, 1 lần/đơn/ngày), và tính vào thời lượng lượt (600 giây). Lỗi phiên / 429 dừng lượt như PLAN-080.

---

## 16. Financial Safety

PLAN-081 (cả A và B) **không** đổi:
- công thức V1.1 / V1.2, snapshot chính sách, gán theo Sub ID;
- commission validation, settlement evidence, sổ ví, payout, Financial Lock;
- điều khoản, tuỳ chọn thông báo.

**Cấm, sẽ có test chặn:**

| Cấm | Lý do |
|---|---|
| pending tự thành APPROVED | không có dữ liệu Shopee |
| quá 30 ngày tự thành REJECTED | quá hạn không phải bị từ chối |
| quá 60 ngày tự thành CANCELLED | quá hạn không phải bị huỷ |
| vắng khỏi API tự thành FRAUD | vắng mặt không phải gian lận |
| COMPLETED tự thành SETTLED | chỉ PLAN-075 có chứng từ mới được |
| đối soát tay không chứng từ mở quyền rút | — |

`tracking_status` không được đọc bởi `Wallet.refresh`, `payout_gate` hay `entry_payable`.

---

## 17. Performance & API Cost

| | Hiện tại | B | A (nếu duyệt) |
|---|---|---|---|
| Yêu cầu Shopee / lượt | ~3 (status, 1 trang click, 1 trang đơn) | +0 | + tối đa N (≤ 1 lần/đơn/ngày) |
| Lượt / ngày | 6 (240 phút) | 6 | 6 |
| Thời lượng lượt | ~1 giây | + vài truy vấn SQLite | + ~1 giây mỗi yêu cầu, trong trần 600 giây |
| Ghi DB | 1 transaction / đơn | + cập nhật theo dõi cho đơn qua bot đang chờ (hiện 2) | như B |

**Kết luận:** B chấp nhận được (ACCEPTABLE). A chưa đánh giá được (UNKNOWN), vì chưa biết Shopee có chấp nhận khung cũ hay không.

---

## 18. Test Matrix (Gate B, chưa viết code)

| # | Tình huống | Kỳ vọng |
|---|---|---|
| 1–3 | Đơn chờ ngày 29 / 30 / 31 (dùng đồng hồ giả, biên đúng tới giây) | `APPROACHING` / `OUTSIDE_WINDOW_UNVERIFIED` đúng mốc 30×86400 giây |
| 4–7 | Ngày 35 / 45 / 60 / 90 | `OUTSIDE…`, tới 45 thì `RECONCILIATION_REQUIRED`; không đổi tiền |
| 8 | Mua cũ nhưng Shopee báo muộn (lần đầu thấy ở tuổi 28) | `created_at` muộn; tuổi tính theo giờ mua |
| 9–11 | Đơn cũ tăng / giảm hoa hồng / bị từ chối (A: qua khung hẹp; B: qua chứng từ) | qua `record_conversion_snapshot`, 1 tin khách theo ngưỡng PLAN-079 |
| 12 | Đơn cũ được xác minh có chứng từ PLAN-075 | `RECONCILED`; `settlement_status` theo PLAN-075 |
| 13 | Khung hẹp không trả dữ liệu | `not_returned`, trạng thái tiền giữ nguyên |
| 14–15 | Thiếu một trang / lượt PARTIAL | không cập nhật `last_seen_at` cho đơn không đọc được; không chuyển `RECONCILED` |
| 16–17 | 429 / cookie hết hạn | dừng như PLAN-080; ghi lần thử `error:<loại>` |
| 18 | Schema đổi | PARSE_ERROR; không cập nhật theo dõi |
| 19 | Hai lượt cùng kiểm tra một đơn | khoá PLAN-080 chặn; 1 lần thử / ngày |
| 20 | Restart giữa lúc đối soát | lượt `interrupted`; lần thử không ghi nửa chừng |
| 21 | Không có `purchase_time` | `RECONCILIATION_REQUIRED` lý do `no_purchase_time`; không đoán tuổi |
| 22 | Thiếu `last_seen_at` (dữ liệu cũ) | dùng giá trị backfill có đánh dấu, hoặc "chưa rõ"; không coi là vắng |
| 23 | Lệch UTC / giờ VN | lưu UTC; hiển thị giờ VN; biên ngày đúng |
| 24 | Đơn vắng trong khung 2 lượt liên tiếp | `RECONCILIATION_REQUIRED` lý do `missing_in_window` |
| 25 | Đơn không đổi nhưng vẫn theo dõi | `last_seen_at` cập nhật, không có tin khách |
| 26 | Báo admin không trùng | 1 tin / ngày / tập đơn |
| 27 | Không gửi nhầm tin khách | 0 tin khách khi chỉ đổi `tracking_status` |
| 28–30 | Không đổi pending / không available / không payout | sổ ví như trước |
| 31 | Không ảnh hưởng lịch PLAN-080 | `next_due_at` và chu kỳ không đổi |

---

## 19. Migration Proposal (chỉ thiết kế)

- **`shopee_conversions` thêm cột** `last_seen_at`, `last_seen_run_id`, `last_seen_source`; chạy lại nhiều lần vẫn an toàn.
- **Backfill (cần duyệt):**
  - đặt `last_seen_at = updated_at`, `last_seen_source = 'backfill_updated_at'` cho các dòng chỉ được ghi qua `record_conversion_snapshot` (hiện là cả 3);
  - hoặc để NULL và hiển thị "chưa rõ".
  Không lẫn với giá trị thật nhờ `last_seen_source`.
- **Tạo bảng** `conversion_reconciliation` và `conversion_reconciliation_events` (chỉ thêm, có trigger chặn sửa / xoá sự kiện).
- **Không sửa:** dữ liệu tiền, `validation_status`, `settlement_status`, hàng đợi, mốc PLAN-079, lịch PLAN-080.
- **Diễn tập:** trên bản sao DB 0600, kiểm tra `integrity_check`, so mã băm các bảng không liên quan.

---

## 20. Rollback Proposal (chỉ thiết kế)

| Mức | Cách |
|---|---|
| Tắt cảnh báo / theo dõi | Cờ cấu hình; lớp theo dõi chỉ đọc nên tắt không ảnh hưởng tiền |
| Tắt đọc bổ sung (A) | Cờ riêng; lượt PLAN-080 quay về chỉ quét 30 ngày |
| Về code trước PLAN-081 | `git revert`. Cột và bảng mới để lại vô hại; code cũ không đọc. Không restore DB, không sửa trạng thái tiền |

---

## 21. Open Decisions (chờ chủ bot)

1. **Chọn phương án:** B trước (khuyến nghị), A sau khi thử nguồn; hay chỉ B.
2. **Ngưỡng:** "sắp ra khung" 20 ngày; "cần đối soát" 45 ngày hoặc vắng 2 lượt liên tiếp. Duyệt hay đổi.
3. **Có cho phép một lần thử nguồn (5.4) không:** 1 yêu cầu thật tới Shopee, chỉ đọc, không ghi DB.
4. **Backfill `last_seen_at`** từ `updated_at` có đánh dấu, hay để "chưa rõ".
5. **Tần suất báo admin:** tối đa 1 tin / ngày khi danh sách đổi; có cần nhắc lại khi không đổi không.
6. **Phạm vi theo dõi:** chỉ đơn qua bot đang chờ (đề xuất), hay mọi đơn của tài khoản affiliate.
7. **Nếu A được duyệt:** trần N đơn / lượt (đề xuất 10) và 1 lần / đơn / ngày.

---

## 22. Gate A Conclusion

| Gate | Kết luận |
|---|---|
| Current Sync Audit | **GO** |
| 30-Day Window Analysis | **GO** (có bằng chứng code và production: đơn …7156) |
| Database Aging Analysis | **GO** (số liệu thật, 3 đơn) |
| Shopee API Capability (> 30 ngày, tra theo mã) | **UNVERIFIED** |
| Reconciliation Backlog Design | **GO** (đặc tả) |
| Manual Reconciliation Fallback | **CONDITIONAL** (chưa biết portal xuất chứng từ theo đơn; dùng hạ tầng PLAN-075) |
| Notification Safety | **GO** |
| Financial Safety | **GO** |
| Performance Impact | B: **ACCEPTABLE**; A: **UNKNOWN** |
| Gate A Audit | **GO** |
| Gate B Code Implementation | **NOT AUTHORIZED** |
| Production Deployment | **NOT AUTHORIZED** |
| Wallet & Payout Activation | **NOT AUTHORIZED** |

---

## 23. Gate B Entry Conditions

1. Chủ bot duyệt phương án và các quyết định ở mục 21.
2. Phương án B cần chạy trên production **trước 2026-11-12**, ngày 2 đơn qua bot bước vào "sắp ra khung" theo ngưỡng đề xuất. Hạn chót tuyệt đối là 2026-11-22.
3. Nếu chọn A: kết quả lần thử nguồn (5.4) phải cho thấy website endpoint trả đúng đơn cũ hơn 30 ngày. Không đạt thì chỉ làm B.
4. Test matrix mục 18 viết thành test; toàn bộ regression đạt; diễn tập migration trên bản sao DB.
5. Triển khai theo quy trình thường lệ (backup, merge, test, push, chủ bot restart, kiểm tra chỉ đọc).

---

## Câu hỏi nghiệm thu Gate A

**Q1. Bot quét 30 ngày theo trường thời gian nào?**
`purchase_time` (giờ mua), khung `[now − 30 ngày, now]` theo unix giây UTC (`shopee_sync.py:291–292`, `shopee_client.py:239–240`).

**Q2. Đơn PENDING ngày thứ 31 có được quét lại không?**
Không. Đơn …7156 trên production là ví dụ thật: vắng từ lượt #4.

**Q3. Bot có lưu lần cuối thấy đơn không?**
Không có cột riêng. `updated_at` và `evidence_ref` đang mang nghĩa gần đúng nhờ cách code ghi, nhưng chưa phải trường được thiết kế cho việc này.

**Q4. Có bao nhiêu đơn thực tế gần hoặc quá 30 ngày?**
- Đơn qua bot đang chờ: 0 (2 đơn mới 1 ngày tuổi).
- Đơn không qua bot: 1 đơn đúng 30 ngày, đã có kết luận FRAUD.
- Hai đơn qua bot ra khung ngày 2026-11-22.

**Q5. Shopee cập nhật sau 40 ngày, bot có cách hợp lệ để đọc không?**
Hiện không. Chỉ có thể đọc được nếu lần thử nguồn chứng minh website endpoint nhận khung cũ, hoặc qua chứng từ nhập theo PLAN-075.

**Q6. Có bằng chứng Shopee cho phép truy vấn > 30 ngày không?**
- Website endpoint: không có.
- Open API: có tài liệu ghi khung 3 tháng, nhưng dự án không có quyền dùng.

**Q7. Truy vấn đúng một đơn được không?**
Không có endpoint theo mã đã được chứng minh. Gần nhất là khung giờ mua hẹp quanh đơn, cũng cần thử nguồn trước.

**Q8. Không truy vấn được thì admin biết đơn nào cần xử lý bằng cách nào?**
Phương án B: trạng thái theo dõi, màn "🧾 Đơn cần đối soát", và tin tổng hợp tối đa 1 lần/ngày.

**Q9. Tránh gửi trùng thông báo khi đối soát lại?**
Dữ liệu thật đi qua `record_conversion_snapshot` với khoá theo sự kiện của PLAN-079. Đổi trạng thái theo dõi không bao giờ tạo tin khách.

**Q10. PLAN-081 có tăng tần suất hoặc tải của PLAN-080 không?**
- B: không thêm yêu cầu tới Shopee.
- A: thêm có trần, trong cùng lượt và cùng khoá; chu kỳ 240 phút giữ nguyên.

**Q11. Có phương án nào tự chuyển pending thành available mà thiếu chứng từ không?**
Không. Lớp theo dõi tách khỏi sổ ví và Financial Lock (mục 16).

**Q12. Nên chọn A hay B, dựa trên chứng cứ nào?**
Chọn **B trước**. Lý do:
- vấn đề đã thấy thật trên production (đơn …7156);
- hạn 2026-11-22 cho 2 đơn qua bot;
- khả năng truy vấn > 30 ngày của nguồn hiện có là UNVERIFIED.

**A** chỉ làm sau khi lần thử nguồn được duyệt và cho kết quả rõ.
