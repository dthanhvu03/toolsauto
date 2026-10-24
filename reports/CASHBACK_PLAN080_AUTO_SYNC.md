# PLAN-080 — Automatic Shopee Sync V1

| | |
|---|---|
| Ngày | 2026-10-24 |
| Người làm | Claude Code |
| Nhánh | `cursor/cashback-plan080-auto-sync`, tách từ `main@4712c9a` (worktree `/home/vu/toolsauto-cashback-notifications`) |
| ADR | ADR-057 (mới) |
| Trạng thái | **Gate A đã triển khai 2026-10-24** (`main@5232840`). **Gate B đã bật 2026-10-24 10:34Z** (chủ bot, chu kỳ 240 phút; lượt tự động #11 thành công). Đang theo dõi 24–48 giờ. Chi tiết: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN080.md` |

Trong lúc làm PLAN này, em không gọi Shopee thật, không đổi cookie, không merge, không restart và không đổi `.env` production. DB production chỉ được đọc (`mode=ro`) hoặc chép ra bản sao quyền 0600 trong scratchpad; bản sao đã xoá sau khi dùng.

---

## 1. Executive Summary

- **Đồng bộ chạy ở một luồng nền riêng.** Cả lượt tay (🔄) lẫn lượt tự động đều chạy ở đó, nên trong lúc gọi Shopee, Telegram vẫn nhận link, trả lời khách, mở `/donhang`, `/thongbao`, `/hotro` và màn admin. Trước đây đồng bộ chạy ngay trong vòng poll và chặn toàn bộ bot.
- **Chỉ một lượt chạy tại một thời điểm.** Khoá lượt nằm trong DB, có chủ khoá, mã lượt, hạn khoá, gia hạn sau mỗi trang, và tự thu hồi khi tiến trình chết. Admin bấm 🔄 lúc lượt tự động đang chạy thì nhận: "🔄 Shopee đang được đồng bộ tự động. Mã lượt: #…", và bot không chạy lượt thứ hai.
- **Lịch lưu bền trong DB**, giờ UTC:
  - restart không chạy lại lượt vừa xong;
  - bot tắt nhiều ngày thì chỉ chạy bù một lượt;
  - lỗi tạm thì lùi lịch 15 / 30 / 60 / 120 phút; lỗi 429 thì theo `Retry-After`.
- **Lỗi được phân loại 9 loại:**
  - lỗi phiên Shopee → trạng thái NEEDS_AUTH: dừng tự gọi, báo admin một lần, chạy lại khi admin dán cookie mới;
  - 403 không kèm dấu hiệu đăng nhập không còn bị coi là cookie hết hạn;
  - gặp trang xác minh / CAPTCHA thì báo admin, bot không tự vượt.
- **Không kết luận "hết đơn" khi dữ liệu bất thường.** Trang lỗi, cấu trúc lạ, Shopee lặp trang hay chạm trần số trang đều cho kết quả PARTIAL. Không xoá đơn nào.
- **Thông báo khách dùng nguyên luồng của PLAN-079.** Một đơn được cả lượt tay lẫn lượt tự động xử lý cũng chỉ có một tin. Mốc kích hoạt PLAN-079 không bị thay đổi.
- **Màn admin mới** ⏱ Tự động đồng bộ: trạng thái, chu kỳ, lần chạy, lịch sử 15 lượt, sự cố, tạm dừng / tiếp tục.
- **Cờ `SHOPEE_AUTO_SYNC_ENABLED` mặc định TẮT.** Nút Telegram không bật được tự đồng bộ.
- **Test:** 648 passed (607 + 41 mới), ruff sạch.

---

## 2. Production Baseline (xác minh lại)

| Mục | Giá trị |
|---|---|
| Git | `main@4712c9a` (PLAN-080 viết trên đầu commit này). PLAN ghi `792397d` là bản cũ hơn; đã có thêm commit giao diện `/donhang` `e3f31e7` |
| Bot | PID 646983; `CUSTOMER_NOTIFICATIONS_ENABLED=1`; chế độ thông báo `on`, mốc 2026-10-24T09:21:19Z |
| Tự đồng bộ | `bot_state.shopee_auto_sync` không có, nghĩa là **tắt**. Lượt chạy theo lịch duy nhất là lượt #1 (2026-10-23 11:34), khi kết nối cookie lần đầu |
| Lịch sử đồng bộ | 9 lượt (1 tự động, 8 thủ công), tất cả `success`, mỗi lượt khoảng 1 giây. 2 đơn qua bot |
| Cookie | `storage/db/config/shopee_affiliate_cookies.json`, quyền 0600; trạng thái `connected` |
| Tiền | 2 khoản pending 12.157đ / 960đ; ví khoá; 0 available; 0 payout; 6 trigger khoá |
| Test | 607 passed |

---

## 3. Existing Shopee Sync Audit (A1–A10)

| # | Câu hỏi | Trả lời (theo code) |
|---|---|---|
| A1 | Đồng bộ thủ công gọi gì? | `admin_policy._shopee_sync` đặt `bot_state.shopee_sync_requested=1`. `poller._check_shopee_auto_sync` ở vòng kế tiếp gọi `ShopeeSyncEngine.sync(trigger="manual")`, theo thứ tự: `load_cookies` → `check_status` → `record_shopee_sync_run` → `_paged(fetch_clicks)` → `_paged(fetch_conversions)` → `_process_order_item` → `record_conversion_snapshot` → `complete_shopee_sync_run`. Sau đó gọi `service.refresh_wallet`, `notify_shopee_sync_result` và `flush_pending` |
| A2 | Có scheduler 4 giờ không? | **Có**, chung hàm trên: `interval_sec=14400`, chỉ chạy khi `bot_state.shopee_auto_sync == "1"`, do admin bật bằng nút `c:shopee:auto:on`. Đang tắt vì chủ bot chưa bật (theo memory: "user tự bấm 🔄; bot tự đồng bộ chỉ khi admin bật công tắc") |
| A3 | Chạy ở đâu? | **Ngay trong vòng poll Telegram**, đồng bộ (không thread, không asyncio). Trong lúc gọi Shopee, bot không nhận update nào |
| A4 | Chống chạy trùng? | Chỉ có khoá file một tiến trình (`fcntl` trên `/tmp/cashback_bot.lock`). Không có khoá lượt. Vòng poll chạy tuần tự nên không chạy song song, nhưng bấm 🔄 ngay sau lượt tự động vẫn gọi Shopee thêm một lần |
| A5 | Giới hạn API? | Theo code và chú thích (đã thử thật 2026-10-23): `page_size=100`, tối đa 20 trang mỗi loại, timeout 20 giây mỗi request. Đơn lọc theo `purchase_time_s/e`, quét lại 30 ngày mỗi lần. **Không có tài liệu Shopee về rate limit**, nên em không tự đặt con số |
| A6 | Cookie lưu thế nào? | `shopee_cookie.save_cookies` ghi JSON quyền 0600 vào `storage/db/config/`; `load_cookies` đọc mỗi lượt; `cookies_to_header` dựng header. Không ghi cookie vào log hay DB |
| A7 | Cookie hết hạn báo thế nào? | `check_status` hoặc report trả 401/403 thì `_mark_expired` đặt `shopee_cookies.status='expired'` và gọi `notify_shopee_cookie_expired`. Khoá chống trùng của tin này theo **giờ**, nên một sự cố kéo dài cho mỗi giờ một tin |
| A8 | Lỗi giữa chừng? | Mỗi đơn ghi trong transaction riêng, nên đơn đã ghi được giữ lại. Lượt ghi `failed`, hoặc `partial` nếu chỉ một loại báo cáo lỗi |
| A9 | Phát hiện cập nhật đơn cũ? | Có, trong khung 30 ngày theo giờ mua: `record_conversion_snapshot` so từng trường và ghi `shopee_conversion_changes` |
| A10 | PLAN-079 lấy sự kiện ở đâu? | `TrackingRepository.conversion_hooks`, gọi trong `record_conversion_snapshot` sau khi ghi lịch sử thay đổi, bọc SAVEPOINT (ADR-056) |

**Đường đi (không đổi sau PLAN-080, chỉ thay nơi chạy):**

```
ShopeeAffiliateClient (check_status, fetch_clicks, fetch_conversions)
→ _paged (phân trang, nay có thống kê và phát hiện bất thường)
→ _process_order_item → commission_validation.assess
→ record_conversion_snapshot (đơn + shopee_conversion_changes + hook PLAN-079 → admin_notifications, cùng transaction)
→ complete run → (luồng chính) Wallet.refresh → Dispatcher.flush → Telegram
```

---

## 4. Existing 4-Hour Scheduler Audit

| Vấn đề | Hậu quả |
|---|---|
| Chạy trong vòng poll | Shopee chậm thì khách đợi. Trường hợp xấu nhất: 2 loại × 20 trang × timeout 20 giây |
| Nút Telegram bật thẳng | Không có cờ cấu hình nào đứng trên nút; PLAN-080 cấm đường vượt cờ này |
| Lịch là `time.time()` trong `bot_state` | Đặt mốc **trước** khi chạy, nên lỗi cũng bị coi như đã chạy. Không có giãn cách khi lỗi |
| Không có khoá lượt | Tay và tự động có thể gọi Shopee liền nhau |
| Mọi 401/403 là cookie hết hạn | 403 vì lý do khác cũng bắt admin dán cookie lại |
| `_paged` dừng lặng lẽ | Thiếu `data`, Shopee lặp trang hay chạm 20 trang đều thành "success" |
| Báo cookie hết hạn mỗi giờ | Một sự cố cho nhiều tin trùng |
| Không có số liệu từng lượt | Không biết số trang đọc, số đơn mới / đổi / không đổi, số tin khách |

---

## 5. Architecture Before / After

```
TRƯỚC:  vòng poll ─ getUpdates ─ xử lý update ─ [đồng bộ Shopee: 1–800 giây, chặn] ─ ví ─ backup ─ lặp
SAU:    vòng poll ─ getUpdates ─ xử lý update ─ nhận kết quả lượt (queue) → ví, tin admin, gửi hàng đợi ─ lặp
        luồng nền ─ next_job()? ─ lấy khoá DB ─ engine.sync(run_id, heartbeat) ─ đóng lượt + nhả khoá ─ sự cố ─ queue
```

---

## 6. Scheduler Design

- `SyncWorker` là một thread daemon duy nhất, khởi động trong `poller.main` sau khi đã có khoá file. Mỗi 30 giây nó kiểm tra có việc không; nút 🔄 đánh thức ngay qua `WAKE`.
- `next_job()` trả về:
  - `manual` nếu có yêu cầu tay;
  - `auto` khi cờ bật, không tạm dừng, không ở NEEDS_AUTH và đã tới `next_due_at`.
  Khi ở NEEDS_AUTH mà cookie được kết nối lại sau mốc sự cố, nó trả `auto` ngay.
- Lỗi của một lượt không làm chết thread.

**Cấu hình** (`.env`, đọc lúc khởi động):

| Biến | Mặc định | Giới hạn |
|---|---|---|
| `SHOPEE_AUTO_SYNC_ENABLED` | tắt | — |
| `SHOPEE_AUTO_SYNC_INTERVAL_MINUTES` | 120 | 60–1440. Dưới 60 bị từ chối khi khởi động |
| `SHOPEE_AUTO_SYNC_MAX_RUNTIME_SECONDS` | 600 | 120–3600 |
| `SHOPEE_AUTO_SYNC_FAILURE_THRESHOLD` | 3 | 1–20 |

Chính sách thử lại cố định trong code (ADR-057): lùi 15 × 2ⁿ phút, không quá một chu kỳ; 429 chờ ít nhất `Retry-After`; trong một lượt, lỗi tạm ở một trang được thử lại 2 lần (sau 2 giây và 5 giây).

**Lịch:**

| Tình huống | `next_due_at` |
|---|---|
| Bật cờ lần đầu, hoặc tiếp tục sau tạm dừng | bây giờ + 5 phút |
| Lượt thành công (cả thủ công) | xong + chu kỳ |
| PARTIAL / lỗi tạm | xong + min(chu kỳ, 15 × 2^(lỗi liên tiếp − 1) phút) |
| 429 | như trên, nhưng ít nhất `Retry-After` |
| Lỗi phiên, cờ tắt, tạm dừng | không hẹn |
| Đổi chu kỳ | lần xong gần nhất + chu kỳ mới |
| Bot tắt lâu | quá hạn thì chạy 1 lượt, sau đó + chu kỳ |

---

## 7. Persistent State

**Bảng `shopee_sync_state`** (một dòng duy nhất):
- cấu hình: `enabled`, `interval_minutes`, `paused` (kèm thời điểm và người tạm dừng);
- lịch: `next_due_at`, `last_scheduled_at`, `last_started_at`, `last_finished_at`, `last_success_at`;
- kết quả: `last_result`, `last_run_id`, `last_error_category`, `consecutive_failures`, `needs_auth_since`, `last_success_window_start/end`;
- khoá: `lease_owner`, `lease_run_id`, `lease_trigger`, `lease_started_at`, `lease_expires_at`, `heartbeat_at`.

Tất cả lưu giờ UTC; màn admin hiển thị giờ Việt Nam.

**Bảng `shopee_sync_runs`** thêm các cột: `lease_owner`, `error_category`, `pages_fetched`, `pages_failed`, `conversions_new/changed/unchanged`, `invalid_records`, `notifications_queued/suppressed`, `window_start/end`. Trạng thái lượt: `running`, `success`, `partial`, `failed`, `interrupted`.

---

## 8. Manual / Auto Single Flight

- **Lấy khoá:** trong một transaction `BEGIN IMMEDIATE`: đọc khoá. Khoá còn hạn và chủ còn sống → trả lượt đang chạy. Khoá quá hạn hoặc chủ đã chết → ghi lượt cũ `interrupted`, tạo lượt mới, ghi khoá. Hai luồng cùng lấy khoá thì SQLite xếp hàng, chỉ một bên thắng (test 20).
- **Gia hạn:** sau mỗi trang. Mất khoá, hoặc quá `MAX_RUNTIME`, thì dừng trước trang kế tiếp (test 15).
- **Đóng lượt:** ghi lượt, cập nhật lịch và nhả khoá trong một transaction, chỉ khi `lease_owner` và `lease_run_id` vẫn khớp. Lượt cũ đã bị thu hồi không ghi được kết quả cho lượt mới (test 17–18).
- **Nút 🔄 khi đang bận:** trả mã lượt đang chạy và không đặt cờ. Nếu cờ đã lỡ đặt sát lúc lượt bắt đầu, lượt tay không chạy và admin nhận tin "đang đồng bộ, mã lượt #…" (test 14).
- **Hai tiến trình:** khoá file vẫn chặn (test 19). Nếu khoá file không chặn được, khoá DB vẫn đảm bảo chỉ một lượt.
- **Chưa có force-sync.** Nếu cần, làm thành PLAN riêng.

---

## 9. Cookie & Session Handling

- Cookie vẫn đọc từ file 0600 mỗi lượt. Không ghi cookie vào log, DB, tin admin hay thông báo lỗi; thông báo lỗi chỉ ghi tên lớp lỗi và mã HTTP (test 49).
- Chỉ đánh dấu `shopee_cookies.status='expired'` khi có `AUTH_EXPIRED`. Khi gặp `ACCESS_DENIED` hoặc `CHALLENGE`, cookie vẫn để `connected` kèm `last_error`, còn lịch chuyển sang NEEDS_AUTH (test 39–40).
- **NEEDS_AUTH:**
  - không gọi Shopee theo lịch;
  - mở **một** sự cố và báo admin một lần, kèm hướng dẫn "🔑 Cập nhật Cookie";
  - admin dán cookie mới thì lịch chạy lại ngay; lượt thành công thì đóng sự cố và báo phục hồi (test 37–38, 48);
  - với lượt tự động, không gửi thêm tin "Cookie hết hạn" theo giờ nữa. Đồng bộ tay vẫn báo như cũ.
- Bot không tự đăng nhập, không vượt CAPTCHA, không hỏi khách thông tin Shopee.

---

## 10. Error Classification

| Loại | Căn cứ | Xử lý trong lượt | Lịch sau lượt |
|---|---|---|---|
| `AUTH_EXPIRED` | 401; `user/status` trả 401/403 / `code ≠ 0` | dừng ngay | NEEDS_AUTH |
| `ACCESS_DENIED` | 403 báo cáo không có dấu hiệu xác minh; `allow_to_login=false` | dừng ngay | NEEDS_AUTH |
| `CHALLENGE` | 403 hoặc response không phải JSON có "captcha / verify / xác minh / challenge" | dừng ngay | NEEDS_AUTH |
| `RATE_LIMITED` | 429 (+ `Retry-After`) | dừng ngay, không gọi tiếp | lùi ≥ `Retry-After` |
| `NETWORK_TIMEOUT` / `NETWORK_ERROR` / `TRANSIENT_SERVER_ERROR` | timeout / lỗi kết nối, DNS / 5xx | thử lại trang 2 lần, rồi PARTIAL | lùi có giãn cách |
| `PARSE_ERROR` | thiếu `data`, thiếu khoá danh sách, không phải JSON | PARTIAL | lùi; mở sự cố "định dạng đổi" ngay |
| `PARTIAL_SYNC` | trang lỗi, Shopee lặp trang, chạm 20 trang | PARTIAL | lùi |
| `DATABASE_ERROR` / `UNKNOWN_ERROR` | lỗi sqlite3 / còn lại | dừng | lùi |
| `INTERRUPTED` / `LEASE_LOST` | bot dừng giữa lượt / mất khoá, quá giờ | không ghi tiếp | lượt sau theo lịch |

**Lưu ý:** dấu hiệu CAPTCHA chỉ là đoán từ chữ trong trang trả về, vì em không có response thật của Shopee cho trường hợp này. Nếu Shopee dùng dạng khác, lỗi đó sẽ rơi vào `ACCESS_DENIED` hoặc `PARSE_ERROR`; cả hai đều dừng hoặc báo admin, không gọi liên tục.

---

## 11. Pagination & Late Data

- **Phân trang:** `PAGE_SIZE=100`, `MAX_PAGES=20`, như code đã thử thật.
- **Mỗi lượt ghi:** số trang đã đọc, số trang lỗi, và danh sách vấn đề (`PARSE_ERROR:pageN`, `PAGINATION_ANOMALY:pageN`, `TRUNCATED:20`).
- **Lượt chưa đủ dữ liệu:**
  - kết quả là `partial` với `ok=False`, không ghi là kỳ thành công;
  - không xoá và không huỷ đơn vắng mặt (test 33, 34, 36);
  - đơn của các trang đã đọc vẫn được ghi.
- **Đơn về muộn:** mỗi lượt quét lại 30 ngày theo giờ mua. Đơn mua hôm trước mà hôm nay Shopee mới báo vẫn được bắt, và được báo "đơn mới" nếu mua sau mốc PLAN-079 (test 23). Đơn cũ đổi trạng thái hoặc hoa hồng trong 30 ngày cũng được bắt (test 24–29).
- **Chưa làm:** mở rộng khung quét cho đơn còn chờ xác minh mà mua quá 30 ngày. Em không có bằng chứng Shopee cho phép khung dài hơn hay chi phí truy vấn ra sao. Việc này cần chủ bot quyết định (mục 21).

---

## 12. Notification Integration

- Không thêm đường thông báo mới. Lượt tự động và lượt tay đều đi qua `record_conversion_snapshot`, rồi hook PLAN-079, rồi `admin_notifications`, rồi `Dispatcher`. Không gửi Telegram trong lúc gọi HTTP hay trong transaction.
- **Chống trùng:** khoá theo sự kiện nghiệp vụ (`conversion:<id>:first_matched`, `…:changes:<id thay đổi>`), không theo lượt.
  - Lượt tay rồi tự động, hay tự động rồi tay, vẫn chỉ một tin (test 51–55).
  - 10 lượt y hệt nhau chỉ cho một tin (test 21).
- **Ngưỡng 500đ / 10%**, quy tắc huỷ / từ chối / về 0 và tuỳ chọn của khách giữ đúng như PLAN-079 (test 24–29, 57).
- **Mốc kích hoạt PLAN-079** không bị bộ lập lịch đổi (test 62).
- **Số tin khách của từng lượt** đếm theo mã dòng hàng đợi kể từ đầu lượt, chỉ tính tin đơn hàng (`source_ref LIKE 'conversion:%'`), nên không lẫn tin của lượt trước.
- **Lượt tự động đầu tiên có thể gửi tin thật cho khách.** Nếu từ lần 🔄 gần nhất Shopee đã có thay đổi (ví dụ đơn 12.157đ chuyển "đã thanh toán"), khách sẽ nhận tin cập nhật theo đúng quy tắc PLAN-079. Bot không lặng lẽ bỏ qua những thay đổi này.

---

## 13. Admin UI

- **🔗 Shopee Affiliate:** dòng "Tự đồng bộ" lấy theo trạng thái thật (tắt / mỗi N phút, lần tới … / tạm dừng / cần kiểm tra phiên…). Nút cũ "🟢 Bật tự đồng bộ 4 giờ" được thay bằng **⏱ Tự động đồng bộ**.
- **⏱ Tự động đồng bộ** (`c:sy:home`) hiển thị:
  - trạng thái (TẮT / BẬT / TẠM DỪNG / ĐANG CHẠY #… / CHỜ THỬ LẠI / LỖI LIÊN TIẾP / CẦN KIỂM TRA PHIÊN) và chu kỳ;
  - lần dự kiến tiếp theo, lần chạy gần nhất (loại, kết quả, thời lượng, số đơn / mới / đổi / tin khách), lần thành công gần nhất;
  - lượt tự động gần nhất, hoặc "chưa có lượt chạy";
  - tình trạng phiên Shopee, lỗi liên tiếp, lỗi gần nhất, sự cố đang mở.
- **📜 Lịch sử 15 lượt** (`c:sy:hist`): loại, giờ, kết quả, số liệu, lỗi.
- **⏸️ Tạm dừng / ▶️ Tiếp tục:** chỉ hiện khi cờ `.env` bật; lưu bền; có audit ở 📊 Lịch sử. Gọi các callback này khi cờ tắt thì nhận "chủ bot bật bằng SHOPEE_AUTO_SYNC_ENABLED" và không có gì thay đổi.
- **Không có** nút bật, nút đổi chu kỳ, nút force-sync.

---

## 14. Admin Alerts

| Khi nào | Tin |
|---|---|
| Lỗi phiên (lần đầu) | 🔑 Shopee cần kiểm tra phiên đăng nhập, sự cố #N |
| Dữ liệu đổi định dạng (lần đầu) | 🧩 Dữ liệu Shopee đổi định dạng |
| Lỗi liên tiếp / PARTIAL tới ngưỡng (3) | ⚠️ Đồng bộ Shopee lỗi liên tiếp / chưa đọc đủ dữ liệu |
| Sự cố chuyển thành lỗi phiên | tin cập nhật (escalated) |
| Sự cố còn mở sau 24 giờ | nhắc lại |
| Lượt thành công khi đang có sự cố | ✅ Đồng bộ Shopee đã hoạt động lại |
| Lượt tự động thành công, không có sự cố | không nhắn |

- Mỗi tin có khoá riêng `sync_incident:<id>:open|escalated|remind:<n>|resolved`, nên không trùng (test 45–48).
- Đi qua hàng đợi admin, không phụ thuộc lựa chọn thông báo của khách.
- Đơn mới và hoa hồng đổi vẫn có tin admin riêng như trước.

---

## 15. Resource Usage

- **Tài nguyên:** thêm 1 thread, nghỉ 30 giây giữa các lần kiểm tra. Mỗi lần kiểm tra vài câu SELECT; không có vòng lặp bận.
- **Gọi Shopee:** bằng cách cũ, một lượt mỗi chu kỳ. Với chu kỳ 120 phút là 12 lượt/ngày, mỗi lượt gồm `user/status` cộng ít nhất 1 trang click và 1 trang đơn. Hiện mỗi lượt khoảng 1 giây (lịch sử 9 lượt thật).
- **SQLite:** hai luồng ghi xen nhau; mỗi transaction ngắn; `timeout=15`. Không đổi chế độ journal.
- **Chưa đo** CPU / RAM trên production. Đây là việc cần theo dõi ở Gate B (mục 19).

---

## 16. Migration

- **Cách chạy:** tự động trong `migrate()`, chạy lại nhiều lần vẫn an toàn.
  - Tạo `shopee_sync_state` và `shopee_sync_incidents` (có unique index để tối đa một sự cố mở).
  - Thêm 12 cột vào `shopee_sync_runs`.
  - Không sửa dữ liệu nào.
- **Diễn tập trên bản sao DB production** (0600, đã xoá):
  - `migrate()` 2 lần: không đổi gì ở đơn, lịch sử thay đổi, sổ ví, payout, hàng đợi, tuỳ chọn khách, mốc PLAN-079, snapshot chính sách, trigger. So bằng mã băm từng nhóm. `integrity_check` = ok.
  - Cờ tắt: `enabled=0`, `next_due_at` trống, không có việc nào.
  - Một lượt tay qua Shopee giả phát lại đúng 2 đơn thật đã lưu: `success`, 2 trang, **0 mới, 0 đổi, 2 không đổi, 0 tin khách**. Dữ liệu trước và sau không đổi.
- **Tương thích ngược:** code production hiện tại (`4712c9a`) chạy trên DB đã có schema mới: đồng bộ được, `integrity_check` ok. Khoá và dòng `running` của bản mới để lại vô hại; khi lên lại bản mới, `start()` sẽ thu hồi.

---

## 17. Test Evidence

- `tests/test_cashback_*.py`: **648 passed** (607 + 41 trong `tests/test_cashback_auto_sync.py`). `ruff check cashback_bot` sạch.
- 2 test cũ trong `test_cashback_wallet.py` được viết lại theo hành vi mới:
  - nút 🔄 chạy qua bộ điều phối;
  - nút Telegram không bật được tự đồng bộ khi cờ tắt.

| Nhóm PLAN | Test |
|---|---|
| Lịch 1–13 | tắt không gọi Shopee; lần đầu sau 5 phút, rồi mỗi chu kỳ; restart không chạy lại; tắt 3 ngày chỉ chạy bù 1 lượt; đổi chu kỳ; bật ↔ tắt; dừng giữa lượt → `interrupted`; khoá của tiến trình chết; giờ UTC; Telegram không bị chặn khi Shopee treo |
| Khoá 14–20 | tay khi tự động đang chạy; quá thời gian tối đa; engine lỗi; khoá hết hạn; lượt cũ không ghi đè lượt mới; hai tiến trình; hai luồng cùng lúc chỉ một lần gọi Shopee |
| Shopee 21–36 | không đổi; đơn mới; về muộn; PAID / COMPLETED / tăng / giảm / dưới ngưỡng / về 0; huỷ, gian lận; không có / sai Sub ID; nhiều trang; trang lỗi → PARTIAL, giữ đơn; cấu trúc đổi; lặp trang; chạm trần trang |
| Cookie, lỗi 37–49 | hết hạn → NEEDS_AUTH, 1 tin; kết nối lại → chạy lại, báo phục hồi; 403 và xác minh không đánh dấu hết hạn; 429 theo `Retry-After`; 5xx / timeout / mạng thử lại trong lượt; giãn cách 15 → 30 → 60 → 120; ngưỡng, nhắc lại sau 24 giờ; không lộ cookie; phân loại HTTP; client đọc `Retry-After` |
| Thông báo 50–64 | đúng người; link chia sẻ; tay rồi tự động không trùng; khách tắt thông báo; không đổi mốc PLAN-079; không có tin khi không có đơn |
| Tài chính 65–71 | không available, không payout, không APPROVED / SETTLED; trigger còn |
| Admin | chưa có lượt, tắt, lịch sử, sai quyền, nút giả; bật, tạm dừng, có audit, đồng bộ tay vẫn chạy khi tạm dừng |
| Regression 72–83 | toàn bộ test cũ |

---

## 18. Files Changed

| File | Thay đổi |
|---|---|
| `cashback_bot/sync_scheduler.py` (mới) | `SyncCoordinator` (lịch, khoá, đóng lượt, sự cố), `SyncWorker`, `request_manual`, `busy`, `snapshot` |
| `cashback_bot/admin_sync.py` (mới) | Màn ⏱ Tự động đồng bộ và lịch sử |
| `cashback_bot/shopee_client.py` | Phân loại lỗi, `Retry-After`, `_report` dùng chung |
| `cashback_bot/shopee_sync.py` | `PageStats`, phát hiện bất thường, thử lại trang, `LeaseLost`; `sync(run_id, heartbeat, alert_auth)`; số liệu lượt; bỏ đơn không có mã; bỏ `AUTO_SYNC_KEY` |
| `cashback_bot/db.py` | Bảng và cột mới; `complete_shopee_sync_run(category, stats, conn)`; `notification_mark` / `order_events_after`; `timeout=15` |
| `cashback_bot/poller.py` | Bỏ `_check_shopee_auto_sync`; khởi động bộ điều phối và luồng nền; `drain_sync_results` |
| `cashback_bot/config.py` | `AutoSyncConfig` và 4 biến `SHOPEE_AUTO_SYNC_*` |
| `cashback_bot/admin_policy.py`, `admin_ui.py`, `service.py` | Nút 🔄 khi bận; tạm dừng / tiếp tục chỉ khi cờ bật; route `c:sy:`; nhãn audit |
| `tests/test_cashback_auto_sync.py` (mới), `tests/test_cashback_wallet.py` | 41 test mới, 2 test cũ viết lại |
| `agents/decisions/ADR-057-shopee-auto-sync-scheduler.md` | ADR mới |

---

## 19. Rollout Plan

**Gate A (cần chủ bot duyệt):**
1. Backup và verify.
2. Merge, test, push.
3. Chủ bot restart. **Không** thêm biến `SHOPEE_AUTO_SYNC_*`.
4. Kiểm tra:
   - log có dòng `shopee auto sync enabled=False`, không lỗi, không lộ token;
   - màn ⏱ hiện "TẮT";
   - bấm 🔄 một lần: bot nhắn kết quả (có thể chậm tới 30 giây), lịch sử có lượt `thủ công · thành công`;
   - `gate_b_check` OK; 2 khoản pending giữ số; không có lượt `auto` mới.

**Gate B (duyệt riêng):**
1. Diễn tập đã có (Shopee giả, DB riêng, đồng hồ giả).
2. **Kiểm tra nguồn:** chủ bot bấm 🔄 một lần ngay trước khi bật, xem lượt `success` và số trang. Lượt này là một lần gọi Shopee thật, có tính vào giới hạn tần suất của Shopee.
3. Thêm `SHOPEE_AUTO_SYNC_ENABLED=1` (chu kỳ mặc định 120 phút) và restart. Lượt tự động đầu tiên chạy sau 5 phút.
   - **Lượt này có thể gửi tin cập nhật thật cho khách** nếu Shopee đã có thay đổi so với lần 🔄 trước (mục 12).
   - Giữ nguyên `CUSTOMER_NOTIFICATIONS_ENABLED=1`.
4. Theo dõi 24–48 giờ:
   - tỷ lệ lượt thành công, thời lượng mỗi lượt;
   - số tin khách; đơn có hai tin "đơn mới" (`gate_b_check`);
   - lỗi phiên; số lần gọi Shopee mỗi ngày;
   - log `database is locked` (phải bằng 0); poll Telegram có bình thường không.

   Sau đó mới quyết định giữ 120 phút hay đổi 60 / 240.

---

## 20. Rollback Plan

| Mức | Làm gì | Giữ nguyên |
|---|---|---|
| **R0: tắt tự đồng bộ** | Xoá `SHOPEE_AUTO_SYNC_ENABLED`, restart | Đồng bộ tay, thông báo khách, `/donhang`, `/thongbao`, `/hotro`, lịch sử lượt |
| **R1: tạm dừng nóng** | /admin → 🔗 → ⏱ → ⏸️ Tạm dừng (không cần restart). Lỗi phiên tự chuyển NEEDS_AUTH | Như trên. Không xoá đơn, không xoá hàng đợi, không gửi dồn khi tiếp tục |
| **R2: về code trước PLAN-080** | `git revert` các commit PLAN-080, restart | Bảng và cột mới để lại vô hại (đã thử code `4712c9a` trên schema mới). Không sửa lượt thành `success`, không sửa tin `unknown`, không restore DB |

**Lưu ý khi R2:** code cũ có lại nút "🟢 Bật tự đồng bộ 4 giờ" trên Telegram. `bot_state.shopee_auto_sync` vẫn không tồn tại (tức là tắt), nên sau rollback tự đồng bộ vẫn tắt, trừ khi có người bấm nút.

---

## 21. Remaining Risks

- **Khung quét 30 ngày theo giờ mua.** Đơn còn chờ xác minh mà mua quá 30 ngày thì không được cập nhật nữa, vì Shopee có thể duyệt muộn. Cần chủ bot quyết định có mở rộng khung không, sau khi biết Shopee cho phép và chi phí truy vấn thế nào.
- **Chưa có giới hạn tần suất chính thức của Shopee.** Mức 60 phút tối thiểu là chính sách vận hành, không dựa trên tài liệu Shopee.
- **Dấu hiệu CAPTCHA đoán theo chữ.** Chưa thấy response thật cho trường hợp này.
- **Tin kết quả của lượt tay chậm hơn trước,** tới một vòng long-poll (≤ 30 giây), vì lượt chạy ở luồng nền.
- **Giữa hai lần gia hạn khoá,** một lượt quá giờ vẫn có thể ghi xong đúng một trang. Việc ghi đơn là idempotent nên không trùng dữ liệu.
- **CPU / RAM / độ tranh chấp khoá SQLite** chưa đo trên production. Cần theo dõi ở Gate B.
- **Endpoint v3** là API nội bộ của web Shopee Affiliate, không cam kết ổn định. Nếu đổi định dạng, bot báo "🧩 Dữ liệu Shopee đổi định dạng"; đơn cũ giữ nguyên.

---

## 22. Release Gates

| Gate | Kết luận |
|---|---|
| Existing Sync Reuse | **GO** (cùng engine, cùng pipeline) |
| Scheduler | **GO** |
| Persistent State | **GO** |
| Concurrency Safety | **GO** |
| Cookie Handling | **CONDITIONAL** (dấu hiệu CAPTCHA chưa thấy response thật) |
| Pagination | **CONDITIONAL** (khung 30 ngày, mục 21) |
| Error Recovery | **GO** |
| Customer Notifications | **GO** |
| Admin Monitoring | **GO** |
| Financial Lock | **GO** |
| Regression | **GO** (648/648) |
| Gate A Code Deployment | **GO, đã triển khai** (chủ bot duyệt 2026-10-24) |
| Gate B Auto Sync Activation | **GO, đã bật** (chủ bot, 240 phút, 2026-10-24) |
| Wallet & Payout | **NOT AUTHORIZED** |

---

## Câu hỏi nghiệm thu

**Q1. Bật rồi bot có tự chạy khi tới giờ không?**
Có. Lượt đầu chạy sau 5 phút, sau đó mỗi chu kỳ; không cần bấm (test 02).

**Q2. Đồng bộ mất 3 phút, khách có dùng bot bình thường không?**
Có. Đồng bộ chạy ở luồng nền. Test 13 giữ Shopee "treo" trong lúc khách tạo link và mở `/donhang`, và cả hai vẫn chạy.

**Q3. Admin bấm 🔄 lúc lượt tự động đang chạy?**
Bot trả "🔄 Shopee đang được đồng bộ tự động. Mã lượt: #…" và không chạy lượt thứ hai (test 14).

**Q4. Restart trước giờ hoặc giữa lượt có chạy trùng không?**
Không.
- Restart trước giờ: lịch nằm trong DB, nên không chạy lại lượt vừa xong (test 04).
- Restart giữa lượt: lượt cũ ghi `interrupted`, khoá được thu hồi; sau đó chạy theo lịch (test 10).

**Q5. Shopee hết phiên thì sao?**
Bot dừng tự gọi, chuyển NEEDS_AUTH và báo admin đúng một lần. Admin dán cookie mới thì bot tự chạy lại và báo phục hồi (test 37, 48).

**Q6. Shopee trả 429 thì sao?**
Bot dừng lượt ngay, không gọi tiếp, và lùi lịch ít nhất `Retry-After`. Lỗi lặp lại thì giãn cách tăng dần (test 41, 45).

**Q7. Đơn hôm trước mà hôm nay Shopee mới ghi nhận?**
Bắt được. Mỗi lượt quét lại 30 ngày theo giờ mua (test 23).

**Q8. Một đơn được cả lượt tay lẫn lượt tự động xử lý có bị báo hai lần không?**
Không. Khoá chống trùng theo sự kiện nghiệp vụ, không theo lượt (test 51–55).

**Q9. Shopee không có thay đổi thì có tin thừa không?**
Không. 10 lượt y hệt nhau chỉ có tin "đơn mới" ban đầu (test 21); không có đơn thì không có tin khách (test cuối nhóm thông báo).

**Q10. Một trang Shopee lỗi, bot có tưởng là không có đơn hoặc xoá dữ liệu cũ không?**
Không. Lượt ghi PARTIAL kèm số trang lỗi, không xoá đơn và không ghi là kỳ thành công (test 33–36).

**Q11. Có thay đổi nào cho khách rút tiền trước khi Shopee duyệt không?**
Không. Bot không gán APPROVED / SETTLED, không tạo khoản available hay payout; trigger khoá còn đủ (test 65–71).

**Q12. Tắt riêng tự đồng bộ mà vẫn giữ đồng bộ tay và thông báo khách?**
Có hai cách:
- tắt nóng: ⏸️ Tạm dừng ở màn ⏱;
- tắt hẳn: xoá `SHOPEE_AUTO_SYNC_ENABLED` rồi restart.

Cả hai cách đều giữ nguyên đồng bộ tay và `CUSTOMER_NOTIFICATIONS_ENABLED`.
