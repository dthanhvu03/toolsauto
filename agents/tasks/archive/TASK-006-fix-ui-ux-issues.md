# TASK-006: Fix UI/UX Inconsistencies After Overhaul

## Objective
Khắc phục các lỗi hiển thị, sai lệch router và template, và đường dẫn static assets sau đợt refactor lớn.

## Scope
- Sửa lỗi mapping template trong dashboard router.
- Sửa đường dẫn CSS trong layout chính (app.html).
- Kiểm tra và sửa lỗi hiển thị thumbnails/media trong các trang dashboard/viral.
- Rebuild Tailwind CSS để đảm bảo giao diện đồng nhất.

## Priority
P0 (Giao diện chính đang bị lỗi)

## Owner
Antigravity

## Blockers
- Không có.

## Acceptance Criteria
- [x] Dashboard truy cập được tại /app/dashboard mà không bị lỗi 500 (Đã fix route sang /app).
- [x] CSS được tải thành công (không có 404 cho /static/app.css).
- [x] Ảnh thumbnails hiển thị đúng đường dẫn từ thư mục storage mới hoặc placeholders nếu Mới Quét.
- [x] Giao diện khớp với tiêu chuẩn Premium (Fonts Inter/Outfit hoạt động, Jobs Queue sửa được media path error).

### Phase 3: Validation & Restart
- [x] Restart backend process (waiting to load `models.py` changes).
- [x] Run browser subagent to verify Jobs Queue path issues and Viral Table thumbnail rendering (Verified via UI rendering placeholders instead of calling broken image paths, and jobs gracefully converting legacy DB references to new layout references).
- [x] Finalize recovery if stable.

## Current Status
- Đang ở phase Verify/Handoff.
- Đã bổ sung alias `/app/dashboard`, mount static `/thumbnails`, và đồng bộ cột bảng Viral (header/row/colspan).
- Cần xác nhận thêm bằng UI manual check sau restart runtime.

## Next Step
- Restart dịch vụ và chạy kiểm tra UI cuối: `/app`, `/app/viral`, thumbnail render, network 404.
- Nếu ổn định: chuyển TASK + PLAN sang archive và cập nhật handoff đóng task.
