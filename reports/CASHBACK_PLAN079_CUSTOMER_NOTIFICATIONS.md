# PLAN-079 — Customer Order Tracking & Notifications V1

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Nhánh | `cursor/cashback-plan079-notifications`, tách từ `main@1b0d145` (production `c4b9b1a`) |
| Worktree | `/home/vu/toolsauto-cashback-notifications` |
| ADR | ADR-056 (mới) |
| Trạng thái | **CODE READY (Gate A).** Chưa merge, chưa triển khai. Gate B (bật thông báo đơn) **NOT AUTHORIZED** |

---

## 1. Tóm tắt

- **Khách tự xem đơn:**
  - `/donhang` (và nút 📦 Đơn hàng của tôi ở trang chủ): tổng quan, danh sách mới nhất trước (5 đơn mỗi trang), chi tiết từng đơn;
  - chỉ thấy đơn của chính mình, không có dữ liệu người mua, không có dữ liệu Shopee gốc.
- **Khách chỉnh thông báo:** `/thongbao` có 4 loại (đơn mới, cập nhật đơn, hỗ trợ, ví), bật/tắt riêng cho từng khách.
- **Thông báo đơn tự động đã sẵn sàng nhưng TẮT:**
  - sự kiện sinh **trong cùng transaction** với lúc ghi đơn;
  - mỗi sự kiện có khoá chống trùng; mỗi lần đồng bộ, mỗi đơn tối đa một tin;
  - tiền hoàn tính theo snapshot của link.
  Cờ `CUSTOMER_NOTIFICATIONS_ENABLED` mặc định tắt. Sự kiện phát sinh khi cờ tắt chỉ được ghi dạng "bỏ qua", nên khi bật cờ không bị gửi dồn tin cũ.
- **Một bộ gửi chung** cho cả tin admin và tin khách:
  - 429 đợi đúng `retry_after`; 5xx thử lại có giãn cách;
  - khách chặn bot thì đánh dấu và không gửi tiếp tới khi khách nhắn lại;
  - không rõ kết quả (hết giờ, bot dừng giữa lúc gửi) thì **không tự gửi lại**;
  - lưu mã tin Telegram.
- **Tin hỗ trợ:** giờ gửi được cả khi thông báo admin tắt (trước đây bị chặn theo cờ admin).
- **Màn admin 🔔 Thông báo khách:** số tin theo trạng thái, lý do lỗi hoặc bỏ qua, khách chặn bot, khách tắt thông báo, gửi lại từng tin có xác nhận, xem mẫu tin.
- **Không đổi:** sổ ví, 2 khoản pending, khoá tài chính, quy tắc gán đơn của PLAN-074.
- **588 test pass** (555 + 33 mới).

---

## 2. Baseline production

| Mục | Giá trị |
|---|---|
| Git | `main@1b0d145` (code `c4b9b1a`); PID 631959 |
| Đơn qua bot | 2: HH 17.368đ → hoàn 12.157đ (`UNPAID`), HH 1.372đ → 960đ (`PAID`); cả hai PENDING / NOT_VERIFIED |
| Hàng đợi `admin_notifications` | 42 dòng, tất cả `sent` |
| Ví / khoá | tắt; 6 trigger khoá; 0 available; 0 payout |
| Điều khoản | V1 công bố; không bắt buộc đồng ý |
| Đồng bộ Shopee | admin bấm 🔄 (tự đồng bộ 4 giờ đang tắt) |
| Test | 555 passed |

---

## 3. Audit thông báo hiện có

| Loại | Đã có | Người nhận | Kích hoạt | Chống trùng | Cần bổ sung |
|---|---|---|---|---|---|
| Admin: người dùng mới, gửi link, lỗi, kết quả đồng bộ, thay đổi hoa hồng, ticket | ✅ | admin | sự kiện | `event_key` unique | giãn cách khi thử lại, `retry_after` |
| Phản hồi tức thời khi khách bấm hoặc gõ | ✅ | khách | thao tác | `outbound_messages` theo update | — |
| Ví: khoản đổi trạng thái | ✅ | khách | làm mới ví, chỉ khi ví bật | `event_key` | tuỳ chọn của khách |
| Hỗ trợ: admin trả lời hoặc kết luận | ✅ | khách | admin thao tác | `event_key` | gửi được cả khi cờ admin tắt |
| Chi trả: đã trả / tiền về ví | ✅ | khách | admin thao tác (ví khoá) | `event_key` theo phiên bản | — |
| **Đơn mới / đổi trạng thái / đổi hoa hồng** | ❌ | — | — | — | **làm mới** |
| Xem đơn của mình | ❌ | — | — | — | **`/donhang`** |
| Tuỳ chọn thông báo | ❌ | — | — | — | **`/thongbao`** |

