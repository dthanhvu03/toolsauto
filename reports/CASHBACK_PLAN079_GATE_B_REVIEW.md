# PLAN-079 — Gate B Pre-Activation Review (Customer Notifications)

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Production | `main@e36281c` (code `0deb060`), PID 636239, thông báo đơn **TẮT** |
| Nhánh sửa | `cursor/cashback-plan079-gate-b` (worktree `/home/vu/toolsauto-cashback-notifications`), **chưa merge** |
| Nhánh rollback | `rollback/plan079-compat` (worktree `/home/vu/toolsauto-cashback-rollback`), **chỉ dùng khi chủ bot duyệt rollback** |
| ADR | ADR-056, thêm mục "Sửa đổi 2026-10-24 — Gate B pre-activation review" |
| Kết luận | **CONDITIONAL GO**: điều kiện ở mục 9 |

Không merge, không restart, không đổi `.env` production, không bật `CUSTOMER_NOTIFICATIONS_ENABLED`, không gửi tin Telegram thật. DB production chỉ đọc ở chế độ `mode=ro`. Mọi diễn tập chạy trên bản sao quyền 0600 trong scratchpad, đã xoá.

---

## 1. Tóm tắt

| # | Vấn đề | Mức | Trạng thái |
|---|---|---|---|
| A1 | Mốc kích hoạt chỉ đặt **lần đầu bật**. Bật → tắt → bật giữ mốc cũ: đơn mua trong lúc tắt, và tin đơn còn chờ từ lần bật trước, có thể bị gửi dồn sau khi bật lại | Cao | **Đã sửa** |
| A2 | Thông báo admin tắt mà còn ≥ 10 tin admin chờ: vòng gửi lấy lại đúng 10 tin admin đó mãi, tin khách phía sau **không bao giờ được gửi** (bỏ sót sự kiện đã commit) | Cao | **Đã sửa** |
| A3 | Gặp 429 vẫn gửi tiếp các tin còn lại trong vòng. Telegram giới hạn cả bot nên mọi tin sau đều 429 và tốn lượt thử | Trung bình | **Đã sửa** |
| A4 | Đơn Shopee không trả thời điểm mua bị ghi lý do "đơn trước mốc" (sai lý do) | Thấp | **Đã sửa** (lý do `no_purchase_time`) |
| B1 | Đơn đã huỷ hoặc không đủ điều kiện ngay lần đầu thấy: tin "đã ghi nhận" vẫn hiện "Hoàn tạm tính: X đ", trong khi `/donhang` không hiện số | Trung bình | **Đã sửa** |
| B2 | Ngưỡng 500đ / 10% đang là **OR**. Đây là đề xuất của em, PLAN-079 không quy định | Quyết định | **Chờ chủ bot duyệt** (mục 3) |
| C1 | Rollback cũ cần `UPDATE … SET status='sent'` (làm giả trạng thái). Code `c4b9b1a` nguyên bản sẽ gửi lại 6 loại dòng lạ | Cao | **Đã thiết kế lại**: nhánh rollback tương thích, không sửa dòng nào |
| D1 | Chưa có cách thử với tài khoản test mà không bật cho mọi khách. Bật cờ là 2 khách thật có thể nhận tin cập nhật đơn | Cao | **Đã thêm** chế độ tài khoản test, 🧪 tin thử, lệnh kiểm tra chỉ đọc |

Test:
- nhánh sửa: **606 passed** (588 cũ + 18 mới), ruff sạch;
- nhánh rollback: **558 passed** (555 cũ + 3 tương thích).

---

## 2. A — Activation Watermark

### Audit (code production `0deb060`)

| Câu hỏi | Trả lời |
|---|---|
| Mốc lưu ở đâu | `bot_state.customer_notify_baseline_at` (SQLite), **không ở RAM**. Production hiện chưa có mốc |
| Đặt khi nào | `service.py`: lúc khởi động nếu cờ bật **và chưa có mốc**, tức chỉ lần bật đầu tiên |
| Sự kiện đủ điều kiện | Đơn mới: `purchase_time ≥ mốc`. Cập nhật: thay đổi phát hiện khi cờ bật. Cờ tắt: ghi `suppressed: feature_off` |
| Restart | Giữ mốc. Bộ gửi chuyển `sending` thành `unknown` |
| Đồng bộ sát lúc bật | An toàn: khoá một tiến trình, mốc đặt trong constructor trước vòng poll và trước mọi lần đồng bộ |

