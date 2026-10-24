# Cashback Bot — Production Safety Hardening V1

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Nhánh | `cursor/cashback-safety-hardening`, tách từ `main@eca64fd` |
| Worktree | `/home/vu/toolsauto-cashback-safety` |
| Đầu vào | `reports/CASHBACK_FULL_AUDIT.md`: P0-4, P1-8, P1-9 và khoá tài chính cho P0-1, P0-2, P0-3 |
| Triển khai production | **CHƯA. Không được phép tự triển khai** |

---

## A. Preflight

| Mục | Trạng thái lúc bắt đầu |
|---|---|
| Process | PID 590993, `.venv/bin/python -m cashback_bot`, cwd `/home/vu/toolsauto`, khởi động 2026-10-24 02:14:25 UTC |
| DB đang dùng | `/home/vu/toolsauto/data/cashback.sqlite` (fd của process), lock `/tmp/cashback_bot.lock` |
| Git production | `main`, HEAD `eca64fd`, `git status` sạch |
| Worktree / branch | chưa tồn tại → tạo mới `/home/vu/toolsauto-cashback-safety` trên `cursor/cashback-safety-hardening` |
| Ví | `wallet_enabled=0`; 2 khoản `pending`; 0 yêu cầu rút |
| Migration | không có bảng phiên bản; 001, 004–006 đã có; 003 chưa áp dụng |
| Test baseline | 291 passed (`tests/test_cashback_*.py`), chạy trong worktree với biến môi trường giả cho app chung; không chép `.env` |

---

## B. Nguyên nhân

| Lỗi | Nguyên nhân | Vị trí | Tái hiện |
|---|---|---|---|
| P0-4 update làm kẹt bot | Vòng `for update` không bắt lỗi từng update. Lỗi bay ra `_loop`, nghỉ 5s rồi lấy lại đúng offset cũ, lặp mãi | `poller.process_updates` (cũ 228-296), `_loop` | `handle_update` ném `KeyError` với một update: bot không bao giờ xử lý update sau |
| P0-4 phụ: lỗi Telegram phụ cũng chặn | `answer_callback`, `send_document`, `send_chat_action` không bọc lỗi | `poller.process_updates` | Mạng lỗi lúc trả lời nút: cả update bị thử lại |
| P2-7 cảnh báo một lần trong đời | `event_key` cảnh báo lỗi vòng lặp không có thời gian (`request_failed:poll_loop_failed:0:0`) | `admin_notify.notify_request_failed` | Lỗi vòng lặp lần 2 không bao giờ báo admin |
| P1-8 token vào log | Log nguyên chuỗi lỗi của `requests`, mà chuỗi này chứa `/bot<TOKEN>/…` | `telegram_api.edit_message_text`, `delete_message`; tương tự `shopee_sync` (2 chỗ), `poller` (1), `shopee_cookie` (2) | `requests.ConnectionError("…url: /bot<TOKEN>/editMessageText")` |
| P1-9 backup tay | Không có lịch; `_prune` xoá theo glob rộng; không kiểm tra bảng; file 0644 | `backup.py`, BACKUP.md | — |
| Khoá tài chính | Ví đưa khoản sang `available` theo `COMPLETED + N ngày`; bật ví chỉ là một dòng `bot_state`; tạo yêu cầu rút và xác nhận "đã chuyển" không có điều kiện Shopee đã trả | `wallet.refresh`, `wallet.set_enabled`, `wallet.request_payout`, `wallet.decide_payout`, `admin_wallet` | Bật ví, đơn hoàn thành 15 ngày → khách rút được tiền Shopee chưa trả |

---

## C. Đã sửa

### P0-4 — Cô lập từng update (`poller.py`, `db.py`)
- Tách `_process_one`. Mỗi update được bọc riêng và phân loại lỗi (`classify_update_error`):
  - `network`, `telegram_send`, `database`: thử lại tối đa 5 lần. `unknown`: tối đa 3 lần.
  - `business` (`CalculationError`, `ReconciliationRequired`, `AdminSafetyError`), `invalid_update` (`KeyError`, `TypeError`, `ValueError`, …) và `telegram_rejected` (4xx): lỗi vĩnh viễn.
