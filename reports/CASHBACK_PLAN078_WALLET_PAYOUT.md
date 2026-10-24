# PLAN-078 — Wallet & Payout Readiness V1

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Nhánh | `cursor/cashback-plan078-payout`, tách từ `main@88ebf63` (production `5a14fc1`) |
| Worktree | `/home/vu/toolsauto-cashback-payout` |
| ADR | ADR-055 (mới) |
| Trạng thái | **CODE READY.** Chưa merge, chưa triển khai. Gate A chờ review; Gate B (mở ví, chi tiền) **NOT AUTHORIZED** |

> **CODE READY ≠ TEST READY ≠ FINANCIAL READY ≠ LIVE PAYOUT ENABLED.** Bản này chỉ đạt CODE READY: code chạy đúng trên DB test. Production vẫn khoá và không phát sinh đồng nào.

---

## 1. Tóm tắt

- **Không dựng ví mới.** Bản này hoàn thiện ví PLAN-066:
  - mỗi đồng trong yêu cầu rút trỏ về đúng đơn (`payout_allocations`);
  - yêu cầu rút đi theo máy trạng thái 11 bước, có lịch sử chỉ thêm (`payout_events`);
  - tài khoản ngân hàng có lịch sử và bước xác minh có bằng chứng;
  - quỹ chi trả lấy từ các kỳ đối soát khớp của PLAN-075;
  - hạn mức ở dạng bản nháp, chưa có hiệu lực.
- **Chống rút trùng bằng ba lớp:**
  - transaction `BEGIN IMMEDIATE`;
  - unique index một phần ở DB: mỗi khách tối đa một yêu cầu còn giữ tiền;
  - khoá chống gửi lặp theo mã callback Telegram và số phiên bản của từng nút.
  Đã chạy thử song song thật bằng thread.
- **Không trả thiếu bằng chứng:**
  - không có đường từ "mới gửi" tới "đã trả";
  - "đã trả" chỉ ghi được từ "đã gửi, chờ xác nhận" và phải có mã chứng từ ngân hàng;
  - trigger DB chặn, kể cả khi sửa bằng SQL trực tiếp.
- **Không trả lại hai lần:** đã gửi lệnh rồi thì không còn nút từ chối hay huỷ để giải phóng tiền. Chỉ còn "thất bại" kèm chứng từ, hoặc xác nhận đã trả. Bot không tự chuyển lại.
- **Khoá tài chính chặt hơn:**
  - trigger mới khoá cả các bước duyệt chi, đang chuyển, đã gửi;
  - khoản chỉ vào ví khi đơn đã đối soát khớp (SETTLED) và không có điều chỉnh đang mở;
  - thêm 9 điều kiện hệ thống mới, cộng vào 2 điều kiện cũ.
- **Phát hiện và sửa một lỗ:** quỹ cũ (`payout_headroom`) chỉ trừ yêu cầu ở trạng thái `requested` và `paid`. Giờ tính đủ mọi trạng thái còn giữ tiền và đã trả.
- **Không đổi:** 2 khoản pending thật, công thức tiền, điều khoản V1, cờ `CASHBACK_TERMS_REQUIRED=OFF`.
- **554 test pass** (521 + 33 test mới; 17 test cũ viết lại theo máy trạng thái).

---

## 2. Baseline production (kiểm tra lại trước khi code)

| Mục | Giá trị |
|---|---|
| Git | `main@88ebf63` (code `5a14fc1`), sạch; PID 620902 |
| Backup gần nhất | `cashback-20261024T060320Z.sqlite` |
| Sổ ví | 2 khoản `pending`: 12.157đ, 960đ |
| Yêu cầu rút | 0 |
| `bank_accounts` | 1 dòng (tài khoản thử của admin, VCB) |
| Kỳ đối soát | 0 |
| Khoá | 4 trigger; không có bảng mở khoá; `wallet_enabled=0` |
| Điều khoản | V1 đã công bố; 1 lượt đồng ý (chủ bot); `CASHBACK_TERMS_REQUIRED` không đặt (tắt) |
| Test | 521 passed |

---

## 3. Audit ví hiện có

