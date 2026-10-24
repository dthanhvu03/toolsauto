# ADR-057 — Tự đồng bộ Shopee: một luồng nền, khoá một lượt trong DB, lịch bền

| | |
|---|---|
| Trạng thái | Accepted (PLAN-080), chưa triển khai production |
| Ngày | 2026-10-24 |
| Liên quan | ADR-056 (hàng đợi thông báo), PLAN-065/066 (đồng bộ cookie), PLAN-074 (lịch sử thay đổi đơn) |

## Bối cảnh
- Đồng bộ Shopee chạy **ngay trong vòng poll Telegram** (`poller._check_shopee_auto_sync`). Trong lúc gọi Shopee, bot không nhận update nào của khách. Mỗi trang có timeout 20 giây, tối đa 20 trang cho mỗi loại báo cáo.
- Tự đồng bộ 4 giờ được bật bằng nút Telegram (`bot_state.shopee_auto_sync`); không có cờ cấu hình nào đứng trên nút này.
- Lịch chạy là một mốc thời gian `time.time()` lưu trong `bot_state`. Không có khoá lượt, không có số liệu từng lượt.
- Lỗi chưa được phân loại: mọi 401/403 đều bị coi là cookie hết hạn, và bot báo admin mỗi giờ.
- Trang trả về bất thường (thiếu `data`, Shopee lặp lại trang, chạm trần số trang) bị bỏ qua lặng lẽ, nhưng lượt vẫn ghi "success".

## Quyết định
1. **Dùng lại `ShopeeSyncEngine`**, không viết pipeline thứ hai. Engine nhận thêm:
   - `run_id` của lượt đã mở;
   - `heartbeat`, được gọi sau mỗi trang; trả False thì dừng;
   - `alert_auth=False` khi chạy theo lịch.

   Engine trả `status` / `category` / `stats` để bên giữ khoá ghi vào lượt. Gọi không có `run_id` thì hoạt động như cũ.
2. **Một luồng nền duy nhất** (`sync_scheduler.SyncWorker`) chạy cả lượt thủ công lẫn tự động. Luồng chính (poll Telegram) chỉ nhận kết quả qua `queue.Queue`, rồi làm mới ví, nhắn kết quả lượt thủ công cho admin và gửi hàng đợi. Không có transaction SQLite nào giữ trong lúc gọi HTTP. `connect(timeout=15)` để hai luồng chờ khoá ghi thay vì báo lỗi ngay.
3. **Khoá một lượt trong DB** (`shopee_sync_state`, một dòng duy nhất):
   - lấy khoá bằng `BEGIN IMMEDIATE`: kiểm tra khoá, tạo lượt, ghi khoá trong cùng transaction;
   - gia hạn khoá sau mỗi trang, có trần `SHOPEE_AUTO_SYNC_MAX_RUNTIME_SECONDS`;
   - đóng lượt, cập nhật lịch và nhả khoá trong một transaction, chỉ khi `lease_owner` và `lease_run_id` vẫn khớp;
   - khoá quá hạn, hoặc thuộc tiến trình đã chết trên cùng máy, thì được thu hồi; lượt cũ ghi `interrupted`;
   - lượt mất khoá không ghi kết quả.

   Khoá file một tiến trình (`/tmp/cashback_bot.lock`) vẫn giữ như cũ.
4. **Cờ `.env` là công tắc chính:**
   - `SHOPEE_AUTO_SYNC_ENABLED` (mặc định tắt);
   - `SHOPEE_AUTO_SYNC_INTERVAL_MINUTES` (mặc định 120, trong khoảng 60–1440);
   - `SHOPEE_AUTO_SYNC_MAX_RUNTIME_SECONDS` (600);
   - `SHOPEE_AUTO_SYNC_FAILURE_THRESHOLD` (3).

   Nút Telegram chỉ còn **tạm dừng / tiếp tục**, lưu bền, có audit, và chỉ có tác dụng khi cờ đã bật. Khoá `bot_state.shopee_auto_sync` cũ không còn được đọc.
5. **Lịch bền** (`next_due_at`, UTC):
   - bật lần đầu: lượt tự động đầu tiên sau 5 phút;
   - lượt thành công (cả thủ công): lượt kế tiếp sau một chu kỳ;
   - lỗi tạm hoặc lượt chưa đủ dữ liệu: lùi 15 / 30 / 60… phút, không quá một chu kỳ; 429 thì chờ ít nhất `Retry-After`;
   - lỗi phiên: không hẹn lượt tiếp;
   - bot tắt lâu: chỉ chạy bù **một** lượt;
   - đổi chu kỳ: tính lại từ lần chạy xong gần nhất.
6. **Phân loại lỗi** trong `shopee_client`:

   | Loại | Khi nào |
   |---|---|
   | `AUTH_EXPIRED` | 401; hoặc `user/status` từ chối phiên |
   | `ACCESS_DENIED` | 403 không kèm dấu hiệu đăng nhập |
   | `CHALLENGE` | trang xác minh / CAPTCHA |
   | `RATE_LIMITED` | 429 |
   | `NETWORK_TIMEOUT`, `NETWORK_ERROR` | lỗi mạng |
   | `TRANSIENT_SERVER_ERROR` | 5xx |
   | `PARSE_ERROR` | cấu trúc trả về lạ |
   | `UNKNOWN_ERROR` | còn lại |

   - Chỉ `AUTH_EXPIRED` mới đánh dấu cookie hết hạn.
   - Ba loại phiên (`AUTH_EXPIRED` / `ACCESS_DENIED` / `CHALLENGE`) đưa lịch sang `NEEDS_AUTH`: dừng tự đồng bộ cho tới khi admin kết nối lại cookie hoặc đồng bộ tay thành công. Bot không tự đăng nhập hay vượt bước xác minh.
   - Lỗi tạm ở một trang: thử lại 2 lần trong lượt (2 giây, 5 giây).
7. **Không kết luận "hết đơn" khi dữ liệu bất thường.** Lượt ghi `partial` (không phải `success`) khi:
   - một trang lỗi;
   - thiếu `data` hoặc thiếu khoá danh sách;
   - Shopee lặp lại trang;
   - chạm `MAX_PAGES` khi trang vẫn đầy.

   Không xoá đơn vắng mặt khỏi kết quả. Chỉ lượt đủ dữ liệu mới cập nhật "kỳ thành công gần nhất".
8. **Sự cố** (`shopee_sync_incidents`, tối đa một sự cố mở):
   - mở ngay khi có lỗi phiên hoặc dữ liệu đổi định dạng; mở khi số lỗi liên tiếp tới ngưỡng;
   - báo admin một lần khi mở, nhắc lại tối đa mỗi 24 giờ, báo khi phục hồi;
   - lượt tự động thành công không nhắn admin.
9. **Thông báo khách không đổi.** Sự kiện vẫn sinh trong `record_conversion_snapshot` (ADR-056). Khoá chống trùng theo sự kiện nghiệp vụ, không theo lượt, nên một đơn được cả thủ công lẫn tự động xử lý chỉ có một tin. Mốc kích hoạt PLAN-079 không bị đụng tới.

## Hệ quả
- Telegram trả lời khách ngay cả khi Shopee chậm.
- Gate A không gọi Shopee theo lịch (cờ tắt). Đồng bộ tay vẫn chạy, nhưng qua luồng nền nên tin kết quả có thể đến chậm tới một vòng long-poll (≤ 30 giây).
- Khung quét giữ 30 ngày theo giờ mua (như trước). Đơn còn chờ xác minh mà mua quá 30 ngày thì không được cập nhật nữa; mở rộng khung cần quyết định riêng.
