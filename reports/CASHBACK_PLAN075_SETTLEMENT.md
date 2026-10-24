# PLAN-075 — Shopee Settlement & Fund Reconciliation V1

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Nhánh | `cursor/cashback-plan075-settlement`, tách từ `main@5bf2796` (code production `cef3467`) |
| Worktree | `/home/vu/toolsauto-cashback-settlement` |
| ADR | ADR-052 (mới); ADR-050, ADR-051 giữ nguyên |

---

## 1. Tóm tắt

- **Đã có khung đối soát tiền Shopee thật:**
  - ghi nhận kỳ thanh toán;
  - lưu chứng cứ có chống trùng và chỉ thêm, không sửa;
  - đối chiếu ba nguồn: báo cáo thanh toán Shopee ↔ số học kỳ ↔ tiền ngân hàng thực nhận;
  - tách tiền đơn qua bot / ngoài bot / không rõ đơn;
  - ghi điều chỉnh khi Shopee giảm hoặc thu hồi hoa hồng ở kỳ sau.
- **Màn mới:** /admin → 🔗 Shopee Affiliate → **🧾 Đối soát thanh toán**, nằm cạnh màn 🧾 Duyệt hoa hồng.
- **Chưa có chứng từ thật nào:** trên máy không có báo cáo Xác thực, Thanh toán Shopee hay sao kê. Vì vậy:
  - mọi số tiền trên màn đối soát hiện **"Chưa xác minh"**;
  - chưa có parser đọc file Shopee thật; chứng từ vào bằng định dạng chuẩn nội bộ `cashback_settlement_v1` qua công cụ trên máy chủ;
  - **APPROVED vẫn BLOCKED.** Báo cáo xác thực chỉ được lưu như chứng cứ, không đổi trạng thái duyệt.
- **Ví và chi trả vẫn khoá hoàn toàn.** Bảng mới cố ý không trùng tên với điều kiện mở khoá, nên kể cả khi một kỳ "chứng từ khớp", ví vẫn không mở được.
- **412 test pass** (368 cũ + 44 mới).

| Phần | Trạng thái |
|---|---|
| **Đã code và test** | schema 5 bảng, engine đối soát, phân bổ quỹ, điều chỉnh, công cụ nhập, màn admin |
| **Đã triển khai production** | toàn bộ phần đã code, tại `6dc2dd1` (mục 14) |
| **Chưa xác minh được** | định dạng thật của báo cáo Shopee và sao kê; quy tắc thuế người nhận |
| **Đang bị chặn bởi nguồn chứng cứ** | APPROVED (cần báo cáo xác thực thật); parser file Shopee |

---

## 2. Preflight và baseline

| Mục | Giá trị |
|---|---|
| Git production | `main@5bf2796` (code `cef3467`), sạch |
| Process | PID 601747, khởi động 03:30:51 UTC, DB `data/cashback.sqlite` |
| Khoá | 4 trigger `financial_lock_*`; không có `shopee_settlements` / `payout_tax_policies`; `wallet_enabled=0` |
| Backup gần nhất | `cashback-20261024T032835Z.sqlite` |
| Conversion | 2 đơn bot PENDING / NOT_VERIFIED (18.740đ); 1 đơn ngoài bot FRAUD |
| Lịch sử, sổ ví | `shopee_conversion_changes` 0 dòng; 2 khoản `pending` (13.117đ); 0 yêu cầu rút |
| Test baseline | **368 passed** |

---

## 3. Khảo sát nguồn chứng cứ