| Chức năng | Đã có | Thiếu | Cần sửa | Không cần xây lại |
|---|---|---|---|---|
| Sổ `cashback_entries` (pending / holding / available / cancelled) | ✅ | điều kiện đối soát theo đơn | `entry_payable` thêm SETTLED + không điều chỉnh OPEN | ✅ giữ |
| Số dư | ✅ gộp | truy từng đồng | thêm phân bổ; `Balance.held_vnd` | ✅ công thức gộp giữ để đối chiếu |
| Yêu cầu rút `cashback_payouts` | ✅ requested / paid / rejected | máy trạng thái, phiên bản, chống gửi lặp | mở rộng cột, trạng thái | ✅ giữ bảng |
| Một yêu cầu mở mỗi khách | ✅ trong code | ở tầng DB | unique index một phần | — |
| Chụp tài khoản vào yêu cầu | ✅ | — | — | ✅ |
| `bank_accounts` | ✅ ghi đè | lịch sử, xác minh | bảng lịch sử và xác minh | ✅ giữ bảng hiện tại |
| VietQR (NAPAS, CRC) | ✅ | — | chỉ hiện ở bước "đang chuyển" | ✅ |
| Admin duyệt | ✅ requested → paid | các bước, chứng từ | viết lại theo máy trạng thái | — |
| Khoá tài chính | ✅ 2 bảng + 4 trigger | trạng thái mới, điều kiện mới | thêm điều kiện và trigger, không gỡ gì | ✅ |
| Quỹ | ✅ bảng nháp `shopee_settlements` | quỹ từ đối soát thật | `fund_position` từ `settlement_*`; sửa lỗ quỹ cũ | ✅ giữ quỹ cũ |
| Hạn mức | ✅ rút tối thiểu, số ngày giữ | tối đa, ngày, tháng | `payout_limit_policies` (mặc định không có) | ✅ |

---

## 4. Mô hình sổ

| Khái niệm | Nguồn | Ghi chú |
|---|---|---|
| Pending (chờ Shopee) | entry `pending` | không bao giờ rút được, không tính vào quỹ |
| Held (đang giữ) | entry `holding`: đã hoàn thành nhưng thiếu APPROVED, SETTLED, snapshot chứng minh được, hoặc có điều chỉnh OPEN | |
| Available | entry `available`: đủ mọi bằng chứng | chỉ khi khoá mở |
| Reserved for payout | Σ yêu cầu ở trạng thái còn giữ tiền | phân bổ trỏ về entry; không nằm trong Available |
| Paid | Σ `paid_confirmed` (và `paid` cũ) | không rút lại được |
| Released | `rejected` / `cancelled` / `failed` / `returned` | tiền trở lại Available; lịch sử giữ nguyên |

**Công thức:** rút được = available − reserved − paid. Công thức này không đổi.

**Truy vết:** `payouts.allocations` trả về, cho mỗi phân bổ, đúng khoản trong sổ ví và các thông tin: link, snapshot chính sách, trạng thái duyệt, trạng thái đối soát, kỳ đối soát.

**Bất biến** (`payouts.invariants`):
- phân bổ = số tiền yêu cầu;
- không giữ quá số của một khoản;
- khoản đang giữ phải còn `available`;
- số dư không âm.

Vi phạm về cấu trúc (phân bổ lệch, giữ quá số) chặn mọi lần ghi. Khoản bị huỷ khi đang giữ thì yêu cầu tự chuyển "cần xử lý", không trừ tiền khách.

**Ví dụ B3 (test 01):**
- khách có 50.000đ đang chờ, 30.000đ đủ điều kiện, 10.000đ đang giữ;
- rút 20.000đ: đang giữ cho yêu cầu 20.000đ, còn rút được 10.000đ; 50.000đ và 10.000đ không đổi;
- yêu cầu thứ hai bị chặn;
- từ chối có lý do: còn rút được 30.000đ, có lịch sử.

---

## 5. Tài khoản nhận tiền

- **Kiểm định dạng** (`parse_bank_text`, giữ nguyên): ngân hàng trong danh mục, số 6–19 chữ số, tên chỉ gồm chữ cái (bỏ dấu, viết hoa).
- **Lịch sử** `bank_account_history`:
  - mỗi lần thêm hoặc đổi tài khoản ghi một dòng, chỉ gồm 4 số cuối + sha256 (không lưu số đầy đủ), chỉ thêm;
  - lưu lại cùng tài khoản thì không ghi thêm;
  - tài khoản đã khai trước PLAN-078 được ghi một dòng `add` khi migrate.