- Lỗi tạm: ghi `failed_updates`, **giữ offset**, dừng lô hiện tại để không đảo thứ tự. Lần poll sau thử lại, giãn cách 1, 2, 4, 8 giây.
- Lỗi vĩnh viễn hoặc hết lượt: ghi bền vững → `quarantined` → báo admin (một tin cho mỗi update) → **rồi mới** tiến offset.
- Không ghi được bản cách ly (DB hỏng): lỗi bay ra ngoài, offset giữ nguyên.
- Bảng mới `failed_updates`: khoá chính `telegram_update_id`, gồm loại update, người gửi, nhóm lỗi, mã lỗi, chi tiết đã che, số lần, trạng thái, thời gian. Không lưu nội dung tin.
- Lỗi của các lệnh gọi Telegram phụ (typing, xoá tin, trả lời nút, gửi file, gửi ảnh) chỉ ghi log, không làm hỏng update.
- Cảnh báo lỗi vòng lặp giờ có mốc thời gian trong khoá. Chống spam vẫn do giới hạn 1 tin/phút theo loại lỗi.
- Màn 📊 Thống kê hiện "Update cách ly: N".
- Giữ nguyên: chống trùng link (`telegram_update_id UNIQUE`), outbox, thứ tự xử lý.

### P1-8 — Log an toàn (`redact.py` mới, `telegram_api.py`, `shopee_sync.py`, `shopee_cookie.py`, `poller.py`, `backup.py`)
- `redact()` che token Telegram (có hoặc không có `/bot`), cookie `SPC_*`, header Cookie và Authorization, `api_key=`, `token=`, `secret=`. Không bao giờ ném lỗi.
- `error_brief(exc)` trả `Loại: thông điệp đã che`, cắt 200 ký tự.
- `RedactingFormatter` gắn vào mọi handler của process (`configure_logging`), nên traceback cũng được che. Đây là lớp chặn thứ hai cho các chỗ sót.
- Sửa toàn bộ 11 chỗ log hoặc lưu chuỗi lỗi thô. Lỗi cookie chỉ log tên loại lỗi.
- Đã kiểm: API key AddLiveTag đi trong header (`X-API-Key`), không nằm trong URL. Lỗi Shopee đã tự làm sạch thông điệp.
- Không đổi quyền file production (xem F).

### P1-9 — Backup tự động (`backup.py`, `poller._check_backup`, BACKUP.md)
- Bot tự backup **mỗi 24 giờ** trong vòng lặp; lỗi thì báo admin (`backup_failed`) và thử lại sau 1 giờ. **Một cơ chế duy nhất, không cài cron.** Lý do: máy có sẵn cron và systemd, nhưng chạy trong bot thì triển khai chỉ cần restart, và cảnh báo đi chung hàng đợi có sẵn.
- Vẫn dùng SQLite Backup API. Ghi ra `.partial`, kiểm tra `integrity_check` và đủ bảng chính, rồi mới đổi tên. File 0600, thư mục 0700.
- Sau mỗi lần backup, mở lại bản vừa tạo ở chế độ chỉ đọc để kiểm tra (`verify_backup`).
- Dọn chỉ file đúng mẫu `cashback-<UTC>Z.sqlite`, sàn tối thiểu 3 bản, không bao giờ xoá bản vừa tạo hay file lạ.
- `python -m cashback_bot.backup` trả mã 1 khi lỗi.
- `OFFSITE_BACKUP = NOT CONFIGURED`.

### Khoá tài chính (`payout_gate.py` mới, `wallet.py`, `admin_wallet.py`, `db.py`, `admin_ui.py`, `messages.py`)
- Tách bốn khái niệm:
  - `wallet_feature_enabled`: công tắc đã lưu trong `bot_state`.
  - `financial_readiness_verified`: `FinancialGate.readiness()`.
  - `withdrawal_allowed`: `check_withdrawal`.
  - `payout_allowed`: `check_payout`.
  - `WalletSettings.enabled` = công tắc **và** sẵn sàng tài chính.
