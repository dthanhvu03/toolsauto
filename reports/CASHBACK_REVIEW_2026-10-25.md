# Rà soát cashback_bot — 4 góc nhìn (2026-10-25)

Chủ bot yêu cầu rà soát. 4 agent chỉ đọc code (không chạy bot, không gọi mạng, không mở DB thật), Claude Code kiểm chứng lại các điểm nặng: chạy lại test thử, đọc code, đọc log, đọc DB thật ở chế độ chỉ đọc.
Test thử của agent nằm ở scratchpad phiên này (không commit).

Mức: 🔴 nặng · 🟠 trung bình · 🟡 nhẹ. **Đã kiểm chứng** = Claude Code tự xác nhận lại.

**Trạng thái sau khi vá:**
- A2–A11 và D1, D2, D4, D5 đã vá trong PLAN-087.
- B1–B16 và C3–C7 đã vá trong PLAN-088.
- Còn mở:
  - C1: công bố V3.
  - C2: công cụ xoá dữ liệu, chờ chủ bot chọn hạn lưu.
  - D3: chép backup ra ngoài máy, chờ chủ bot chọn nơi lưu.
  - Parser báo cáo thanh toán Shopee (ADR-059).
- Cài systemd và logrotate: chủ bot làm theo `deploy/cashback/README.md`.

## A. Ảnh hưởng ngay lúc này (bot đang chạy)

| # | Mức | Vấn đề | Chỗ | Ghi chú |
|---|---|---|---|---|
| A1 | 🔴 | Bot Zalo chạy code cũ từ 24/10 15:59Z. Sau đó có 7 commit vào `cashback_bot/`, gồm hạn mức theo từng khách và `admin_notify`. Các lần restart chỉ làm bot Telegram | `ps`, `git log` | **Đã kiểm chứng.** Chủ bot restart Zalo là xong |
| A2 | 🔴 | Backup chỉ còn khoảng 1 ngày: giữ 14 bản, mà bản backup tay trước mỗi lần sửa dùng cùng mẫu tên nên đẩy mất bản tự động hằng ngày. Backup nằm cùng ổ với DB | `backup.py:23,147-155` | **Đã kiểm chứng:** bản cũ nhất là 24/10 08:48Z. Tạm thời: chủ bot đặt `CASHBACK_BACKUP_KEEP=60` trong `.env` rồi restart bot Telegram |
| A3 | 🔴 | Mất mạng thì tin gửi khách bị chuyển `unknown` và không gửi lại: lỗi kết nối, DNS (chưa gửi được gì) bị coi là "không rõ đã gửi chưa". Vòng lặp còn flush 5 tin mỗi 5 giây lúc đang mất mạng | `telegram_api.py:119-122`, `notify_dispatch.py:176-178`, `poller.py:590-593` | Agent tái hiện trên DB thử |
| A4 | 🟠 | Tin admin phát sinh khi mất mạng quá ~8 phút bị bỏ (thử 5 lần: 30/60/120/240 giây) | `notify_dispatch.py:180-185` | Gộp với A3: không flush hoặc không đếm lượt thử khi `net_down_since` đang có |
| A5 | 🟠 | Lỗi HTTP 400 nào cũng đánh dấu khách "đã chặn bot", nên mọi thông báo sau bị bỏ. Chỉ 403 mới là chặn thật | `notify_dispatch.py:166-173`, `zalo_api.py:82` | **Đã kiểm chứng.** DB thật hiện 0 khách bị đánh dấu |
| A6 | 🟠 | Bot Telegram có thể tắt hẳn nếu DB lỗi ngay trong khối `except` của vòng lặp. Không có gì canh hay khởi động lại (nohup) | `poller.py:590-604` | Ngày 23/10 01:13Z bot đã tắt khoảng 2 giờ, do `flush_pending` ném lỗi gửi Telegram. Đường lỗi đó đã sửa (Dispatcher bắt lỗi), còn lại rủi ro lỗi DB |
| A7 | 🟠 | Tin Zalo của khách bị mất nếu DB lỗi giữa chừng: dòng kẹt ở `received`, không được thử lại, không báo admin | `zalo_bot.py:166-188,337-341` | Đọc code |
| A8 | 🟠 | Luồng đồng bộ Shopee có thể quay vòng nóng tới 10 phút, tranh khoá DB, khi có lỗi sau `_acquire` | `sync_scheduler.py:292-313,504-510` | Agent tái hiện: ~359 lượt lấy khoá trong 1 giây |
| A9 | 🟡 | Đơn nhiều món một lần thanh toán: hoa hồng chưa trừ phí MCN nên số hoàn bị tính cao | `shopee_sync.py:579-587` | Kiểm tra lúc làm PLAN; đối soát hiện báo lệch số |
| A10 | 🟡 | Tin Zalo nhiều phần có thể bị gửi trùng phần đầu khi thử lại. Dòng `sending` của Zalo chỉ được gỡ kẹt khi bot Telegram restart | `zalo_bot.py:282`, `db.py:1412` | |
| A11 | 🟡 | `test_14` hỏng vì màn admin dùng giờ thật, còn test dùng đồng hồ giả | `sync_scheduler.py:88-95` | Truyền đồng hồ vào màn admin |

