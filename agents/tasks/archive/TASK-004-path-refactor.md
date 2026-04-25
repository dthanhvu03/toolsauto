# TASK-004: Rà soát & Refactor đường dẫn (Path Hardcoding)

## Mục tiêu
Dọn dẹp triệt để "Nợ kỹ thuật" liên quan đến các đường dẫn (paths) được viết cứng trong mã nguồn. Đảm bảo toàn bộ hệ thống sử dụng `app/config.py` để tìm tài nguyên, tạo điều kiện cho việc chạy trên layout `storage/` mới.

## Trình thực thi (Performer)
- [x] **@Codex** (Lead - Refactor)
- [x] **@Claude** (Quality Control - Scan & Audit)
- [ ] **@Antigravity** (Orchestrator - Verification)

## Trạng thái
- `[ ]` In Progress (Phase 1 & 2 completed; awaiting Phase 3 verification)

## Checklist
- `[x]` **Phase 1: Quét toàn diện (Deep Scan)**
    - [x] Tìm kiếm các chuỗi `"reup_videos"`, `"profiles"`, `"thumbnails"`, `"data"`, `"content"`.
    - [x] Tìm kiếm các hàm `os.path.join` và `Path()` đang dùng chuỗi ký tự cứng.
    - [x] Tổng hợp danh sách các file cần sửa.
- `[x]` **Phase 2: Thực thi Refactor**
    - [x] Thay thế lệnh gọi trực tiếp bằng biến từ `app.config`.
    - [x] Xử lý đặc biệt cho `app/routers/insights.py`.
- `[ ]` **Phase 3: Kiểm chứng (Verification)**
    - [ ] Kiểm tra lỗi runtime với `STORAGE_LAYOUT_MODE=storage`.
    - [ ] Đảm bảo scripts trong `scripts/archive/` vẫn gọi được.

## Ghi chú
- Ưu tiên các file trong `app/services/` và `workers/`.
- Không sửa các chuỗi ký tự thuộc về UI (Label) hoặc Key của Settings nếu không liên quan đến đường dẫn tệp.
- Phase 2 đã refactor các file:
  - `app/routers/manual_job.py`
  - `app/services/video_protector.py`
  - `app/services/ai_pipeline.py`
  - `app/routers/syspanel.py`
  - `app/utils/logger.py`
  - `app/routers/insights.py`
  - `workers/maintenance.py`
- Verification kỹ thuật ban đầu: `python3 -m py_compile` pass cho toàn bộ 7 file.