| Nguồn | Có mẫu thật? | Dùng trong V1 |
|---|---|---|
| 1. Shopee Conversion Report | Có (PLAN-074) | trạng thái đơn, hoa hồng Shopee báo, gian lận. Không chứng minh duyệt hay trả |
| 2. Báo cáo Xác thực hoa hồng | **Không** | nhập được ở định dạng chuẩn (`shopee_validation_report`); chỉ lưu số "Shopee báo duyệt" |
| 3. Báo cáo Thanh toán Shopee Affiliate | **Không** | định dạng chuẩn (`shopee_payment_report`): tổng kỳ, phí, VAT, thuế, điều chỉnh, số chuyển, khoản theo đơn |
| 4. Sao kê / chứng từ ngân hàng | **Không** | định dạng chuẩn (`bank_statement`): số tiền nhận. Không chứng minh từng đơn |

- Đã tìm toàn ổ đĩa theo tên file liên quan: không có.
- Em không gọi endpoint Shopee nào.
- Parser cho file Shopee và sao kê thật chỉ viết được khi có mẫu. Khi đó parser chuyển về `cashback_settlement_v1` và engine giữ nguyên.

---

## 4. Nguồn APPROVED và giới hạn

**APPROVED = BLOCKED.** Thiếu cả sáu điều kiện ở Phase F, vì chưa có dữ liệu Shopee chứng minh duyệt. Hiện trạng:

- Báo cáo xác thực (nếu nhập) được lưu thành các khoản có `approved_vnd`, hiện trên màn đối soát là "Shopee báo đã duyệt … (chưa đối chiếu)".
- Code **không đổi** `validation_status` theo báo cáo này (test `test_validation_report_never_sets_approved`).
- Ba sự kiện được tách bạch:

| Sự kiện | Nơi ghi | Cách xảy ra |
|---|---|---|
| Admin đã xem chứng từ | `settlement_evidence.viewed_by/at` | nút "👁 Đã xem chứng từ" |
| Chứng từ đã xác minh | `verification = VERIFIED` | chỉ khi kỳ MATCHED (hai nguồn độc lập khớp) |
| Hoa hồng Shopee xác nhận | `validation_status = APPROVED` | **không có đường nào** |

- Không có nút "xác nhận" nào tạo ra bằng chứng Shopee duyệt.

---

## 5. Data model (ADR-052)

| Bảng | Vai trò | Ràng buộc chính |
|---|---|---|
| `settlement_batches` | một kỳ hoặc một lần Shopee trả: kỳ, mã thanh toán, hoa hồng báo, điều chỉnh, phí, VAT, phí gồm VAT?, thuế khấu trừ, Shopee báo chuyển, ngân hàng nhận, trạng thái, chứng từ gốc | trạng thái thuộc 6 giá trị; `UNIQUE(period, shopee_payment_ref)` khi có mã. **NULL = chưa xác minh**, không phải 0 |
| `settlement_evidence` | chứng cứ: loại, mã chứng từ, sha256, tên lưu (= sha256), kích thước, parser, xác minh, admin đã xem, thay bằng | `UNIQUE(content_sha256)`, `UNIQUE(kind, document_ref)`; trigger chặn xoá |
| `settlement_items` | khoản theo đơn: mã đơn, conversion, qua bot?, người dùng (chỉ khi qua bot), duyệt/trả/điều chỉnh, trạng thái khớp | `UNIQUE(batch_id, evidence_id, order_ref)` |
| `settlement_adjustments` | điều chỉnh sau kỳ: cũ, mới, chênh, nguồn, khoá sự kiện, trạng thái | `UNIQUE(source, source_ref)`: một sự kiện một dòng |
| `settlement_audit` | mọi thao tác: tạo kỳ, nhập chứng từ (kèm tổng số và sha), đã xem, đối soát, đảo kỳ, ghi điều chỉnh | trigger chặn sửa và xoá |

**Tên bảng cố ý khác `shopee_settlements` / `payout_tax_policies`.** Đó là điều kiện mở khoá của `payout_gate` (PLAN-073), nên đối soát không thể mở ví. Nối đối soát vào khoá là việc của PLAN-078.

---

## 6. Engine đối soát (`settlement.SettlementEngine`)