**Phát hiện:** tin khách đi chung hàng đợi với tin admin và chỉ được xả khi thông báo admin bật. Gửi lỗi thì thử lại ngay mỗi vòng, tối đa 5 lần, không phân biệt khách chặn bot.

---

## 4. Ma trận sự kiện

| Sự kiện | Điều kiện | Khoá | Loại | Hiện trạng |
|---|---|---|---|---|
| B1 Đơn mới được ghi nhận | đơn khớp link bot lần đầu, có người nhận, không xung đột, mua sau mốc kích hoạt | `conversion:<id>:first_matched` | `order_new` | sẵn sàng, cờ tắt |
| B2 Trạng thái đơn | `PAID` / `COMPLETED` / `CANCELLED` mới xuất hiện | `conversion:<id>:changes:<max change id>` | `order_update` | sẵn sàng, cờ tắt |
| B3 Hoa hồng đổi | hoàn tính theo snapshot đổi ≥ 500đ hoặc ≥ 10%, hoặc về 0 | như trên (gom chung) | `order_update` | sẵn sàng, cờ tắt |
| B4 Không đủ điều kiện | hoa hồng sang REJECTED / FRAUD | như trên | `order_update` | sẵn sàng; chữ trung lập, có `/hotro` |
| B5 Shopee duyệt | hoa hồng sang APPROVED | như trên | `order_update` | có mẫu và test; **chưa nguồn nào gán APPROVED nên không bao giờ phát sinh** |
| B6 Đủ điều kiện rút | khoản sang `available` (cần mở khoá) | `wallet:<cid>:available` | `wallet` | có sẵn từ PLAN-066; ví khoá nên không phát sinh |
| B7 Đã chuyển tiền | `paid_confirmed` có chứng từ | `payout:<id>:<v>:paid_confirmed` | `wallet` | có sẵn từ PLAN-078; ví khoá |
| B8 Hỗ trợ | admin trả lời, yêu cầu bổ sung, kết luận | `support_customer:<ticket>:<mốc>` | `support` | đang chạy; nay theo tuỳ chọn của khách |

**Không gửi tin khi:**
- Sub ID không thuộc bot, thiếu hoặc sai;
- có xung đột gán người nhận (Sub ID trỏ link khác), kể cả các thay đổi sau đó cho tới khi admin đánh dấu đã xem;
- đồng bộ lại y hệt; response thiếu field;
- thay đổi hoa hồng nhỏ;
- admin chỉ mở màn hình.

---

## 5–7. Trải nghiệm khách

**Trang chủ:** thêm hàng 📦 Đơn hàng của tôi. Menu lệnh thêm `/donhang` và `/thongbao`.

### `/donhang`

Ví dụ thật, dựng trên bản sao DB production:

```
📦 Đơn hàng của tôi

Shopee đã ghi nhận: 1 đơn
⏳ Chờ xác minh: 1 · ✅ Đã được duyệt: 0 · ❌ Không đủ điều kiện: 0
Hoàn tạm tính (đơn còn chờ): 12.157đ
Chưa có khoản nào đủ điều kiện rút.

• ••••WJ0N · 24/10/2026 · Người mua chưa thanh toán đơn · Hoa hồng đang chờ Shopee xác minh · 12.157đ
```

- **Chi tiết đơn** gồm: ngày bot ghi nhận, link của khách (Sub ID), cách tính V1.1/V1.2 (theo snapshot), tình trạng đơn, trạng thái hoa hồng, trạng thái Shopee thanh toán hoa hồng, hoàn tạm tính, lý do chưa rút được, nút 📩 Yêu cầu kiểm tra.
- **Chưa có đơn:** "Hiện Shopee chưa ghi nhận giao dịch nào khớp với các link bạn đã tạo. Dữ liệu đơn có thể cập nhật muộn…". Bot không nói chắc là khách chưa mua.
- **Bảo mật:** mọi nút đều kiểm tra chủ đơn ở server. Đổi mã đơn trong nút → "Không thấy đơn này"; nhóm chat không xem được.

### `/thongbao`

