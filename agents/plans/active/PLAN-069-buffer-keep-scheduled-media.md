# PLAN-069: Dọn ổ đĩa không xóa video của bài đang hẹn trên Buffer

- Executor: Claude Code (Owner duyệt 2026-10-23 21:27 ICT, "Vá code + gia hạn file")
- Status: Code xong, đang chạy thật (chưa commit)

## Bối cảnh

20:30 23/10 Buffer tải `/buffer-media/1280/...mp4` (bài Sống Nhẹ, job 1113) và nhận 404 (log Web_Dashboard).

- `StorageCleanupService.prune_media` (Maintenance gọi 6 giờ/lần, và ngay khi Maintenance khởi động) xóa mọi file trong `reup/<platform>/` có mtime quá 7 ngày. Nó chỉ chừa file nằm trong `media_path` của job PENDING/RUNNING/….
- Job Buffer chuyển DONE ngay khi hẹn xong và không có `media_path`. Buffer lấy video theo `viral_material_id` qua `/buffer-media/<id>/<sig>.mp4`, và chỉ tải lúc tới giờ đăng.
- 20:10 23/10 (vòng đầu sau restart 20:07): xóa file của material 1280 (job 1113, 20:30 23/10) và 1300 (job 1118, 14:30 24/10), rồi đặt material thành FAILED "Đã dọn dẹp theo chính sách lưu trữ".
- Vòng 02:10 24/10 sẽ xóa thêm 1326, 1330, 1332, 1333, 1334 (bài 24–25/10). Vòng 20:10 24/10 xóa 1380–1388.

Đã làm tạm 21:28 ICT: `touch -m` 10 file reup của bài đang hẹn (1326, 1330, 1332, 1333, 1334, 1380, 1381, 1382, 1383, 1388), gia hạn thêm 7 ngày.

## Scope

1. `app/features/maintenance/storage_cleanup_service.py`:
   - Thêm `_get_buffer_scheduled_material_ids()`: `viral_material_id` của job `platform="buffer"` đã có `external_post_id`, status khác FAILED/CANCELLED, `schedule_ts` không cũ hơn 2 ngày.
   - `prune_media` bước 2 bỏ qua file `viral_<id>_…` có id nằm trong tập đó.
2. Test trong `tests/test_storage_cleanup.py`.

## Không làm

- Không đổi chu kỳ 6 giờ, hạn 7 ngày, bước `da-dang`, frames, thumbs.
- Không khôi phục file 1280, 1300 (đã mất). Job 1118 sẽ fail trên Buffer, material 1300 giữ FAILED.
- Không sửa test có sẵn đang đọc DB thật (`_get_active_job_media_paths`, `_update_material_failed_if_stale`). Ghi nhận riêng.

## Rollback

Revert commit.

## Definition of Done

- File `viral_<id>_…_reup.mp4` quá 7 ngày, id thuộc bài Buffer đang hẹn → không bị xóa, material không bị đặt FAILED.
- Id không thuộc bài đang hẹn → vẫn xóa như cũ.
- Lỗi đọc DB → trả tập rỗng, dọn như cũ (không ném).
- Hồi quy `tests/test_storage_cleanup*.py` pass.
- Chạy thật: restart Maintenance, vòng dọn đầu không làm mất file nào của bài đang hẹn.

## Proof

2026-10-23, Claude Code:

- `tests/test_storage_cleanup.py` thêm 4 test: file material 301 quá hạn mà 301 thuộc bài Buffer đang hẹn → giữ cả bản reup lẫn bản gốc, không gọi `_update_material_failed_if_stale`; id 30, 3010 không che nhầm `viral_301_…`; `SessionLocal` lỗi → tập rỗng; query trả `{1326, 1334}` với 4 điều kiện lọc.
- `tests/test_storage_cleanup.py`, `test_storage_cleanup_adversarial.py`, `test_hardware_resource_optimization.py`: 145 passed.
- DB thật (chỉ đọc): `_get_buffer_scheduled_material_ids()` trả 24 id, gồm đủ 14 bài đang hẹn từ 24/10 trở đi cộng bài đã đăng trong 2 ngày.
- Chạy thật 21:33 ICT: restart Maintenance và Web_Dashboard. Vòng dọn đầu ("Giai phong 0.33 MB | Videos: 1") không xóa file của bài nào đang hẹn. 18 bài hẹn từ 24/10 còn đủ file. Ngoại lệ là job 1118 (material 1300), file đã mất từ 20:10. Không material nào bị đặt FAILED trong 10 phút sau đó.
- Ghi nhận thêm: test có sẵn `test_prune_media_*` gọi `_get_active_job_media_paths` / `_update_material_failed_if_stale` thật, tức đọc và có thể ghi DB thật với id 301. Không sửa ở đây.
