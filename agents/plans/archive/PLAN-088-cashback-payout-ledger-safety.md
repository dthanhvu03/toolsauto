# PLAN-088 — Cashback: sổ chi trả trước khi mở ví, câu chữ ví, dữ liệu cá nhân

| | |
|---|---|
| Executor | Claude Code (chủ bot giao trực tiếp 2026-10-25: "duyệt và vá tất cả") |
| Nguồn | `reports/CASHBACK_REVIEW_2026-10-25.md` mục B1–B17, C1–C7; ADR-059 |
| Không đổi | Khoá tài chính vẫn đóng; không bật ví, không tạo payout, không ghi quyết định chính sách |
| Trạng thái | ✅ Done 2026-10-25: hai bot chạy `1b957b7`. Việc còn mở ở mục «Chưa làm» chuyển sang PLAN sau |

## Scope đã làm

| # | Sửa | File |
|---|---|---|
| B1 | Trước khi duyệt chi hoặc bắt đầu chuyển, mọi khoản nguồn phải còn `available`; nếu không, báo `source_changed`. Màn chi tiết có thêm điều kiện «khoản nguồn còn trong ví» | `payouts.py`, `payout_readiness.py`, `admin_wallet.py` |
| B2 | `needs_review`: nếu đã từng tới bước Đang chuyển thì không quay lại vòng duyệt hay từ chối. Nếu chưa từng chuyển thì không nhảy thẳng tới «đã gửi» | `payouts.py` |
| B3 | Quỹ chỉ cộng các dòng thuộc chứng từ thanh toán hiện hành (`statement_evidence_id`) | `payouts.py` |
| B4 | Thu hồi theo ADR-059: Shopee giảm hoa hồng thì thêm dòng `<conv>:clawback:n` (số âm) và báo admin; số dư âm thì khoá rút tới khi đơn sau bù đủ, yêu cầu đang mở chuyển «cần kiểm tra». Kỳ bị đảo thì khoản về `holding`. Huỷ sau khi đã trừ một phần thì không trừ lần hai | `wallet.py`, `payouts.py`, `service.py`, `admin_notify.py`, `messages.py` |
| B5 | Mã callback Zalo gắn theo từng tin, nên khách Zalo rút được nhiều lần | `zalo_bot.py` |
| B6 | Nút Rút lấy min(số dư, hạn mức mỗi lần, phần còn lại của ngày và tháng); phần còn lại rút lần sau | `payouts.py`, `wallet.py`, `service.py`, `messages.py` |
| B7 | Ghi «đã gửi / đã trả» không còn bị chặn bởi backup cũ, hạn mức vừa hạ hay quỹ. Kiểm tra quỹ cũ (`shopee_settlements`) chuyển lên bước Đang chuyển | `wallet.py` |
| B8 | Trigger DB: máy trạng thái (khớp `TRANSITIONS`, có test so khớp), chặn quay lại vòng duyệt sau khi đã chuyển, khoá theo dữ liệu (`financial_lock_v2_*`: cần kỳ MATCHED, quyết định thuế APPROVED, đơn đã SETTLED). Chỉ thêm, không xoá trigger cũ | `db.py` |
| B9 | Đổi tài khoản thì chờ 7 ngày (`bank_cooldown`). Admin bấm 👥 Thành viên → ✅ Xác minh tài khoản thì khách rút ngay. Khai lần đầu không phải chờ | `payouts.py`, `admin_wallet.py`, `messages.py` |
| B10 | Escape lý do từ chối hoặc huỷ trước khi gửi khách | `admin_wallet.py` |
| B11 | Câu chữ đúng cho cả khi ví mở và khi ví tắt: "vào ví khi Shopee đã duyệt và thanh toán, sớm nhất N ngày…". Mô tả bot có bản khi ví mở; màn điều khoản theo công tắc ví | `messages.py`, `customer_desk.py`, `poller.py` |
| B12 | Màn chi tiết bớt dòng nguồn để giữ phần Điều kiện và Lịch sử, không cắt giữa thẻ HTML. Mọi yêu cầu đang mở (tối đa 10) đều có nút | `admin_ui.py` |
| B13 | Điều kiện điều khoản chi trả: đồng ý bản trong quyết định hoặc bản công bố sau nó | `payout_readiness.py` |
| B14 | Màn Ví hiện hạn mức và khoản đang bị trừ lại. Câu hạn mức ghi "bạn đã rút tới hạn mức…", bỏ câu hứa "bot sẽ báo" | `messages.py` |
| B15 | Tin đã trả kèm mã giao dịch. Tin tiền trở lại ví có tiêu đề theo từng trường hợp. Câu "nhắn admin" đổi thành `/hotro` | `messages.py`, `admin_wallet.py` |
| B16 | Đổi số ngày giữ phải bấm xác nhận; chọn 0 ngày có cảnh báo | `admin_wallet.py` |
| B17 | `DEFAULT_HOLD_DAYS` = 15. Production đã đặt 15 nên không đổi gì | `wallet.py` |
| C3 | Tin admin có số tài khoản đầy đủ: gửi xong thì xoá nội dung trong `outbound_messages` | `db.py`, `admin_ui.py` |
| C4 | Cảnh báo lúc khởi động nếu chat admin không phải chat riêng của admin. Production: đúng chat riêng | `poller.py` |
| C5 | CSV: ô chữ bắt đầu bằng `= + - @` được thêm `'` ở đầu | `admin_stats.py` |
| C6 | Tối đa 5 ticket mới mỗi khách trong 24 giờ; bổ sung vào ticket cũ không giới hạn | `support.py`, `customer_desk.py`, `messages.py` |
| C7 | `storage/db/config/gemini_cookies.json` đổi 0644 → 0600. Mọi tiến trình đọc file đều chạy bằng root. Nếu script đăng nhập Gemini tạo lại file thì quyền có thể về 0644 | quyền file (không phải code) |