- 4 loại tin, mỗi loại ✅/⬜, lưu theo từng khách. Chưa có dòng nào thì mặc định bật.
- Khi cờ tắt, trang ghi thật: "Bot chưa bật gửi thông báo đơn hàng tự động".

---

## 8. Hàng đợi thông báo

| Thuộc tính PLAN | Cột trong `admin_notifications` |
|---|---|
| Notification ID, event type, recipient | `id`, `event_type`, `chat_id` |
| Event source ID | `source_ref` (ví dụ `conversion:<id>`) |
| Unique event key | `event_key` (UNIQUE) |
| Payload tối thiểu | `message_html`, `reply_markup_json` (nút 📦 Xem đơn, 📩 Hỗ trợ) |
| Status | `pending` (QUEUED), `sending`, `sent`, `retry` (RETRYABLE_FAILED), `failed` (PERMANENT_FAILED), `suppressed`, `unknown` (không rõ kết quả) |
| Attempt count, next retry, last error (đã che), sent at, message id | `attempt_count`, `next_retry_at`, `last_error`, `sent_at`, `telegram_message_id` |
| Đối tượng, loại | `audience` (admin / customer), `category` |

- **Cùng transaction:** hook được gọi trong `record_conversion_snapshot` sau khi ghi đơn và lịch sử, bọc SAVEPOINT. Rollback thì không có tin (test 27–28). Hook lỗi thì đơn vẫn được ghi (test 16).
- **Không gửi Telegram trong transaction:** bộ gửi chạy sau ở vòng poll, mỗi tin là một transaction ngắn để nhận việc và một transaction ngắn để ghi kết quả.

---

## 9. Tích hợp đồng bộ Shopee

1. Admin bấm 🔄.
2. Bot đọc dữ liệu Shopee.
3. Mỗi đơn ghi trong một transaction: đơn, lịch sử thay đổi, sự kiện thông báo.
4. Làm mới ví.
5. Tin kết quả đồng bộ ghi thêm "Thông báo khách: N chờ gửi, M bỏ qua (xem /admin → 🔔)".
6. `flush_pending` gửi ngay.

- Lỗi gửi Telegram không làm đồng bộ thất bại.
- Đồng bộ một phần vẫn ghi `partial` như trước. Sự kiện chỉ có cho đơn đã ghi được.
- **Không tự gọi Shopee định kỳ**; tự đồng bộ 4 giờ vẫn do công tắc admin (đang tắt).

---

## 10–11. Gửi, thử lại, chống trùng

| Tình huống | Xử lý |
|---|---|
| 429 | `retry`, đúng `retry_after` (test 31) |
| 5xx / lỗi tạm | `retry` giãn cách 30 giây × 2ⁿ; 5 lần thì `failed` (test 32) |
| Khách chặn bot / chat không tồn tại (400, 403) | `failed`, đánh dấu khách; tin sau `suppressed: blocked`; khách nhắn lại thì bỏ đánh dấu (test 33). Khách khác vẫn gửi bình thường |
| Khách chưa /start (không có trong `telegram_users`) | `suppressed: not_started` (test 34) |
| Hết giờ hoặc mất kết nối với tin khách | `unknown`, **không tự gửi lại** (test 30) |
| Bot dừng giữa lúc gửi | dòng `sending` chuyển `unknown` lúc khởi động (test 36) |
| Restart khi còn tin chờ | gửi tiếp (test 35) |
| Tin đơn quá 72 giờ chưa gửi | `suppressed: stale` |
| Cờ tắt / khách tắt loại tin | `suppressed: feature_off` / `pref_off`; bật cờ sau không gửi dồn (test 39–40) |

- **Chống trùng:** khoá theo sự kiện nghiệp vụ. Đồng bộ 10 lần y hệt chỉ cho 1 tin (test 15). Thử gửi lại không tạo sự kiện mới. Admin gửi lại đúng dòng đó.
- **Không hứa đúng một lần:** khi Telegram có thể đã nhận tin mà bot mất kết nối, dòng ở trạng thái `unknown` để admin quyết định. Màn gửi lại cảnh báo "có thể thành 2 tin".

---

## 12. Dữ liệu cá nhân

- Chỉ đơn của đúng khách; kiểm tra ở server; mã đơn chỉ hiện 4 ký tự cuối.
- Không hiện dữ liệu người mua, raw Shopee, cờ gian lận nội bộ. Tin "không đủ điều kiện" không nói "gian lận" (test 10).
- Xung đột gán người nhận thì không gửi (test 5).
- Không đổi chính sách dữ liệu đã công bố: điều khoản V1 đã nêu bot lưu thông tin đơn qua link để ghi nhận cho đúng người.

