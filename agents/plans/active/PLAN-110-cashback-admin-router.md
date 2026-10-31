# PLAN-110 — Admin cashback: tách UI, nối AdminRouter, tách panel.py

- **Executor:** Claude Code
- **Duyệt:** chủ bot, 2026-10-31 («em làm bước 2 và bước 3 cho anh luôn nha»), sau Bước 1 (b60296b).
- **Nguyên tắc:** chỉ đổi cấu trúc, **không đổi hành vi**. Câu chữ, nút, callback_data, SQL, thứ tự xử lý giữ nguyên. Bộ test cashback là thước đo: phải giữ 1102 qua + 1 hỏng sẵn `test_b9`.

## Bước 2 — Tách `cashback_bot/admin/ui/__init__.py` (1.193 dòng)

| File | Chứa |
|---|---|
| `ui/keyboards.py` | `Keyboard`, mọi hằng `*_KEYBOARD`, `BACK_HOME`, `WALLET_ADMIN_BACK`, hàm `*_keyboard`, `with_rows` |
| `ui/glossary.py` | `GLOSSARY`, `ADMIN_KEEP_NOTE`, bảng nhãn / mã (`STATS_PERIODS`, `PAYOUT_STATUS`, `STEP_*`…) |
| `ui/views.py` | Hàm `*_text` và hàm phụ định dạng |
| `ui/__init__.py` | Re-export tên công khai (đường import cũ `cashback_bot.admin.ui` / `admin_ui` không đổi) |

## Bước 3 — Nối `AdminRouter`, tách `panel.py` (1.725 dòng)

1. `BaseAdminHandler` thêm `keeps_state(data)` (mặc định = `can_handle`). `AdminRouter.clear_states` dọn theo `keeps_state`; `dispatch_text` hỏi theo thứ tự đăng ký.
2. Luật dọn trạng thái chờ giữ đúng như cũ:
   - cookie Shopee: giữ khi `c:shopee:auth`;
   - mô phỏng: giữ khi `c:sim:input`;
   - hỗ trợ: `c:hp:*`;
   - ví: `c:wl:mv:*`, `c:wl:vb:*`;
   - insights: `c:in:cost`, `c:in:f`, `c:in:t:*`;
   - giữ chân: `c:rt:e:*`.
3. Thứ tự xử lý chữ giữ đúng: `/tim` → cookie Shopee → mô phỏng → hỗ trợ → ví → giữ chân → insights → dự phòng → chia → số chính sách.
4. Tách khỏi `panel.py`:
   - `handlers/shopee.py`: màn Shopee, tự đồng bộ, đồng bộ tay, CSV, dán cookie;
   - `handlers/simulation.py`: 🧮 mô phỏng;
   - `handlers/policy.py`: bản nháp hạng, dự phòng phí / thuế, tỷ lệ chia, huỷ lịch.
5. Màn domain cũ (ví, insights, TikTok…) đăng ký qua adapter `route(user_id, data, now)`; `ReconciliationAdmin` / `AutoSyncAdmin` có adapter riêng cho chữ ký khác.
6. `panel.py` còn: cấu hình, `menu` / `consume_text` / `handle_callback`, các màn tổng quan / cài đặt / chính sách / hạng / phí / lịch sử, `resolve_policy`, kết nối DB + audit. Tên cũ (`parse_sim_amount`, `SIM_AMOUNTS`, `customer_policy_due`…) vẫn import được từ `panel` / `admin_policy`.

## Ngoài phạm vi

Không sửa handler domain (wallet, insights…) ngoài phần adapter, không đổi câu chữ, không đổi DB / migration, không restart bot.

## Kết quả

- **Bước 2:** `ui/__init__.py` 1.193 → re-export 70 tên; `keyboards.py` 218, `views.py` 896, `glossary.py` 91 dòng. Tách bằng AST, giữ nguyên chữ nguồn; so hằng số với bản cũ: không khác. Chiều import một hướng: keyboards → views / glossary, views → glossary.
- **Bước 3:** `panel.py` 1.725 → 477 dòng. Mới:
  - `admin/common.py` (hằng + `percent` / `stamp` / `AdminSafetyError`);
  - `admin/routes.py` (`DomainRoute` + `build_router`, 20 handler);
  - `handlers/shopee.py`, `simulation.py`, `policy.py`, `history.py`.
  - `BaseAdminHandler` thêm `callback_exact`, `keeps_state`, `consume_text(…, message_id)`. `AdminRouter.register` báo lỗi khi hai handler trùng callback.
  - Panel dựng router trong `__post_init__` (cả khi `dataclasses.replace`); trạng thái chờ vẫn là dict trên panel như cũ.
  - Test đổi 1 dòng: `patch` cookie trỏ `cashback_bot.admin.handlers.shopee.save_cookies` (code dán cookie đã chuyển sang đó).
- `AdminContext` vẫn chưa có nơi dùng (giữ, không thuộc phạm vi).

## Kiểm tra (proof)

- [x] Bước 2: toàn bộ test cashback (chặn TCP) 1102 qua, 1 hỏng sẵn `test_b9`; ruff `cashback_bot` sạch.
- [x] Bước 3, so trực tiếp bản cũ / mới: cùng chuỗi 196 nút (đi hết các màn từ trang chủ) + 12 lượt gõ chữ (mô phỏng, hạng, tỷ lệ chia, chi phí, tìm, cookie, `/tim`, số %), nonce cố định → 220 phản hồi **giống hệt từng byte** (chữ, nút, toast, file, xoá tin).
- [x] Bước 3: `tests/test_cashback_admin_router.py` (luật giữ trạng thái chờ 15 trường hợp, thứ tự chữ, nút lạ, trùng callback, `replace`, tên cũ) + test admin liên quan: 169 qua.
- [x] Bước 3: toàn bộ test cashback (chặn TCP) 1123 qua (1102 cũ + 21 test router), 1 hỏng sẵn `test_b9`; ruff `cashback_bot` sạch.
