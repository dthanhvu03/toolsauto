# PLAN-074 — Shopee Validation & Commission V1

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Nhánh | `cursor/cashback-plan074-validation`, tách từ `main@539e3d9` (code production `a9bb42a`) |
| Worktree | `/home/vu/toolsauto-cashback-validation` |
| Triển khai production | **CHƯA. NOT AUTHORIZED** |

---

## 1. Tóm tắt

- **Bot giờ phân biệt được ba trạng thái độc lập** cho mỗi đơn Shopee:
  - trạng thái đơn (`order_status`, có từ trước);
  - trạng thái duyệt hoa hồng (`validation_status`, mới);
  - trạng thái tiền Shopee đã trả (`settlement_status`, mới, luôn `NOT_VERIFIED`).
- **Shopee hiện không cung cấp field nào chứng minh hoa hồng đã được duyệt.** Trong cả 3 response thật đã lưu, `estimated_validation_month` rỗng và `validation_cycle=0`. Vì vậy:
  - **APPROVED bị BLOCKED**: code không có đường nào gán APPROVED;
  - hai đơn thật của bot đang ở **PENDING** ("Shopee chưa duyệt hoa hồng").
- **Gian lận có bằng chứng thật (1 mẫu)**: đơn 23/09 có `is_fraud=1` và `fraud_reason="Rejected due to fraudulent activity detected"`. Bot đánh dấu FRAUD và không phát sinh nghĩa vụ chi.
- **Phát hiện thay đổi hoa hồng**:
  - mỗi lần đồng bộ so với lần trước, chỉ ghi lịch sử khi có thay đổi thật;
  - giữ hoa hồng ban đầu, không để response thiếu field ghi đè số cũ;
  - phát hiện dữ liệu cũ đến muộn;
  - gom các thay đổi đáng kể thành một cảnh báo cho admin.
- **Sub ID**: người được ghi nhận giữ theo lần gắn đầu tiên, không bao giờ chuyển sang người khác.
- **Màn mới**: /admin → 🔗 Shopee Affiliate → **🧾 Duyệt hoa hồng**.
- **Khoá tài chính PLAN-073 giữ nguyên**, và thêm một điều kiện: khoản chỉ được rút khi trạng thái duyệt là `APPROVED`, mà hiện chưa nguồn nào gán được.
- 368 test pass (334 cũ + 34 mới).

---

## 2. Baseline production (đã kiểm lại)

| Mục | Giá trị |
|---|---|
| Git | `main@539e3d9` (code `a9bb42a`, commit sau chỉ có tài liệu), sạch |
| Process | PID 597550, khởi động 02:58:43 UTC 24/10, DB `data/cashback.sqlite` |
| Khoá tài chính | 4 trigger `financial_lock_*` đang có; không có bảng bằng chứng; `wallet_enabled=0` |
| Backup gần nhất | `cashback-20261024T025919Z.sqlite` (tự động) |
| Dữ liệu | 3 conversion (2 qua bot), 2 khoản `pending`, 0 yêu cầu rút, 7 lần đồng bộ |
| Test baseline | 334 passed |

---

## 3. Khảo sát field Shopee

Nguồn: `raw_json` của 3 conversion đã lưu từ `/api/v3/report/list` (API nội bộ của web Shopee Affiliate, đọc bằng cookie khi admin bấm 🔄). Em **không gọi Shopee** trong PLAN này.

Mức độ tin cậy:
- **VERIFIED**: có bằng chứng thật trong dữ liệu.
- **INFERRED**: suy ra từ quan sát, chưa xác minh.
- **NOT OBSERVED**: chưa từng thấy giá trị.

