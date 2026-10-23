# PLAN-067: Buffer nhớ kênh từng key, hỏi trạng thái bài gộp theo key

- Executor: Claude Code (Owner giao trực tiếp 2026-10-23, nối PLAN-061)
- Status: Code xong, đang chạy thật (chưa commit)

## Bối cảnh

Bật lại Maintenance 19:17 ICT 23/10 (current-status phiên (p)):

- Key 2 còn 1617/3000, dưới ngưỡng giữ 2100 → `refresh_channels_map` bỏ quét kênh key 2. Kênh của key 2 không có trong bảng → đổ về key 1 (primary).
- `BufferManager.post_statuses` gom bài theo object client. `get_clients()` tạo `BufferClient` mới mỗi lần → mỗi bài một nhóm, một request. Vòng đầu: 7 request "Account is not allowed" + 5 "Post not found", đều trên key 1, lặp mỗi 15 phút.
- Bảng kênh chỉ nằm trong RAM, làm mới mỗi 5 phút: mỗi key tốn 2 request (organizations + channels) mỗi 5 phút dù kênh hầu như không đổi.

## Scope

1. `manager.py`:
   - Lưu danh sách kênh từng key ra `storage/db/config/buffer_channels.json` (khóa = sha256 rút gọn của key như PLAN-061, không ghi key).
   - Kênh đã lưu chưa quá 6 giờ thì dùng luôn, không gọi Buffer. Key đang khóa hoặc chạm mức giữ suất thì dùng bảng đã lưu dù cũ.
   - Key chưa từng có bảng mà chạm mức giữ suất: vẫn quét một lần (2 request). Đang cooldown thì không quét.
   - Kênh lạ: quét lại các key có bảng cũ hơn 30 phút, tối đa một lần mỗi 30 phút.
   - `post_statuses` gom bài theo `_key`, bỏ qua bài không gắn được key đang mở.
   - Còn key chưa có bảng kênh (khóa/lỗi) thì kênh lạ trả `None`, không đổ về key chính (thêm 19:39 sau khi thấy key 2, 3 khóa).
2. `client.py`: `organizations()` / `channels()` nhận `purpose`; thêm purpose `channel_bootstrap` không bị mức giữ suất chặn (chỉ dùng ở bước 1 khi key chưa có bảng).
3. `tests/conftest.py`: trỏ file kênh sang `tmp_path`. Test mới trong `tests/test_buffer_manager.py`.

## Không làm

- Không đổi `cluster_router` (dashboard tự quét kênh khi trang mở, có cache 5 phút riêng).
- Không đổi `get_client_for_post` nhánh hỏi từng key cho bài không có job trong DB.
- Không đổi nhịp 5 phút, nhịp sync 15 phút, mức giữ 70%.

## Rollback

Revert commit. Xóa `storage/db/config/buffer_channels.json` là quét lại từ đầu.

## Definition of Done

- 12 bài thuộc cùng một key → đúng 1 request `post_statuses`.
- Key bị mức giữ suất chặn, chưa có bảng → quét bootstrap một lần, lần sau đọc file, không gọi.
- Restart (manager mới) trong 6 giờ → không gọi organizations/channels.
- Key đang cooldown, có bảng cũ → kênh vẫn trỏ đúng key đó, không gọi.
- Chạy thật: log Maintenance hết dòng "không thấy trong danh sách quét" và "Account is not allowed" ở kênh đã biết.

## Proof

2026-10-23, Claude Code:

- `tests/test_buffer_manager.py` 15 passed (8 test mới: 14 bài cùng 2 key → 2 request; bootstrap một lần rồi đọc file; restart không gọi Buffer; file không có key; key cooldown dùng bảng cũ; key cooldown chưa có bảng không quét; kênh lạ quét lại tối đa mỗi 30 phút; kênh lạ không đổ về key chính khi còn key chưa có bảng).
- Hồi quy: adversarial 148, api 16, queue 8, sync_posted 11, rate_limit_guard 10, cooldown_store 8, cluster_challenger 22, fuzz_probes 102, first_comment 23, media 7, slots 9, challenger_m1_r3_1 57: passed. `test_e2e_buffer_cluster.py` 1 lần fail không lặp lại trong 7 lần chạy lại (186 passed). Fail có sẵn trên code gốc giữ nguyên (cluster 3, concurrency 3, telegram_schedule 1).
- Chạy thật 19:37–19:56: restart vẫn thấy 3 key khóa từ file (`Tam dung tu xep lich — moi key dang cooldown`), không request. Kênh key 2, 3 log "chưa biết thuộc key nào … bỏ qua" thay vì đổ về key 1.
- Phát hiện từ tài liệu Buffer (developers.buffer.com/guides/api-limits.html): giới hạn theo từng key, Free = 100/15 phút, **250/24 giờ**, 3000/30 ngày; 429 không tính suất, không kéo dài khóa. `x-ratelimit-limit 3000` tool đang đọc là cửa sổ 30 ngày, không phải ngày.
- Owner thay key 1 bằng key mới `f8pL...Y1DI` (tổ chức mới, Uyển Nhi `6adb578c…9cde9b`, Sống Nhẹ `6adb578c…9cde9a`). Owner duyệt đổi dữ liệu: `BUFFER_CHANNELS` đổi 2 mã; 48 material READY/NEW đổi `target_page`; job 1110, 1111 (hẹn ở tài khoản cũ đã gỡ) → FAILED. Backup `data/backups/buffer-channel-move-20261023T125358Z.json`. 19:56 job 1113 → "Đã hẹn Sống Nhẹ Tuổi 40 lúc 20:30 23/10" qua key mới.

Chưa làm: đọc đúng cửa sổ 24 giờ từ header `RateLimit`; giãn sync trạng thái 15 → 60 phút (đề xuất, chờ Owner).