Độc lập với Telegram; màn admin và công cụ nhập chỉ gọi engine.

**Nhập chứng từ** (`import_document`):
- Kiểm tra chặt định dạng:
  - tiền là số nguyên VND; từ chối số thực, chuỗi, bool, số âm (trừ điều chỉnh), số quá lớn;
  - kỳ `YYYY-MM`; mã chứng từ chỉ gồm ký tự an toàn (chặn `../`);
  - tối đa 2 MB, 20.000 khoản; không trùng đơn trong cùng file.
- Kỳ hoặc mã thanh toán phải khớp kỳ đang nhập.
- Mỗi kỳ có một chỗ cho báo cáo thanh toán và một chỗ cho chứng từ ngân hàng. Muốn thay thì phải chỉ rõ `--replaces`: chứng từ cũ chuyển SUPERSEDED, không bị sửa đè.

**Gắn từng khoản với đơn** (theo `order_sn` hoặc `conversion_id`):

| Trường hợp | Trạng thái khoản |
|---|---|
| Không tìm thấy đơn | `UNKNOWN_ORDER` (không gán cho ai) |
| Đơn ngoài bot | `NOT_BOT` |
| Đơn bot đã FRAUD / REJECTED mà Shopee vẫn trả | `NEEDS_REVIEW` |
| Đơn đã được trả ở kỳ khác mà khoản này không phải điều chỉnh | `DUPLICATE` |
| Số trả khác hoa hồng bot đang ghi (gồm trả một phần) | `AMOUNT_MISMATCH` |
| Còn lại | `MATCHED` |

**Đối soát** (`reconcile`):

| Kiểm tra | Mã chênh lệch | Kéo kỳ về |
|---|---|---|
| Chưa có báo cáo thanh toán / chứng từ ngân hàng | `NO_STATEMENT` / `NO_BANK` | EVIDENCE_PENDING |
| Thiếu phí, thuế, điều chỉnh, hoặc không rõ phí đã gồm VAT chưa | `TOTALS_INCOMPLETE` | EVIDENCE_PENDING |
| `hoa hồng + điều chỉnh − phí − VAT (nếu phí chưa gồm) − thuế ≠ Shopee báo chuyển` | `STATEMENT_ARITHMETIC` | DISPUTED |
| Ngân hàng nhận < / > Shopee báo chuyển | `BANK_SHORT` / `BANK_OVER` | DISPUTED |
| Tổng theo đơn > tổng kỳ | `OVER_ALLOCATED` | DISPUTED |
| Tổng theo đơn < tổng kỳ | `UNALLOCATED` | PARTIALLY_MATCHED |
| Có khoản không rõ đơn / lệch số / trùng / cần kiểm tra | `ITEM_*` | PARTIALLY_MATCHED |
| Không có chênh lệch nào | — | **MATCHED** |

- Chứng từ chỉ được đánh `VERIFIED` khi kỳ MATCHED.
- `settlement_status` của đơn chỉ là `SETTLED` khi đơn có khoản khớp trong một kỳ MATCHED; kỳ bị đảo hoặc lệch thì trả về `NOT_VERIFIED`.
- **MATCHED không phải công tắc** cho ví hay chi trả.

---

## 7. Phân bổ quỹ

| Nhóm | Gồm |
|---|---|
| Đơn qua bot (khớp) | khoản `MATCHED` của đơn có Sub ID bot |
| Đơn ngoài bot | `NOT_BOT`, **không bao giờ** vào quỹ cashback |
| Không rõ đơn | `UNKNOWN_ORDER`, không gán cho người dùng nào |
| Cần kiểm tra | lệch số, trùng, Shopee trả cho đơn gian lận |
| Chưa phân bổ | tổng kỳ − tổng theo đơn (Shopee chỉ báo tổng mà không có chi tiết thì toàn bộ nằm ở đây) |
| **Quỹ có chứng từ của đơn bot** | chỉ có khi kỳ MATCHED. Hiện kèm chữ "chưa phải tiền khách được rút" |