### Lỗi tìm thấy

- **A1:** chuỗi bật lúc T1 → tắt lúc T2 → bật lại lúc T3 vẫn giữ mốc T1.
  - Đơn mua giữa T2 và T3 nhưng đồng bộ sau T3 được báo "đơn mới", tức tin của lúc đang tắt.
  - Tin đơn ghi lúc bật lần 1 mà bot chưa kịp gửi (bị dừng trước vòng gửi đầu tiên của lần tắt) cũng được gửi khi bật lại.
- **A2:** `list_pending_admin_events` lấy 10 dòng đầu theo `id`, gồm cả tin admin. Khi thông báo admin tắt, Dispatcher bỏ qua các tin admin nhưng không đánh dấu gì, nên vòng sau lấy lại đúng 10 dòng đó.

### Đã sửa

- **`cashback_bot/order_notify.py` · `sync_activation`:**
  - có ba chế độ `off` / `test` / `on`, ghi ở `customer_notify_state`;
  - khi đổi sang `test` hoặc `on`, đặt mốc mới bằng giờ khởi động; restart cùng chế độ giữ mốc;
  - DB của Gate A có mốc mà chưa có chế độ được coi là đang `on`, nên không đặt lại mốc;
  - lịch sử đổi chế độ chỉ thêm, ở `customer_notify_history`, gồm thời điểm, chế độ và mốc.
- **`cashback_bot/notify_dispatch.py` · `customer_block_reason`:**
  - tin đơn có `created_at` trước mốc hiện tại → `suppressed: before_activation`;
  - kiểm tra cả lúc ghi sự kiện lẫn lúc gửi.
- **`Dispatcher.flush` + `db.list_pending_admin_events(audiences=…)`:** thông báo admin tắt thì chỉ lấy tin khách. Tin admin giữ nguyên `pending`, không bị sửa.
- **`Dispatcher._send`:** gặp 429 thì dừng vòng gửi. Tin đó chuyển `retry` theo `retry_after`; các tin còn lại giữ `pending` với `attempt_count` không đổi.
- **`order_notify.make_hook`:** thiếu `purchase_time` → `no_purchase_time`, không báo "đơn mới".

### Kiểm thử (`tests/test_cashback_gate_b.py`)

| Tình huống PLAN | Test | Kết quả |
|---|---|---|
| OFF → ON lần đầu | `test_a1_…` | Có mốc, chế độ `on`, lịch sử `off → on`. Đơn có từ trước (như 2 đơn production) đồng bộ lại 3 lần: 0 tin mới, 0 tin gửi |
| Restart khi ON | `test_a2_…`, `test_a2b_…` | Giữ mốc, không thêm lịch sử. DB Gate A (có mốc, chưa có chế độ) không bị đặt lại mốc |
| ON → OFF → ON | `test_a3_…` | Mốc mới bằng lần bật lại. Tin còn chờ từ lần bật 1 → `before_activation`. Đơn ghi lúc tắt → `feature_off`. Đơn mua lúc tắt, đồng bộ sau → `historical`. Đơn mua sau khi bật lại → **gửi**. Lịch sử `off, on, off, on` |
| Sự kiện queued trước restart | `test_a4_…` | Gửi sau restart, đúng người |
| Sync sát lúc bật | `test_a5_…` | Mua trước mốc 1 giây → `historical`. Mua đúng mốc → `pending`. Thiếu thời điểm mua → `no_purchase_time` |
| Đơn lịch sử có thay đổi mới sau khi bật | `test_a6_…` | Báo **cập nhật** (UNPAID → PAID), không báo "đơn mới" |
| Không gửi lại lịch sử | `test_a1_…`, `test_a3_…` | Như trên |
| Không bỏ sót sự kiện đã commit | `test_a8_…`, `test_a9_…`, `test_a4_…` | 12 tin admin chờ không chặn tin khách; 429 không đốt lượt các tin sau; restart vẫn gửi |

