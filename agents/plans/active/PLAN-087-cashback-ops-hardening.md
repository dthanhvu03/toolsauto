# PLAN-087 — Cashback: vận hành (rớt mạng, 400, Zalo, đồng bộ, backup, canh bot)

| | |
|---|---|
| Executor | Claude Code (chủ bot giao trực tiếp 2026-10-25: "duyệt và vá tất cả") |
| Nguồn | `reports/CASHBACK_REVIEW_2026-10-25.md` mục A3–A11, D1–D5 |
| Không đổi | Ví, payout, khoá tài chính, quyết định chính sách, `.env` production |
| Trạng thái | Code xong, chờ chủ bot restart cả hai bot |

## Scope

| # | Sửa | File |
|---|---|---|
| A3 | Lỗi trước khi kết nối được (DNS, mất mạng, từ chối kết nối, hết giờ lúc kết nối) là `offline`: tin chắc chắn chưa đi, nên được trả về hàng đợi, không tính lượt thử và dừng vòng gửi. Hết giờ chờ trả lời hoặc đứt giữa chừng vẫn là `ambiguous` (tin khách → `unknown`) | `telegram_api.py` (`never_sent`), `zalo_api.py`, `notify_dispatch.py`, `db.py` (`release_admin_event`), `poller.py` |
| A4 | Tin admin không bị bỏ khi mất mạng lâu (do không tính lượt thử khi `offline`) | như trên |
| A5 | Chỉ 403 mới đánh dấu khách chặn bot; 400 chỉ là `failed` | `notify_dispatch.py` |
| A6 | Bot chết thì systemd tự chạy lại; bot Zalo canh nhịp sống của bot Telegram và báo admin thẳng qua API Telegram | `deploy/cashback/*.service`, `ops_watch.py` |
| A7 | Zalo lỗi DB sau khi ghi inbox: dòng thành `failed/handler_error`, khách nhận câu "bot đang lỗi, thử lại", admin được báo. Lỗi sau khi đã gửi: chỉ báo admin | `zalo_bot.py` |
| A8 | Đồng bộ Shopee: lỗi khi dựng lượt nằm trong `try`; không đóng được lượt thì nhả khoá và hẹn sau 15 phút; luồng nền thấy bận thì đợi một nhịp | `sync_scheduler.py` |
| A9 | Checkout nhiều đơn: chia phí MCN theo tỉ lệ `net / (net + phí)`. Production hiện 0 đơn loại này (đọc `mode=ro`) | `shopee_sync.py` |
| A10 | Zalo: tin nhiều phần lỗi từ phần 2 trở đi thì `unknown`, không gửi lại phần đầu. Mỗi bot chỉ gỡ kẹt `sending` của kênh mình, bot Zalo gỡ lúc khởi động | `zalo_bot.py`, `db.py` |
| A11 | `test_14`: khoá giả dùng giờ thật (nút admin dùng giờ thật) | test |
| A2 / D3 | Backup tay mang tên `cashback-manual-…`, dọn riêng; bản tự động không bị đẩy mất | `backup.py` |
| D1 | Unit systemd hai bot (`Restart=always`, không chạy lại khi thoát mã 2 / 3) | `deploy/cashback/` |
| D4 | Mỗi bot ghi mã commit lúc khởi động; hai bot khác commit thì báo admin một lần | `ops_watch.py`, `admin_notify.py` |
| D5 | 8 giờ sáng: tóm tắt tin `unknown` / `failed` / trả lời cần xem lại trong 24 giờ (chỉ khi có). Logrotate hằng tuần | `ops_watch.py`, `deploy/cashback/logrotate-cashback` |

Ngoài scope:
- Chép backup ra ngoài máy: chờ chủ bot chọn nơi lưu.
- Xoay vòng 7 bản ngày và 4 bản tuần: chưa làm, vì đang giữ 60 bản.
- Cài systemd và logrotate: chủ bot tự chạy theo `deploy/cashback/README.md`.

## Proof

- `pytest tests/test_cashback_*.py`: **751 passed** (trước: 730 passed / 1 failed `test_14`).
- `tests/test_cashback_ops_hardening.py` có 19 test mới; `tests/test_cashback_shopee_sync.py` thêm 1 test MCN.
- `ruff check cashback_bot/`: sạch. Ba lỗi ruff ở `tests/test_cashback_admin.py`, `tests/test_cashback_admin_ui_ux.py`, `tests/test_cashback_wallet.py` có từ trước.
- `systemd-analyze verify` hai unit: không lỗi. `logrotate -d`: đọc được cấu hình.
- Đã thử thật trên máy: lỗi khi gọi `127.0.0.1:9` (từ chối kết nối) và `no-such-host.invalid` (DNS) đều được xếp loại `offline`.