- Điều kiện sẵn sàng là có dòng trong `shopee_settlements` (kỳ Shopee đã trả, có mã chứng từ) **và** `payout_tax_policies` (thuế người nhận đã duyệt).
  - Hai bảng này **chưa tồn tại** trên production. DDL chỉ là nháp (`migrations/007_settlement_evidence.DRAFT.sql`), không tự áp dụng, nên mặc định luôn **KHOÁ**.
  - Không có công tắc admin nào bỏ qua được.
- Điều kiện từng khoản (`entry_payable`): đủ ngày giữ, **không gian lận** (`is_fraud=1` hoặc có `fraud_reason`; raw hỏng cũng coi là chưa sạch), có `validation_month`, và tháng đó đã có kỳ Shopee trả.
- `wallet.refresh`:
  - `COMPLETED + N ngày` giờ chỉ còn là `holding`, `available_at = NULL`.
  - Không tự chuyển khoản cũ nào sang `available`.
  - Không xoá dòng nào.
- Các thao tác bị chặn khi còn khoá:
  - `set_enabled(True)`: ném `PayoutBlocked`.
  - `request_payout`: trả `locked`, hoặc `fund` khi vượt số Shopee đã trả.
  - `decide_payout(paid=True)`: ném `PayoutBlocked`, kiểm tra trong `BEGIN IMMEDIATE`. Từ chối yêu cầu vẫn làm được vì tiền chỉ trở lại ví.
- `admin_wallet`:
  - Nút bật ví và callback cũ `c:wl:on:ok` đều bị từ chối.
  - Không tạo ảnh QR khi còn khoá.
  - Màn ví hiện "🔒 KHOÁ TÀI CHÍNH" kèm từng lý do.
- **Trigger SQLite** (lớp chặn cuối, kể cả khi gọi SQL trực tiếp): khi chưa có hai bảng bằng chứng thì không ghi được entry `available`, không chèn được `cashback_payouts`, không đặt được `paid`.
- Không bị chặn: tạo link, đồng bộ Shopee, ghi cashback pending/holding, màn đối soát của admin, các lệnh thông tin.

### Giữ nguyên
- Công thức báo giá V1.1 (70%) và V1.2: không sửa `pricing.py`, `calculator.py`, `money.py`, `service._quote_cashback`.
- Hạng thành viên vẫn tắt.
- Snapshot trên link không đổi.

---

## D. Bằng chứng test