| Field | Vị trí | Có trong response? | Giá trị đã thấy | Ý nghĩa và độ tin cậy | Lưu DB? | Chứng minh "đã duyệt"? |
|---|---|---|---|---|---|---|
| `order_id` | orders[] | có | chuỗi số | mã đơn, khoá chính · VERIFIED | `conversion_id` | — |
| `order_sn` | orders[] | có | `261023…` | mã đơn hiển thị · VERIFIED | `order_sn` | — |
| `utm_content` | top | có | `u3e52GNL----`, `----` | Sub ID (phần trước `-`) · VERIFIED (2 đơn khớp đúng người) | `sub_id` | — |
| `order_status` | orders[] | có | UNPAID, PAID, COMPLETED | trạng thái mua hàng · VERIFIED | `order_status` | **Không** |
| `cancel_reason` | orders[] | có | "" | lý do huỷ · INFERRED (chưa thấy giá trị) | dùng cho REJECTED | Không |
| `conversion_status` | top | có | 1 (2 đơn chờ), 3 (đơn gian lận đã hoàn thành) | INFERRED | `conversion_status` | **Không** |
| `checkout_status` | top | có | "Pending"; "Waiting for payment" ở đơn **đã hoàn thành** | mâu thuẫn với trạng thái đơn → không tin được · INFERRED | `checkout_status` (mới) | **Không** |
| `affiliate_item_status` | items[] | có | 1, 3 | đi cùng `display_item_status` "Pending"/"Completed" · INFERRED | `affiliate_item_status` (mới) | **Không** |
| `is_fraud` | items[] | có | 0, 1 | cờ gian lận · **VERIFIED** khi đi kèm `fraud_reason` (1 mẫu) | `fraud_flag` (mới) | chứng minh **bị từ chối**, không chứng minh duyệt |
| `fraud_reason` | items[] | có | "", "Rejected due to fraudulent activity detected" | lý do bằng chữ · **VERIFIED** | dùng trong đánh giá | như trên |
| `fraud_status` | items[] | có | 2 (đơn sạch), 3 (đơn gian lận) | INFERRED. 3 đứng một mình bị coi là mâu thuẫn → NEEDS_REVIEW | raw | Không |
| `fraud_complete_time` | orders[] | có | có giá trị cả ở đơn sạch | có lẽ là giờ chạy kiểm tra gian lận · INFERRED | raw | Không |
| `estimated_total_commission`, `affiliate_net_commission` | top | có | 1.736.775.000 (= 17.368đ) | hoa hồng **ước tính**, có thể đổi · VERIFIED (khớp cách tính) | `gross/net_commission_vnd`, `first_commission_vnd` (mới) | **Không** (là ước tính) |
| `estimated_validation_month` | top | có | "" ở cả 3 đơn | NOT OBSERVED | `validation_month` (NULL) | **Không**, kể cả khi có giá trị (vẫn chỉ là ước tính) |
| `report_payment_validation_info` | top | có | `validation_cycle=0`, mọi field rỗng/0 | NOT OBSERVED | raw | **Không** |
| `complete_time` | orders[] | có | 0 / timestamp | giờ đơn hoàn thành · VERIFIED | `complete_time` | Không |
| `refunded_amount` | items[] | có | 0 | NOT OBSERVED | raw | Không |
| Field "đã duyệt", "đã thanh toán", ngày trả | — | **không có** | — | — | — | — |

**Cổng khảo sát:**

| Nội dung | Kết luận |
|---|---|
| Hoa hồng đã duyệt (APPROVED) | **BLOCKED**: không có nguồn xác minh |
| Gian lận (FRAUD) | **PARTIAL**: có bằng chứng chữ rõ ràng, nhưng mới 1 mẫu |
| Bị từ chối do huỷ (REJECTED) | **PARTIAL**: dùng `order_status=CANCELLED` / `cancel_reason`, chưa thấy mẫu thật |
| Đã thanh toán (SETTLED) | **BLOCKED**: không có trong báo cáo conversion (để PLAN-075) |

**Cần chủ bot duyệt nếu muốn mở khoá APPROVED.** Cần **một mẫu đơn đã được Shopee duyệt hoa hồng**. Không cần gọi endpoint mới, có hai cách:
- (a) đợi Shopee duyệt kỳ tháng 10 (thường sau khi hết tháng), rồi chủ bot bấm 🔄 một lần. Bot sẽ lưu response, em đọc chỉ đọc để xem `conversion_status`, `affiliate_item_status`, `estimated_validation_month`, `report_payment_validation_info` đổi thế nào;
- (b) chủ bot xuất báo cáo "Xác thực" hoặc "Thanh toán" từ trang Shopee Affiliate (CSV) để đối chiếu.

