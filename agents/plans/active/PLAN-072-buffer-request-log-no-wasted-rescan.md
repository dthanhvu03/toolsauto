# PLAN-072: Log từng request Buffer theo key, bỏ quét lại kênh vô ích

- Executor: Claude Code (Owner duyệt 2026-10-23, "oke em làm đi em")
- Status: Code xong, chờ key mở lại để thấy log thật

## Bối cảnh

Key 1 mới (`f8pL...Y1DI`, tạo khoảng 19:50 23/10) hết 250 suất/ngày trước 22:00 rồi dính 429.

- Suất còn lại: 59/250 lúc 21:05, 50 lúc 21:33, 0 lúc khoảng 22:00. Trong 21:33–22:00 tool chỉ đăng 2 bài.
- Không có log từng request nên không biết suất đi đâu (current-status phiên (t)).
- Có một chỗ tốn đã rõ. Key 2, 3 khóa nên chưa có bảng kênh. Kênh của chúng (`6ad24d45…`, `6ab38f18…`, `6ad72561…`) là "kênh lạ", nên `get_client_for_channel` cứ 30 phút lại quét lại bảng kênh key 1 (organizations + channels). Trong khi đó kênh lạ gần như chắc thuộc key chưa có bảng.

## Scope

1. `client.py`: hàm `log_request(key, op, purpose, response)` ghi một dòng INFO cho mỗi request đã gửi.
   - Nội dung: key che (`f8pL...Y1DI`), số thứ tự trong ngày của process, tên thao tác GraphQL, purpose, HTTP status, các cửa sổ `RateLimit` còn lại.
   - `execute` gọi hàm này sau mỗi response.
2. `cluster_router._handle_ping_key`: gọi `log_request` sau ping. Ping không đi qua `execute`.
3. `manager.get_client_for_channel`: còn key chưa có bảng kênh thì không quét lại key khác vì kênh lạ. Key chưa có bảng mở lại vẫn được quét qua đường làm mới thường (5 phút, `refresh_channels_map`).
4. Test.

## Không làm

- Không đổi mức giữ 70%, TTL 6 giờ, nhịp 30 phút khi mọi key đã có bảng.
- Không ghi file đếm request. Log là đủ, grep được `[Buffer][req]`.

## Rollback

Revert commit.

## Definition of Done

- Mỗi request qua `execute`/ping có đúng 1 dòng `[Buffer][req]`, không chứa key thô.
- Key 2 chưa có bảng, kênh lạ, bảng key 1 cũ hơn 30 phút → không gọi `organizations` key 1.
- Mọi key có bảng → kênh lạ vẫn quét lại tối đa 30 phút/lần (test cũ).
- Hồi quy Buffer pass.

## Proof

2026-10-23, Claude Code:

- Test mới:
  - `test_buffer_manager.py`: key 2 chưa có bảng, kênh lạ, bảng key 1 quá 30 phút → `organizations` key 1 vẫn 1 lần. Trên code cũ test này fail.
  - `test_buffer_rate_limit_guard.py`: 2 request → 2 dòng `[Buffer][req]` (`#1 GetOrganizations purpose=background HTTP 200 | … 250-in-1day r=142`, `#2 account purpose=publish`), không có key thô. Request bị mức giữ chặn không ghi dòng nào.
- Hồi quy Buffer: 695 passed. `test_buffer_cluster.py` + `test_challenger_m1_2_concurrency.py`: 12 fail như trước (đọc DB thật, xem PLAN-068).
- Restart Maintenance + Web_Dashboard: vòng đầu không lỗi. Cả 3 key cooldown (`Tam dung tu xep lich … con 62327s`), không gửi request, không quét lại kênh.
- Chưa có dòng `[Buffer][req]` thật. Key 2, 3 mở lại khoảng 15:20 24/10, key 1 khoảng 20:00 24/10. Đếm bằng lệnh: `grep "\[Buffer\]\[req\]" ~/.pm2/logs/Maintenance-out.log ~/.pm2/logs/Web-Dashboard-out.log`.