**Diễn tập trên bản sao DB production** (code nhánh sửa, 3 lần khởi động: tắt, tắt, test):
- khởi động 1 (tắt): chỉ ghi `customer_notify_state=off` và một dòng lịch sử, không đặt mốc;
- khởi động 2 (tắt, cùng chế độ): không ghi gì;
- khởi động 3 (test): đặt mốc, ghi lịch sử `off → test`;
- trong cả 3 lần: đồng bộ lại y hệt 2 đơn, rồi làm mới ví. Hàng đợi 42 → 42 dòng, 0 tin gửi; 2 khoản pending giữ 12.157đ / 960đ; `quick_check` ok.

---

## 3. B — Notification Threshold

### Quy tắc đang chạy (`order_notify.significant_change`)

| Câu hỏi | Trả lời |
|---|---|
| OR hay AND | **OR**: báo khi chênh **≥ 500đ** *hoặc* **≥ 10%** |
| Tính trên gì | Trên **tiền hoàn của khách** (cashback), không phải hoa hồng |
| Giá trị trước và sau | Lấy `old` / `new` của `net_commission_vnd` trong `shopee_conversion_changes` của lần đồng bộ này. Mỗi giá trị được tính ra tiền hoàn bằng **snapshot chính sách của link** (`cashback_of` → `pricing.cashback_for`), không theo chính sách hiện tại, không theo sổ ví |
| Làm tròn | Tiền hoàn là số nguyên VND theo công thức chính sách: V1.1 làm tròn xuống theo bps, V1.2 theo đơn vị làm tròn của snapshot. Chênh lệch là hiệu hai số nguyên. Phần trăm là phép chia chính xác `|mới − cũ| / cũ ≥ 0,10`, không làm tròn |
| Giá trị ban đầu = 0 | Không có phần trăm, chỉ xét 500đ |
| Giá trị mới = 0 | Luôn báo |
| Link không có snapshot dùng được | Không báo thay đổi số tiền (không có số đúng để nói); thay đổi trạng thái vẫn báo |

Ví dụ trên đơn thật (`test_b_nguong_…`):

| Đơn | OR (đang chạy): báo khi chênh ≥ | AND (phương án khác): báo khi chênh ≥ |
|---|---|---|
| 12.157đ | 500đ (4,1%) | 1.216đ |
| 960đ | 96đ (10%) | 500đ (52%) |

**Đề xuất: giữ OR.**
- Với AND, đơn 960đ giảm còn 500đ (mất 48%) vẫn không được báo.
- OR chỉ "ồn" với đơn rất lớn, khi chênh vài trăm đồng; hoa hồng Shopee hiếm khi đổi kiểu đó.

**Cần chủ bot duyệt** ngưỡng này; em không tự thay.

### Trạng thái quan trọng: báo, không phụ thuộc ngưỡng

| Sự kiện | Báo | Ghi chú |
|---|---|---|
| Đơn mới được ghi nhận | ✅ | Một lần (`first_matched`) |
| Đơn bị huỷ | ✅ | `CANCELLED` / `CANCELED` (test `test_b_trang_thai_…`: hoa hồng không đổi vẫn báo) |
| Hoa hồng bị từ chối / gian lận | ✅ | REJECTED / FRAUD, chữ trung lập, có `/hotro` |
| Tiền hoàn về 0 | ✅ | Bỏ qua ngưỡng |
| Đơn huỷ / không đủ điều kiện **ngay lần đầu thấy** | ✅ | **Đã sửa B1:** tin không hiện số hoàn, ghi "không được tính", có `/hotro` |
| Người mua thanh toán, đơn hoàn thành | ✅ | PAID / COMPLETED |
| `NEEDS_REVIEW` (bot tự đánh dấu cần xem) | ❌ | Trạng thái nội bộ; nếu hoa hồng về 0 thì đã được báo theo dòng "Tiền hoàn về 0" |
| Đồng bộ không có thay đổi | ❌ | Không có dòng thay đổi nên không có sự kiện (test 15 của PLAN-079; diễn tập: 0 tin) |