Em **không tự thăm dò** endpoint nào khác.

---

## 4. Mô hình dữ liệu

Dùng lại bảng `shopee_conversions` (thêm 13 cột qua `_add_column`) và thêm một bảng lịch sử:

| Cột mới | Ý nghĩa |
|---|---|
| `first_commission_vnd` | hoa hồng lần đầu bot thấy, không đổi về sau |
| `validation_status` | UNKNOWN / PENDING / APPROVED / REJECTED / FRAUD / NEEDS_REVIEW (mặc định UNKNOWN) |
| `validation_reason` | mã lý do, ví dụ `awaiting_shopee_validation`, `fraud_flag`, `status_regression` |
| `fraud_flag` | 1 / 0 / NULL (không đọc được) |
| `affiliate_item_status`, `checkout_status` | mã Shopee thô để tra cứu |
| `settlement_status` | mặc định `NOT_VERIFIED`. PLAN-074 không đổi giá trị này |
| `validation_source`, `validation_confidence` | `shopee_report_v3`, `INFERRED` |
| `evidence_ref` | `sync_run:<id>`: lần đồng bộ cung cấp trạng thái |
| `review_status`, `reviewed_by`, `reviewed_at` | none / needs_review / reviewed |

Bảng `shopee_conversion_changes` (chỉ thêm, không sửa, không xoá): `conversion_id`, `field`, `old_value`, `new_value`, `significant`, `source`, `sync_run_id`, `detected_at`, `UNIQUE(conversion_id, field, sync_run_id)`.

`raw_json` vẫn lưu như trước: phần `top` và `order` của báo cáo, không có cookie. Tên tài khoản affiliate có trong raw; màn admin không hiển thị.

---

## 5. Mô hình trạng thái (`commission_validation.assess`)

Thứ tự đánh giá:

| Điều kiện | Trạng thái | Lý do |
|---|---|---|
| Không có items, hoặc thiếu `is_fraud` | UNKNOWN | `missing_fields`. Dòng cũ giữ nguyên |
| `is_fraud=1` hoặc có `fraud_reason` | **FRAUD** | `fraud_flag` |
| `order_status` chứa CANCEL, hoặc có `cancel_reason` | **REJECTED** | `order_cancelled` |
| `fraud_status=3` mà không có cờ gian lận | NEEDS_REVIEW | `fraud_status_conflict` |
| `affiliate_item_status` hoặc `conversion_status` ngoài {1, 3} | NEEDS_REVIEW | `unmapped_status` |
| Hoa hồng = 0 mà không có cờ gian lận | NEEDS_REVIEW | `commission_zero_unexplained` (không kết luận gian lận) |
| Thiếu hoa hồng | UNKNOWN | `missing_commission` |
| Còn lại | **PENDING** | `awaiting_shopee_validation` hoặc `completed_awaiting_validation` |
| *(không có điều kiện nào)* | ~~APPROVED~~ | BLOCKED |

---

## 6. Phát hiện thay đổi (`TrackingRepository.record_conversion_snapshot`)

Mỗi đơn của mỗi lần đồng bộ được xử lý trong **một transaction `BEGIN IMMEDIATE`**:
- Lấy dòng cũ.
- So sánh hoa hồng, trạng thái đơn, trạng thái duyệt, cờ gian lận và Sub ID.
- Chỉ ghi lịch sử khi giá trị thật sự đổi. Đồng bộ lại y hệt không tạo dòng nào.
- **Giá trị thiếu (None) không ghi đè giá trị cũ.** Hoa hồng không bị đưa về 0 vì response thiếu field. Thiếu items thì giữ nguyên trạng thái duyệt cũ.
- **Thay đổi đáng kể** (đánh dấu `significant`, chuyển đơn sang "cần kiểm tra", báo admin):
  - hoa hồng giảm từ 1.000đ hoặc từ 10% trở lên, hoặc về 0;
  - xuất hiện gian lận;
  - đơn bị huỷ;
  - trạng thái chuyển sang FRAUD / REJECTED / NEEDS_REVIEW;
  - Sub ID trỏ sang link khác.