## B. Phải sửa trước khi mở ví

| # | Mức | Vấn đề | Chỗ |
|---|---|---|---|
| B1 | 🔴 | **Vẫn chi tiền được dù đơn nguồn đã bị huỷ.** Yêu cầu chuyển `needs_review` rồi được duyệt tiếp tới `paid`; điều kiện chi không kiểm tra khoản còn `available` không | `payouts.py:58-92,643-646`, `payout_readiness.py:86-95` — **đã kiểm chứng** (test thử) |
| B2 | 🔴 | **Một yêu cầu có thể chuyển tiền hai lần**: từ `needs_review` quay lại `processing → sent` sau khi đã `sent`. `needs_review → sent` còn bỏ qua bước duyệt | `payouts.py:79-90` — **đã kiểm chứng** |
| B3 | 🔴 | **Quỹ bị đếm đôi**: cộng mọi dòng trong kỳ MATCHED, không lọc theo chứng từ thanh toán, nên trần quỹ bị thổi phồng | `payouts.py:166-192` — **đã kiểm chứng** (bot 20.000 thay vì 10.000) |
| B4 | 🔴 | **Thu hồi chưa có** (ADR-059): khoản đã `available` bị "đóng băng", Shopee cắt hoa hồng hay kỳ bị đảo vẫn rút đủ. Chỉ huỷ toàn bộ mới trừ | `wallet.py:279-280` — **đã kiểm chứng** |
| B5 | 🟠 | Khách Zalo chỉ rút được **một lần**: mọi lần bấm nút đều dùng chung mã `zalo:{id}`, nên khoá chống trùng trả lại yêu cầu cũ | `zalo_bot.py:220`, `service.py:287` — **đã kiểm chứng** |
| B6 | 🟠 | Số dư lớn hơn hạn mức mỗi lần thì không rút được: nút Rút luôn rút toàn bộ, báo "thử số nhỏ hơn" nhưng không có chỗ chọn số | `service.py:275-290`, `messages.py:309,363` — **đã kiểm chứng** |
| B7 | 🟠 | Đã chuyển tiền nhưng không ghi "đã trả" được khi backup quá 48 giờ hoặc vừa hạ hạn mức. Cách lách dễ nghĩ tới là bấm "thất bại", mà vậy thì tiền về ví và khách rút lần nữa được | `wallet.py:466-481` — đã kiểm chứng |
| B8 | 🟠 | Trigger DB chỉ kiểm tra bảng có tồn tại. Chạy migration 007 (kể cả bảng rỗng) là khoá ở tầng DB mất tác dụng; không trigger nào giữ máy trạng thái | `db.py:670-698` |
| B9 | 🟠 | Chưa có quy tắc chờ 7 ngày khi đổi tài khoản (ADR-059) | `payouts.py:299-332` |
| B10 | 🟠 | Lý do từ chối hay huỷ yêu cầu rút không escape HTML: Telegram trả 400 và (A5) khách bị đánh dấu chặn | `admin_wallet.py:234` |
| B11 | 🟠 | Câu chữ ví cứng: "ví chưa mở" vẫn hiện khi ví bật. "Tiền vào ví N ngày sau khi đơn hoàn thành" sai: thực tế cần Shopee duyệt, đối soát khớp và đủ ngày giữ | `messages.py:132,360,495,614,747,789` |
| B12 | 🟠 | Màn chi tiết yêu cầu rút cắt cứng ở 4.000 ký tự, nên mất phần "Điều kiện" và "Lịch sử". Yêu cầu thứ 6–10 không có nút mở | `admin_ui.py:898,1104` |
| B13 | 🟠 | Điều kiện "đã đồng ý điều khoản chi trả" gắn cứng một phiên bản: công bố V4 là không khách nào đạt | `payout_readiness.py:67-83` |
| B14 | 🟠 | Thông báo hạn mức còn ghi "hạn mức chi của bot" và hứa "bot sẽ báo khi rút được" mà không có cơ chế báo. Màn Ví không hiện hạn mức và khoản đang bị trừ | `messages.py:304-311,342` |
| B15 | 🟠 | Tin chi trả không kèm mã giao dịch như V3 hứa; tin thất bại hay hoàn lại dùng tiêu đề "chưa được duyệt"; câu "nhắn admin" nên đổi thành "/hotro" | `messages.py:458-470` |
| B16 | 🟡 | Đổi số ngày giữ chỉ một chạm, có nút 0 ngày, không hỏi lại | `admin_ui.py:951` |
| B17 | 🟡 | `entry_payable` chấp nhận mọi kỳ sau; `DEFAULT_HOLD_DAYS = 30` khác 15 trong ADR-059 (chủ bot đã tự chọn 15) | `payout_gate.py:146-148`, `wallet.py:30` |