- Không chia tiền theo tỷ lệ ước lượng.
- Phí và thuế thực tế nằm ở cấp kỳ, ghi "chưa phân bổ theo từng đơn".

**Ví dụ (câu Q3):** kỳ Shopee chuyển 1.000.000đ, trong đó 200.000đ có khoản theo đơn khớp đơn bot. Kết quả:
- quỹ đơn bot = 200.000đ;
- phần còn lại nằm ở "ngoài bot", "không rõ đơn" hoặc "chưa phân bổ" tuỳ chứng từ;
- không đồng nào của phần còn lại vào quỹ cashback.

---

## 8. Điều chỉnh hoa hồng

- Tiếp tục dùng `shopee_conversion_changes` của PLAN-074.
- Sau mỗi lần đồng bộ có thay đổi, bot gọi `scan_adjustments`. Với đơn đã nằm trong một kỳ MATCHED mà Shopee giảm hoa hồng hoặc gắn gian lận/từ chối, bot ghi một dòng `settlement_adjustments` (OPEN) gồm: cũ = số đã trả, mới, chênh, nguồn, khoá sự kiện, kỳ gốc.
- **Một sự kiện một dòng.** Gian lận làm hoa hồng về 0 sinh hai dòng lịch sử trong cùng lần báo, nhưng chỉ thành **một** điều chỉnh (khoá theo lần đồng bộ). Quét lại không tạo trùng.
- Điều chỉnh có chứng từ ở kỳ sau (khoản có `adjustment_vnd`) cũng thành một dòng (`source=settlement_item`).
- **Không thu hồi tiền, không đổi sổ ví, không trừ khách.** Ví đang khoá nên chưa có khoản nào đã chi để phải thu lại. Khi mở chi trả, chính sách thu hồi sẽ là một quyết định riêng.

---

## 9. Màn admin 🧾 Đối soát thanh toán

/admin → 🔗 Shopee Affiliate → **🧾 Đối soát thanh toán** (`c:sm:home`). Màn 🧾 Duyệt hoa hồng giữ nguyên. Dựng từ bản sao DB production:

```
Chưa có kỳ thanh toán nào được nhập.
HH chờ xác minh (bot)  18.740đ · 2 đơn
Shopee báo đã duyệt      Chưa xác minh
Shopee báo thanh toán    Chưa xác minh
Tiền thực nhận           Chưa xác minh
Thuộc đơn Cashback Bot   Chưa xác minh
Chênh lệch nhận/Shopee               —
Khoản cần kiểm tra                   0
ⓘ «Chứng từ khớp» chỉ nói chứng từ Shopee, số học và tiền ngân hàng khớp nhau. Ví khách vẫn khoá; thuế người nhận: chưa duyệt.
📥 Nhập chứng từ bằng công cụ trên máy chủ: python -m cashback_bot.settlement_import …
```

- **Nút:** 📅 Kỳ thanh toán · 📄 Chứng từ · 🏦 Đối chiếu tiền nhận · 🔍 Khoản chênh lệch · 🕘 Lịch sử đối soát · ◀️ Shopee Affiliate.
- **Chi tiết kỳ:** hoa hồng, điều chỉnh, phí, VAT, thuế, Shopee báo chuyển, "số học kỳ phải là", ngân hàng nhận, phân bổ 5 nhóm, chênh lệch, nút 📦 Đơn thuộc kỳ, 📄 Chứng từ kỳ, 🔄 Đối soát lại.
- **Thao tác có ghi:**
  - "👁 Đã xem chứng từ": không phải xác minh;
  - "🔄 Đối soát lại": tính lại từ chứng từ đã có, không thêm số liệu.