- **Dữ liệu cũ đến muộn**: đơn đã FRAUD hoặc REJECTED mà lần sau lại "chờ" thì đánh dấu `NEEDS_REVIEW` (`status_regression`), không âm thầm quay lại PENDING.
- Hoa hồng tăng: có ghi lịch sử, không báo động.
- Đồng bộ lỗi giữa chừng:
  - phần đã đọc được vẫn được ghi;
  - không đơn nào bị xoá vì lần sau không thấy;
  - lần chạy ghi `partial`, tin báo nói rõ "Đơn chưa đọc được giữ nguyên số cũ".
- Cảnh báo admin: **một tin cho mỗi lần đồng bộ** (`event_key=commission_changes:<run_id>`), tối đa 10 dòng.

**Sổ ví:** đơn FRAUD hoặc REJECTED (hay raw có cờ gian lận) được ghi `cancelled`, tức không phát sinh nghĩa vụ chi. Lịch sử nằm trong `shopee_conversion_changes`. Đơn chưa vào ví được tính lại theo hoa hồng mới (chưa có nghĩa vụ chi nào). Đơn đã vào ví thì hiện chưa thể tồn tại vì khoá; điều chỉnh âm cho trường hợp này để PLAN-075.

---

## 7. Màn admin 🧾 Duyệt hoa hồng

/admin → 🔗 Shopee Affiliate → **🧾 Duyệt hoa hồng** (`c:cv:home`, `admin_validation.py`). Dựng thử từ bản sao DB thật:

```
Đơn qua bot: 2 · Đồng bộ gần nhất: 09:02 24/10 (success)
Chờ xác minh       2
Shopee đã duyệt    0
Bị từ chối         0
Gian lận           0
Cần kiểm tra       0
Hoa hồng đã đổi    0
⚠️ Chưa có dữ liệu đủ điều kiện xác nhận hoa hồng đã được Shopee duyệt.
ⓘ Trạng thái suy ra từ báo cáo Shopee (độ tin cậy: suy luận). Tiền Shopee đã trả: chưa xác minh.
```

- **Các nút:** 📋 Chờ xác minh · ✅ Đã duyệt · ❌ Bị từ chối · 🚨 Cần kiểm tra · 🔄 Hoa hồng thay đổi · 🕘 Lịch sử · ◀️ Shopee Affiliate.
- **Chi tiết đơn:**
  - mã đơn rút gọn (`261023…0N`), Sub ID, người được ghi nhận;
  - trạng thái đơn, trạng thái duyệt kèm lý do, "Tiền Shopee đã trả: chưa xác minh";
  - hoa hồng ban đầu / hiện tại / chênh lệch, lần đồng bộ gần nhất, nguồn và độ tin cậy;
  - 8 dòng lịch sử gần nhất.
- **Thao tác duy nhất có ghi:** "✔️ Đã kiểm tra cảnh báo" (`c:cv:ack:<id>`). Chỉ đổi `review_status`, ghi `admin_change_audit` và hiện trong 📊 Lịch sử. Không đổi tiền, không đổi trạng thái duyệt, không đổi quyền rút.
- **Không có nút** sửa hoa hồng, gán APPROVED, đánh dấu đã nhận tiền, mở ví hay chi trả.
- Quyền: mọi `c:cv:*` đi qua kiểm tra admin và chat riêng có sẵn. Callback sai định dạng bị từ chối. Đơn không qua bot thì không mở được.

---

## 8. File đã sửa

