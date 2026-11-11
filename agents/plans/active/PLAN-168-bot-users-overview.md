# PLAN-168 — Một chỗ xem tổng khách của mọi bot (web + /users Telegram)

- Trạng thái: chủ bot yêu cầu trực tiếp 11/11 («chưa có chỗ nào để anh tổng user»), chọn: cả web lẫn Telegram; cần
  khách mới theo ngày, theo nguồn, khách đang dùng, danh sách khách. Executor: Claude Code (chủ bot giao trực tiếp).
- Bối cảnh: mỗi bot đếm riêng — AI Pass Store ở 📊 Thống kê (Telegram), Cashbot ở 📈 Thống kê + /cashback/users (chỉ Cashbot).

## Phạm vi
1. `cashback_bot/all_users.py`: CHỈ ĐỌC (`mode=ro`) data/cashback.sqlite + data/store.sqlite. Không import store_bot.
   - Bot: `cashbot_tg` (ID dương), `cashbot_zalo` (ID âm, tên từ channel_identities), `ai_store`.
   - Mỗi bot: tổng, mới 24h, mới 7 ngày, đang dùng 7 ngày (Cashbot: tạo link; Store: có đơn hoặc nạp xong), có đơn
     (Cashbot: có đơn Shopee/TikTok ghi nhận; Store: có đơn done).
   - Khách mới theo ngày (14 ngày, giờ VN), theo nguồn (mã `?start=` lưu ở `src:<id>`; không mã = «tự vào»).
   - Danh sách khách gộp, lọc bot + tìm tên / ID.
2. Web: API `GET /bot-users/api/report`, trang React `/app/go/bot-users` «Khách các bot», thêm vào 2 sidebar (React + Jinja).
   Khách Cashbot bấm sang /cashback/users/{id} sẵn có.
3. Telegram: admin Cashbot gõ `/users` → bảng tổng + 7 ngày + nguồn; `/users <tên|ID>` → tối đa 10 khách khớp.

## Ngoài phạm vi
- Không ghi DB, không gộp 1 người dùng nhiều bot (ID Telegram trùng thì vẫn đếm ở mỗi bot, có ghi chú).
- Không thêm lệnh vào AI Pass Store (chủ bot chọn xem ở Cashbot).

## XONG 11/11 (Claude Code)
- `cashback_bot/all_users.py` (report/search, chỉ đọc), API `app/features/bot_users/router.py` `GET /bot-users/api/report?q=&bot=`
  (danh sách tối đa 300 dòng), trang React `frontend/src/features/bot-users` → `/app/go/bot-users`, menu «Khách các bot» cả 2 sidebar.
- Telegram: `cashback_bot/admin/handlers/users.py`, `/users` nối trong `AdminPanel.consume_text` (chỉ admin), thêm vào ADMIN_COMMANDS.
- Số thật 11/11: Cashbot TG 29 · Zalo 21 · Store 55 = 105; mới 7 ngày 77; đang dùng 27; có đơn 18.
- Proof: tests/test_bot_users.py 4 passed; test cashback + zalo + store 1309 passed, 1 hỏng sẵn phụ thuộc giờ thật
  (`test_b9_doi_tai_khoan_cho_7_ngay…`: mốc T cố định + 7 ngày chờ, màn admin so với giờ thật — không liên quan); ruff sạch; tsc + vite OK.
- Cần: `pm2 restart Web_Dashboard` + `systemctl restart cashback-bot cashback-zalo` (menu lệnh /users đăng ký lúc khởi động).