### Khác biệt nghiệp vụ cần chủ bot duyệt
1. **Ngưỡng:** OR 500đ / 10% (đề xuất giữ) hay AND.
2. **Đơn mua trước lúc bật** nhưng Shopee báo về sau lúc bật: **không** báo "đơn mới" (khách vẫn xem ở `/donhang`). Mục đích: tránh dồn tin khi bật.
3. **Đơn có từ trước lúc bật** mà có thay đổi sau lúc bật: **có** báo "cập nhật".
   - Khi bật cho mọi khách, 2 khách thật có thể nhận tin cập nhật cho 2 đơn hiện tại, ví dụ đơn 12.157đ chuyển từ "chưa thanh toán" sang "đã thanh toán".
   - Ở chế độ test thì không có tin này.
4. **`NEEDS_REVIEW`** không báo khách.

---

## 4. C — Rollback Safety

**Không dùng** `UPDATE admin_notifications SET status='sent'` ở bất cứ bước nào. Không có bước rollback nào sửa dòng hàng đợi, lịch sử thử, tuỳ chọn hay đánh dấu chặn bot.

### Thang rollback

| Mức | Khi nào | Làm gì | Sửa DB |
|---|---|---|---|
| **R0: tắt Gate B** | Câu chữ sai, gửi nhầm, khách phàn nàn | Bỏ `CUSTOMER_NOTIFICATIONS_ENABLED` (và `CUSTOMER_NOTIFICATIONS_TEST_IDS`) khỏi `.env`, restart | Không. Tin đơn còn chờ → `suppressed: feature_off` ở vòng gửi đầu; bật lại sau không gửi dồn (mốc mới) |
| **R1: về code Gate A** (`0deb060`) | Lỗi trong code sửa của review này | `git revert` các commit của nhánh sửa, restart | Không. Trạng thái giống hệt Gate A; lý do mới chỉ là chữ trong `last_error` |
| **R2: về code trước PLAN-079** | Lỗi trong bộ gửi chung hoặc hook ghi đơn | Deploy nhánh `rollback/plan079-compat`, **không** dùng `c4b9b1a` nguyên bản | Không |

- **Cảnh báo cho R1:** code Gate A không biết `CUSTOMER_NOTIFICATIONS_TEST_IDS`. Nếu còn `CUSTOMER_NOTIFICATIONS_ENABLED=1`, sau R1 **mọi khách** sẽ nhận tin. Phải bỏ cờ trước khi R1.
- Lệnh deploy R2 (khi chủ bot duyệt): `git merge --ff-only rollback/plan079-compat` (nhánh dựa trên `main@e36281c`). Nếu `main` đã có commit mới, rebase nhánh rollback trước.

### Nhánh `rollback/plan079-compat`

- Commit `0e7eadf`: `cashback_bot/` và `tests/` trở về đúng `c4b9b1a`; docs giữ nguyên.
- Commit `f3ab6ec`: bộ lọc tương thích trong `db.py` của code cũ:
  - **`list_pending_admin_events`:** khi DB đã chạy migration PLAN-079, chỉ lấy `pending` / `retry`, bỏ `order_new` / `order_update`, bỏ tin khách của người đã chặn bot hoặc đã tắt loại tin. Chỉ đọc, không sửa dòng nào. DB chưa có PLAN-079 thì giữ câu lệnh cũ;
  - **`enqueue_admin_event`:** tin gửi khách tạo trong lúc rollback được gắn `audience='customer'` và `category`, để khi nâng cấp lại bộ gửi mới nhận ra.

**Bằng chứng:**

