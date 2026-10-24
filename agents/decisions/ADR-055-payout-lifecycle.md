# ADR-055 — Vòng đời yêu cầu rút, phân bổ, quỹ có chứng từ, điều kiện chi trả

| | |
|---|---|
| Trạng thái | Accepted (PLAN-078), chưa triển khai production |
| Ngày | 2026-10-24 |
| Liên quan | ADR-049 (sổ ví), ADR-050 (khoá tài chính), ADR-051, ADR-052 (đối soát), ADR-053, ADR-054 |

## Bối cảnh
- Ví PLAN-066 tính số dư gộp (available − requested − paid), nên không truy được từng đồng về đơn nào.
- Yêu cầu rút chỉ có `requested → paid / rejected`; admin có thể bấm thẳng «đã chuyển» mà không cần chứng từ.
- Tài khoản ngân hàng bị ghi đè, không có lịch sử hay bước xác minh.
- Quỹ chỉ có một bảng nháp (`shopee_settlements`) làm điều kiện khoá.

## Quyết định
1. **Mở rộng, không làm ví mới:**
   - giữ `cashback_entries` và `cashback_payouts`;
   - thêm cột `version` (chặn callback cũ), `idempotency_key` (chặn Telegram gửi lại), `account_sha`;
   - thêm unique index một phần: mỗi khách tối đa một yêu cầu còn giữ tiền.
2. **Máy trạng thái:**
   - luồng chính: `requested → under_review → approved_for_payment → processing → sent_unconfirmed → paid_confirmed`;
   - nhánh rẽ: `rejected`, `cancelled`, `failed`, `needs_review`, `returned`;
   - không có đường `requested → paid`;
   - đã từng tới `processing` hay `sent_unconfirmed` thì không còn từ chối hay huỷ được: chỉ `failed` kèm chứng từ, hoặc đi tiếp tới `paid_confirmed`;
   - mỗi bước là một dòng `payout_events` (chỉ thêm): ai làm, lý do, chứng từ, phiên bản.
3. **Phân bổ:**
   - mỗi đồng của yêu cầu là một dòng `payout_allocations` (chỉ thêm) trỏ về một khoản sổ ví, lấy khoản cũ trước;
   - trạng thái giữ / đã trả / giải phóng suy ra từ trạng thái yêu cầu, không sửa dòng phân bổ;
   - kiểm tra bất biến sau mỗi lần ghi (phân bổ = số tiền; không giữ quá số của một khoản); hiện ở màn admin.
4. **Khoản vào ví:** ngoài điều kiện cũ, đơn phải `SETTLED` (khoản khớp trong một kỳ đối soát MATCHED) và không có điều chỉnh đang OPEN.
5. **Quỹ có chứng từ:**
   - quỹ = Σ theo kỳ MATCHED của max(0, tiền đơn bot khớp − phí − VAT chưa gồm − thuế khấu trừ của cả kỳ);
   - tiền ngoài bot, không rõ đơn, chưa phân bổ không vào quỹ;
   - điều kiện chi: tiền đang giữ + đã trả ≤ quỹ, kiểm cùng lúc với quỹ cũ.
6. **Điều kiện chi trả** (`payout_readiness`), cộng thêm vào khoá cũ, không thay nó:
   - **hệ thống:** quyết định đã duyệt cho 6 chủ đề (thuế, thu hồi, điều khoản chi trả, xác minh tài khoản, hạn mức, quy trình chuyển khoản), hạn mức ACTIVE có người duyệt, ít nhất một kỳ MATCHED, backup ≤ 48 giờ;
   - **khách:** đã đồng ý bản điều khoản mà quyết định `payout_terms` trỏ tới;
   - **từng yêu cầu:** tài khoản đã xác minh, quỹ còn đủ, trong hạn mức.
   Bảng `payout_policy_decisions` và `payout_limit_policies` chỉ thêm và không có nút duyệt trong bot.
7. **Tài khoản nhận tiền:**
   - `bank_account_history` (4 số cuối + sha) và `bank_account_verifications` (thủ công, bắt buộc có bằng chứng, gắn với sha);
   - đổi tài khoản thì về UNVERIFIED; yêu cầu đang mở giữ tài khoản đã chụp và chuyển `needs_review`;
   - tạo được QR không phải là xác minh.
8. **Trigger DB:**
   - `financial_lock_payout_progress` khoá cả các trạng thái đưa tiền ra;
   - `payout_paid_needs_evidence`: chỉ ghi được `paid_confirmed` từ `sent_unconfirmed`, và phải có sự kiện kèm chứng từ.

## Hệ quả
- CODE READY không có nghĩa FINANCIAL READY. Production vẫn khoá vì thiếu cả điều kiện cũ lẫn điều kiện mới.
- Test thành công chỉ dựng dữ liệu trong DB test; code không có công tắc bỏ qua.
- Không có API ngân hàng; chuyển khoản là thao tác tay của admin, được ghi bằng chứng từ.