- **Xác minh** `bank_account_verifications`:
  - admin nhập bằng chứng (≥ 4 ký tự), ví dụ "chuyển thử 1.000đ, app hiện đúng tên";
  - gắn với đúng sha của tài khoản: đổi tài khoản là về UNVERIFIED;
  - **tạo được QR không phải là xác minh** (test 15).
- **Dùng chung tài khoản:** màn chi tiết cảnh báo khi nhiều khách khai cùng một tài khoản (theo sha).
- **Đổi tài khoản khi đang có yêu cầu rút:** yêu cầu giữ tài khoản đã chụp và chuyển "cần xử lý" (test 13, 37). Bot không âm thầm đổi đích chuyển.
- **Che dữ liệu:**
  - màn chi tiết yêu cầu chỉ hiện ••••4 số cuối;
  - số đầy đủ chỉ hiện ở bước "Đang chuyển", cùng mã QR;
  - không ghi số tài khoản vào log (test 17).
- **VietQR:** đúng ngân hàng, số tài khoản, số tiền, nội dung chuyển (test 14). Màn ghi "Mã QR không chứng minh đã chuyển tiền".

---

## 6. Máy trạng thái yêu cầu rút

```
requested ─► under_review ─► approved_for_payment ─► processing ─► sent_unconfirmed ─► paid_confirmed ─► returned*
    │              │                  │                   │                │
    ├► rejected*   ├► rejected*        ├► cancelled*       ├► failed*†      ├► failed*†
    ├► cancelled*  └► needs_review     └► needs_review     └► needs_review  └► needs_review
    └► needs_review ─► under_review | sent_unconfirmed | rejected*(nếu chưa từng gửi) | failed*†

*  cần lý do     † cần chứng từ ngân hàng     returned cần lý do + chứng từ
```

- **Bước đưa tiền ra** (duyệt chi, đang chuyển, đã gửi, đã trả) kiểm lại mỗi lần bấm:
  - khoá cũ và điều kiện mới;
  - điều khoản chi trả của khách;
  - tài khoản đã xác minh;
  - quỹ có chứng từ;
  - hạn mức;
  - bước đã trả kiểm thêm quỹ cũ.
- **Tầng DB:**
  - trigger `financial_lock_payout_progress` khoá các trạng thái đưa tiền ra;
  - trigger `payout_paid_needs_evidence` chỉ cho ghi đã trả từ đã gửi, khi đã có sự kiện kèm chứng từ.
- **Ba cặp khác nhau, không được nhầm:**
  - admin bấm "Bắt đầu chuyển" ≠ ngân hàng đã chuyển;
  - có mã QR ≠ đã gửi;
  - "đã gửi, chờ xác nhận" ≠ đã trả.
- **Chống trùng:**
  - mỗi nút mang số phiên bản; nút cũ trả "Nút đã cũ";
  - mỗi bước có khoá chống gửi lặp (`admin:<id>:<payout>:<version>:<đích>`);
  - lần bấm rút của khách có khoá `cb:<user>:<callback id>`.

---

## 7. Quỹ có chứng từ

- `payouts.fund_position`:
  - chỉ tính các kỳ `settlement_batches.status = 'MATCHED'`;
  - quỹ của mỗi kỳ = max(0, tiền đơn bot khớp − phí − VAT chưa gồm − thuế khấu trừ của cả kỳ);
  - **giả định toàn bộ phí và thuế kỳ rơi vào đơn bot, nên không bao giờ cấp quá.** Không chia theo tỷ lệ ước tính.
- **Không vào quỹ:** tiền đơn ngoài bot, không rõ đơn, chưa phân bổ, hoa hồng pending, số dư ngân hàng của chủ bot, dự phòng 10%.
- **Điều kiện chi:** đang giữ + đã trả ≤ quỹ, kiểm khi tạo yêu cầu và ở mọi bước đưa tiền ra. Quỹ cũ (`shopee_settlements`) vẫn phải đạt.
- **Thiếu quỹ:** bot trả `fund`, không tạo yêu cầu, không ghi đã trả. Màn admin hiện quỹ còn lại, hoặc "Chưa xác minh" khi chưa có kỳ khớp (không hiện 0đ). Không vay quỹ kỳ khác.
- **Ví dụ test 43:** kỳ có 20.000đ đơn bot, 800.000đ đơn ngoài bot, 50.000đ không rõ đơn, phí 1.000 + VAT 100 + thuế 2.000 → quỹ **16.900đ**. Kỳ chuyển DISPUTED thì quỹ thành "Chưa xác minh".

---

## 8. Hạn mức

