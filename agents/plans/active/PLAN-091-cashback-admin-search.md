# PLAN-091 — 🔍 Tìm mã cho admin cashback (Telegram + web)

| | |
|---|---|
| Executor | Claude Code (chủ bot duyệt 2026-10-26: "oke em triển khai plan này đi") |
| Trạng thái | ✅ Đã merge vào main 2026-10-26, chờ chủ bot restart |
| Không đổi | Chỉ đọc DB (`mode=ro`), không ghi audit vì không đổi gì; chỉ admin dùng được; số tài khoản chỉ hiện 4 số cuối |

## 1. Một ô tìm, tự nhận ra loại mã

| Gõ | Tìm trong | Kết quả dẫn tới |
|---|---|---|
| Mã link 8 ký tự (`BiE1mRa5`), hoặc dán cả link có `sub_id=` | `link_requests.sub_id` | 🔗 Chi tiết link (mới) |
| Mã đơn Shopee / conversion id | `shopee_conversions.order_sn`, `conversion_id` | 🔗 Chi tiết link của đơn (nếu đơn khớp link bot) |
| `#12` | `support_tickets.id` | 📩 ticket `c:hp:t:<id>` |
| `Hoan tien 000012` | `cashback_payouts.transfer_note` | 👛 yêu cầu rút `c:wl:rq:<id>` |
| Số (`7123456789`, `-5`) | `telegram_users.telegram_user_id` | hồ sơ khách `c:in:d:<id>` |
| `@tên` hoặc chữ | username, tên Zalo, tên sản phẩm của link | hồ sơ khách / chi tiết link |

- Tối đa 10 kết quả. Tìm theo chữ cần ít nhất 2 ký tự.
- Gõ sai mã hoặc không có kết quả: bot báo rõ và gợi ý các dạng mã gõ được.

## 2. 🔗 Chi tiết link

Gồm: khách (bấm sang hồ sơ), sản phẩm, giá, hoàn dự kiến, giờ tạo, trạng thái giao tới khách, số click và click gần nhất (kèm ghi chú báo cáo Shopee về trễ khoảng 1 ngày), các đơn (mã đơn, trạng thái, hoa hồng, hoàn thành), sổ ví (trạng thái, phần khách), ticket gắn với link.

## 3. Giao diện

- **Telegram**
  - Gõ `/tim <mã>`, hoặc bấm `/admin` → 🔍 Tìm (`c:in:f`) rồi gõ mã. Chờ nhập 10 phút.
  - Chi tiết link: `c:in:l:<link_id>`.
  - Thêm lệnh `tim` vào menu lệnh của admin.
- **Web**
  - Ô tìm ở đầu `/cashback`.
  - Trang `/cashback/search?q=` và `/cashback/links/{id}`.
  - Ticket và yêu cầu rút chỉ hiện chữ; xem chi tiết ở Telegram.

## 4. Phạm vi file

- `cashback_bot/insights.py`: `search`, `link_detail`.
- `cashback_bot/admin_insights.py`: màn tìm và màn chi tiết link.
- `cashback_bot/admin_policy.py`: lệnh `/tim`.
- `cashback_bot/admin_ui.py`: nút menu.
- `cashback_bot/messages.py`: `ADMIN_COMMANDS`.
- Web: `app/features/cashback_insights/router.py`, template `cashback_search.html`, `cashback_link.html`, ô tìm trên `cashback_overview.html`.
- `tests/test_cashback_insights.py`.

## 5. Proof

- `pytest tests/test_cashback_*.py`: 797 passed. `ruff check`: sạch.
- Test mới:
  - `test_tim_ma_link_don_khach_san_pham`: link, chữ thường, link có sub_id, mã đơn, ID, @tên, tên có dấu, chi tiết link.
  - `test_tim_ticket_va_yeu_cau_rut`.
  - `test_man_tim_telegram_lenh_va_nut`: `/tim`, nút, chờ nhập, khách thường không dùng được.
  - `test_web_tim_va_chi_tiet_link`.
- Chạy trên DB production (`mode=ro`):
  - `BiE1mRa5` ra 1 link: Zalo · Thanh Vu, đã giao tới khách, 0 click (báo cáo click chưa về), chưa có đơn.
  - "chăn" ra 2 link.
  - Web `/cashback/search`, `/cashback/links/{id}`, `/cashback` đều trả 200.
