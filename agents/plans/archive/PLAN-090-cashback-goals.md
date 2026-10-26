# PLAN-090 — 🎯 Mục tiêu của bot cashback (Telegram + web)

| | |
|---|---|
| Executor | Claude Code (chủ bot giao 2026-10-26: "xây dựng mục tiêu của bot", "oke em triển khai đi") |
| Trạng thái | ✅ Đang chạy production từ 2026-10-26 01:35Z (`bbc1da8`, chủ bot đã restart) |
| Không đổi | Không đổi % hoàn, sổ ví, chính sách hay trạng thái đơn; không gọi Shopee. Ghi duy nhất: mục tiêu admin nhập (`bot_state.goals_monthly`, có 📊 Lịch sử) |
| Nguồn số | `cashback_bot/insights.py`, cùng nguồn với PLAN-089 |

## 1. Khung mục tiêu (chủ bot đồng ý 2026-10-26)

- **Chỉ số chính (North Star): đơn hoàn thành mỗi tháng**: vừa ra tiền thật, vừa cho thấy khách tin bot.
- **Giai đoạn**
  - G1 · Chạy trọn vòng tiền: đi qua 4 mốc, tự đọc từ dữ liệu: đơn đầu tiên → đơn đầu tiên hoàn thành → Shopee trả đơn đầu tiên → khách đầu tiên nhận tiền.
  - G2 · Đủ dữ liệu: gợi ý 100 đơn hoàn thành / tháng và 50 khách hoạt động.
  - G3 · Hoà vốn: mức HH ròng lấy từ 🧮 Hoà vốn.
- **Mục tiêu chủ bot tự nhập.** Bot không tự đặt số. Mục nào chưa nhập thì chỉ hiện số thật. Các số gợi ý chỉ hiện ở màn nhập.

| Mã | Mục tiêu | Cách đo | Kiểu |
|---|---|---|---|
| `completed` | ⭐ Đơn hoàn thành trong tháng | `shopee_conversions.complete_time` trong tháng (giờ VN), dòng sổ chưa huỷ | cộng dồn, có dự báo |
| `net` | Hoa hồng ròng trong tháng | `money(tháng).net` (tạm tính) | cộng dồn, có dự báo |
| `new` | Khách mới trong tháng | `telegram_users.created_at` trong tháng | cộng dồn, có dự báo |
| `active` | Khách hoạt động 30 ngày | `growth.active_30d` | mức hiện tại |
| `activation` | % khách mới có đơn trong 7 ngày | khách vào từ 37 tới 7 ngày trước, có đơn ≤ 7 ngày sau khi vào | mức hiện tại |
| `cancel` | Tỉ lệ huỷ 30 ngày tối đa | `money(30 ngày).cancel_rate` | giới hạn trên |

- **Dự báo cuối tháng** = số đã đạt × số ngày trong tháng ÷ số ngày đã qua (ít nhất 1 ngày).
- **Cần mỗi ngày** = phần còn thiếu ÷ số ngày còn lại.
- Đơn hoàn thành đến chậm vài tuần sau ngày đặt, nên màn hiện kèm số **đơn đặt trong tháng**.

**Giới hạn an toàn** (không được xấu đi khi chạy theo tăng trưởng), dùng lại ngưỡng của 🛠 Vận hành:
- tỉ lệ huỷ (ngưỡng do chủ bot nhập);
- số khách có biên âm, số khách có số dư âm;
- tin gửi khách lỗi trong 24 giờ;
- ticket mở quá 24 giờ;
- cảnh báo sổ ví.

## 2. Giao diện

- **Telegram:** `/admin` → 🎯 Mục tiêu (`c:in:t`).
  - Nút ✍️ cho từng mục (`c:in:t:<mã>`). Gõ số để đặt, gõ `bỏ` để xoá.
  - Chờ nhập 10 phút; gõ lệnh `/` thì huỷ chờ.
  - Ghi audit action `goal`.
- **Web:** thẻ 🎯 Mục tiêu trên `/cashback`. Chỉ đọc, nhập ở Telegram.

## 3. Phạm vi file

- `cashback_bot/insights.py`: `GOALS`, `goal_targets`, `goals()`.
- `cashback_bot/admin_insights.py`: màn, nhập, `parse_goal`.
- `cashback_bot/admin_policy.py`: kiểu dữ liệu chờ nhập, dòng 📊 Lịch sử `goal`.
- `cashback_bot/admin_ui.py`: nút menu.
- `app/features/cashback_insights/router.py` và `app/templates/pages/cashback_overview.html`: thẻ web.
- `tests/test_cashback_insights.py`.

## 4. Proof

- `pytest tests/test_cashback_*.py`: 792 passed. `ruff check`: sạch.
- Test mới trong `tests/test_cashback_insights.py`:
  - `test_muc_tieu_so_that_trang_thai_va_moc`: số thật, các trạng thái, 4 mốc, mục lạ / hỏng bị bỏ qua, chưa đủ mẫu.
  - `test_man_muc_tieu_telegram_nhap_bo_va_lich_su`: nhập, `bỏ`, huỷ chờ khi bấm màn khác, 📊 Lịch sử.
  - `test_doc_so_muc_tieu`.
  - `test_web_the_muc_tieu`.
- Render trên DB production (`mode=ro`):
  - Giai đoạn G1, 1/4 mốc.
  - Tháng 10: đơn hoàn thành 0 (2 đơn đặt); HH ròng 18.740đ, dự báo khoảng 22,9k; khách mới 11; khách hoạt động 11; % có đơn trong 7 ngày chưa đủ mẫu (11 khách chưa đủ 7 ngày).
  - Giới hạn an toàn đều xanh.