- **Không có nút** nhập số tiền, gán duyệt, gán đã trả, mở ví hay chi.
- **Nhập chứng từ:** công cụ trên máy chủ `python -m cashback_bot.settlement_import new-batch | import | show`.
  - Chỉ nhận file thường, không nhận symlink, tối đa 2 MB.
  - Người thực hiện được audit dạng `cli:<user>`.
  - Không nhận file qua Telegram trong V1.

---

## 10. Thuế và phí

| Loại | Nơi ghi | Ghi chú |
|---|---|---|
| Thuế Shopee khấu trừ hoa hồng của chủ bot | `tax_withheld_vnd` (theo chứng từ) | không lấy từ dự phòng 10% |
| Phí dịch vụ Shopee | `fee_vnd` | không thay bằng 0,98% |
| VAT trên phí | `fee_vat_vnd` + `fee_includes_vat` | phí đã gồm VAT thì không trừ VAT lần nữa; không rõ thì kỳ dừng ở `TOTALS_INCOMPLETE` |
| Thuế khi chủ bot trả cho người nhận | **không có trường nào** | `PAYOUT_TAX_POLICY = NOT APPROVED` (bảng `payout_tax_policies` vẫn chưa tồn tại) |
| Dự phòng lúc báo giá | `reserve_policies` (không đổi) | chỉ dùng cho báo giá V1.2 |

---

## 11. Bảo mật

- **Quyền:**
  - mọi `c:sm:*` đi qua kiểm tra admin và chat riêng có sẵn;
  - callback sai định dạng, kỳ không tồn tại, hoặc nút không có thật (ví dụ `c:sm:paid:1`) đều bị từ chối;
  - callback cũ chỉ đọc hoặc tính lại, không có tác dụng phụ về tiền.
- **Chứng từ:**
  - lưu ở `data/settlement_evidence/` (thư mục 0700, file 0600), cạnh DB, không nằm trong git;
  - tên file là sha256, không dùng tên người gửi, nên không có path traversal;
  - nội dung chỉ được đọc như JSON, không thực thi.
- **Log và màn hình:** công cụ nhập không in nội dung chứng từ; audit chỉ lưu tổng số, sha và mã chứng từ; màn admin không hiện số tài khoản.
- **Chống trùng:** theo nội dung, theo mã chứng từ, theo kỳ + mã thanh toán, theo đơn trong file, theo sự kiện điều chỉnh.

---

## 12. Migration

Tự chạy trong `repo.migrate()`: `CREATE TABLE/INDEX/TRIGGER IF NOT EXISTS` cho 5 bảng và 3 trigger chỉ-thêm. Không sửa bảng cũ, không đổi dữ liệu.

**Diễn tập trên bản sao DB production** (Backup API, 0600, đã xoá), `migrate()` chạy 2 lần:
- chỉ thêm `settlement_adjustments`, `settlement_audit`, `settlement_batches`, `settlement_evidence`, `settlement_items`;
- không bảng cũ nào đổi số dòng; conversion và sổ ví giống hệt trước;
- 4 trigger khoá còn nguyên;
- không có `shopee_settlements` / `payout_tax_policies`; ví khoá với 2 lý do;
- `integrity_check = ok`.

---

## 13. Bằng chứng test