- Bảng `payout_limit_policies` (chỉ thêm) gồm: tối thiểu, tối đa một lần, tổng ngày, tổng tháng của cả bot, tối đa 1 yêu cầu mở mỗi khách.
- Chỉ dòng mới nhất ở trạng thái `ACTIVE` và có người duyệt mới có hiệu lực. **Mặc định không có dòng nào, nên khoá.**
- Có hàm tạo bản nháp (`create_limit_draft`, trạng thái DRAFT). Bản nháp không có hiệu lực và làm hạn mức đang dùng mất hiệu lực (test).
- Rút tối thiểu thực tế = số lớn hơn giữa cài đặt ví và hạn mức.
- **Không đặt số production nào.**

---

## 9. Quy trình chuyển khoản tay

1. Khách gửi yêu cầu, nhận mã `Hoan tien 000123` (duy nhất).
2. Admin: 🔎 Bắt đầu kiểm tra, xem nguồn từng đồng, điều kiện, lịch sử.
3. ✅ Xác minh tài khoản người nhận, kèm bằng chứng.
4. 🟢 Duyệt chi: kiểm lại mọi điều kiện.
5. 🏦 Bắt đầu chuyển khoản: bot hiện số tài khoản đầy đủ và mã QR (đúng ngân hàng, số tiền, nội dung).
6. 📤 Đã gửi lệnh, chờ biên nhận: bấm ngay sau khi gửi, kể cả khi app treo.
7. ✅ Xác nhận đã trả: nhập mã giao dịch trên biên nhận hoặc sao kê. Bot báo khách.

- Mỗi bước có màn hỏi lại.
- Bước cần lý do hoặc chứng từ thì bot chờ admin gõ (10 phút, lưu trong RAM).
- Không kết nối API ngân hàng (test 60 quét mã nguồn).

---

## 10. Thất bại và phục hồi

| Tình huống | Cách xử lý |
|---|---|
| Khách nhập sai tài khoản | → cần xử lý (có lý do) → từ chối nếu chưa từng gửi lệnh (tiền về ví, báo khách), hoặc kiểm tra lại |
| Ngân hàng từ chối | thất bại, **cần chứng từ** (ví dụ "GD lỗi mã E05, không trừ tiền"); tiền về ví |
| Chưa rõ kết quả (app treo) | đã gửi, chờ xác nhận / cần xử lý; tiền **vẫn giữ**; **không có đường từ chối, huỷ hay quay lại bước chuyển**; khách không tạo được yêu cầu thứ hai |
| Admin bấm nhầm | mọi bước có màn hỏi lại; bước đã trả bắt buộc nhập chứng từ; không xoá lịch sử |
| Bot restart giữa chừng | trạng thái và lịch sử lưu trong DB; sau restart không tự làm gì; admin thấy yêu cầu chưa kết luận ở màn Ví khách (test 29) |
| Ngân hàng hoàn khoản đã trả | hoàn lại, cần lý do và chứng từ; sự kiện `paid_confirmed` giữ nguyên trong lịch sử; tiền về ví; **không tự trừ khách** |

---

## 11. Trải nghiệm khách

- **Ví đóng (hiện tại):** "👛 Ví hoàn tiền chưa mở. Các khoản được ghi nhận đang chờ Shopee xác minh và đối soát; chưa thể yêu cầu rút." Không có nút rút; không hiện 13.117đ là tiền rút được.
- **Ví mở (tương lai):**
  - các dòng: có thể rút, đang chờ Shopee xác minh, đang giữ chờ đủ điều kiện, đã nhận, đang xử lý rút (kèm trạng thái dễ hiểu);
  - lỗi rõ ràng: cần đồng ý điều khoản chi trả, vượt hạn mức, quỹ chưa đủ…
- **Báo khách** chỉ khi có kết luận: đã trả (có chứng từ), tiền về ví (kèm lý do), cần kiểm tra thêm. Không báo ở bước duyệt chi hay đang chuyển, tránh hứa sớm.
- Không gửi tin chủ động nào trong PLAN này.

---

## 12. Màn admin

- **👛 Ví khách:**
  - trạng thái khoá: 2 lý do gốc, cộng số điều kiện PLAN-078 còn thiếu;
  - chờ duyệt (và đang giữ), trong ví, đang giữ cho yêu cầu rút, đã trả;
  - quỹ có chứng từ (hoặc "Chưa xác minh");
  - đếm theo trạng thái; cảnh báo sổ.
