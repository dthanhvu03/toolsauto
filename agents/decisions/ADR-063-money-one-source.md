# ADR-063 — Một nguồn số tiền, một bộ từ ngữ, một chỗ cho mọi màn tiền

| | |
|---|---|
| Trạng thái | Accepted (chủ bot yêu cầu 2026-11-03: «không được rời rạc, đúng domain nghiệp vụ») |
| Ngày | 2026-11-03 |
| Liên quan | ADR-052 (đối soát), ADR-059 (thu hồi), ADR-062 (khoá theo kỳ khớp) |

## Bối cảnh
Rà soát 24 màn /admin có số tiền (2026-11-03) thấy:
- Mỗi màn tự tính: `payouts.owner_position`, `insights.liabilities`, `wallet.totals`, bảng tóm tắt ở màn đối soát. Cùng một khái niệm ra số khác nhau («quỹ có chứng từ» 20.861 vs 18.075; «chờ» 0 vs 11.494; «thực» 4.130 vs 8.148).
- Một trạng thái có 4 tên («Chờ duyệt», «Đang giữ», «Chờ ngày giữ», «Chờ Shopee»).
- Câu đã sai sự thật sau ADR-062 («Ví khách vẫn khoá», «cần khoá cũ mở», «Shopee đã duyệt 0»).
- Màn tiền nằm rải ở Shopee, Đơn & hoa hồng, Ví khách, Cài đặt; nút quay lại dẫn sang chỗ khác.

## Quyết định
1. **Một nguồn số**: `cashback_bot/money_flow.py` → `snapshot(conn)` (kỳ thanh toán, tiền hoàn của khách, quỹ chi trả, điều chỉnh mở). Mọi màn tiền (Telegram, web) đọc từ đây. Bỏ `payouts.owner_position` và `insights.Liabilities`.
2. **Mô hình nghiệp vụ**: Đơn → Shopee duyệt, gom vào kỳ → Shopee chuyển (HH − phí − thuế giữ) → tiền về tài khoản = kỳ khớp → chia tiền hoàn khách + phần anh.
   - Phần anh: **Thực nhận** = tiền về − tiền hoàn của đơn trong các kỳ khớp (phí, thuế cả kỳ trừ vào phần anh); **Sắp về** = kỳ chưa khớp.
   - Tiền hoàn của khách: **Chờ Shopee trả → Trong ví → Đang chờ chuyển → Đã chuyển** (+ «Chờ đủ ngày giữ», «Đang trừ lại»).
   - **Quỹ chi trả** chỉ một nghĩa: phần đơn bot của kỳ khớp sau phí, thuế − đang chờ chuyển − đã chuyển.
   - Số **ước tính** (dự phòng, biên) chỉ ở Dòng tiền / % hoàn / Mô phỏng, luôn ghi «ước tính».
   - Đơn trong kỳ khớp (SETTLED) = «Shopee đã trả» ở màn Duyệt hoa hồng, không còn «cần kiểm tra».
3. **Một bộ từ ngữ**: hằng số trong `admin/ui/glossary.py` (WAIT_SHOPEE, IN_WALLET, RESERVED, PAID_OUT, FUND_LEFT, OWNER_REAL, OWNER_SOON…); bảng Thuật ngữ viết lại theo mô hình trên.
4. **Một chỗ**: trang chủ → 💰 Tiền & ví (Ví của anh, Ví khách, Kỳ thanh toán Shopee, Dòng tiền, ⚙️ Cài đặt tiền: % hoàn, dự phòng thuế & phí, giữ tiền & rút, chi phí vận hành, mô phỏng, hoà vốn, sẵn sàng chi trả). Tiêu đề «Quản trị › Tiền & ví › …», nút quay về đúng cha và luôn có ◀️ Tổng quan. Đơn (Duyệt hoa hồng, Theo dõi đơn) ở 🧾 Đơn & hoa hồng; Shopee chỉ còn kết nối / đồng bộ.

## Hệ quả
- Thêm khái niệm tiền mới: thêm vào `money_flow.Snapshot`, đặt tên trong `glossary.py`, rồi mới dùng ở màn.
- Test `tests/test_cashback_owner_wallet.py` khoá: cùng số trên mọi màn, cùng tiêu đề / nút quay lại, không còn câu cũ.
- Phía khách (2026-11-03, cùng ngày): tên gọi chuyển vào `money_flow.py`, admin (`glossary.py`) và khách (`messages.py`, Zalo dùng chung) cùng đọc. Ví khách: Trong ví (rút được) · Chờ Shopee trả · Đang chờ chuyển · Đã chuyển cho bạn · Đang trừ lại. Tiến trình đơn: Đã mua › Hoàn thành › Shopee trả › Vào ví (đơn trong kỳ khớp = Shopee đã trả). Đơn đã vào ví hiện «tiền hoàn», không còn «tạm tính».