## C. Dữ liệu cá nhân và bảo mật

Phần lõi ổn: chỉ admin vào được màn admin (chat riêng + đúng ID), khách không xem được dữ liệu của nhau, SQL dùng tham số, nội dung do khách nhập đều được escape, không có SSRF, log không lộ khoá hay cookie, quyền file DB, log, backup đều 0600/0700.

| # | Mức | Vấn đề | Chỗ |
|---|---|---|---|
| C1 | 🟠 | Điều khoản V2 không nhắc dữ liệu ngân hàng; nháp V3 đã thêm | `terms_content.py:82-88` |
| C2 | 🟠 | Điều khoản hứa xoá dữ liệu qua /hotro nhưng chưa có công cụ xoá hay ẩn danh, không bảng nào có hạn lưu | `terms_content.py:101` |
| C3 | 🟡 | Số tài khoản đầy đủ (màn admin lúc PROCESSING) nằm lại trong `outbound_messages` và mọi bản backup | `admin_ui.py:1065`, `db.py:1249` |
| C4 | 🟡 | Cần kiểm tra `CASHBACK_ADMIN_CHAT_ID` là chat riêng, không phải nhóm, vì tin admin có nội dung ticket | `config.py:144-151` |
| C5 | 🟡 | File CSV xuất cho admin: tên sản phẩm bắt đầu bằng `=`, `+`, `-`, `@` sẽ chạy như công thức Excel | `admin_stats.py:469-494` |
| C6 | 🟡 | Không giới hạn số ticket mỗi khách, có thể bị spam vào chat admin | `service.py:436-449` |
| C7 | 🟡 | Ngoài cashback: `storage/db/config/gemini_cookies.json` đang 0644 | |

## D. Gợi ý vận hành

1. Chạy hai bot bằng systemd (bật `systemd=true` trong WSL) hoặc supervisord, `Restart=always`, và một lệnh restart cả hai bot.
2. Cảnh báo khi bot Telegram chết, ví dụ bot Zalo kiểm tra heartbeat của bot Telegram.
3. Backup: tách tên bản tay và bản tự động; giữ 7 bản ngày và 4 bản tuần; chép ra ngoài máy; mỗi tháng thử khôi phục một lần.
4. Log mã commit lúc khởi động, gửi kèm trong heartbeat Zalo, và báo khi hai bot chạy khác commit.
5. Gửi admin tóm tắt hằng ngày số tin `unknown` / `failed`. Bật logrotate cho `logs/*.log`.

## Đề xuất chia việc

| Gói | Nội dung | Ai |
|---|---|---|
| Ngay | A1 restart Zalo; A2 đặt `CASHBACK_BACKUP_KEEP` | Chủ bot |
| PLAN vận hành | A3–A8, A10, A11, D1–D5, tách tên backup (A2) | Backend, chủ bot duyệt |
| PLAN sổ chi trả | B1–B10, B17, cùng 3 PLAN ADR-059 (parser thanh toán, 7 ngày, thu hồi) | Backend, chủ bot duyệt; xong mới mở ví |
| PLAN câu chữ ví và admin | B11–B16, C1 (V3) | Claude Code |
| PLAN dữ liệu cá nhân | C2–C6 | Backend + Claude Code |
