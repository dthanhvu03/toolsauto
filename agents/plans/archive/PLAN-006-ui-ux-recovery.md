# PLAN-006: UI/UX Recovery After Overhaul

## Goal
Phục hồi giao diện Dashboard và sửa các lỗi hiển thị do thay đổi cấu trúc thư mục (storage) và gom nhóm config.

## Context
- **Đã xử lý một phần**:
  - Router dashboard đã render `pages/app_overview.html`.
  - Layout đã dùng đúng CSS `/static/app.css`.
- **Còn thiếu**:
  - Các fragment Viral chưa đồng bộ số cột sau khi thêm thumbnail column.
  - `thumbnail_url` trả `/thumbnails/...` nhưng chưa có static mount tương ứng trong `app/main.py`.
  - Hồ sơ agents (`current-status`, plan) chưa phản ánh đúng trạng thái triển khai thực tế.

## Scope
- Mount static thumbnails route trong `app/main.py`.
- Đồng bộ cấu trúc bảng Viral ở:
  - `app/templates/fragments/viral_row.html`
  - `app/templates/fragments/viral_table.html`
  - `app/templates/fragments/app_viral_table.html`
  - `app/routers/viral.py` (các row dùng `colspan`).
- Cập nhật checkpoint/handoff trong `agents/handoffs/current-status.md`.

## Out of Scope
- Thêm tính năng mới không liên quan đến UI cũ đã có.
- Refactor logic database (trừ khi cần thiết để lấy path assets).

## Proposed Approach
1. Mount `/thumbnails` -> `config.THUMB_DIR` bằng `StaticFiles`.
2. Đồng bộ header/cell/colspan trong toàn bộ bảng Viral để không lệch layout.
3. Verify nhanh bằng:
   - check route map (đảm bảo có `/thumbnails`),
   - check grep `colspan=\"6\"` không còn sót ở bảng Viral mới,
   - check compile Python cho file đã sửa.

## Risks
- Nếu mount static path sai thư mục, ảnh thumbnail vẫn 404.
- Nếu sót một fragment chưa đồng bộ cột, bảng sẽ lệch và khó thao tác.

## Validation Plan
- Kiểm tra route `/thumbnails` tồn tại trong danh sách route FastAPI.
- Kiểm tra `colspan` và số cột Viral đồng nhất sau patch.
- Chạy `python -m py_compile` cho các file Python bị sửa.

## Execution Notes (Current Session)
- ✅ Đã mount `/thumbnails` trong `app/main.py`.
- ✅ Đã thêm alias `/app/dashboard` trong `app/routers/dashboard.py`.
- ✅ Đã đồng bộ bảng Viral: `viral_table.html`, `app_viral_table.html`, `app/routers/viral.py`.
- ✅ Verify kỹ thuật pass:
  - `python -m py_compile app/main.py app/routers/dashboard.py app/routers/viral.py app/database/models.py`
  - Route map check trong venv: `/thumbnails=True`, `/app/dashboard=True`
  - FastAPI `TestClient` smoke check: `/app/dashboard=200`, `/static/app.css=200`, `/thumbnails/<sample_collage>.jpg=200`
  - Không còn `colspan=\"6\"` trong các file Viral đã sửa.
- ✅ Đã verify thủ công trên browser sau khi restart dịch vụ thành công: Dashboard map đúng route, UI Thumbnail chạy đúng, error path jobs đã sạch bóng. Handoff hoàn thành!

## Rollback Plan
- Sử dụng Git checkout để quay lại trạng thái trước khi sửa.

## Related
- Task: TASK-006
- Decision: (None yet)