| Kiểm tra | Kết quả |
|---|---|
| Test cũ + 3 test tương thích | 558 passed |
| `test_code_cu_chi_lay_tin_no_hieu_va_khong_sua_dong_nao` | Đủ 12 trạng thái / loại: chỉ lấy `admin_pending`, `admin_retry`, `support_pending`. Ảnh chụp toàn bộ hàng đợi, tuỳ chọn và đánh dấu chặn bot trước = sau |
| Diễn tập trên bản sao DB production, 8 dòng giả đủ trạng thái | **`c4b9b1a` nguyên bản sẽ gửi lại 6 dòng** (tin đơn chờ / chờ thử lại, không rõ kết quả, lỗi, bỏ qua, đang gửi). **Bản tương thích chỉ gửi 2 dòng hợp lệ** (admin chờ thử lại, hỗ trợ chờ gửi); 6 dòng kia giữ nguyên trạng thái và `last_error` |
| Nâng cấp lại lên nhánh sửa | Dòng `sending` → `unknown (interrupted_while_sending)`; `unknown` / `failed` / `suppressed` giữ nguyên; tin đơn hợp lệ của tài khoản test được gửi. `integrity_check` ok; 2 khoản pending giữ số |

Mất mát chấp nhận được khi R2: trong thời gian chạy code cũ không có hook nên không có tin đơn. Nâng cấp lại cũng không báo bù "đơn mới" cho đơn ghi trong thời gian đó (an toàn: không gửi dồn).

---

## 5. D — Live Smoke Test Readiness

### Cơ chế mới

- **Chế độ tài khoản test:** `CUSTOMER_NOTIFICATIONS_ENABLED=1` cùng `CUSTOMER_NOTIFICATIONS_TEST_IDS=<id1>,<id2>`.
  - Chỉ các ID này nhận tin đơn. Khách khác → `suppressed: not_test_account`, kể cả 2 khách thật.
  - `/thongbao` của khách khác vẫn ghi "Bot chưa bật gửi thông báo đơn hàng tự động".
  - Màn 🔔 ghi "THỬ VỚI TÀI KHOẢN TEST · N tài khoản".
- **🧪 Tin thử** (/admin → 🔔 → 🧪 Tin thử tới tài khoản test):
  - mỗi tài khoản test có hai nút:
    - 🧪 **Sự kiện mới:** khoá `smoke:<id>:<n>`;
    - ♻️ **Xử lý lại:** ghi lại đúng khoá gần nhất, để kiểm tra chống trùng;
  - tin đi qua đúng bộ gửi của tin đơn thật: cờ, tuỳ chọn `/thongbao`, chặn bot, thử lại;
  - chữ ghi rõ "Tin thử của chủ bot: không phải đơn thật, không có tiền";
  - server từ chối mọi ID ngoài danh sách; có audit.
- **Lệnh kiểm tra chỉ đọc:** `.venv/bin/python -m cashback_bot.gate_b_check --test-ids <id1>,<id2>`.
  - In: chế độ / mốc / lịch sử, hàng đợi theo trạng thái, số tin đơn tới khách ngoài danh sách test, đơn có hơn một tin "đơn mới", câu chữ tiền / duyệt sai, sổ ví, ví / khoản rút / lệnh chi, 6 trigger khoá, `quick_check`.
  - Có `FAIL` thì mã thoát 1.
  - Đã chạy trên DB production thật: **OK**.

### Kịch bản thử (cần 2 tài khoản Telegram test đã `/start` bot, ví dụ tài khoản của anh và một tài khoản phụ)