---

## 13. Màn admin 🔔 Thông báo khách

- Hiện:
  - cờ BẬT / TẮT, mốc kích hoạt;
  - số tin theo 7 trạng thái; đã gửi theo loại;
  - khách chặn bot, khách tắt ít nhất một loại tin;
  - lần gửi gần nhất.
- Danh sách tin gửi lỗi, không rõ kết quả, bỏ qua, chờ gửi (8 tin gần nhất), kèm lý do.
- **Gửi lại** chỉ cho tin `failed` / `unknown`, có bước xác nhận (với `unknown` có cảnh báo trùng), có audit ở 📊 Lịch sử. Vẫn áp tuỳ chọn của khách lúc gửi.
- **Xem mẫu tin:** đơn mới, hoa hồng đổi, không đủ điều kiện, đã duyệt (ghi rõ "chưa dùng").
- **Không có:** gửi hàng loạt, sửa đơn, gán APPROVED / SETTLED, tạo khoản chi.

---

## 14. Mẫu tin

| Nhãn | Nghĩa |
|---|---|
| Shopee đã ghi nhận giao dịch | đơn xuất hiện trong báo cáo Affiliate |
| Người mua chưa / đã thanh toán đơn | `UNPAID` / `PAID` |
| Đơn đang được xử lý | `PENDING` (không khẳng định đã thanh toán) |
| Đơn hàng đã hoàn thành | `COMPLETED` |
| Hoa hồng đang chờ Shopee xác minh | mặc định |
| Hoa hồng đã được Shopee duyệt | chỉ khi APPROVED |
| Shopee đã thanh toán hoa hồng cho chương trình | chỉ khi SETTLED |
| Chưa phải tiền có thể rút: ví hoàn tiền chưa mở | khi ví khoá |

- Không dùng PENDING, SETTLED, APPROVED trong tin gửi khách.
- Không dùng "đặt hàng thành công", "chắc chắn nhận", "tiền sắp về ví".
- Mỗi tin có nút 📦 Xem đơn và 📩 Hỗ trợ.

---

## 15. Migration

- **Cơ chế:** tự chạy, idempotent.
  - `admin_notifications` thêm 6 cột và 1 index;
  - thêm bảng `customer_notification_prefs`;
  - `telegram_users` thêm cột `notify_blocked_at`.
  Không sửa dữ liệu tiền. 42 dòng cũ nhận `audience='admin'` và vẫn là `sent`.
- **Diễn tập trên bản sao DB production** (0600, đã xoá; `migrate()` 2 lần, khởi động service, ghi lại y hệt 2 đơn, làm mới ví):
  - 0 tin mới;
  - mốc kích hoạt chưa đặt (cờ tắt);
  - bảng cũ chỉ đổi ở cột mới thêm và `updated_at`;
  - 2 khoản pending giữ 12.157đ / 960đ;
  - ví khoá; `integrity_check` = ok.

---

## 16. Bằng chứng test

- `tests/test_cashback_*.py`: **588 passed** (555 + 33), ruff sạch.
- 5 test cũ và 1 helper được cập nhật:
  - menu lệnh và nút trang chủ;
  - tin admin lỗi tạm giờ ở `retry`, 4xx ở `failed`;
  - helper đếm tin khách bỏ qua các dòng `suppressed`.