| Nhóm | Test | Kết quả |
|---|---|---|
| Toàn bộ cashback | `tests/test_cashback_*.py` | **334 passed** (291 cũ + 43 mới). ruff sạch |
| Cô lập update | `TestUpdateIsolation` (13 test): lỗi vĩnh viễn được cách ly và update sau vẫn chạy; lỗi tạm giữ offset rồi thử lại thành công (`resolved`); lỗi mạng kéo dài bị cách ly đúng lần thứ 5 với giãn cách 1, 2, 4, 8 (không lặp vô hạn); bản ghi còn sau restart; không ghi được bản cách ly thì không tiến offset; thử lại cùng update không tạo link hay outbound thứ hai; outbox không bị đụng; lệnh Telegram phụ lỗi không hỏng update; chi tiết lỗi đã che token và cookie; phân loại 7 nhóm; cảnh báo vòng lặp không còn "một lần trong đời"; số update cách ly hiện ở 📊 | pass |
| Log an toàn | `TestSecretSafeLogging` (10 test): giả lập `ConnectionError` có token trong URL cho `editMessageText`/`deleteMessage`, log không có token nhưng có tên thao tác và loại lỗi; nội dung HTTP lỗi được che; traceback chứa token, cookie, API key bị che; formatter không ném lỗi thứ cấp; 5 mẫu bí mật; chữ debug bình thường giữ nguyên | pass |
| Backup | `TestBackup` (5 test) và `test_prune_backup_cu` (cập nhật): backup → restore ra file mới → `integrity_check` → đếm dòng; quyền 0600/0700; từ chối ghi đè DB đang chạy; phát hiện backup hỏng; thiếu bảng thì lỗi và không để lại file; lịch 24 giờ, lỗi báo admin một lần, thử lại sau 1 giờ; không đổi mtime DB nguồn; file lạ không bị dọn; sàn 3 bản | pass |
| Khoá tài chính | `TestFinancialLock` (15 test): mặc định khoá với 2 lý do; admin bấm bật ví hoặc callback cũ đều bị từ chối; `set_enabled(True)` trực tiếp ném lỗi; công tắc đã lưu "1" không mở ví; `COMPLETED + 40 ngày` thiếu bằng chứng vẫn `holding`; đơn gian lận không bao giờ `available` kể cả khi đủ bằng chứng; kỳ chưa trả thì không `available`; chỉ có settlement hoặc chỉ có thuế vẫn khoá; `request_payout` trực tiếp trả `locked`; thiếu quỹ trả `fund`; mất điều kiện thuế sau khi khách yêu cầu thì `paid` bị chặn, nút admin cũ bị chặn, không có QR, từ chối vẫn được; tổng chi vượt số Shopee trả thì `paid` bị chặn; SQL trực tiếp bị trigger chặn; lịch sử giữ nguyên, tạo link và theo dõi đơn vẫn chạy; báo giá V1.1 vẫn 14.000đ | pass |
| Test cũ được cập nhật theo quy tắc mới | `test_cashback_wallet.py`, `test_cashback_vietqr.py`: luồng rút tiền dựng bằng chứng **trong DB test** bằng DDL nháp; `holding` không còn ngày vào ví cố định | pass |
| Diễn tập migration | Bản sao DB production (SQLite Backup API, 0600, scratchpad), chạy `migrate()` 2 lần: chỉ thêm `failed_updates` và 4 trigger, không bảng nào đổi số dòng, 2 khoản pending giữ nguyên số tiền, ví khoá với 2 lý do, `set_enabled(True)` bị chặn, `integrity_check=ok`. Bản sao **đã xoá** | đạt |
| Không có traffic thật | Mọi lệnh gọi Telegram/Shopee/AddLiveTag trong test đều là mock | — |

Chưa chạy: bộ test ngoài cashback (Buffer, Viral…). Hai bộ đó không import `cashback_bot`.

---

## E. An toàn production

| Câu hỏi | Trả lời |
|---|---|
| Source production có đổi không? | **Không.** Mọi thay đổi nằm trong worktree và nhánh mới. `main@eca64fd` không đổi |
| SQLite production có đổi không? | **Không do task này.** Chỉ mở `mode=ro` và sao chép bằng Backup API. mtime thay đổi trong thời gian làm là do chính bot ghi offset và trạng thái định kỳ |
| Process có bị restart không? | **Không.** PID 590993 vẫn chạy |
| `.env`, quyền file, crontab | Không đổi |
| Traffic Telegram/Shopee/AddLiveTag ngoài ý muốn | Không |

---

## F. Kế hoạch triển khai (chờ chủ bot duyệt)

**Điều kiện:** chủ bot duyệt; đọc diff của nhánh; Anti xác nhận phạm vi. Không có thay đổi chưa commit trên `main`.

1. **Backup trước:**
   ```bash
   cd /home/vu/toolsauto && umask 077 && .venv/bin/python -m cashback_bot.backup
   ```
   Ghi lại tên file in ra.
2. **Merge:** `git merge --ff-only cursor/cashback-safety-hardening` trên `main`, rồi push.
3. **Restart** (chủ bot chạy; thêm `umask 077` để log mới tạo có quyền hẹp):
   ```bash
   kill -TERM <PID hiện tại>
   cd /home/vu/toolsauto && umask 077 && setsid nohup .venv/bin/python -m cashback_bot >> logs/cashback_bot.log 2>&1 &
   ```