## Chưa làm: cần chủ bot quyết hoặc cần dữ liệu thật

| # | Việc | Vì sao |
|---|---|---|
| C2 | Công cụ xoá / ẩn danh dữ liệu và hạn lưu từng loại | Chủ bot cần chọn: giữ chứng từ chi trả để kê khai thuế (A1), còn xoá được gì (tên, tài khoản ngân hàng, nội dung ticket) và giữ bao lâu |
| C1 | Công bố V3 (có dữ liệu ngân hàng) | Công bố khi ví sắp mở, như đã thống nhất |
| ADR-059 | Đọc báo cáo thanh toán Shopee vào đối soát, cùng bảng `shopee_settlements` / `payout_tax_policies` (migration 007) | Cần file báo cáo thật của lần trả đầu tiên cho đơn qua bot; migration cần PLAN và chủ bot duyệt |
| B17 | `entry_payable` vẫn chấp nhận kỳ `shopee_settlements` có `period >=` | Không cần sửa: từ PLAN-078 mỗi đơn đã phải SETTLED trong một kỳ MATCHED; bảng cũ chỉ là lớp khoá phụ |

## Proof

- `pytest tests/test_cashback_*.py`: **773 passed**.
- `tests/test_cashback_payout_safety.py` có 22 test mới. Đã sửa 11 test cũ theo hành vi mới:
  - mặc định 15 ngày;
  - đổi ngày giữ phải xác nhận;
  - Rút tự cắt theo hạn mức;
  - tiêu đề tin;
  - kỳ trong test có chứng từ hiện hành.
- `ruff check cashback_bot/`: sạch.
- Bản sao DB production (0600, scratchpad, đã shred): `migrate` hai lần không lỗi, có 5 trigger mới, ví vẫn khoá (4 lý do), số liệu không đổi.
- Production sau restart: 5 trigger mới đã có trong DB; ví vẫn khoá (`wallet_enabled=0`, 0 payout); `gate_b_check` OK.