- **Chi tiết yêu cầu:**
  - người nhận dạng che, trạng thái xác minh, cảnh báo dùng chung;
  - nguồn từng đồng; ✅/❌ từng điều kiện; quỹ;
  - 8 sự kiện gần nhất, kèm chứng từ;
  - nút theo máy trạng thái: **ẩn bước đưa tiền ra khi còn khoá**, thay bằng "🔒 Bước chi tiền đang khoá".
- **⚖️ Sẵn sàng chi trả:** thêm ma trận điều kiện PLAN-078, quỹ có chứng từ, kiểm tra sổ.

---

## 13. Kiến trúc khoá tài chính

| Lớp | Điều kiện | Ở đâu |
|---|---|---|
| Cũ (giữ nguyên) | `shopee_settlements`, `payout_tax_policies` có dòng; 4 trigger | `payout_gate`, `db.SCHEMA` |
| Hệ thống (mới) | 6 quyết định APPROVED, hạn mức ACTIVE, ≥ 1 kỳ MATCHED, backup ≤ 48 giờ | `payout_readiness.system_conditions`, cộng vào `FinancialGate.readiness` |
| Khoản | APPROVED, SETTLED, snapshot chứng minh được, không gian lận, không điều chỉnh OPEN, đủ ngày giữ | `entry_payable` |
| Khách | đồng ý bản điều khoản chi trả | `user_conditions` |
| Yêu cầu | tài khoản đã xác minh, quỹ, hạn mức | `payout_conditions` |
| DB | khoá các trạng thái đưa tiền ra; đã trả cần chứng từ; một yêu cầu mở mỗi khách; bảng mới chỉ thêm | trigger, index |

- **Không có công tắc bỏ qua.**
- **Không tạo** `shopee_settlements` hay `payout_tax_policies`. Duyệt cả 6 quyết định cũng không làm mất 2 lý do khoá cũ (test 52).
- **Test** chỉ dựng dữ liệu trong DB test (`_financially_ready`, `_payout_policies_ready`), không dùng bản sao DB thật để gán APPROVED.

---

## 14. Phụ thuộc thuế, điều khoản, thu hồi

| Quyết định | Nơi lưu | Trạng thái |
|---|---|---|
| Thuế người nhận | `payout_policy_decisions.topic = tax` | chưa có dòng = chưa duyệt (chờ kế toán, PLAN-077 mục 10.3) |
| Thu hồi hoa hồng đã chi | `clawback` | chưa duyệt |
| Điều khoản chi trả | `payout_terms` (cột reference = phiên bản điều khoản) | chưa có: V1 không chứa điều kiện chi trả |
| Xác minh tài khoản | `bank_verification` | chưa duyệt (quy trình đề xuất ở mục 5) |
| Hạn mức | `payment_limits` + `payout_limit_policies` | chưa có |
| Quy trình chuyển khoản và chứng từ | `manual_payment` | chưa duyệt (đề xuất ở mục 9) |

- Bot **không có nút duyệt** các quyết định này. Ghi quyết định là việc làm sau khi chủ bot quyết, qua một bước phát hành riêng.
- Điều khoản V1 giữ nguyên; khách vẫn không bắt buộc đồng ý khi tạo link.
- Muốn bắt đồng ý trước khi **rút**: tạo một bản điều khoản mới có điều kiện chi trả, rồi trỏ quyết định `payout_terms` tới bản đó. Không áp hồi tố cho link cũ.

---

## 15. Bảo mật

- Mọi `c:wl:*` chỉ dành cho admin trong chat riêng.
- Callback sai định dạng, nút cũ (sai phiên bản) hay trạng thái không cho phép đều bị từ chối (test 28).
- Số tài khoản đầy đủ: chỉ có trong `bank_accounts`, bản chụp trong yêu cầu, và màn "Đang chuyển". Lịch sử chỉ có 4 số cuối và sha; log không có.
- Lý do và chứng từ được làm sạch (che token, cookie, số giống thẻ) và giới hạn 300 ký tự.
- 6 bảng mới đều chỉ thêm, trigger chặn sửa và xoá.

---

## 16. Migration

- **Cơ chế:** tự chạy trong `repo.migrate()`, idempotent.
  - thêm 6 bảng;
  - 3 cột `cashback_payouts` (`version` mặc định 1, `idempotency_key`, `account_sha`);
  - 2 unique index một phần;
  - 2 trigger mới và các trigger chỉ-thêm;
  - ghi lịch sử cho tài khoản đã khai.
  Không sửa dữ liệu tiền.