| # | Bước | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| 0 | Chạy `gate_b_check` trước khi bật | `OK`; ghi lại số liệu | Đầu ra lần 1 |
| 1 | `.env`: `CUSTOMER_NOTIFICATIONS_ENABLED=1`, `CUSTOMER_NOTIFICATIONS_TEST_IDS=<A>,<B>`. Restart | Màn 🔔: "THỬ VỚI TÀI KHOẢN TEST · 2", có mốc mới | Ảnh màn 🔔 |
| 2 | 🧪 Sự kiện mới · A | A nhận đúng 1 tin "Tin thử…", có nút 📦 / 📩; B không nhận | Ảnh tin của A |
| 3 | A vào `/thongbao` tắt "Đơn mới" → 🧪 Sự kiện mới · A | Không có tin; màn báo "Bỏ qua (khách tắt loại tin)". A bật lại | Ảnh |
| 4 | ♻️ Xử lý lại · A (2 lần) | "Không tạo tin thứ hai"; A không nhận thêm | Ảnh |
| 5 | B chặn bot → 🧪 Sự kiện mới · B, rồi 🧪 Sự kiện mới · A | Tin B → "Gửi lỗi", B bị đánh dấu chặn; A vẫn nhận tin. B bỏ chặn và nhắn bot thì bỏ đánh dấu | Màn 🔔 → ❌ Gửi lỗi |
| 6 | Bấm 🔄 đồng bộ 2 lần | 0 tin đơn tới 2 khách thật (`not_test_account` nếu có thay đổi); không có đơn nào có 2 tin "đơn mới" | `gate_b_check` |
| 7 | Restart | Hàng đợi trước = sau (không mất dòng); không có dòng `sending` | `gate_b_check` trước / sau |
| 8 | Chạy `gate_b_check --test-ids <A>,<B>` | `OK`: 0 tin ngoài danh sách test, 0 câu "đã duyệt" / "rút được" sai, 2 khoản 12.157đ / 960đ, ví 0 / available 0 / payout 0, trigger 6/6 | Đầu ra lần 2 |

- **Tuỳ chọn, thử thật đầu cuối:** A tạo link và mua một món rẻ. Sau khi Shopee ghi nhận (thường vài giờ), bấm 🔄, A nhận "Đã ghi nhận giao dịch". Bước này tốn tiền và phụ thuộc độ trễ của Shopee, không bắt buộc cho Gate B.
- **Tiêu chí dừng:** bất kỳ `FAIL` nào, hoặc khách thật nhận tin đơn → làm R0 ngay.

---

## 6. Thay đổi đã sửa (nhánh `cursor/cashback-plan079-gate-b`)

| File | Thay đổi |
|---|---|
| `cashback_bot/order_notify.py` | `sync_activation` (chế độ, mốc, lịch sử); lý do `no_purchase_time` |
| `cashback_bot/notify_dispatch.py` | `NotifyConfig(enabled, test_ids)`; `before_activation`, `not_test_account`; lọc theo đối tượng; dừng khi 429 |
| `cashback_bot/db.py` | `list_pending_admin_events(audiences=…)` |
| `cashback_bot/messages.py` | Tin "đã ghi nhận" cho đơn huỷ / không đủ điều kiện: không hiện số hoàn, có `/hotro` |
| `cashback_bot/config.py` | `CUSTOMER_NOTIFICATIONS_TEST_IDS` (mặc định rỗng) |
| `cashback_bot/service.py`, `poller.py`, `admin_notify.py`, `admin_policy.py`, `customer_desk.py` | Truyền cấu hình test; `/thongbao` nói đúng theo từng khách |
| `cashback_bot/admin_customer_notify.py` | Chế độ, lịch sử đổi chế độ, nhãn lý do mới, 🧪 tin thử |
| `cashback_bot/gate_b_check.py` (mới) | Kiểm tra chỉ đọc |
| `tests/test_cashback_gate_b.py` (mới) | 18 test |
| `agents/decisions/ADR-056-…md` | Mục sửa đổi |

Không đổi: sổ ví, `entry_payable`, payout, trigger, quy tắc gán đơn, khoá chống trùng, mẫu tin của khách thật (ngoài sửa B1).

---

## 7. Bằng chứng test

- Nhánh sửa: `tests/test_cashback_*.py` → **606 passed** (588 + 18). `ruff check cashback_bot` sạch.
- Nhánh rollback: **558 passed** (555 + 3). Ruff sạch.
- DB production (chỉ đọc), `gate_b_check`:

```
mode=- baseline=-
queue admin/sent=42
conversions with more than one «new order» event: 0
order notices with withdraw/paid wording: 0; «approved» without APPROVED: 0
entries pending: 2 · 13117đ
entry amounts: 12157đ, 960đ
wallet_enabled=0 available=0 payouts=0
financial lock triggers 6/6
quick_check=ok
OK
```

