# PLAN-160 — Đếm «sẵn sàng» không tính video đã hẹn + chừa 15 phút khi đếm hàng chờ Buffer

- Executor: Claude Code · Duyệt: chủ bot (07/11: «xử lý lỗi logic và bật lên quét thêm video đi em»)
- Nguồn: báo cáo buffer-chk4 (current-status.md, 07/11)

## Vấn đề
1. PLAN-071 `SourceService._ready_by_page` đếm mọi material READY. Video đã hẹn Buffer vẫn READY (sync «đã đăng» tắt do
   mức giữ 70%) → Sống Nhẹ «45 sẵn sàng» trong khi 45/45 đã có job Buffer DONE → nguồn `nunhanthongtue` bỏ quét mãi.
2. `queue_job.schedule_reup` đếm hàng chờ bằng `schedule_ts > now`. Bài vừa tới giờ hẹn được coi là đã ra khỏi hàng chờ,
   Buffer cần vài phút mới đăng → CreatePost bị «Scheduled posts limit reached 10/10» (5 lần 03–07/11, mỗi lần mất 1 request).

## Scope (2 file code + 2 file test)
- `app/features/viral_intake/sources.py`: `_ready_by_page` bỏ material có job `buffer` DONE cùng `target_page`.
- `app/features/buffer/queue_job.py`: đếm hàng chờ với `schedule_ts > now - QUEUE_GRACE_SEC` (900 giây).
- Test: `tests/test_viral_sources.py`, `tests/test_buffer_queue.py` (chặn mạng, không gọi Buffer thật).

## Không làm
- Không sửa sync «đã đăng», mức giữ 70%, cluster_router, dữ liệu DB.

## Proof (07/11)
- pytest (không chặn mạng; chỉ chạy file dùng adapter / yt-dlp giả, bỏ 2 file gọi Buffer thật): test_buffer_queue + test_viral_sources + test_buffer_slots +
  test_source_fanout 89 passed; test_buffer_{adversarial_m1,api,cooldown_store,first_comment,manager,media,
  rate_limit_guard,sync_posted} + test_viral_sources_page 259 passed. ruff sạch.
- Test mới: `test_ready_count_ignores_videos_already_scheduled_on_buffer`, `test_post_just_due_still_counts_in_queue`.
- DB thật (chỉ đọc): `_ready_by_page` cũ {9cde9a: 45, 2b6865: 15, 66d584: 2, 9cde9b: 40} → mới {9cde9b: 15}.
- Chủ bot yêu cầu bật quét: bật lại nguồn 3 (nhung_1410tn), 6 (hoalexx2), 7 (FB reels trnvp89), quét tay 1 lượt:
  #5 nunhanthongtue 0 mới / 68 đã có · #6 hoalexx2 11 mới · #7 0 mới / 3 · #3 nhung_1410tn 22 mới.
- Còn: `pm2 restart Maintenance` để code mới chạy (chủ bot chạy).