| File | Thay đổi |
|---|---|
| `cashback_bot/commission_validation.py` (mới) | `assess`, `assess_raw`, hằng trạng thái, ngưỡng thay đổi đáng kể, `is_regression` |
| `cashback_bot/admin_validation.py` (mới) | màn 🧾 Duyệt hoa hồng |
| `cashback_bot/db.py` | `VALIDATION_COLUMNS`, bảng `shopee_conversion_changes`, `record_conversion_snapshot` (thay phần thân của `record_shopee_conversion`, bản cũ vẫn giữ làm wrapper), `conversion_changes`, `mark_conversion_reviewed`, `_backfill_validation` |
| `cashback_bot/shopee_sync.py` | gọi `assess` và `record_conversion_snapshot` kèm `sync_run_id`; gom thay đổi; báo admin cả khi lỗi giữa chừng; tin kết quả có số thay đổi |
| `cashback_bot/admin_notify.py` | `notify_commission_changes`, `short_order`, `change_value` |
| `cashback_bot/wallet.py` | đọc `validation_status`; FRAUD/REJECTED/cờ gian lận → `cancelled`; truyền trạng thái duyệt vào cổng khoá |
| `cashback_bot/payout_gate.py` | `entry_payable` bắt buộc `validation_status == APPROVED` (thêm vào các điều kiện PLAN-073) |
| `cashback_bot/admin_policy.py`, `admin_ui.py` | route `c:cv:*`, nút 🧾 ở màn Shopee, dòng lịch sử `commission_review_ack` |
| Tests | `tests/test_cashback_validation.py` (34 test mới); `test_cashback_wallet.py`, `test_cashback_vietqr.py`, `test_cashback_safety_hardening.py`: các test luồng rút tiền gán APPROVED **trong DB test** (`_order(approved=True)`) |

Không sửa: `pricing.py`, `calculator.py`, `money.py`, `service._quote_cashback`, các trigger khoá, `backup.py`.

---

## 9. Migration

Tự chạy trong `repo.migrate()` lúc khởi động:
- `CREATE TABLE IF NOT EXISTS shopee_conversion_changes` và index;
- 13 lệnh `_add_column` (idempotent);
- `_backfill_validation`: chỉ đụng dòng có `validation_source IS NULL`, chép hoa hồng hiện tại làm mốc đầu, đánh giá lại từ `raw_json`. Không ghi lịch sử, không bao giờ ra APPROVED hay SETTLED, không tính lại tiền rút.

**Diễn tập trên bản sao DB production** (Backup API, 0600, đã xoá), `migrate()` chạy 2 lần:
- chỉ thêm bảng `shopee_conversion_changes` (0 dòng);
- 4 trigger còn nguyên;
- 2 khoản trong sổ ví không đổi (12.157đ, 960đ);
- backfill cho kết quả:

| Đơn | Kết quả backfill |
|---|---|
| …0309 DOPI (qua bot) | PENDING · `awaiting_shopee_validation` · HH ban đầu 17.368đ |
| …0025 bộ cọ (qua bot) | PENDING · HH ban đầu 1.372đ |
| …7156 (ngoài bot, 23/09) | FRAUD · `fraud_flag` |

`settlement_status` = NOT_VERIFIED cho cả 3.

---

## 10. Bằng chứng test