- **Diễn tập trên bản sao DB production** (0600, đã xoá; `migrate()` 2 lần, khởi động service 2 lần, làm mới ví một lần, mở các màn):

| Kiểm tra | Kết quả |
|---|---|
| Bảng mới | `payout_allocations`, `payout_events`, `bank_account_history`, `bank_account_verifications`, `payout_policy_decisions`, `payout_limit_policies` |
| Bảng cũ | hash không đổi, trừ `updated_at` của sổ ví và các cột mới thêm vào `cashback_payouts` (0 dòng) |
| Khoản pending | 12.157 / 171 / 1.737 và 960 / 14 / 138, `pending` |
| Lịch sử tài khoản | 1 dòng `add` (VCB, 4 số cuối) cho tài khoản đã khai |
| Khoá | 4 trigger cũ còn; thêm `financial_lock_payout_progress`, `payout_paid_needs_evidence`; bật ví bị chặn; tạo yêu cầu rút trả `locked` |
| Bất biến | ổn |
| `integrity_check` | ok |

---

## 17. Bằng chứng test

- `tests/test_cashback_*.py`: **554 passed** (521 + 33), ruff sạch. Không test nào gọi Shopee, Telegram hay ngân hàng.

| Nhóm PLAN | Test (`test_cashback_payout_lifecycle.py` và các test viết lại) |
|---|---|
| Sổ ví 1–8 | ví dụ B3; chỉ vào ví khi APPROVED + SETTLED và không điều chỉnh OPEN; đã trả không rút lại; khoản bị huỷ khi đang giữ → cần xử lý, không trừ tiền; bất biến |
| Tài khoản 9–17 | định dạng; lịch sử không lưu số đầy đủ; đổi → UNVERIFIED; đổi khi đang có yêu cầu → cần xử lý, giữ đích; dùng chung; QR đúng nội dung và không phải xác minh; không log số |
| Yêu cầu 18–30 | hợp lệ; vượt số dư; vượt hạn mức; hạn mức nháp không hiệu lực; thiếu kỳ đối soát hoặc quyết định thuế → khoá; thiếu APPROVED, gian lận, từ chối → không vào ví; thiếu xác minh hoặc điều khoản; **hai yêu cầu đồng thời (thread)**; Telegram gửi lại; DB chặn hai yêu cầu mở; callback giả, sai quyền, sai phiên bản, requested → paid bị chặn; restart giữa chừng |
| Chuyển khoản 31–40 | đã trả cần chứng từ (cả qua SQL trực tiếp); ngân hàng từ chối cần chứng từ; chưa rõ kết quả không giải phóng và không quay lại; sai tài khoản; hoàn lại giữ lịch sử; không trả hai lần |
| Quỹ 41–50 | đủ / thiếu quỹ; pending không là quỹ; tiền ngoài bot, không rõ đơn, phí, thuế không vào quỹ; nhiều khách đồng thời không vượt quỹ; một khách một yêu cầu mở; hạn mức ngày và tháng |
| An toàn 51–60 | production vẫn khoá; quyết định không mở khoá cũ; trigger chặn bước chi tiền khi khoá; không có API chuyển tiền; link `unresolved` không vào ví (PLAN-077) |
| Regression 61–72 | toàn bộ test cũ: PLAN-073…077, V1.1/V1.2, Sub ID, đồng bộ, poller, phân quyền admin, backup, log an toàn |

---

## 18. Code thay đổi