4. **Migration tự chạy lúc khởi động** (`repo.migrate()`): thêm bảng `failed_updates` và 4 trigger `financial_lock_*`. Chỉ thêm, không sửa dữ liệu. Đã diễn tập trên bản sao.
5. **Xác minh sau triển khai:**
   - `tail logs/cashback_bot.log`: có dòng `start …`, rồi `backup ok file=…` (lần đầu chạy ngay vì chưa có `backup_last_ok`).
   - `ls -l data/backups`: bản mới nhất có quyền `-rw-------`.
   - /admin → 👛: có "🔒 KHOÁ TÀI CHÍNH" kèm 2 lý do; bấm "Bật ví" bị từ chối.
   - Gửi một link thử: bot trả link với số hoàn như trước.
   - Đọc DB chỉ đọc: `SELECT name FROM sqlite_master WHERE type='trigger'` có 4 trigger.
6. **Quyền file (tuỳ chủ bot, chạy riêng):**
   ```bash
   chmod 600 /home/vu/toolsauto/logs/cashback_bot.log /home/vu/toolsauto/data/backups/cashback-*.sqlite
   ```
   Hiện log và 14 backup cũ đang 0644, thư mục backup 0700. Bot chạy bằng `root`; `.env` thuộc `vu`, quyền 0600 (root vẫn đọc được).

**Rollback:**
- Dừng bot, trả `main` về `eca64fd` bằng `git revert` các commit của nhánh, rồi restart.
- Bảng `failed_updates` và các trigger để lại cũng vô hại với code cũ. Trigger còn tiếp tục chặn chi trả, đúng ý muốn.
- Nếu cần gỡ trigger, phải được chủ bot duyệt riêng (`DROP TRIGGER financial_lock_*`). Không xoá dữ liệu.
- Hỏng DB: theo BACKUP.md, khôi phục ra file mới rồi đổi tên.

---

## G. Rủi ro còn lại

**Trước khi mở rộng người dùng:**
- Bot đang công khai (`CUSTOMER_ACCESS_ENABLED=true`), cần chủ bot xác nhận.
- Ước tính lệch −17% đến −43% so với hoa hồng thật.
- Chữ trên /admin còn gây hiểu nhầm (audit P1-3), màn 🧮 không trừ phí và thuế.
- Đồng bộ Shopee vẫn chạy trong vòng poll, có thể làm bot đứng vài phút khi đồng bộ (P2-11).

**Trước khi cho rút tiền:**
1. Luồng nhập bằng chứng kỳ Shopee đã trả: ai nhập, chứng từ gì, đối chiếu sao kê. Đây mới là thứ mở khoá. Task này chỉ có DDL nháp.
2. **Hoa hồng giảm hoặc bị gắn gian lận *sau khi* khoản đã `available`**: `refresh` vẫn bỏ qua dòng `available` chưa huỷ. Hiện không gây thiệt hại vì chưa có khoản nào vào ví được, nhưng phải sửa trước khi mở khoá (ghi điều chỉnh âm).
3. Quyết định thuế người nhận (kế toán, ADR).
4. Quét VietQR thật với số tiền nhỏ; trần rút mỗi tháng; audit chi trả vào `admin_change_audit` (P1-5).
5. Snapshot chính sách V1.2 trên link (P1-4).

**Thuế:** chưa có chứng từ nào. Dự phòng 10% chỉ là số nội bộ.

**Conversion và settlement:** phụ thuộc cookie và API nội bộ Shopee. Chưa có đơn nào qua bot được Shopee duyệt hay trả tiền.

**Vận hành:**
- Backup vẫn cùng ổ đĩa (`OFFSITE_BACKUP = NOT CONFIGURED`).
- Chưa có supervisor; restart tay.
- Tin gửi khách có thể bị gửi trùng khi Telegram timeout (gửi ít nhất một lần).

---

## H. Release gates

