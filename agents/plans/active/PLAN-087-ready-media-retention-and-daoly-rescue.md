# PLAN-087: Giữ file video READY 21 ngày; lấy lại 42 video đạo lý cho Sống Nhẹ Tuổi 40

- Executor: Claude Code (Owner duyệt 2026-10-25, "triển khai cho anh hoàn tất em nhé")
- Status: Done

## Bối cảnh

Page Sống Nhẹ Tuổi 40 (`6adb578c…9cde9a`) có video đạo lý tốt nhất, 4,8K view (current-status phiên (bw)). Nguồn #5 `nunhanthongtue` có 50 video lấy hôm 16/10, chỉ 4 video được đăng.

- 24 video: bộ dọn dẹp xóa file sau 7 ngày (`prune_media`, mức 7 ngày cố định) rồi đặt FAILED. Lúc đó hàng chờ bị kẹt vì đổi kênh và 429.
- 18 video: pHash chặn nhầm là trùng (khoảng cách 6–8). Bước 1 đã hạ ngưỡng xuống 5.
- Lần quét sau bước 1 có thêm 18 video NEW. Cộng 42 video cũ là 60 video, page đăng 5 bài/ngày nên mất khoảng 12 ngày. Với mức 7 ngày, khoảng 25 video sẽ bị xóa trước khi kịp đăng.
- Ổ đĩa còn trống 909G. `storage/media` chiếm 3,1G.

## Scope

1. `storage_cleanup_service.py`: file `reup` của material READY được giữ tới `READY_RETENTION_DAYS = 21` ngày, thay vì 7. Quá 21 ngày thì dọn như cũ.
2. Test trong `tests/test_storage_cleanup.py`.
3. Dữ liệu, sửa qua ORM của app, backup trước:
   - 42 material nguồn #5 (FAILED vì bị dọn và DUPLICATE) về NEW, `process_tries=0`, xóa `last_error`.
   - Trang đích đổi thành `6adb578c…9cde9a`. 21 video còn trỏ kênh cũ `6ad724e7…d1f8`, kênh này đã gỡ.

## Không làm

- Không đổi mức 7 ngày cho file khác (raw, da-dang, frames) và cho các lời gọi `run_all(retention_days=7)`.
- Không đụng 4 material BOOST_PENDING (`kids0810`, `maymacenter`) và 4 material POSTED.

## Rollback

- Revert commit.
- Dữ liệu: khôi phục từ file backup JSON (status, target_page, target_pages, last_error, process_tries).

## Definition of Done

- READY 14 ngày tuổi → không xóa. READY 30 ngày tuổi → xóa. Không đọc được DB → không che file nào.
- 42 material về NEW, trỏ đúng page. Bộ xử lý Maintenance bắt đầu tải lại.

## Proof

(điền sau)
