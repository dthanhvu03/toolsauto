# PLAN-162 — Vá an toàn luồng Buffer: dọn ổ đĩa, file đã đăng, bài thiếu video, job kẹt, đường 10/10

- Executor: Claude Code · Duyệt: chủ bot (07/11: «oke em fix và vá cho anh nhé em», sau buffer-review)
- Nguồn: current-status.md mục (buffer-review) 07/11, mục 1–5. Mục 6 (mức giữ suất 30 ngày) chờ chủ bot quyết hướng.

## Mục và cách vá
1. **Dọn ổ đĩa lỗi DB → xoá hết** (`app/features/maintenance/storage_cleanup_service.py`): 3 hàm lấy tập bảo vệ trả `None`
   khi lỗi; `prune_media` thấy `None` thì bỏ dọn video (bước 1–2), log WARNING. Mỗi file video xoá ghi 1 dòng INFO.
   Test `/donrac` (`tests/test_telegram_resource_cleanup_commands.py`) không được chạy dọn thật trên `storage/` → giả `run_all`.
2. **`da-dang` xoá vô điều kiện**: bước 1 bỏ qua file của material còn bài Buffer hẹn (cùng tập `buffer_material_ids`).
3. **Thiếu video → bài chỉ chữ** (`app/features/buffer/adapter.py`): job có `viral_material_id` mà không có link video công khai
   → lỗi fatal, không gửi Buffer (cả đường feed và story).
4. **Job kẹt RUNNING** (`app/features/buffer/queue_job.py`): job Buffer RUNNING quá 30 phút (theo `created_at`) → FAILED
   kèm lý do; `auto_schedule_ready` không còn trả True «Đang xếp lịch» (sweep không đếm và không dừng ở video đó).
5. **Đường 10/10 của `queue_reup`**: đặt FAILED (như đường 429) thay vì PENDING không ai chạy; câu báo không hứa tự thử lại.

## Không làm
- Mục 6–10 của review; không đổi schema; không gọi Buffer thật trong test.

## Proof (07/11)
- Test mới: test_prune_media_keeps_every_video_when_db_unreachable, test_da_dang_keeps_file_still_scheduled_on_buffer,
  test_*_db_error_returns_none (đổi từ «returns_empty» — hành vi cố ý đổi), test_bai_tu_video_ma_mat_file_thi_khong_goi_buffer,
  test_queue_full_on_buffer_marks_failed_not_pending, test_stuck_running_job_expires_and_does_not_block_sweep.
- Test sửa: test_telegram_resource_cleanup_commands giả `StorageCleanupService.run_all` (autouse);
  test_buffer_manager::test_buffer_adapter_routes_with_manager đặt `viral_material_id=None` (MagicMock tự sinh giá trị truthy).
- pytest 19 file (buffer_* trừ 2 file gọi API thật, storage_cleanup*, viral_sources, source_fanout, telegram_schedule,
  adversarial_m4/first_comment, story_pacing): 551 passed, 1 failed = test_telegram_schedule::test_edit_post_gui_kem_gio_va_chu
  (hỏng sẵn, đã ghi trong current-status; lỗi stub thiếu `purpose` ở client.py — file không đổi).
- ruff sạch mọi file đổi; lint-imports 2 BROKEN như HEAD.
- Còn: `pm2 restart Maintenance Web_Dashboard` (chủ bot).