| Nhóm | Test | Kết quả |
|---|---|---|
| Toàn bộ cashback | `tests/test_cashback_*.py` | **368 passed** (334 cũ + 34 mới), ruff sạch |
| G1 Duyệt (8) | mọi tổ hợp field (24 tổ hợp) không ra APPROVED; không cờ duyệt → PENDING kèm nguồn/độ tin cậy/`sync_run`; thiếu dữ liệu → UNKNOWN; mâu thuẫn → NEEDS_REVIEW; cờ gian lận → FRAUD; COMPLETED vẫn PENDING; PAID vẫn NOT_VERIFIED; có tháng duyệt vẫn chưa duyệt | pass |
| G2 Thay đổi (10) | tăng (ghi, không báo động); giảm 20.000 → 12.000 (ghi, cần kiểm tra, báo admin 1 lần); về 0 (NEEDS_REVIEW, không kết luận gian lận); thành FRAUD (lịch sử + sổ `cancelled`); huỷ (REJECTED + sổ `cancelled`); đồng bộ 3 lần y hệt (0 lịch sử, 1 dòng); lỗi giữa chừng (`partial`, đơn đã đọc được giữ, đơn cũ không mất); thiếu field không ghi đè; dữ liệu cũ đến muộn → `status_regression`; 20.000 → 15.000 → 10.000 → 0 đủ 3 dòng, mốc đầu giữ 20.000 | pass |
| G3 Sub ID (5) | đúng Sub ID → đúng người; Sub ID sai/không có → không gắn, không có khoản; link chia sẻ → về người tạo link; Sub ID lần sau trỏ người khác → giữ người cũ, ghi `attribution`, cần kiểm tra; một đơn đồng bộ nhiều lần → một dòng sổ ví | pass |
| G4 Bảo mật và khoá (6) | khách bấm `c:cv:*` bị chặn; callback giả, SQL injection, đơn ngoài bot bị chặn; APPROVED chưa có settlement → `holding`, rút trả `locked`; FRAUD kể cả bị gán APPROVED → `cancelled`; migrate 2 lần vẫn đủ 4 trigger, không có bảng bằng chứng, ví khoá; không tạo payout, trigger vẫn chặn SQL | pass |
| Màn admin và backfill (5) | số liệu thật và câu "chưa có dữ liệu… duyệt"; chi tiết có ban đầu/hiện tại/chênh và lịch sử; "Đã kiểm tra" ghi audit, không đổi tiền, bấm lại báo không còn cảnh báo; danh sách cần kiểm tra và màn lịch sử; mỗi lần đồng bộ một cảnh báo, không đổi thì không báo; backfill dòng cũ không ra APPROVED, không ghi lịch sử | pass |
| Không có traffic thật | mọi client Shopee/Telegram là mock | — |

---

## 11. An toàn tài chính

- Khoá PLAN-073 không đổi: trigger, `FinancialGate.readiness`, chặn bật ví, chặn yêu cầu rút, chặn xác nhận "đã chuyển".
- Thêm điều kiện: `entry_payable` yêu cầu `validation_status == APPROVED`. Hiện **không đường nào gán APPROVED**, nên không khoản nào vào ví được, kể cả khi có settlement.
- Sáu loại số tiền vẫn tách bạch:

| # | Loại | Trạng thái trong PLAN-074 |
|---|---|---|
| 1 | ước tính lúc tạo link (`link_requests.estimated_*`) | không đổi |
| 2 | hoa hồng Shopee báo (`net_commission_vnd`, `first_commission_vnd`) | đang dùng |
| 3 | hoa hồng đã duyệt | chưa có nguồn |
| 4 | hoa hồng đã trả | PLAN-075 |
| 5 | tiền hoàn đã tính (`cashback_entries.cashback_vnd`) | qua `service._real_cashback`, không có công thức mới |
| 6 | tiền hoàn được chi | không thể có (khoá) |

- V1.1, V1.2, tỷ lệ 70% không đổi. Membership vẫn tắt.

---

## 12. Bảng trạng thái thực tế

| Chức năng | Trước PLAN-074 | Sau PLAN-074 | Bằng chứng | Trạng thái |
|---|---|---|---|---|
| Lưu trạng thái đơn | có (`order_status`) | không đổi | DB | Hoạt động production |
| Trạng thái duyệt hoa hồng | không có | PENDING/REJECTED/FRAUD/NEEDS_REVIEW/UNKNOWN | G1, diễn tập | Đã code và test, chưa triển khai |
| APPROVED | không có | khai báo nhưng không gán | khảo sát field | **Bị chặn bởi nguồn dữ liệu** |
| Trạng thái settlement | không có | cột `NOT_VERIFIED` | — | Không đủ bằng chứng (PLAN-075) |
| Phát hiện gian lận | chỉ trong cổng khoá | FRAUD + lịch sử + sổ `cancelled` | G1/G2, 1 mẫu thật | Đã code và test, chưa triển khai |
| Lịch sử thay đổi hoa hồng | không có (ghi đè) | `shopee_conversion_changes` | G2 | Đã code và test, chưa triển khai |
| Thiếu field ghi đè số cũ | **có lỗi** | đã sửa | `test_missing_fields_never_overwrite_good_data` | Đã code và test, chưa triển khai |
| Sub ID bị gắn lại người khác | **có thể** | đã chặn | `test_never_reassigned_to_another_user` | Đã code và test, chưa triển khai |
| Cảnh báo thay đổi cho admin | không có | 1 tin/lần đồng bộ | G2, màn admin | Đã code và test, chưa triển khai |
| Màn 🧾 Duyệt hoa hồng | không có | có | màn admin, diễn tập | Đã code và test, chưa triển khai |
| Khoá tài chính | hoạt động | hoạt động + điều kiện APPROVED | G4 | Production + đã test |