| Nhóm PLAN | Test (`test_cashback_order_notifications.py`) |
|---|---|
| Thông báo đơn 1–16 | đơn mới đúng người, có số theo snapshot, nút Xem đơn; Sub ID lạ / thiếu / sai; xung đột gán; UNPAID không nói "đã thanh toán"; PAID, COMPLETED (không nói "đã duyệt"), CANCELLED; FRAUD chữ trung lập; hoa hồng tăng / giảm / về 0 / dưới ngưỡng; thiếu field; 10 lần y hệt → 1 tin; hook lỗi không hỏng ghi đơn |
| Theo dõi đơn 17–26 | tổng quan, chi tiết; chưa có đơn; phân trang 12 đơn → 3 trang; khách khác, mã giả, nhóm chat bị chặn; link chia sẻ thuộc người tạo; snapshot V1.1 (12.157đ), V1.2 (62.314đ / 100.000đ); link không chứng minh được chính sách → "chưa xác định" |
| Gửi tin 27–41 | rollback không có tin; khoá trùng; hết giờ → không rõ; dừng giữa lúc gửi → không rõ; 429; 5xx đến failed; chặn bot không ảnh hưởng khách khác và tự bỏ đánh dấu; chưa /start; restart gửi tiếp; gom thay đổi; tuỳ chọn riêng từng khách; cờ tắt và bật sau không gửi dồn; đơn trước mốc; tin quá cũ |
| Hỗ trợ, tài chính 42–50 | trả lời hỗ trợ qua hàng đợi chung, gửi được khi cờ đơn tắt, không lặp; khách tắt tin hỗ trợ; không có "đã duyệt", "Shopee đã thanh toán", "vào ví"; mẫu đã duyệt nói "chưa thanh toán"; không tạo available hay payout; trigger khoá còn |
| Admin | đếm, danh sách lỗi, gửi lại có xác nhận, mẫu tin, sai quyền, nút giả |
| Regression 51–62 | toàn bộ test cũ |

---

## 17. An toàn tài chính

- Không đổi sổ ví, `entry_payable`, payout, trigger.
- Sự kiện đơn chỉ đọc snapshot và sổ ví; không ghi `cashback_entries`, `cashback_payouts`, `validation_status`, `settlement_status`.
- Tin "đủ điều kiện rút" và "đã chuyển tiền" vẫn chỉ đến từ luồng ví và chi trả (đang khoá).

---

## 18. Triển khai (Gate A, khi chủ bot duyệt)

1. Backup và verify.
2. Merge, test, push.
3. Chủ bot restart.
4. Kiểm tra:
   - log sạch; cột và bảng mới có;
   - `CUSTOMER_NOTIFICATIONS_ENABLED` không đặt (tắt), mốc kích hoạt chưa có;
   - menu có `/donhang`, `/thongbao`;
   - `/donhang` của 2 khách đúng số;
   - đồng bộ 🔄 không gửi tin đơn cho khách;
   - 2 khoản pending giữ số.

**Khách thấy:** nút 📦 Đơn hàng của tôi, lệnh `/donhang`, `/thongbao`. **Không** nhận thêm tin nào.

**Gate B (sau khi duyệt riêng):**
1. Thử với tài khoản test thật.
2. Đặt `CUSTOMER_NOTIFICATIONS_ENABLED=1` trong `.env`, restart. Mốc kích hoạt được đặt lúc khởi động.
3. Tắt nhanh: bỏ cờ và restart. Lịch sử giữ nguyên; tin chưa gửi chuyển "bỏ qua", không gửi dồn.

---

## 19. Rollback

- `git revert` rồi restart.
- Cột và bảng mới để lại vô hại: code cũ đọc `admin_notifications` theo `status != 'sent'`.
- Rủi ro khi rollback: code cũ sẽ gửi các dòng `suppressed` / `unknown` / `retry` còn lại.
  - Khi cờ tắt, các dòng đó chỉ là tin khách `suppressed`, nên cần đánh dấu chúng `sent` trước khi revert.
  - Lệnh: `UPDATE admin_notifications SET status = 'sent' WHERE status IN ('suppressed', 'unknown', 'failed')`. Đây là sửa DB, chỉ chạy khi chủ bot duyệt.
- Không restore DB.

---

## 20. Rủi ro còn lại

- **Gần thời gian thực cần tự đồng bộ:** hiện tin chỉ có sau khi admin bấm 🔄. Cần một PLAN riêng cho tự đồng bộ: tần suất, giữ phiên cookie, rate limit, phát hiện nguồn mất hiệu lực, không chặn poller, giám sát.
- **Nghĩa của `PENDING` trong báo cáo Shopee chưa chắc chắn**, nên bot ghi "Đơn đang được xử lý" (không khẳng định người mua đã thanh toán).
- **Ngưỡng 500đ / 10%** là đề xuất, chờ chủ bot duyệt cùng Gate B.
- **Tin không rõ kết quả** cần admin xem tay; chưa có tra cứu tự động trên Telegram.
- **Khách chưa có dòng tuỳ chọn mặc định bật.** Khi bật cờ, khách nhận tin đơn trừ khi đã tắt.

---

## 21. Release gates