| File | Thay đổi |
|---|---|
| `cashback_bot/payouts.py` (mới) | máy trạng thái, tạo yêu cầu, phân bổ, quỹ, hạn mức, tài khoản, bất biến |
| `cashback_bot/payout_readiness.py` (mới) | điều kiện hệ thống / khách / yêu cầu |
| `cashback_bot/db.py` | 6 bảng, trigger, cột, index, ghi lịch sử tài khoản |
| `cashback_bot/payout_gate.py` | cộng điều kiện mới; `entry_payable` thêm SETTLED và điều chỉnh OPEN; sửa lỗ quỹ cũ |
| `cashback_bot/wallet.py` | `request_payout` (số tiền, khoá chống gửi lặp), `advance` (thay `decide_payout`), `save_bank` ghi lịch sử, `bank_status`, `Balance.held_vnd`, đánh dấu khoản bị huỷ khi đang giữ |
| `cashback_bot/admin_wallet.py`, `admin_ui.py` | màn chi trả theo máy trạng thái, xác minh tài khoản, bảng tổng quan |
| `cashback_bot/admin_policy.py` | chuyển trạng thái chờ nhập cho Ví khách; lịch sử xác minh tài khoản |
| `cashback_bot/admin_readiness.py` | ma trận điều kiện PLAN-078, quỹ, kiểm tra sổ |
| `cashback_bot/messages.py`, `service.py` | chữ ví đóng và mở, lỗi rút, khoá chống gửi lặp theo callback |
| `tests/test_cashback_payout_lifecycle.py` (mới), `test_cashback_wallet.py`, `test_cashback_vietqr.py`, `test_cashback_safety_hardening.py`, `test_cashback_validation.py`, `test_cashback_terms_support.py` | 33 test mới; fixture DB test; viết lại luồng chi trả cũ |
| `agents/decisions/ADR-055-payout-lifecycle.md` | ADR |

---

## 19. Kế hoạch triển khai (Gate A, chỉ khi chủ bot duyệt)

1. Backup và verify.
2. `git merge --ff-only cursor/cashback-plan078-payout`, test, push.
3. Chủ bot restart.
4. Kiểm tra:
   - 6 bảng mới; 1 dòng lịch sử tài khoản;
   - 2 khoản pending giữ số;
   - ví vẫn tắt, bật ví bị chặn, tạo yêu cầu rút trả `locked`;
   - màn 👛 Ví khách và ⚖️ hiện đúng;
   - log sạch.

**Khách thấy:** câu ví đóng mới (chỉ khi mở `/vi`). Không có gì khác.

---

## 20. Rollback

- `git revert` rồi restart.
- 6 bảng mới, cột mới và trigger mới để lại vô hại: code cũ không đọc, và trigger chỉ khiến khoá chặt hơn.
- Unique index "một yêu cầu mở" vẫn đúng với code cũ.
- Không restore DB để rollback.

---

## 21. Quyết định còn chờ

1. **Gate A:** duyệt phát hành code (không mở gì).
2. **Thuế người nhận:** câu trả lời của kế toán (14 câu hỏi ở PLAN-077).
3. **Chính sách thu hồi** khi Shopee lấy lại hoa hồng đã chi.
4. **Điều khoản chi trả:** một bản điều khoản mới có điều kiện rút, thời điểm, cách xử lý thu hồi. Khi công bố, khách tự đồng ý.
5. **Hạn mức:** số tối thiểu, tối đa một lần, tổng ngày, tổng tháng.
6. **Cách xác minh tài khoản:** đề xuất chuyển thử 1.000đ khớp tên, hoặc khách xác nhận qua `/hotro`.
7. **Quy trình chuyển khoản và chứng từ cần lưu:** đề xuất ở mục 9.
8. **Bằng chứng thật:** báo cáo Xác thực (APPROVED), báo cáo Thanh toán và sao kê của một kỳ có tiền, để có kỳ MATCHED thật.
9. Ghi quyết định vào `payout_policy_decisions` qua một bước phát hành riêng: chưa có nút trong bot, cố ý.

---

## 22. Release gates

| Gate | Kết luận |
|---|---|
| Wallet Ledger | **GO** |
| Bank Account Validation | **CONDITIONAL**: định dạng, lịch sử, xác minh thủ công có; chưa có dịch vụ xác thực chủ tài khoản |
| Payout Request Lifecycle | **GO** |
| Double-Spend Protection | **GO** (transaction + unique index + khoá gửi lặp + phiên bản; test song song) |
| Fund Allocation | **CONDITIONAL**: đúng trên dữ liệu test; chưa có kỳ đối soát thật |
| Limit Rules | **CONDITIONAL**: cơ chế có; chưa có số được duyệt |
| Manual Payment | **GO** (code); quy trình chờ duyệt |
| Failed Payment Recovery | **GO** |
| Admin UI | **GO** |
| Customer UX | **GO** |
| Financial Lock | **GO** |
| Migration | **GO** |
| Regression | **GO** (554/554) |
| Production Code Deployment | **NOT AUTHORIZED UNTIL REVIEW** |
| Wallet Activation | **NOT AUTHORIZED** |
| Real Payout | **NOT AUTHORIZED** |

---

## Câu hỏi nghiệm thu

