# PLAN-086: Đếm hàng chờ trước khi hỏi suất Buffer

- Executor: Claude Code (Owner duyệt 2026-10-25, "có vá luôn đi em")
- Status: Done, chờ quan sát log thật

## Bối cảnh

Log `[Buffer][req]` (PLAN-072) cho thấy hôm 24/10 key `f8pL...Y1DI` gửi 75 request nền mà chỉ có 8 CreatePost (current-status phiên (bu)).

- Nguyên nhân: `queue_job.schedule_reup` gọi `_quota_block` (GetOrganizations + Limits, 2–3 request) trước khi đếm hàng chờ trong DB.
- Kênh đã 10/10 bài thì vòng Maintenance nào (5 phút một lần) cũng mất 2 request, rồi mới trả "đã kín".
- Mức giữ 70% chặn được 429, nhưng phần suất nền bị dùng hết, nên `post_statuses` không chạy được.

## Scope

1. `app/features/buffer/queue_job.py` `schedule_reup`: đưa phần đếm `future_count >= 10` lên trước `_quota_block`. Logic và câu báo giữ nguyên.
2. Test trong `tests/test_buffer_queue.py`: kênh đã 10 bài thì không gọi `_quota_block`.

## Không làm

- Không đổi đường sửa lịch bài cũ (`_apply_reschedule`). Đường này vẫn chạy trước, không hỏi suất.
- Không đổi mức giữ, nhịp quét, `schedule_block_reason`.

## Rollback

Revert commit.

## Definition of Done

- Kênh có 10 bài DONE trong tương lai → `schedule_reup` trả "đã kín", `_quota_block` gọi 0 lần.
- Kênh còn chỗ → `_quota_block` vẫn gọi đúng 1 lần như cũ.
- Hồi quy Buffer pass.

## Proof

2026-10-25, Claude Code:

- Test mới `test_buffer_queue.py::test_queue_full_skips_quota_request`: kênh 10 bài → "đã kín (10/10 bài)", `_quota_block` gọi 0 lần. Trên code cũ (`git stash`) test này fail.
- `test_lan_hai_sua_dung_bai_khong_them_job` (kênh còn chỗ, `_quota_block` đúng 1 lần) vẫn pass.
- Hồi quy `test_buffer*.py` + `test_telegram_schedule.py` + `test_challenger_m1_2_concurrency.py` + `test_storage_cleanup.py`: 493 passed, 12 failed. Cả 12 lỗi có từ trước:
  - 11 test cluster/concurrency đọc DB thật (xem PLAN-068).
  - `test_edit_post_gui_kem_gio_va_chu`: fake `execute` thiếu tham số `purpose`. Fail cả trên code cũ.
- Restart Maintenance 11:11Z: vòng đầu báo 3 kênh "đã kín (10/10 bài)" mà không có dòng `Limits`. Mỗi key chỉ gửi 1 GetOrganizations (làm mới kênh).
- **Phát hiện thêm:** 17 test trong `test_buffer_cluster.py` và `test_challenger_m1_2_concurrency.py` gọi thẳng `api.buffer.com` bằng key thật trong `.env`.
  - Lần hồi quy 11:03–11:10Z làm mất 57 suất (key `f8pL`), 43 suất (`RZX2`) và 58 suất (`ZVsP`) trong 30 ngày. Cùng lúc đó PM2 không ghi dòng `[Buffer][req]` nào.
  - Chạy lại có plugin chặn socket (`-p block_buffer_net`) thì thấy 17 test cố kết nối ra ngoài, không tốn suất.
  - Đây gần như chắc là phần "suất mất không rõ" hôm 23/10.
  - KHÔNG chạy 2 file này khi chưa chặn mạng. Cần PLAN riêng để chặn mạng trong test (conftest).
