# PLAN-004: Chiến lược Phá dỡ Hardcoded Paths (Technical Debt Cleanup)

## Trạng thái: Proposed
**Người lập**: @Antigravity
**Ngày**: 2026-04-18

## 1. Bối cảnh (Context)
Sau khi triển khai **PLAN-003 (Storage Standardization)**, chúng ta đã có một hệ thống quản lý đường dẫn tập trung tại `app/config.py`. Tuy nhiên, nếu trong code vẫn còn những chỗ gọi trực tiếp `"reup_videos"` hoặc `/home/vu/...` thay vì dùng biến config, hệ thống sẽ gặp lỗi khi chúng ta xóa thư mục cũ hoặc thay đổi môi trường.

## 2. Mục tiêu (Objectives)
- Rà soát 100% codebase (app/, workers/, scripts/).
- Thay thế mọi chuỗi ký tự đường dẫn cứng bằng biến từ `app.config`.
- Đảm bảo tính di động (Portability) của dự án.

## 3. Các bước thực hiện (Execution Strategy)

### Phase 1: Quét (Scan) - @Claude thực hiện
Sử dụng `grep` và `ripgrep` để tìm các pattern sau:
- `/home/vu/` (Đường dẫn tuyệt đối).
- `os.path.join` với các chuỗi `"profiles"`, `"data"`, `"thumbnails"`, `"content"`.
- `Path("...")` với các giá trị tương đương.

### Phase 2: Sửa đổi (Refactor) - @Codex thực hiện
- Chuyển đổi các lời gọi file sang `config.PROFILES_DIR`, `config.REUP_DIR`, v.v.
- Đặc biệt chú ý: `app/routers/insights.py` (đang gọi scripts bằng `os.path.join`).

### Phase 3: Kiểm soát chất lượng (QA) - @Antigravity
- Chuyển `STORAGE_LAYOUT_MODE=storage`.
- Chạy hệ thống và audit log. Nếu không còn lỗi `FileNotFoundError` liên quan đến đường dẫn cũ thì đạt yêu cầu.

## 4. Rủi ro & Giải pháp (Risks & Mitigations)
- **Rủi ro**: Sửa nhầm các chuỗi ký tự là UI text hoặc Settings Key (không phải đường dẫn).
- **Giải pháp**: @Claude sẽ audit từng dòng thay đổi trước khi @Codex commit.

## 5. Tiêu chí Nghiệm thu (Acceptance Criteria)
- Không còn kết quả nào khi quét chuỗi `"reup_videos"` trong code (ngoại trừ file config và các hằng số hợp lệ).
- Mọi thao tác file đều đi qua `app/config.py`.
