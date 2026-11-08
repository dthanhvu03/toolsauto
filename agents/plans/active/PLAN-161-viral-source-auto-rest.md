# PLAN-161 — Nguồn video tự nghỉ khi cạn, tự quét lại, báo Telegram

- Executor: Claude Code · Duyệt: chủ bot (07/11: «thêm logic và nghiệp vụ tự động bật và tự động tắt … không phải làm thủ công nữa»)
- Nối tiếp PLAN-160.

## Nghiệp vụ
Công tắc `enabled` vẫn là quyền của chủ bot (tắt tay = không bao giờ quét, ví dụ nguồn nội dung xấu). Với nguồn đang bật, bot tự lo:

1. **Theo kho (đã có, PLAN-071 + PLAN-160):** mọi kênh đích còn ≥ `viral.source_skip_ready_per_page` (15) video chưa hẹn
   → nguồn nghỉ; dưới mức → quét lại theo nhịp `viral.source_scan_interval_min`.
2. **Nguồn cạn (mới):** 3 lần quét thành công liền nhau không ra video mới → nghỉ 24 giờ rồi tự thử lại. Vẫn cạn thì nghỉ tiếp
   24 giờ (không báo lại). Quét lỗi (yt-dlp, rate limit) không tính là cạn.
   - Lần đầu cạn: Telegram «🔕 Nguồn @X hết video mới — tự nghỉ, 24 giờ thử lại» + số video chưa hẹn của từng kênh đích.
   - Có lại video sau khi đã báo cạn: Telegram «🔔 Nguồn @X có lại N video mới», xoá trạng thái nghỉ.
3. Quét tay (`only_due=False`, nút trên web) vẫn quét nguồn đang nghỉ và cập nhật trạng thái.

Trạng thái lưu ở `storage/db/config/viral_source_rest.json` theo id nguồn (không migration).

## Scope
- `app/config.py`: hằng `VIRAL_SOURCE_REST_FILE`.
- `app/features/viral_intake/sources.py`: đọc/ghi trạng thái, bỏ qua nguồn đang nghỉ trong `scan_all`, gửi tin.
- `tests/test_viral_sources.py`: test nghiệp vụ (giả yt-dlp, giả notifier).

## Không làm
- Không đổi cột `enabled`, không đổi UI, không đụng Buffer.

## Proof (07/11)
- Thêm ngoài scope ban đầu: `tests/conftest.py` fixture autouse đưa `VIRAL_SOURCE_REST_FILE` vào tmp (test cũ gọi `scan_all`
  không được ghi file thật). Kết quả `scan_all` có thêm khoá `resting` → sửa 1 assert so dict cũ.
- Test mới: `test_empty_source_rests_after_three_scans_then_retries`, `test_scan_errors_do_not_count_as_empty`,
  `test_found_resets_empty_streak` (giả yt-dlp, giả `_notify`, giả đồng hồ).
- pytest test_viral_sources{,_ui,_page} + test_source_fanout + test_buffer_{queue,adversarial_m1,api,manager,media,
  sync_posted,slots}: 327 passed (không gồm 2 file gọi Buffer thật). ruff sạch.
- lint-imports: 2 hợp đồng BROKEN giống hệt HEAD (worktree tạm), không chuỗi nào qua sources.py.
- Maintenance có đăng ký TelegramNotifier (log «Registered notifier») → tin 🔕/🔔 gửi được.
- Còn: `pm2 restart Maintenance`.

## Sau code review (07/11)
- Sửa: đọc-sửa-ghi trạng thái dưới `fcntl.flock` (`viral_source_rest.lock`) từng nguồn, không giữ bản cũ cả vòng
  (Maintenance + quét tay trên web không ghi đè nhau); mục trạng thái mang `url`, nguồn đổi URL / id dùng lại thì bỏ qua;
  lỗi ghi trạng thái bọc try/rollback, không dừng các nguồn còn lại.
- Không sửa: gọi `queue_job.channel_name` (luật import cấm feature gọi nhau); chuyển trạng thái sang cột ViralSource (cần
  migration — ngoài vai trò Claude Code); `_broadcast` riêng tư (processor.py đã dùng y vậy).
- Ghi nhận (có từ PLAN-071): `_ready_by_page` chỉ đếm `target_page` đầu, nguồn nhiều kênh đích đếm kênh phụ = 0. DB thật
  hiện mọi nguồn chỉ 1 kênh đích nên chưa ảnh hưởng.
- Test thêm: `test_rest_state_ignored_when_source_url_changed`, `test_rest_bookkeeping_error_does_not_stop_other_sources`.
  pytest test_viral_sources{,_ui,_page} + test_source_fanout + test_buffer_queue: 122 passed; ruff sạch.