---

## 13. Rủi ro còn lại

- **APPROVED chưa có nguồn**: cần một mẫu đơn đã duyệt (mục 3).
- **Ý nghĩa mã trạng thái của Shopee** mới là suy luận. Shopee đổi mã thì bot đánh dấu NEEDS_REVIEW, không đoán.
- **Gian lận mới có 1 mẫu.** Các dạng gian lận khác (không có `fraud_reason`) có thể không bắt được.
- **Đơn đã vào ví mà hoa hồng giảm**: chưa có dòng điều chỉnh âm (PLAN-075). Hiện không gây thiệt hại vì khoá.
- **Nguồn dữ liệu**: vẫn là API nội bộ bằng cookie; Shopee đổi API thì mất đối soát. Đồng bộ vẫn chạy trong vòng poll (vài chục đơn không đáng kể; khi có hàng nghìn đơn nên tách luồng).
- **Không có giờ cập nhật từ phía Shopee**: bot chỉ biết lúc mình phát hiện (`detected_at`), không biết Shopee đổi lúc nào.

---

## 14. Triển khai và rollback (chờ chủ bot duyệt)

1. Backup: `cd /home/vu/toolsauto && umask 077 && .venv/bin/python -m cashback_bot.backup`.
2. `git merge --ff-only cursor/cashback-plan074-validation` trên `main`, chạy test, push.
3. Chủ bot restart (`kill -TERM <PID>`, `umask 077`, `setsid nohup …`).
4. Migration tự chạy (đã diễn tập).
5. Xác minh:
   - log khởi động sạch;
   - DB chỉ đọc có `shopee_conversion_changes` và 13 cột mới;
   - /admin → 🔗 → 🧾 hiện 2 đơn chờ xác minh và 0 đã duyệt;
   - 👛 vẫn khoá.
6. Lần 🔄 kế tiếp: bot bắt đầu ghi lịch sử thay đổi.

**Rollback:** `git revert` các commit của nhánh rồi restart. Bảng và cột mới vô hại với code cũ (code cũ không đọc). Trigger khoá không bị đụng. DB hỏng: khôi phục từ backup ở bước 1.

---

## 15. Release gates

| Gate | Kết luận | Lý do |
|---|---|---|
| Shopee Field Discovery | **CONDITIONAL** | Đã kê đủ field trong response đã lưu; nghĩa của mã duyệt cần một mẫu đơn đã duyệt |
| Commission Validation | **CONDITIONAL** | PENDING/REJECTED/FRAUD/NEEDS_REVIEW/UNKNOWN đã chạy; **APPROVED BLOCKED** |
| Fraud Detection | **CONDITIONAL** | Chạy đúng với mẫu thật, mới 1 mẫu |
| Commission Adjustment | **GO** | Phát hiện, lịch sử, mốc đầu, chống ghi đè, dữ liệu cũ đến muộn, cảnh báo |
| Sub ID Attribution | **GO** | Giữ người ghi nhận đầu tiên; xung đột được ghi và đánh dấu |
| Admin Validation UI | **GO** | Số liệu thật, không suy diễn, chỉ có thao tác "đã kiểm tra" kèm audit |
| Financial Lock | **GO** | Không đổi PLAN-073; thêm điều kiện APPROVED |
| Database Migration | **GO** | Idempotent, đã diễn tập trên bản sao DB thật |
| Regression Tests | **GO** | 368/368 |
| Production Deployment | **NOT AUTHORIZED** | |
| Wallet Activation | **NOT AUTHORIZED** | |
| Payout | **NOT AUTHORIZED** | |

---

## Câu hỏi nghiệm thu