| Nhóm | Test (file `tests/test_cashback_settlement.py`) | Kết quả |
|---|---|---|
| Toàn bộ | `tests/test_cashback_*.py` | **412 passed** (368 + 44), ruff sạch |
| Chứng cứ (1–10) | fixture hợp lệ → MATCHED; thiếu chứng từ → EVIDENCE_PENDING; trùng nội dung/mã → từ chối; cùng kỳ hai mã thanh toán được, trùng mã bị chặn; số âm/thực/chuỗi/bool bị chặn; file giả (rỗng, nhị phân, CSV, sai format, `../`, quá 2 MB) bị chặn; symlink và thư mục bị chặn; sai kỳ, trùng đơn trong file; lưu theo sha 0600/0700; đơn không rõ → UNKNOWN_ORDER; thay chứng từ giữ lịch sử | pass |
| Đối soát quỹ (11–23) | khớp hoàn toàn; ngân hàng thiếu/thừa → DISPUTED; ngoài bot không vào quỹ; thuế và VAT trong số học; phí gồm VAT không trừ hai lần; không rõ VAT → chưa đủ; nhiều lần trả một kỳ; trả một phần → cần kiểm tra; tổng đơn vượt tổng kỳ → DISPUTED; chỉ có tổng → chưa phân bổ, không gán SETTLED; số nguyên chính xác; trùng kỳ → DUPLICATE, điều chỉnh có chứng từ → một dòng | pass |
| Duyệt và điều chỉnh (24–30) | báo cáo xác thực không tạo APPROVED; PAID/COMPLETED chưa SETTLED khi chưa có kỳ; báo cáo thiếu đơn không xoá đơn; Shopee trả cho đơn gian lận → cần kiểm tra; giảm hoa hồng sau kỳ → 1 điều chỉnh, quét lại 0, gian lận → đúng 1 điều chỉnh nữa; đảo kỳ → NOT_VERIFIED | pass |
| An toàn (31–38) | kỳ MATCHED không mở ví, rút trả `locked`, nút bật ví bị từ chối, 0 khoản `available`, 0 payout, trigger chặn SQL, không có bảng mở khoá; chỉ admin, callback giả bị chặn; audit và chứng cứ không sửa/xoá được; migrate 2 lần không trùng | pass |
| Màn admin và công cụ | chưa có chứng từ → "Chưa xác minh" (không 0đ), có hướng dẫn nhập, nút ở màn Shopee; chi tiết kỳ, đơn thuộc kỳ, đã xem ≠ xác minh, lịch sử, đối soát lại; màn đối chiếu ngân hàng và chênh lệch; công cụ `new-batch/import/show` | pass |
| Regression (39–48) | V1.1/V1.2, Sub ID, gian lận và lịch sử PLAN-074, cô lập update, backup, menu admin cũ: các bộ test cũ (368) vẫn pass; không test nào gọi Shopee hay Telegram thật | pass |

---

## 14. Triển khai production

