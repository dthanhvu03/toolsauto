# ADR-005: Services Layer Reorganization

## Status
Active

## Context
Tầng `app/services/` hiện tại đang chứa khoảng 60 file phẳng (flat structure). Cấu trúc này làm mất đi ranh giới giữa các domain nghiệp vụ, gây khó khăn cho việc định hướng và bảo trì (navigation & maintenance). Việc tái cấu trúc là bắt buộc, tuy nhiên nếu di chuyển ~60 file này sẽ làm vỡ import của hơn 200+ caller files (routers, workers, etc.), tiềm ẩn rủi ro lỗi `ImportError` dây chuyền cực lớn.

## Decision
1. **Gộp nhóm theo Domain (Domain-Driven)**: Tái cấu trúc các file vật lý vào các thư mục theo context nghiệp vụ cụ thể: `ai/`, `telegram/`, `jobs/`, `content/`, `viral/`, `compliance/`, `dashboard/`, `platform/`, và `db/`.
2. **Re-export Pattern**: Khởi tạo file `app/services/__init__.py`. File này sẽ đóng vai trò re-export toàn bộ các class/function/variable từ vị trí mới ra ngoài với đúng namespace cũ. VD: `from app.services.ai.pipeline import *` sẽ được map lại thành `app.services.ai_pipeline`.

## Rationale
- **Tính đóng gói**: Gom nhóm theo domain giúp các file liên quan nằm cạnh nhau, dễ quản lý hơn hẳn việc để 60 file lộn xộn.
- **Zero-breakage**: Mẫu Re-export đảm bảo 0 (không) caller nào phải sửa code trong giai đoạn 1 của việc tái cấu trúc. Code cũ `from app.services.cleanup import ...` vẫn sẽ hoạt động như phép màu mà không nhận ra file đã bị move vào `app/services/jobs/cleanup.py`.

## Alternatives
- **Sửa import hàng loạt**: Di chuyển file và dùng regex thay thế toàn bộ import trên 200+ file. → *Bị loại (Rejected)* vì rủi ro vỡ logic cực cao, vi phạm nguyên tắc an toàn Minimal Diff.
- **Flat-but-prefixed**: Đổi tên file thành `domain_*.py` thay vì tạo thư mục. → *Bị loại (Rejected)* vì không giải quyết triệt để sự lộn xộn của số lượng file trong 1 cấp thư mục.

## Impact
- **Tích cực**: Cấu trúc module chuẩn Enterprise. An toàn tuyệt đối cho hệ thống đang chạy.
- **Tiêu cực**: `app/services/__init__.py` sẽ phải gánh (hardcode) toàn bộ đường dẫn cũ như một God-file tạm thời, cho đến khi các caller được migrate dần dần ở các sprint sau. Các cron/pm2 script cứng (hardcoded paths) có thể phải sửa tay.

## Related
- Plan: PLAN-028
- Task: TASK-028