**Q1. Shopee hiện cung cấp field nào thực sự xác minh được hoa hồng đã duyệt?**
**Không có field nào.** Báo cáo conversion chỉ có hoa hồng **ước tính** (`estimated_total_commission`, `affiliate_net_commission`). Các field nghe như "duyệt" (`estimated_validation_month`, `report_payment_validation_info`) đều rỗng ở cả 3 đơn. Các mã `conversion_status`, `affiliate_item_status`, `fraud_status` chưa xác minh được nghĩa. Field chứng minh được duy nhất là **bị từ chối do gian lận** (`is_fraud=1` kèm `fraud_reason`).

**Q2. Hai đơn thật của bot đang ở trạng thái nào?**
Cả hai là **PENDING · Shopee chưa duyệt hoa hồng**:
- DOPI kem nền: đơn UNPAID, hoa hồng 17.368đ;
- Bộ cọ: đơn PAID, hoa hồng 1.372đ.

Cả hai đều `settlement_status = NOT_VERIFIED`. Còn thiếu: (1) bằng chứng Shopee đã duyệt hoa hồng (chưa có field, cần mẫu); (2) bằng chứng Shopee đã trả (PLAN-075).

**Q3. Shopee hạ hoa hồng từ 20.000đ xuống 12.000đ hoặc 0đ thì bot có phát hiện, lưu lịch sử và hiển thị đúng không?**
Có (đã test):
- 20.000 → 12.000: ghi một dòng lịch sử đáng kể, đơn chuyển "cần kiểm tra", admin nhận một cảnh báo. Màn chi tiết hiện "ban đầu 20.000đ · hiện tại 12.000đ · chênh −8.000đ" kèm dòng lịch sử.
- Về 0đ mà không có cờ gian lận: NEEDS_REVIEW ("hoa hồng về 0, không rõ lý do"), không tự kết luận gian lận.
- Có cờ gian lận: FRAUD, sổ ví ghi `cancelled`.

**Q4. Đơn đã COMPLETED nhưng bị gắn gian lận có thành khoản rút được không?**
**Không.**
- Sổ ví ghi `cancelled` (theo `validation_status=FRAUD` hoặc theo cờ gian lận trong raw).
- Cổng khoá từ chối vì gian lận và vì không có APPROVED.
- Trigger SQLite chặn ghi `available` khi chưa có bằng chứng settlement.

Đã test cả trường hợp ai đó cố gán APPROVED cho đơn gian lận.

**Q5. Có dữ liệu nào bị suy diễn thành APPROVED hoặc SETTLED khi chưa đủ bằng chứng không?**
**Không.**
- `assess` không có nhánh nào trả APPROVED (test 24 tổ hợp field).
- Backfill không tạo APPROVED (test và diễn tập).
- `settlement_status` luôn `NOT_VERIFIED`, không code nào đổi.
- Trong test, APPROVED chỉ được gán bằng tay trong DB tạm để thử cơ chế rút tiền.

**Q6. Sau PLAN-074, còn thiếu gì để làm PLAN-075 (Settlement & Fund Reconciliation)?**
1. **Nguồn bằng chứng Shopee đã trả**: số tiền, kỳ, mã chứng từ, ngày nhận. Lấy từ trang Thanh toán của Shopee Affiliate hoặc sao kê ngân hàng; cần chủ bot chọn nguồn.
2. **Luồng ghi bằng chứng có kiểm soát**: tạo thật `shopee_settlements` và `payout_tax_policies` (hiện là DDL nháp 007), ai nhập, đối chiếu thế nào, audit.
3. **Nguồn cho APPROVED**: mẫu đơn đã duyệt để gán nghĩa mã Shopee, **hoặc** quy trình admin duyệt thủ công có chứng từ (cần quyết định riêng).
4. **Đối chiếu đơn ↔ kỳ thanh toán**: đơn nào thuộc kỳ nào, tổng có khớp số Shopee trả không.
5. **Dòng điều chỉnh âm** cho khoản đã vào ví khi hoa hồng giảm hoặc gian lận xuất hiện sau đó.
6. **Quyết định thuế người nhận** (kế toán, ADR), quét QR thật, trần rút mỗi tháng, audit chi trả.
