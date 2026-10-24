# PLAN-077 — Customer Terms, Tax & Payout Policy Readiness V1

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Nhánh | `cursor/cashback-plan077-terms`, tách từ `main@cca8f8c` |
| Worktree | `/home/vu/toolsauto-cashback-terms` |
| ADR | ADR-054 (mới) |
| Trạng thái | **Đã triển khai 2026-10-24** tại `5a14fc1`, PID 620902 (chủ bot duyệt). Điều khoản V1 vẫn DRAFT. Chi tiết: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN077.md` |

---

## 1. Tóm tắt

- **Điều khoản theo phiên bản:**
  - bảng phiên bản (nháp → công bố → đã thay), nội dung không sửa được sau khi công bố;
  - chấp thuận chỉ ghi khi khách tự bấm đồng ý;
  - mỗi link mới ghi bản điều khoản lúc tạo, tách riêng khỏi snapshot tiền.
- **Dự thảo điều khoản V1** (5 mục, tiếng Việt dễ hiểu) viết đúng chức năng bot đang chạy, không hứa chi trả. **Chưa công bố**: khách vẫn thấy `/dieukien` cũ cho tới khi chủ bot đọc, duyệt và bấm công bố trong /admin.
- **Hỗ trợ và khiếu nại:**
  - khách dùng `/hotro` (6 danh mục) để mở yêu cầu, xem trạng thái, bổ sung thông tin;
  - admin dùng màn 📩 Hỗ trợ để xem dữ liệu đối chiếu, đổi trạng thái có lý do và trả lời qua bot;
  - ticket không chạm tiền.
- **⚖️ Sẵn sàng chi trả:** màn chỉ đọc. Gom lý do khoá, link chưa chứng minh chính sách, thuế và thu hồi hoa hồng (đều PENDING_REVIEW).
- **Cổng tài chính:** link `unresolved` hoặc chưa có snapshot **không bao giờ** vào ví.
- **Dữ liệu tối thiểu:**
  - tin không phải link không còn bị lưu nội dung;
  - màn admin xem khách che số tài khoản;
  - nội dung ticket che token và số giống số thẻ.
- **Thuế:** đã lập bản đồ pháp lý kèm 14 câu hỏi cho kế toán. **Không chọn mức thuế nào**, không tạo bảng làm mất cảnh báo khoá.
- **Không đổi:** công thức tiền, 2 khoản pending, khoá tài chính, ví, payout, Membership.
- **521 test pass** (493 cũ + 28 mới).

| Phần | Trạng thái |
|---|---|
| Phát hành được sau review | schema điều khoản, ticket, `/hotro`, màn admin, cổng `unresolved`, màn sẵn sàng chi trả, che dữ liệu |
| Cần chủ bot duyệt riêng | **nội dung điều khoản V1** (rồi tự bấm công bố), bật cờ bắt buộc đồng ý, SLA, chính sách thuế, chính sách thu hồi, thời gian lưu dữ liệu, điều kiện mở ví |
| Không làm | gửi tin hàng loạt, bật ví, payout, sửa khoản pending |

---

## 2. Baseline (kiểm tra lại trước khi code)

| Mục | Giá trị thực tế |
|---|---|
| Git | `main@cca8f8c`, sạch. Code production `13eb3f5`; báo cáo PLAN-077 ghi `810acc5`, nhưng sau đó đã thêm tin báo admin có bảng chia tiền |
| Process | PID 615042, khởi động 05:17:26 UTC |
| Backup gần nhất | `cashback-20261024T051459Z.sqlite` |
| Bảng | 29. Người dùng: 7. Link: 33 tạo + 1 bị từ chối. Snapshot: 31 backfilled + 2 captured |
| Tiền | 2 khoản `pending` 12.157đ / 960đ; 2 đơn PENDING / NOT_VERIFIED, 1 FRAUD; 0 payout |
| Khoá | 4 trigger `financial_lock_*`; không có `shopee_settlements` / `payout_tax_policies`; `wallet_enabled=0` |
| Dữ liệu ngân hàng | `bank_accounts` có **1 dòng** (từ lúc thử ví 23/10) |
| Test baseline | **493 passed** (PLAN-076 490 + 3 test tin báo admin) |

---

## 3. Audit quyền lợi khách

| # | Tình huống | Đang chạy | Có trong code | Chưa hoạt động | Nguồn chứng minh |
|---|---|---|---|---|---|
| 1 | Khách tạo link | ✅ mỗi lần gửi link: một Sub ID mới, báo giá, snapshot chính sách | | | `service.handle_text`, `link_policy_snapshots` |
| 2 | Khách tự mua qua link mình tạo | ✅ đơn gắn cho người tạo link | | | `db.record_shopee_conversion`: `sub_id` → `link_requests.telegram_user_id` |
| 3 | Chia link cho người khác mua | ✅ đơn vẫn gắn cho **người tạo link** | | | như trên; bot không biết ai là người mua |
| 4 | Người khác gửi lại cùng sản phẩm | ✅ người đó nhận link **mới**, Sub ID riêng | | | `_unique_sub_id` mỗi yêu cầu |
| 5 | Conversion có Sub ID | ✅ đồng bộ Shopee (admin bấm), giữ **lần gắn đầu tiên** | | | `record_shopee_conversion` giữ `matched_link_id` cũ |
| 6 | Shopee chưa ghi nhận đơn | ✅ bot không thấy gì | | | không có dữ liệu |
| 7 | Đã ghi nhận, chưa duyệt | ✅ `PENDING / NOT_VERIFIED`, khoản ví `pending` | | | PLAN-074, sổ ví |
| 8 | Shopee từ chối | ✅ `REJECTED` → khoản `cancelled` | | | `commission_validation`, `wallet.refresh` |
| 9 | Shopee gắn gian lận | ✅ `FRAUD` → `cancelled`, không tạo khoản phải trả | | | như trên |
| 10 | Hoa hồng tăng/giảm | ✅ ghi lịch sử, tính lại khoản pending theo **snapshot của link** | | | `shopee_conversion_changes`, PLAN-076 |
| 11 | Huỷ / trả hàng / hoàn tiền | ✅ `cancelled` | | | `order_state` |
| 12 | Duyệt nhưng chưa thanh toán | | | ❌ chưa có nguồn nào gán APPROVED | PLAN-074 |
| 13 | Shopee đã thanh toán | | khung đối soát có | ❌ chưa có chứng từ thật | PLAN-075 |
| 14 | Yêu cầu rút khi ví đóng | ✅ "Ví hoàn tiền chưa mở" | | ❌ rút tiền | `service._wallet_action`, `payout_gate` |
| 15 | Nhiều người nhận cùng một đơn | ✅ một đơn chỉ gắn một Sub ID; ticket cho admin xem link/đơn của từng người | | | Sub ID + `support_tickets` (mới) |

**Tách quyền:**

| Quyền | Trạng thái |
|---|---|
| Xem khoản hoàn dự kiến | ✅ có: thẻ link, `/cachtinh` |
| Được ghi nhận hoa hồng (đơn gắn đúng người) | ✅ có, theo Sub ID; chỉ khi Shopee báo về |
| Yêu cầu kiểm tra giao dịch | ✅ **mới**: `/hotro` |
| Nhận cashback khi đủ điều kiện | ❌ chưa: thiếu APPROVED, chứng từ thanh toán, chính sách thuế |
| Rút tiền | ❌ chưa mở |
| Hạng thành viên | ❌ chưa bật |

---

## 4. Data model điều khoản (ADR-054)

| Bảng | Cột chính | Bất biến |
|---|---|---|
| `customer_terms_versions` | `version` (unique), `title`, `content` (JSON các mục), `content_hash` (sha256 của tiêu đề + nội dung), `status`, `effective_from`, `created_by`, `approved_by`, `published_at` | Chỉ một bản PUBLISHED. Trigger: không sửa nội dung, ngày hiệu lực, người duyệt sau khi rời DRAFT; trạng thái chỉ tiến; không xoá bản đã công bố. CHECK: bản không phải DRAFT phải có đủ ngày hiệu lực và người duyệt |
| `customer_terms_acceptances` | `telegram_user_id`, `terms_version_id`, `terms_hash`, `acceptance_source`, `accepted_at`, `recorded_at` | `UNIQUE(user, version)`; chỉ thêm |
| `link_terms_context` | `link_id` (PK), `terms_version_id` (NULL: chưa có bản công bố), `acceptance_id` | Chỉ thêm; ghi cùng transaction với link và snapshot tiền |

- **Snapshot tiền** (`link_policy_snapshots`, PLAN-076) và **phiên bản điều khoản** là hai bảng riêng; không bảng nào thay bảng nào.
- Link cũ **không có dòng** `link_terms_context`, hiện là `LEGACY_NOT_RECORDED`. Không tạo chấp thuận giả, không khoá hay xoá link.

---

## 5. Quản lý phiên bản

1. Admin: /admin → 📋 Điều khoản → **📝 Tạo bản nháp V1 từ mẫu**. Nội dung lấy từ `cashback_bot/terms_content.py`. Khách chưa thấy.
2. Admin đọc từng mục đúng chữ khách sẽ thấy, rồi bấm **🟢 Công bố phiên bản này…**
3. Màn xác nhận nói rõ:
   - khách thấy ngay ở `/dieukien`;
   - không gửi tin cho khách, không tự ghi ai đã đồng ý, không bật bắt buộc;
   - sau khi công bố, nội dung không sửa được.
   Nút **✅ Tôi đã duyệt, công bố** mang 12 ký tự đầu của hash; nội dung đổi thì bị từ chối.
4. Công bố bản mới: bản cũ thành SUPERSEDED trong cùng transaction. Chấp thuận bản cũ giữ nguyên, **không chuyển** sang bản mới.
5. Có audit `terms_draft` và `terms_publish` ở 📊 Lịch sử.

**Giới hạn V1:**
- chưa có trình sửa bản nháp trong bot; đổi chữ thì sửa mẫu trong code và tạo phiên bản mới;
- chưa hẹn giờ hiệu lực: công bố là có hiệu lực ngay.

---

## 6. Dự thảo điều khoản V1 (`terms_content.py`, trạng thái **DRAFT**)

| Mục | Nội dung chính |
|---|---|
| 📋 Điều khoản chung | Bot **không phải** dịch vụ Shopee. Không thu phí. **Ví và chi trả chưa mở**; khi mở sẽ có phiên bản mới nêu điều kiện. Mỗi thay đổi là một phiên bản có ngày hiệu lực; link cũ giữ cách tính; khoản đã xác nhận không bị huỷ chỉ vì đổi điều khoản |
| 💰 Ghi nhận và cách tính | Sub ID gắn với người tạo link; **chia sẻ link không chuyển quyền nhận hoàn tiền**. Số dự kiến là ước tính, các lý do có thể đổi. Dự phòng **không phải** thuế khách nộp. Mỗi link giữ cách tính, nhưng số tiền vẫn theo hoa hồng thật. 5 bước của đơn; bot chưa có bước duyệt, thanh toán, chi |
| 🚫 Đơn không được hoàn | Huỷ, trả hàng, Shopee từ chối hay gắn gian lận, không có Sub ID hoặc không có dữ liệu đối chiếu, thao tác bất thường có bằng chứng. **Shopee không ghi nhận không có nghĩa là gian lận**. Khoản đã chi mà bị thu hồi: sẽ quy định trước khi mở ví |
| 🛡 Dữ liệu cá nhân | Danh sách dữ liệu lưu; tin không phải link không lưu nội dung; không hỏi mật khẩu, OTP, cookie, thẻ; mục đích; chỉ người vận hành xem; bảo vệ; thời gian lưu sẽ công bố; quyền xem, sửa, xoá qua `/hotro`; dữ liệu tài chính có thể chưa xoá được ngay, kèm giải thích |
| 📩 Hỗ trợ và khiếu nại | Các loại yêu cầu; mã số và trạng thái; «Chờ Shopee» không bị coi là khách sai; **không bảo đảm** Shopee chấp nhận; **chưa cam kết thời hạn** |

Test kiểm tra:
- nội dung có "chưa mở", "không phải số thuế", "không có nghĩa là gian lận";
- **không** có "sẽ được hoàn", "rút tối thiểu", "trong vòng", "ngày làm việc", "cam kết hoàn", "bảo đảm nhận";
- mỗi mục dưới 3.500 ký tự (giới hạn tin Telegram).

**Chủ bot cần đọc toàn văn trong /admin → 📋 Điều khoản trước khi công bố.**

---

## 7. Chấp thuận của khách

- `/dieukien`:
  - **chưa có bản công bố:** giữ trang cũ, production không đổi;
  - **có bản công bố:** hiện tiêu đề, phiên bản, ngày hiệu lực, nút từng mục, nút **✅ Tôi đã đọc và đồng ý** (chỉ khi chưa đồng ý), nút 📩 Hỗ trợ.
- **Xem không phải đồng ý:** mở mục không ghi gì (test 08).
- Bấm đồng ý:
  - ghi đúng bản đang công bố kèm hash;
  - bấm lại không ghi thêm;
  - bản cũ trả "không còn hiện hành";
  - bấm trong chat không phải của mình hoặc trong nhóm bị từ chối.
- **Cờ `CASHBACK_TERMS_REQUIRED`:**
  - mặc định **tắt**;
  - bật và có bản công bố thì chỉ chặn **tạo link mới**; `/hotro`, `/dieukien` và lịch sử vẫn dùng được;
  - không tự bật khi triển khai.
- **Người dùng cũ:** không bị ép đồng ý; link, đơn và khoản pending vẫn theo dõi bình thường.

---

## 8. Quy trình hỗ trợ và khiếu nại

**Khách:**
1. `/hotro` hoặc nút 📩 Hỗ trợ ở trang chủ, chọn một trong 6 danh mục: không thấy đơn, số hoàn không đúng, sai link / sai người, chờ quá lâu, dữ liệu cá nhân, khác.
2. Gửi một tin mô tả (tối đa 1.000 ký tự). Bot chờ 15 phút.
   - Dán **chỉ một link Shopee** thì vẫn tạo link như thường.
   - Lệnh `/…` thì thôi chờ.
3. Bot trả mã yêu cầu. Khách xem 🗂 Yêu cầu của tôi (5 gần nhất) và bổ sung khi ticket chưa kết thúc.

**Ticket:**
- Trạng thái: OPEN, IN_REVIEW, WAITING_CUSTOMER, WAITING_SHOPEE, RESOLVED, REJECTED, CLOSED.
- Bảng chuyển trạng thái cố định; RESOLVED và REJECTED chỉ còn đi tới CLOSED.
- Kết luận và **chờ Shopee** phải có lý do. **Không có hẹn giờ tự từ chối hay tự đóng.**
- Lưu: người mở, danh mục, link/đơn (chỉ của chính khách, tự nhận từ mã trong nội dung), nội dung đã làm sạch, trạng thái, người xử lý, kết luận, `support_ticket_events` (ai, việc gì, từ → tới, ghi chú).
- Telegram gửi lại cùng update thì không tạo trùng (`source_update_id`).
- Không cần có đơn mới được khiếu nại.
- Nội dung được che token, cookie, dãy số giống số thẻ (giữ 4 số cuối). Bot nhắc không gửi mật khẩu, OTP, cookie, thẻ; không đòi giấy tờ.

**SLA:** đề xuất phản hồi đầu tiên trong 2 ngày làm việc, kết luận trong 15 ngày trừ khi chờ Shopee. **Chưa công bố**, chờ chủ bot duyệt.

---

## 9. Màn admin

| Màn | Nội dung | Thao tác ghi |
|---|---|---|
| 📩 Hỗ trợ (`c:hp:*`) | đếm theo nhóm (mới, đang xử lý, chờ khách, chờ Shopee, đã kết luận); danh sách; chi tiết ticket kèm **dữ liệu đối chiếu chỉ đọc** (link của khách, snapshot chính sách, bản điều khoản, đơn Shopee, trạng thái duyệt / đối soát, khoản ví) và 6 sự kiện gần nhất | đổi trạng thái (theo bảng, có lý do khi cần), 💬 trả lời khách: một tin riêng cho chủ ticket |
| 📋 Điều khoản (`c:tm:*`) | bản đang công bố, số khách đã đồng ý, trạng thái cờ bắt buộc, danh sách phiên bản, đọc từng mục | tạo bản nháp V1, công bố có xác nhận hash |
| ⚖️ Sẵn sàng chi trả (`c:rd:*`) | lý do khoá (đọc từ `payout_gate`), link chứng minh được / chưa xác định chính sách, điều khoản, ticket đang mở, thuế / thu hồi / SLA = PENDING_REVIEW | **không có** |

- Menu /admin thêm 2 hàng: (📩 Hỗ trợ, 📋 Điều khoản), (⚖️ Sẵn sàng chi trả).
- Từ ticket **không có** nút sửa hoa hồng, gán APPROVED / SETTLED, đổi sổ ví hay chi trả. Test thử các callback giả (`c:hp:approve`, `c:hp:paid`, `c:hp:s:1:SETTLED`…): đều bị từ chối.

---

## 10. Sẵn sàng về thuế (PENDING_REVIEW)

### 10.1 Sáu khoản không gộp

| # | Khoản | Nguồn số | Trong bot |
|---|---|---|---|
| 1 | Thuế của chủ bot trên hoa hồng affiliate | chứng từ Shopee / cơ quan thuế | không tính |
| 2 | Thuế Shopee đã khấu trừ | báo cáo thanh toán Shopee | `settlement_batches.tax_withheld_vnd` (PLAN-075) |
| 3 | Phí Shopee | chứng từ | `fee_vnd` |
| 4 | VAT trên phí | chứng từ | `fee_vat_vnd`, `fee_includes_vat` (không trừ hai lần) |
| 5 | Dự phòng 0,98% / 10% của V1.2 | cấu hình | chỉ để **ước tính** số hoàn |
| 6 | Nghĩa vụ thuế khi chi cho người nhận | **chưa xác định** | không có trường nào; sổ quyết định chỉ là DDL nháp |

### 10.2 Bản đồ pháp lý (tra cứu 24/10/2026)

> ⚠️ Đa số mốc năm 2026 dưới đây **mới được xác nhận qua nguồn thứ cấp** (bài phân tích, trang kế toán), chưa đọc được văn bản gốc trên Công báo. **Không dùng để quyết định** trước khi kế toán đối chiếu.

| Chủ đề | Thông tin tìm được | Độ tin |
|---|---|---|
| Luật thuế TNCN | Luật 109/2025/QH15, hiệu lực 01/7/2026 (thu nhập kinh doanh, tiền công áp dụng từ kỳ tính thuế 2026); hướng dẫn: NĐ 253/2026 | thứ cấp |
| Ngưỡng doanh thu hộ / cá nhân kinh doanh | Luật 09/2026/QH16 giao Chính phủ quy định; NĐ 141/2026: **1 tỷ đồng/năm** (các nguồn nói khác nhau về ngày hiệu lực) | Luật 09/2026 đọc toàn văn; NĐ: thứ cấp |
| Thu nhập affiliate của chủ bot | CV 7403/CT-TMĐT (06/10/2026): hoa hồng affiliate là **thu nhập kinh doanh** (trừ khi có quan hệ lao động), TNCN 5%; sàn khấu trừ theo Điều 43 NĐ 252/2026 | thứ cấp, có nguồn mâu thuẫn |
| Shopee khấu trừ | Theo thông báo Shopee: từ **01/10/2026**, khấu trừ **5% GTGT + 5% TNCN** với cá nhân affiliate | trang trợ giúp Shopee + báo chí |
| Quản lý thuế | Luật 108/2025/QH15 và NĐ 252/2026 (hiệu lực 01/7/2026, thay NĐ 117/2025) | thứ cấp |
| Khấu trừ khi trả thu nhập cho cá nhân không có HĐLĐ | ngưỡng **5 triệu đồng/lần** từ 01/7/2026 (khoản 2 Điều 50 NĐ 253/2026); ngưỡng cũ 2 triệu theo TT 111/2013 không còn là mốc hiện hành | thứ cấp |
| Bản chất khoản cashback chia lại hoa hồng | **Không tìm thấy văn bản trả lời trực tiếp.** Có thể là giảm giá, khuyến mại, quà tặng hay tiền công giới thiệu; chủ bot không phải người bán | **CHƯA RÕ** |

**Ảnh hưởng tới đối soát:** nếu Shopee khấu trừ 5% + 5% từ 01/10/2026, tiền thực nhận thấp hơn hoa hồng báo cáo. PLAN-075 đã có ô thuế khấu trừ theo chứng từ, nên khi nhập báo cáo thanh toán thật số sẽ đúng. Còn dự phòng 10% của V1.2 **chỉ là ước tính**, có thể cần chủ bot xem lại; PLAN-077 không đổi mức này.

### 10.3 Câu hỏi gửi kế toán
1. Từ kỳ 2026, hoa hồng Shopee Affiliate của tôi (chưa đăng ký kinh doanh) là thu nhập kinh doanh hay tiền công? Áp dụng CV 7403 và Điều 8 NĐ 253/2026 thế nào?
2. Thuế suất đúng là 5% TNCN, 2% TNCN, hay 5% TNCN + 5% GTGT? Phần Shopee khấu trừ thừa được hoàn ra sao?
3. Doanh thu dưới 1 tỷ/năm thì làm gì để không bị thu, hoặc được hoàn? NĐ 141/2026 có hiệu lực hồi tố không?
4. Có nên đăng ký hộ kinh doanh không (thuế, hoá đơn, nghĩa vụ dữ liệu)?
5. Cashback chuyển cho người mua là gì về thuế, và người nhận có chịu TNCN không?
6. Tôi (cá nhân hoặc hộ kinh doanh) có phải khấu trừ khi mỗi lần chi dưới 5 triệu không?
7. Một người nhận nhiều lần, cộng dồn trên 5 triệu, thì có phát sinh nghĩa vụ không?
8. Khoản chi cashback có được trừ khỏi doanh thu hay thu nhập chịu thuế của tôi không?
9. Mỗi lần chuyển khoản cần lưu chứng từ gì: bảng kê, xác nhận người nhận, MST hay CCCD?
10. Có phải báo cáo danh sách người nhận cho cơ quan thuế không?
11. Bot có bị coi là "nền tảng" phải khấu trừ thay theo Điều 43 NĐ 252/2026 không?
12. Số tài khoản ngân hàng có phải dữ liệu nhạy cảm theo NĐ 356/2025 không?
13. Lưu dữ liệu trên máy chủ hoặc Telegram ở nước ngoài có phải lập hồ sơ chuyển dữ liệu xuyên biên giới không?
14. Nên lưu hồ sơ giao dịch bao lâu để đáp ứng thời hiệu thuế, kế toán và nguyên tắc lưu tối thiểu?

### 10.4 Sổ quyết định thuế
- DDL nháp `migrations/009_tax_decisions.DRAFT.sql`, **không chạy**.
- Cột: loại người nhận, loại khoản chi, cách xử lý, căn cứ pháp lý, người tư vấn, chứng từ, ngày hiệu lực, trạng thái PENDING_REVIEW / APPROVED / REJECTED, phiên bản. CHECK: APPROVED phải có người duyệt và người tư vấn.
- Cố ý **không** tên `payout_tax_policies`, nên không mở được khoá. Nối vào khoá ở PLAN sau, khi đã có quyết định.

---

## 11. Bảng quyết định khi Shopee thu hồi hoa hồng

| Tình huống | Dữ liệu cần | Hành động | Ai duyệt | Rủi ro | Trạng thái |
|---|---|---|---|---|---|
| Trước khi Shopee duyệt, hoa hồng đổi | conversion report, lịch sử thay đổi | cập nhật khoản dự kiến theo snapshot link; ghi lịch sử | — | khách thấy số giảm | **Đã chạy** (PLAN-074/076) |
| Gian lận / từ chối | cờ trong báo cáo Shopee | khoản → «không được hoàn», không tạo khoản phải trả | — | khách khiếu nại → `/hotro` | **Đã chạy** |
| Đã duyệt, chưa thanh toán | APPROVED (chưa có nguồn) | giữ ở trạng thái chưa được chi | — | — | **Đã chạy** (khoá) |
| Đã thanh toán, chưa chi khách, có điều chỉnh | báo cáo thanh toán và điều chỉnh (PLAN-075) | **đề xuất:** chi theo số ròng sau điều chỉnh | chủ bot | đối soát sai | **Chờ quyết định** |
| Đã chi khách rồi bị thu hồi | điều chỉnh có chứng từ, lịch sử chi | phương án: (a) chủ bot chịu; (b) trừ vào khoản hoàn sau, **cần điều khoản và khách đồng ý trước**; (c) xử lý từng ca qua `/hotro` | chủ bot (+ pháp lý cho b) | (a) mất tiền; (b) tranh chấp, pháp lý; (c) tốn công | **Chờ quyết định** |
| Ngưỡng nhỏ bỏ qua, thời gian giữ tiền trước khi chi | dữ liệu hoàn/huỷ thực tế | đề xuất giữ tới khi kỳ Shopee đã thanh toán | chủ bot | — | **Chờ quyết định** |

Hiện tại chỉ ghi điều chỉnh (dòng OPEN ở 🧾 Đối soát). **Không trừ hay thu tiền khách.** Điều khoản V1 nói trước rằng cách xử lý sẽ được quy định trước khi mở ví.

---

## 12. Dữ liệu cá nhân và thời gian lưu

**Văn bản áp dụng** (đọc qua bản dịch hoặc nguồn thứ cấp):
- Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15, hiệu lực 01/01/2026;
- NĐ 356/2025 thay NĐ 13/2023; xử phạt theo NĐ 330/2026.

Các điểm liên quan tới bot:
- áp dụng cả với cá nhân;
- **im lặng không phải đồng ý**;
- quyền xem, sửa, xoá, rút đồng ý;
- chỉ lưu trong thời hạn phù hợp mục đích;
- báo sự cố trong 72 giờ khi có nguy cơ gây hại;
- NĐ 356 quy định thời hạn trả lời yêu cầu: phản hồi 2 ngày làm việc, xem/sửa 10 ngày, rút đồng ý 15 ngày, xoá 20 ngày (thứ cấp).

**Bot đang lưu:**

| Dữ liệu | Nơi | Cần? | Thay đổi PLAN-077 | Đề xuất thời gian lưu (**chờ duyệt**) |
|---|---|---|---|---|
| Telegram ID, username | `telegram_users` | có | — | khi còn dùng + 24 tháng |
| Link Shopee khách gửi, sản phẩm, Sub ID | `link_requests` | có (ghi nhận đơn) | — | theo dữ liệu tài chính |
| Tin không phải link | `link_requests.original_url` (bị từ chối) | **không** | **chỉ lưu độ dài** (1 dòng cũ giữ nguyên, không xoá) | — |
| Đơn, hoa hồng, trạng thái | `shopee_conversions`, lịch sử | có (đối soát) | — | theo kế toán, đề xuất ≥ 5 năm |
| Sổ ví, đối soát, chứng từ | `cashback_entries`, `settlement_*`, `data/settlement_evidence/` | có | — | theo kế toán |
| Tài khoản ngân hàng | `bank_accounts` (1 dòng) | chỉ khi mở ví | màn admin xem khách **che số** | xoá khi khách yêu cầu nếu không còn giao dịch |
| Yêu cầu hỗ trợ | `support_tickets`, events (mới) | có | che token và số thẻ; 1.000 ký tự | 24 tháng sau khi đóng |
| Log | `logs/cashback_bot.log` | có | che token (PLAN-073) | **chưa xoay vòng**, đề xuất 90 ngày |
| Backup | `data/backups/` (0600) | có | — | 14 bản (cấu hình) |

- Khách gửi yêu cầu dữ liệu qua `/hotro` → 🛡 Dữ liệu cá nhân.
- Dữ liệu tài chính cần giữ **không bị xoá tự động**; điều khoản nói rõ có thể chưa xoá được ngay.
- Khách khác không xem được ticket hay dữ liệu của nhau. Màn admin chỉ hiện link và đơn của chính khách mở ticket (test).
- **Chưa làm:** tự xoá theo thời hạn, xoay vòng log. Cần chủ bot chốt thời gian lưu trước.

---

## 13. Link không chứng minh được chính sách

- `payout_gate.proven_policy(link_id)`: chỉ `captured` / `backfilled` mới qua.
- `entry_payable` thêm điều kiện này; `wallet.refresh` truyền `matched_link_id`.
- Link `unresolved` hoặc thiếu snapshot **vẫn**:
  - được theo dõi, có conversion, có khoản pending (tính theo cách cũ);
  - kiểm tra được qua ticket (màn chi tiết hiện "⚠️ chưa xác định chính sách").
- Link đó **không bao giờ** thành `available`, kể cả khi đủ mọi điều kiện khác (test 35). Đối chứng: link có snapshot thì vào ví được trong DB test.
- Không sửa, không xoá link; không gán chính sách hiện hành.
- Production: 33/33 link chứng minh được, 0 bị ảnh hưởng.

---

## 14. Files changed

| File | Thay đổi |
|---|---|
| `cashback_bot/terms.py`, `terms_content.py` (mới) | nghiệp vụ điều khoản; dự thảo V1 |
| `cashback_bot/support.py` (mới) | ticket, bảng chuyển trạng thái, làm sạch nội dung |
| `cashback_bot/customer_desk.py` (mới) | phía khách: `/dieukien`, `/hotro`, nút `u:t:*`, `u:h:*`, cờ bắt buộc |
| `cashback_bot/admin_support.py`, `admin_terms.py`, `admin_readiness.py` (mới) | ba màn admin |
| `cashback_bot/db.py` | 5 bảng và trigger; `insert_created(..., terms=)` |
| `cashback_bot/service.py` | nối desk; `/hotro`; cổng điều khoản; không lưu tin không phải link |
| `cashback_bot/payout_gate.py`, `wallet.py` | `proven_policy`; truyền `link_id` |
| `cashback_bot/admin_policy.py`, `admin_ui.py` | route, menu, lịch sử điều khoản, che số tài khoản |
| `cashback_bot/admin_notify.py` | báo admin ticket mới hoặc khách bổ sung |
| `cashback_bot/messages.py`, `config.py` | chữ khách; nút 📩 Hỗ trợ; lệnh `/hotro`; cờ `terms_required` |
| `migrations/009_tax_decisions.DRAFT.sql` (mới) | DDL nháp, không chạy |
| `tests/test_cashback_terms_support.py` (mới) | 28 test |
| `tests/test_cashback_bot.py`, `test_cashback_plan060.py` | thêm `hotro` vào menu lệnh, nút Hỗ trợ |
| `agents/decisions/ADR-054-customer-terms-support.md` | ADR |

---

## 15. Migration

- **Cơ chế:** tự chạy trong `repo.migrate()`, chỉ `CREATE … IF NOT EXISTS`. Không ALTER bảng cũ, không backfill điều khoản cho link cũ.
- **Diễn tập trên bản sao DB production** (0600, đã xoá; `migrate()` 2 lần, khởi động service 2 lần, làm mới ví một lần, mở các màn mới):

| Kiểm tra | Kết quả |
|---|---|
| Bảng thêm | `customer_terms_versions`, `customer_terms_acceptances`, `link_terms_context`, `support_tickets`, `support_ticket_events` (đều trống) |
| Bảng cũ (29) | hash nội dung không đổi, trừ `updated_at` của `cashback_entries` |
| Khoản pending | 12.157 / 171 / 1.737 và 960 / 14 / 138, `pending` |
| Snapshot chưa chứng minh | 0 |
| Khoá | 4 trigger; 0 available; 0 payout; bật ví bị chặn |
| `/dieukien` | trang cũ (chưa công bố) |
| `integrity_check` | ok |

---

## 16. Bằng chứng test

- `tests/test_cashback_*.py`: **521 passed** (493 + 28), ruff sạch. Không test nào gọi Shopee hay Telegram thật.

| Nhóm PLAN | Test |
|---|---|
| Terms 1–12 | tạo nháp, công bố có hash, không sửa / xoá bản đã công bố, A → B không chuyển chấp thuận, không ghi chấp thuận giả, người dùng cũ không bị ép, link mới ghi phiên bản, không có điều khoản thì không gán, restart |
| Khách 13–19 | `/dieukien` đúng phiên bản, không hứa rút, xem ≠ đồng ý, bấm hợp lệ, chat khác hoặc nhóm bị từ chối, cờ mặc định tắt và chỉ chặn tạo link, `/cachtinh` khớp điều khoản |
| Hỗ trợ 20–28 | mở ticket, retry không trùng, admin xem / trả lời / đổi trạng thái, khách khác không xem được, ticket không cần đơn, chờ Shopee cần lý do và không tự từ chối, lịch sử chỉ thêm, giới hạn và che nội dung, ticket không chạm tiền |
| Thuế / thu hồi 29–34 | màn sẵn sàng chi trả chỉ đọc và vẫn khoá, dự phòng không phải thuế, không có bảng mở khoá, callback giả từ ticket bị từ chối, mã nguồn ticket không có câu lệnh sửa tiền |
| Snapshot / tiền 35–40 | link `unresolved` không vào ví (có đối chứng), link cũ nguyên, không tạo available hay payout, trigger còn |
| Dữ liệu | tin không phải link không lưu nội dung, màn admin che số tài khoản, ticket chỉ gắn dữ liệu của chính khách |
| Regression 41–50 | toàn bộ 493 test cũ (tạo link, Sub ID, đồng bộ, PLAN-074/075/076, backup, cô lập update, log an toàn, callback admin) |

---

## 17. An toàn tài chính

- Không đổi: công thức, snapshot, tỷ lệ, dự phòng, PLAN-073/074/075, trigger khoá.
- Thay đổi duy nhất ở tầng tiền làm khoá **chặt hơn** (`proven_policy`).
- Điều khoản, ticket và màn sẵn sàng chi trả: không ghi `cashback_entries`, `shopee_conversions`, `cashback_payouts`, `settlement_*` (test so trạng thái trước / sau và quét mã nguồn).

---

## 18. Triển khai và rollback

**Triển khai (sau release review):**
1. Backup và verify.
2. `git merge --ff-only cursor/cashback-plan077-terms`, test, push.
3. Chủ bot restart.
4. Kiểm tra:
   - 5 bảng mới trống; `/dieukien` vẫn là trang cũ; nút 📩 Hỗ trợ ở trang chủ;
   - menu lệnh có `/hotro`;
   - màn admin mới mở được;
   - khoản pending giữ số; khoá còn; log sạch.

**Khách thấy ngay:** nút 📩 Hỗ trợ, lệnh `/hotro`. **Không** thấy điều khoản mới cho tới khi chủ bot công bố.

**Rollback:** `git revert` rồi restart.
- 5 bảng mới để lại vô hại.
- Ticket đã có vẫn còn trong DB, nhưng khách không xem được nữa.
- Không restore DB để rollback.

---

## 19. Quyết định còn chờ

1. **Release review PLAN-077** (phần kỹ thuật).
2. **Nội dung điều khoản V1:** đọc trong /admin → 📋 Điều khoản, sửa nếu cần (em sửa mẫu), rồi tự bấm công bố.
3. **Có bật bắt buộc đồng ý trước khi tạo link không**, và từ khi nào.
4. **SLA hỗ trợ** (đề xuất 2 ngày làm việc phản hồi, 15 ngày kết luận trừ chờ Shopee).
5. **Thời gian lưu dữ liệu** (bảng mục 12) và xoay vòng log.
6. **Thuế:** gửi 14 câu hỏi mục 10.3 cho kế toán; chưa có câu trả lời thì giữ PENDING_REVIEW.
7. **Thu hồi hoa hồng đã chi:** chọn (a), (b) hoặc (c) ở mục 11.
8. Xem lại dự phòng thuế 10% của V1.2, vì có thông tin Shopee khấu trừ 5% GTGT + 5% TNCN từ 01/10/2026 (cần kế toán xác nhận).
9. Từ trước: chứng từ Shopee thật (thanh toán, sao kê, xác thực).

---

## 20. Release gates

| Gate | Kết luận |
|---|---|
| Terms Versioning | **GO** |
| Terms Draft | **DRAFT** (chờ chủ bot duyệt nội dung) |
| Customer Acceptance | **GO** (cờ bắt buộc mặc định tắt) |
| Existing User Compatibility | **GO** |
| Support Tickets | **GO** |
| Admin Support UI | **GO** |
| Tax Policy | **PENDING_REVIEW** |
| Clawback Policy | **PENDING_REVIEW** |
| Privacy & Retention | **CONDITIONAL**: che dữ liệu, dữ liệu tối thiểu và kênh yêu cầu đã có; thời gian lưu và xoay vòng log chờ duyệt |
| Unresolved Snapshot Safety | **GO** |
| Financial Lock | **GO** |
| Regression | **GO** (521/521) |
| Production Deployment | **GO, đã triển khai** (chủ bot duyệt 2026-10-24) |
| Wallet Activation | **NOT AUTHORIZED** |
| Payout | **NOT AUTHORIZED** |

---

## Câu hỏi nghiệm thu

**Q1. Khách biết quyền lợi và điều kiện nhận cashback bằng cách nào?**
- **Hiện tại:** thẻ link, `/cachtinh`, `/dieukien` (trang cũ), `/huongdan`.
- **Sau khi chủ bot công bố V1:** `/dieukien` hiện 5 mục theo phiên bản và ngày hiệu lực, có nút đồng ý và nút hỗ trợ.
- Mọi trang đều nói ví và chi trả chưa mở.

**Q2. Điều khoản đổi sau khi khách tạo link, bot có giữ lịch sử phiên bản và chính sách của link không?**
**Có.**
- Phiên bản đã công bố không sửa hay xoá được, bản cũ thành «Đã thay».
- Mỗi link mới ghi bản điều khoản lúc tạo (`link_terms_context`) và vẫn giữ snapshot chính sách tiền (PLAN-076).
- Chấp thuận bản cũ giữ nguyên, không chuyển sang bản mới.
- Link trước PLAN-077 hiện `LEGACY_NOT_RECORDED`.

**Q3. Khách không thấy đơn có tạo được yêu cầu kiểm tra không?**
**Có:** `/hotro` → 📦 Không thấy đơn. Không cần có đơn. Khách nhận mã yêu cầu và xem được trạng thái.

**Q4. Hai người cùng đòi cashback cho một đơn thì admin xử lý bằng dữ liệu nào?**
- Đơn chỉ có một Sub ID; Sub ID thuộc người tạo link; bot giữ lần gắn đầu tiên.
- Màn chi tiết ticket của mỗi người chỉ hiện link và đơn của chính người đó, kèm snapshot chính sách, bản điều khoản và trạng thái duyệt / đối soát.
- Lịch sử ticket chỉ thêm. Điều khoản V1 nói rõ chia sẻ link không chuyển quyền nhận hoàn tiền.

**Q5. Shopee huỷ hoặc thu hồi hoa hồng thì điều khoản quy định thế nào, phần nào còn chờ?**
- Điều khoản V1 nêu: đơn huỷ, từ chối hay gian lận không được tính; hoa hồng giảm thì khoản dự kiến giảm theo; khoản đã chi mà bị thu hồi sẽ được quy định trước khi mở ví.
- **Chờ chủ bot:** chi theo số ròng sau điều chỉnh, và phương án (a)/(b)/(c) khi đã chi (mục 11).

**Q6. Dự phòng thuế 10% có bị nhầm là thuế thực tế của khách không?**
**Không.**
- `/cachtinh`, điều khoản V1 và màn ⚖️ Thuế đều ghi đây là mức bot tự đặt để ước tính, không phải thuế khách nộp.
- Thuế thật lấy từ chứng từ, ở ô riêng của đối soát.

**Q7. Link không xác định được snapshot có thể thành payable không?**
**Không.** `payout_gate.proven_policy` chặn, có test và đối chứng.

**Q8. Có thay đổi nào làm 2 khoản pending thật bị tính lại hoặc huỷ không?**
**Không.** Diễn tập trên bản sao: 12.157đ / 960đ giữ nguyên, `pending`. Cả hai link đều có snapshot `backfilled`.

**Q9. Có thao tác nào từ điều khoản hay hỗ trợ mở được ví hoặc payout không?**
**Không.**
- Không có nút hay đường code nào.
- Không tạo bảng điều kiện mở khoá.
- Test so trạng thái tiền trước / sau và thử callback giả.

**Q10. Còn thiếu quyết định nào trước PLAN-078?**
Các mục 2–8 ở phần 19, cộng chứng từ Shopee thật. Tối thiểu cho PLAN-078 (nối đối soát vào khoá, mở ví có điều kiện) cần:
- câu trả lời thuế từ kế toán;
- chính sách thu hồi;
- điều khoản đã công bố, có điều kiện chi trả;
- ít nhất một kỳ Shopee có chứng từ khớp.