| Gate | Kết luận |
|---|---|
| Customer Order Center (`/donhang`) | **GO** |
| Notification Settings (`/thongbao`) | **GO** |
| Event Matrix & Templates | **GO** (APPROVED: mẫu có, không phát sinh) |
| Durable Outbox | **GO** |
| Dedupe | **GO** |
| Telegram Delivery & Retry | **GO** (tối đa một lần cho tin khách khi không rõ kết quả) |
| Privacy | **GO** |
| Admin Monitoring | **GO** |
| Migration | **GO** |
| Financial Safety | **GO** |
| Regression | **GO** (588/588) |
| Gate A — Production Code Deployment | **NOT AUTHORIZED UNTIL REVIEW** |
| Gate B — Customer Notification Activation | **NOT AUTHORIZED** |
| Wallet / Payout | **NOT AUTHORIZED** |

---

## Câu hỏi nghiệm thu

**Q1. Khách tạo link, Shopee ghi nhận đơn sau một ngày, khi admin đồng bộ thì bot có tự báo đúng người không?**
**Có, khi đã bật Gate B.**
- Lần đồng bộ ghi đơn sẽ sinh sự kiện `first_matched` cho người tạo link (theo Sub ID), cùng transaction với dữ liệu đơn.
- Bộ gửi gửi ngay sau đồng bộ.
- Hiện cờ tắt nên sự kiện chỉ được ghi "bỏ qua".

**Q2. A chia sẻ link cho B mua, tin gửi cho ai?**
**Cho A**, người tạo link có Sub ID. Bot không biết B và không gửi gì cho B (test 23).

**Q3. Đồng bộ một đơn 10 lần không đổi thì khách nhận bao nhiêu tin?**
**Một tin:** tin đơn mới ở lần đầu. Các lần sau không có thay đổi nên không có sự kiện (test 15, và diễn tập trên dữ liệu thật: 0 tin).

**Q4. Hoa hồng giảm nhưng Shopee chưa duyệt, tin có nói đó là số tạm tính không?**
**Có.**
- Tiêu đề "Hoàn dự kiến được cập nhật", dòng "Hoàn tạm tính: cũ → mới", câu "Khoản hoàn vẫn đang chờ xác minh", và "Chưa phải tiền có thể rút".
- Số tính theo snapshot của link, không theo chính sách hiện tại.

**Q5. Telegram lỗi hoặc bot restart, tin có mất không?**
**Không mất.**
- Tin nằm trong DB trước khi gửi; restart thì gửi tiếp.
- Lỗi tạm thì thử lại có giãn cách.
- Không rõ kết quả thì giữ `unknown` để admin quyết định, không tự gửi lại để tránh trùng.

**Q6. Một khách chặn bot, khách khác có được gửi bình thường không?**
**Có.** Mỗi tin xử lý riêng. Khách chặn bot bị đánh dấu và bỏ qua; vòng gửi tiếp tục với khách khác (test 33).

**Q7. Chưa có chứng từ Shopee, bot có gửi sai "Đã duyệt" hay "Đủ điều kiện rút" không?**
**Không.**
- "Đã duyệt" chỉ khi hoa hồng sang APPROVED, mà chưa có nguồn nào gán.
- "Đủ điều kiện rút" và "đã chuyển tiền" chỉ đến từ luồng ví và chi trả đang khoá.
- Test quét nội dung mọi tin của khách.

**Q8. Hai đơn lịch sử có bị gửi lại tin mới khi triển khai không?**
**Không.**
- Hai đơn đã khớp link từ trước, nên đồng bộ lại không tạo `first_matched`.
- Cờ tắt; mốc kích hoạt chỉ đặt khi bật cờ.
- Đơn mua trước mốc không được báo "đơn mới".
- Diễn tập: 0 tin.

**Q9. Có thay đổi nào ảnh hưởng sổ ví, khoản pending hay khoá tài chính không?**
**Không.** Diễn tập: 2 khoản pending giữ số, ví khoá, trigger còn đủ.

**Q10. Muốn thông báo tự động mà không cần admin bấm đồng bộ thì cần gì?**
Một PLAN riêng cho tự đồng bộ Shopee, gồm:
- tần suất hợp lý (ví dụ 1–4 giờ);
- giữ và phát hiện cookie hết hạn (đã có cảnh báo);
- rate limit và thử lại có giãn cách;
- chạy ngoài vòng poll Telegram hoặc giới hạn thời gian;
- giám sát lỗi và báo admin;
- công tắc bật/tắt.
Sau đó mới bật Gate B để khách nhận tin gần thời gian thực.