**Đã triển khai 24/10/2026** tại `6dc2dd1`, PID 604968. Mọi kiểm tra sau triển khai đều đạt: 5 bảng mới, khoá còn nguyên, ví tắt, 0 khoản `available` hay payout, 0 lỗi trong log. Chi tiết: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN075.md`.

Trình tự:
1. Backup bằng Backup API, verify.
2. `git merge --ff-only` lên `main`, chạy test, push.
3. Chủ bot restart.
4. Migration tự chạy.
5. Kiểm tra: process, log, schema, dữ liệu cũ, menu admin, khoá tài chính, không có khoản `available` hay payout mới.

---

## 15. Rollback

- **Rollback code:** `git revert` commit PLAN-075 rồi restart. Năm bảng mới để lại vô hại (code cũ không đọc); trigger khoá không bị đụng.
- **Không restore DB** chỉ để rollback code: sẽ mất link, conversion và lịch sử mới.
- Chỉ restore khi DB hỏng, theo `cashback_bot/BACKUP.md`, từ bản backup trước triển khai.
- Không gỡ khoá tài chính để giải quyết lỗi tương thích.

---

## 16. Rủi ro còn lại

- **Định dạng chứng từ thật chưa biết.** Parser cho báo cáo Shopee và sao kê phải viết khi có mẫu; công cụ nhập hiện chỉ nhận định dạng chuẩn.
- **Định dạng chuẩn do người vận hành tạo.** Người có quyền máy chủ có thể tự soạn số. Giảm rủi ro bằng: hai nguồn độc lập phải khớp, lưu bản gốc theo sha, audit không sửa được. Khi có parser thật nên nhập trực tiếp file Shopee/ngân hàng gốc.
- **APPROVED vẫn chặn.** Đối soát chỉ chứng minh "đã trả", chưa chứng minh "đã duyệt" theo từng đơn.
- **Thuế người nhận chưa duyệt.**
- **Điều chỉnh mới chỉ được ghi**, chưa có quy trình xử lý (RESOLVED/DISPUTED bằng tay) trong giao diện.
- Đồng bộ và quét điều chỉnh vẫn chạy trong vòng poll; dữ liệu hiện nhỏ nên không đáng kể.

---

## 17. Việc chờ chủ bot

1. **Gửi mẫu chứng từ thật** cho kỳ gần nhất có tiền: báo cáo **Thanh toán** Shopee Affiliate (CSV/PDF), **sao kê** hoặc chứng từ ngân hàng của khoản Shopee chuyển, và nếu có, báo cáo **Xác thực** hoa hồng. Che số tài khoản nếu muốn; em cần cấu trúc cột và một kỳ có số liệu để viết parser và kiểm thử.
2. **Quyết định thuế người nhận** (hỏi kế toán).
3. Quyết định chính sách khi Shopee thu hồi hoa hồng đã chi (trừ vào kỳ sau, hay chủ bot chịu).
4. Sau khi có mẫu: duyệt PLAN-076/077 (parser + APPROVED có chứng từ), rồi PLAN-078 (nối đối soát vào khoá, mở ví có điều kiện).

---

## 18. Release gates

| Gate | Kết luận | Lý do |
|---|---|---|
| Evidence Discovery | **CONDITIONAL** | Đã khảo sát đủ 4 nguồn; chưa có mẫu thật của nguồn 2, 3, 4 |
| Approved Commission Evidence | **BLOCKED** | Không có dữ liệu Shopee chứng minh duyệt theo đơn |
| Settlement Recording | **GO** | Ghi kỳ và chứng cứ có kiểm soát, chống trùng, chỉ thêm, audit |
| Bank Reconciliation | **CONDITIONAL** | Engine đúng với fixture; chưa có sao kê thật |
| Fund Allocation | **GO** | Tách bot / ngoài bot / không rõ / chưa phân bổ; không chia tỷ lệ; quỹ chỉ có khi MATCHED |
| Commission Adjustments | **GO** | Một sự kiện một dòng, có nguồn và kỳ gốc; không thu tiền |
| Tax/Fee Evidence | **CONDITIONAL** | Lưu và đối chiếu thuế/phí/VAT theo chứng từ; thuế người nhận NOT APPROVED |
| Admin UI | **GO** | Số liệu thật, "Chưa xác minh" khi thiếu, không có nút tạo bằng chứng |
| Migration | **GO** | Chỉ thêm, idempotent, đã diễn tập trên bản sao DB thật |
| Regression | **GO** | 412/412 |
| Production Deployment | **GO** (phần ghi chứng cứ và đối soát) | Không tạo nghĩa vụ chi; khoá giữ nguyên |
| Wallet Activation | **NOT AUTHORIZED** | |
| Payout | **NOT AUTHORIZED** | |

---

## Câu hỏi cuối cùng

**Q1. Bot có biết khoản hoa hồng nào đã được Shopee duyệt thật không?**
**Chưa.**
- Báo cáo conversion của Shopee không có field "đã duyệt" (PLAN-074).
- Chưa có báo cáo Xác thực thật nào được nhập. Nếu nhập, bot chỉ lưu "Shopee báo đã duyệt (chưa đối chiếu)", không tự đổi đơn thành APPROVED.

**Q2. Bot có xác minh được Shopee đã chuyển tiền vào ngân hàng không?**
**Có khả năng, nhưng chưa làm được với dữ liệu thật.** Khi nhập báo cáo thanh toán Shopee và chứng từ ngân hàng của cùng kỳ, bot đối chiếu số Shopee báo chuyển với số ngân hàng nhận. Chỉ khi hai nguồn khớp (và số học kỳ đúng) thì chứng từ mới được đánh "đã đối chiếu". Hiện chưa có chứng từ thật nên mọi số đều "Chưa xác minh".

**Q3. Một kỳ Shopee chuyển 1.000.000đ nhưng chỉ 200.000đ thuộc đơn qua bot thì sao?**
- 200.000đ (các khoản khớp đơn bot) vào "Đơn qua bot". Đó là quỹ có chứng từ, chỉ có khi cả kỳ khớp, và vẫn không phải tiền khách được rút.
- 800.000đ còn lại nằm ở "Đơn ngoài bot", "Không rõ đơn" hoặc "Chưa phân bổ", tuỳ chứng từ có chi tiết theo đơn hay không.
- Không đồng nào của phần này vào quỹ cashback, và bot không chia theo tỷ lệ.

**Q4. Chứng từ Shopee lệch với số ngân hàng nhận thì sao?**
Kỳ chuyển **🔴 Có chênh lệch**:
- chênh lệch được ghi là "ngân hàng nhận thiếu" hoặc "nhận thừa", kèm số tiền;
- kỳ hiện ở màn 🔍 Khoản chênh lệch và 🏦 Đối chiếu tiền nhận ("Shopee báo X · nhận Y · lệch Z");
- chứng từ không được đánh "đã đối chiếu", không đơn nào được ghi SETTLED.

Bot không tự cho là khớp.

**Q5. Shopee giảm hoặc thu hồi hoa hồng ở kỳ sau thì ghi nhận thế nào?**
- Nếu đơn đã nằm trong một kỳ khớp: lần đồng bộ thấy hoa hồng giảm hoặc gian lận sẽ tạo đúng **một** dòng điều chỉnh OPEN (số đã trả → số mới, chênh, nguồn, kỳ gốc), hiện ở 🔍 Khoản chênh lệch.
- Nếu kỳ sau có chứng từ điều chỉnh: cũng thành một dòng.
- Không xoá số cũ, không thu tiền, không trừ khách.

**Q6. Có trường hợp nào bot tự chuyển đơn thành APPROVED hoặc SETTLED khi không có bằng chứng không?**
- **APPROVED: không có trường hợp nào.** Không đường code nào gán.
- **SETTLED: chỉ khi** đơn có khoản khớp trong một kỳ mà báo cáo thanh toán và chứng từ ngân hàng khớp nhau, số học đúng và không có chênh lệch. Tổng kỳ không có chi tiết đơn, hay chỉ có một nguồn, đều không tạo SETTLED. Kỳ bị đảo thì về NOT_VERIFIED.

**Q7. Có đường nào làm ví bật hoặc cho chi tiền khi chưa đủ điều kiện không?**
**Không.**
- Đối soát dùng bảng riêng, không chạm điều kiện mở khoá.
- 4 trigger SQLite và `payout_gate` giữ nguyên.
- Đã test: sau một kỳ MATCHED, ví vẫn khoá, rút trả `locked`, nút bật ví bị từ chối, SQL trực tiếp bị chặn, 0 khoản `available`, 0 payout.

**Q8. Còn thiếu gì để làm PLAN-076 và PLAN-077?**
1. **Mẫu chứng từ thật:** báo cáo Thanh toán, sao kê/chứng từ ngân hàng, báo cáo Xác thực, của ít nhất một kỳ có tiền.
2. Từ mẫu đó: parser chuyển file gốc về `cashback_settlement_v1`, kèm test với file thật đã che dữ liệu.
3. Quyết định cơ chế APPROVED có chứng từ: map báo cáo xác thực theo đơn, xác minh field, audit, nghiệm thu riêng.
4. Quyết định thuế người nhận; chính sách xử lý điều chỉnh / thu hồi.
5. Quy trình xử lý điều chỉnh trong giao diện (RESOLVED / DISPUTED có audit).