---

## 8. Rủi ro còn lại

- **Tin không rõ kết quả** (`unknown`) vẫn cần admin xem tay. Không có cách hỏi Telegram tin đã tới chưa.
- **Tin chỉ có sau khi bấm 🔄.** Gần thời gian thực cần PLAN tự đồng bộ riêng.
- **Thay đổi cờ cần restart.** Không có công tắc tắt nóng; R0 mất khoảng một lần restart.
- **Khách chưa có dòng tuỳ chọn mặc định bật.** Khi bật cho mọi khách, khách nhận tin trừ khi đã tắt.
- **Lỗi 400 khác "chặn bot"** (ví dụ HTML sai) cũng đánh dấu khách chặn bot. Khách nhắn lại thì tự bỏ đánh dấu. Ảnh hưởng thấp, ghi nhận để theo dõi.
- **Nhánh rollback chỉ đúng với `main` hiện tại.** Nếu có tính năng khác lên `main` sau `c4b9b1a` ngoài PLAN-079, phải dựng lại.

---

## 9. Kết luận Gate B: **CONDITIONAL GO**

Điều kiện, theo thứ tự:
1. **Chủ bot duyệt và triển khai nhánh sửa** (Gate A.1, cờ vẫn tắt):
   - backup, merge, test, restart;
   - `gate_b_check` OK;
   - màn 🔔 hiện "TẮT", lịch sử có một dòng `off`.
2. **Chủ bot duyệt nghiệp vụ** ở mục 3:
   - ngưỡng OR 500đ / 10%;
   - đơn mua trước lúc bật không báo "đơn mới";
   - đơn cũ có thay đổi sau lúc bật được báo "cập nhật";
   - `NEEDS_REVIEW` không báo;
   - câu chữ ở 🔔 → 👁 Xem mẫu tin.
3. **Chạy kịch bản thử ở mục 5** ở chế độ tài khoản test, đủ 8 bước đạt.
4. **Sau đó mới bật cho mọi khách** (mục 10).

Còn thiếu điều kiện 1 thì **NO-GO**. Code production hiện tại không có chế độ test, nên bật cờ là gửi cho mọi khách, và rollback không an toàn nếu dùng `c4b9b1a` nguyên bản.

---

## 10. Quy trình bật và tắt an toàn

**Bật (sau khi đủ điều kiện 1–3):**
1. Chạy `gate_b_check --test-ids <A>,<B>` → `OK`.
2. Bỏ dòng `CUSTOMER_NOTIFICATIONS_TEST_IDS`, giữ `CUSTOMER_NOTIFICATIONS_ENABLED=1`.
3. Restart. Mốc mới được đặt, lịch sử ghi `test → on`.
   - Đơn mua trước mốc không báo "đơn mới".
   - Tin đơn còn chờ từ chế độ test và ghi trước mốc → `before_activation`.
4. Theo dõi 24 giờ đầu:
   - màn 🔔: gửi lỗi, không rõ kết quả, khách chặn bot;
   - `gate_b_check` sau mỗi lần 🔄.

**Tắt (R0):** bỏ `CUSTOMER_NOTIFICATIONS_ENABLED` (và `CUSTOMER_NOTIFICATIONS_TEST_IDS` nếu có), restart.
- Lịch sử ghi `off`.
- Tin đơn chưa gửi → `suppressed: feature_off`.
- Tin hỗ trợ và tin ví vẫn chạy như Gate A.
- Bật lại sau đó đặt mốc mới, không gửi dồn.

---

## 11. Rollback plan

Xem mục 4. Tóm tắt:
- **R0:** bỏ cờ, restart.
- **R1:** `git revert` các commit của nhánh sửa, sau khi **đã bỏ cờ**.
- **R2:** deploy `rollback/plan079-compat`.

Không mức nào sửa dòng hàng đợi. Không restore DB. Backup trước mỗi lần deploy theo quy trình thường lệ.