**Q1. Bot có chứng minh được mỗi đồng Available đến từ đơn nào, link nào, kỳ đối soát nào không?**
**Có, với khoản phát sinh từ nay.**
- Khoản chỉ thành Available khi đơn có khoản khớp trong một kỳ MATCHED (SETTLED) và link có snapshot.
- Mỗi đồng trong yêu cầu rút là một phân bổ trỏ về khoản sổ ví. Màn chi tiết hiện mã đơn, link, nhãn chính sách, trạng thái duyệt / đối soát và số kỳ.
- Hiện production chưa có khoản Available nào.

**Q2. Hai khoản pending 12.157đ và 960đ có giữ nguyên không?**
**Có.** Diễn tập trên bản sao: không đổi số, vẫn `pending`.

**Q3. Khách có 30.000đ Available gửi hai yêu cầu 20.000đ cùng lúc thì sao?**
- Một yêu cầu thành công, yêu cầu còn lại trả `pending_exists` (test chạy hai thread thật).
- Chỉ giữ 20.000đ, còn rút được 10.000đ.
- DB cũng chặn yêu cầu mở thứ hai bằng unique index.

**Q4. Admin bấm thanh toán nhưng ngân hàng chưa xác nhận thì bot ghi gì?**
- `sent_unconfirmed` ("Đã gửi, chờ xác nhận ngân hàng"), hoặc `needs_review` nếu cần kiểm tra.
- Chỉ thành `paid_confirmed` khi admin nhập mã chứng từ ngân hàng.

**Q5. Chuyển thất bại thì tiền được giải phóng lúc nào?**
Chỉ khi admin chuyển sang `failed` kèm lý do **và** chứng từ ngân hàng xác nhận lệnh không thực hiện. Trước đó tiền vẫn giữ.

**Q6. Admin đã chuyển nhưng bot restart trước khi lưu kết quả thì tránh chuyển lại thế nào?**
- Trạng thái lưu bền trong DB. Admin bấm "Đã gửi lệnh" ngay sau khi gửi.
- Sau restart, yêu cầu vẫn ở trạng thái cũ, hiện trên màn Ví khách; bot không tự làm gì.
- Không có đường quay lại bước chuyển hay từ chối để giải phóng tiền, và khách không tạo được yêu cầu thứ hai.
- Admin đối chiếu sao kê rồi xác nhận đã trả hoặc thất bại (kèm chứng từ).
- Trường hợp admin chưa kịp bấm "Đã gửi lệnh": yêu cầu ở bước "đang chuyển" và quy trình yêu cầu kiểm sao kê trước khi chuyển lại. Bot không có nút chuyển lại tự động.

**Q7. Khách đổi tài khoản sau khi gửi yêu cầu thì tiền chuyển vào đâu?**
- Vào **tài khoản đã chụp** lúc gửi yêu cầu.
- Yêu cầu chuyển "cần xử lý" để admin xác nhận lại. Bot không âm thầm đổi đích.

**Q8. Kỳ Shopee có cả đơn bot và ngoài bot, có lấy nhầm tiền ngoài bot để chi không?**
**Không.** Quỹ chỉ cộng các khoản khớp đơn bot, rồi trừ toàn bộ phí và thuế của kỳ. Tiền ngoài bot, không rõ đơn, chưa phân bổ đều không vào quỹ (test 43).

**Q9. Có cách nào dùng callback, config hay SQL để vượt khoá tài chính không?**
**Không tìm thấy cách nào.**
- Callback: kiểm admin, phiên bản và trạng thái; bước chi tiền kiểm lại mọi điều kiện.
- Config: không có công tắc bỏ qua.
- SQL: trigger khoá thêm yêu cầu, các trạng thái đưa tiền ra, `available`, và đã trả khi thiếu chứng từ.
- Ghi APPROVED cho cả 6 quyết định vẫn không mở được khoá cũ.

**Q10. Còn thiếu gì để tổ chức đợt chi trả thử đầu tiên?**
Các mục 2–8 ở phần 21, cộng việc Gate B:
- ít nhất một kỳ Shopee có báo cáo Thanh toán + sao kê khớp (MATCHED) và bằng chứng APPROVED theo đơn;
- quyết định thuế, chính sách thu hồi, điều khoản chi trả, hạn mức, cách xác minh tài khoản;
- một bước phát hành riêng để ghi các quyết định và mở khoá cũ;
- một đợt thử với 1–2 khách, số tiền nhỏ, theo dõi từng bước.
