# PLAN-093 — Thời hạn lưu dữ liệu (admin chỉnh được) + mẫu điều khoản V3

| | |
|---|---|
| Executor | Claude Code (chủ bot duyệt 2026-10-26: "oke em triển khai nhé em, có thể admin cấu hình những con số cho sau này") |
| Trạng thái | ✅ Đã merge vào main 2026-10-26. V3 **chưa công bố** |
| Không đổi | Không xoá dữ liệu nào. Không công bố điều khoản. Không đổi % hoàn, ví, chính sách |

## 1. Thời hạn lưu (C2)

`cashback_bot/retention.py`, lưu ở `bot_state.retention_policy` (chỉ lưu các mốc khác mặc định).

| Mã | Dữ liệu | Mặc định | Khoảng cho phép |
|---|---|---|---|
| `finance_years` | Sổ ví, yêu cầu rút, chứng từ chuyển khoản (gồm tài khoản đã nhận tiền) | 10 năm | 5–20 |
| `bank_idle_months` | Tài khoản ngân hàng chưa từng nhận tiền, tính từ lần cuối dùng bot | 24 tháng | 1–120 |
| `activity_months` | Link, click, đơn không phát sinh tiền | 24 tháng | 3–120 |
| `ticket_months` | Nội dung ticket, tính từ khi đóng | 24 tháng | 3–120 |

- Tin nhắn thường không lưu; log giữ 8 tuần (logrotate). Khách yêu cầu xoá thì xoá hoặc ẩn danh, trừ nhóm tài chính.
- Mốc 10 năm tham chiếu Nghị định 174/2016 (chứng từ kế toán). Chủ bot nên hỏi kế toán hoặc luật sư.
- Màn quản trị: `/admin` → 📋 Điều khoản → 🗄 Thời hạn lưu dữ liệu.
  - `c:rt:home`, `c:rt:e:<mã>` (gõ số, chờ 10 phút), `c:rt:d:<mã>` (về mặc định).
  - 📊 Lịch sử ghi action `retention`.
- **Chưa làm:** việc tự xoá hoặc ẩn danh khi đến hạn. Đây là thao tác xoá trên DB production, cần chủ bot duyệt riêng. V3 hứa việc này, nên phải làm trước khi công bố V3.

## 2. Mẫu điều khoản V3

- `terms_content.py`: `DRAFT_VERSION = "V3"`; `draft_sections(retention.load(conn))` tạo các mục lúc admin bấm 📝 Tạo bản nháp.
- Nội dung theo `reports/CASHBACK_TERMS_V3_DRAFT.md`, đã rà với code 2026-10-26. Mức tối thiểu, hạn mức, số ngày giữ không ghi số cứng mà dẫn sang 👛 Ví, vì admin đổi được.
- Màn 📋 Điều khoản nhắc: chỉ công bố V3 khi chuẩn bị bật ví.
- **Điều kiện trước khi công bố V3:**
  1. Bot đọc được báo cáo thanh toán Shopee (parser).
  2. Có việc tự xoá dữ liệu hết hạn.
  3. Chủ bot bật ví.

## 3. Proof

- `pytest tests/test_cashback_*.py`: 804 passed. `ruff check`: sạch.
- Test mới:
  - `test_thoi_han_luu_admin_chinh_va_ban_nhap_ghi_dung_moc`: nút ở màn Điều khoản; chặn số ngoài khoảng; lưu; bản nháp ghi mốc mới; về mặc định; 📊 Lịch sử.
  - `test_thoi_han_luu_bo_qua_gia_tri_hong`.
- Test hàng rào `test_13_14_…` (PLAN-077) cập nhật theo V3: cho phép "3–7 ngày làm việc" (ADR-059); vẫn cấm "sẽ được hoàn", "cam kết hoàn", "bảo đảm nhận"…
