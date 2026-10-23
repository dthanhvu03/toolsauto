# PLAN-061: Buffer cooldown ghi ra file, không tự kéo dài khóa 429

- Executor: Claude Code (Owner giao trực tiếp 2026-10-23, tiền lệ ADR-010 / PLAN-060 P1)
- Status: Code xong, chờ chạy thật (bật Maintenance + Web, xem log 24 giờ)

## Bối cảnh

Kiểm tra 2026-10-23 (current-status phiên (c)):

- Giờ khóa 429 chỉ nằm trong RAM (`_KEY_GUARD` ở `client.py`). Tắt hoặc restart process là quên khóa, request đầu tiên đi thẳng tới Buffer.
- Maintenance và Web_Dashboard là hai process, mỗi bên một guard. Bên này dính 429, bên kia không biết.
- Trần nội bộ 18 giờ. Buffer từng trả Retry-After 80717s (22,4 giờ) và 142824s (39,7 giờ). Tool gọi lại lúc 18 giờ, khi Buffer vẫn đang khóa.
- `POST /api/buffer/ping-key` (`cluster_router.py`) gọi thẳng `requests.post`, không xem guard, không ghi 429 vào guard.

## Scope

1. File mới `app/features/buffer/cooldown_store.py`: đọc/ghi `storage/db/config/buffer_cooldown.json`. Khóa theo sha256 của key (16 ký tự đầu), không ghi key. Ghi atomic (tmp + `os.replace`), khóa file `fcntl` khi đọc-sửa-ghi. Mục hết hạn tự dọn khi ghi.
2. `client.py`: guard đọc file mỗi lần xem cooldown (cache theo mtime). `mark_rate_limited` ghi file. Trần 18 giờ → 72 giờ.
3. `cluster_router.py` ping-key: key đang cooldown thì trả `COOLDOWN`, không gửi request. Nhận 429 thì ghi vào guard chung (`mark_rate_limited`).
4. `tests/conftest.py`: autouse trỏ file cooldown sang `tmp_path`, test không đụng file thật.

## Không làm

- Không thêm request "đọc thử" riêng trước khi đăng. Request đầu tiên sau giờ khóa chính là lần thử: 429 thì ghi mốc mới, vòng quét dừng (`sweep_unscheduled_ready` đã `break`), job FAILED được vòng sau xếp lại như hiện nay.
- Không đổi đường chọn key, nhịp 5 phút, mức giữ 70% suất, xử lý job FAILED.
- Không thêm key, không đổi gói Buffer.

## Rollback

Revert commit. Xóa `storage/db/config/buffer_cooldown.json` là quên mọi khóa (về hành vi cũ, trừ trần 72 giờ).

## Definition of Done

- Ghi 429 ở client A, client B mới tạo (giả lập process khác) thấy cooldown, không gửi request.
- Xóa `_KEY_GUARD` (giả lập restart) vẫn thấy cooldown từ file.
- Retry-After 142824 → khóa 142824s; Retry-After 400000 → khóa 259200s.
- ping-key với key đang cooldown: không gọi `requests.post`. ping-key nhận 429: client thấy cooldown.
- File không chứa key thật.
- pytest các file `tests/test_buffer_*.py` + cluster/challenger pass.

## Proof

2026-10-23, Claude Code:

- `tests/test_buffer_cooldown_store.py` 8 passed: restart vẫn thấy khóa và không gửi request; process khác ghi thì thấy; file không có key; giữ mốc xa hơn + dọn mục hết hạn; hết giờ thì đi đúng 1 request; file hỏng bị bỏ qua; ping-key đang khóa không gọi `requests.post`; ping-key nhận 429 thì client thấy khóa.
- `tests/test_buffer_rate_limit_guard.py` 10 passed (thay test trần 18 giờ bằng: giữ 142824s, trần 72 giờ với 400000s).
- Hồi quy: adversarial 148, api 16, cluster_challenger 22, fuzz_probes 102, first_comment 23, manager 7, media 7, queue 8, slots 9, sync_posted 11, e2e_cluster 186, challenger_m1_r3_1 57: passed hết.
- Fail có sẵn trên code gốc (đã chạy `git stash` để so): `test_buffer_cluster.py` 3 (code gốc 4), `test_challenger_m1_2_concurrency.py` 3, `test_telegram_schedule.py` 1. Cùng tên test, cùng lỗi (gắn cứng ngày giờ, mock `execute` thiếu `purpose`). Không do PLAN này.
- Hai process Python riêng, file trong scratchpad, key giả: A nhận 429 `Retry-After: 142824` → ghi file; B khởi động sau, gọi `purpose="publish"` → chặn tại chỗ, `requests.post` 0 lần, còn 142823s. File chỉ có `bfd024f4e412cff3`, không có key.
- `ruff check` các file đã sửa: pass. `storage/db/config/buffer_cooldown.json` nằm trong `.gitignore` (`/storage/`).

Chưa làm: chạy thật với Buffer (PM2 vẫn tắt).