| Gate | Kết luận | Ghi chú |
|---|---|---|
| Telegram Update Isolation | **GO** | Code và 13 test. Có hiệu lực sau khi triển khai |
| Secret-safe Logging | **CONDITIONAL** | Code GO (toàn bộ đường log và formatter toàn cục). Còn chờ chủ bot `chmod 600` log và backup cũ |
| Automated Backup | **CONDITIONAL** | Chạy sau khi triển khai. Chỉ cùng ổ đĩa, offsite chưa cấu hình |
| Backup Restore | **GO** | Đã test backup → restore → integrity → dữ liệu mẫu. Bước đổi tên cuối vẫn làm tay theo BACKUP.md |
| Financial Lock | **GO** | Không còn đường nào chi được khi thiếu bằng chứng, kể cả gọi hàm hay SQL trực tiếp |
| Regression | **GO** | 334/334 cashback. Báo giá V1.1/V1.2 không đổi |
| Production Deployment | **NOT AUTHORIZED** | |
| Wallet Activation | **NOT AUTHORIZED** | Và về kỹ thuật cũng không bật được cho tới khi có bằng chứng |
| Payout | **NOT AUTHORIZED** | |

---

## Năm câu trả lời

**Q1. Sau khi sửa, một update lỗi còn làm cả bot đứng không?**
Không. Lỗi vĩnh viễn được cách ly ngay. Lỗi tạm được thử lại tối đa 5 lần, đứng tối đa khoảng 15 giây, rồi cách ly. Sau đó bot xử lý tiếp các update sau.
Trường hợp duy nhất bot vẫn dừng: DB không ghi được cả bản cách ly. Khi đó bot cố ý không bỏ qua update, báo lỗi vòng lặp cho admin và thử lại mỗi 5 giây. Đây là hành vi đúng, vì DB hỏng thì không gì an toàn để chạy tiếp.

**Q2. Còn đường nào làm lộ token Telegram hoặc cookie Shopee vào log không?**
- Mọi chỗ log lỗi thô đã được sửa, và mọi dòng log của process đi qua `RedactingFormatter` (kể cả traceback, kể cả log của thư viện). Không tìm thấy đường nào còn lại.
- Giới hạn:
  - Bộ lọc dựa trên mẫu (token Telegram, `SPC_*`, Cookie, Authorization, `api_key=`). Bí mật có hình dạng lạ thì có thể lọt.
  - File log cũ đang 0644 (chưa chứa token: 0 dòng chứa URL bot).
  - Khi chạy `nohup` mà không có `umask 077`, file log mới vẫn tạo với quyền 0644.

**Q3. Backup có tự chạy và khôi phục được không? Mất máy thì sao?**
Có, sau khi triển khai: bot tự chạy mỗi 24 giờ, kiểm tra từng bản, báo admin khi lỗi. Khôi phục đã được test. **Nếu máy chủ hỏng hoàn toàn thì dữ liệu chưa được bảo vệ**, vì backup nằm cùng ổ (`OFFSITE_BACKUP = NOT CONFIGURED`). Cần chủ bot chọn nơi lưu bản mã hoá.

**Q4. Admin vô tình bật ví hoặc gọi thẳng payout thì có chi được tiền Shopee chưa trả không?**
Không, có ba lớp chặn:
1. Nút và callback (kể cả callback cũ) bị từ chối.
2. `set_enabled`, `request_payout`, `decide_payout` tự kiểm tra và ném lỗi hoặc trả `locked`.
3. Trigger SQLite chặn cả SQL trực tiếp.

Chỉ có thể mở khoá khi có bảng và dữ liệu bằng chứng Shopee đã trả **và** chính sách thuế đã duyệt. Việc tạo hai bảng đó là thay đổi DB cần một PLAN riêng. Admin không có nút nào để tự mở.

**Q5. Còn bắt buộc làm gì để chi tiền hoàn thật?**
1. Luồng ghi bằng chứng kỳ Shopee đã trả (chứng từ, người nhập, đối chiếu sao kê), tạo hai bảng thật.
2. Điều chỉnh âm khi hoa hồng giảm hoặc bị gắn gian lận sau khi đã vào ví.
3. Quyết định thuế người nhận, ghi ADR.
4. Thử QR thật, đặt trần rút mỗi tháng, ghi audit chi trả.
5. Snapshot chính sách V1.2 trên link.
6. Điều khoản và kênh khiếu nại tối giản cho khách.
7. Backup ngoài máy có mã hoá.
