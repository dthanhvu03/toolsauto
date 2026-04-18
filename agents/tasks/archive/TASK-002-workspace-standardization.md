# TASK-002: Quy chuẩn hóa & Dọn dẹp Workspace

## Mục tiêu
Thiết lập lại cấu trúc thư mục Chuẩn (Canonical Structure) cho ToolsAuto và dọn dẹp các thư mục/file "vô tội vạ" do Agent cũ để lại.

## Trình thực thi (Performer)
- [x] @Antigravity

## Trạng thái
- `[/]` In Progress

## Checklist
- `[/]` Kiểm kê và Phân loại (Audit & Categorize)
    - `[x]` Xác định danh sách thư mục Chuẩn (app, agents, data, workers, frontend, docs, logs, maintenance).
    - `[x]` Xác định danh sách "rác" (checks, debug_steps, scratch, mcp, test.js, root logs).
- `[ ]` Thực thi dọn dẹp (Lưu trữ)
    - `[ ]` Di chuyển script kỹ thuật cũ vào `maintenance/archive/`.
    - `[ ]` Di chuyển tài liệu cũ vào `docs/archive/`.
    - `[ ]` Xóa các file log tạm ở thư mục gốc.
- `[ ]` Hồ sơ hóa (Standardization)
    - `[ ]` Cập nhật `agents/README.md` với mô tả cấu trúc chuẩn.
- `[ ]` Nghiệm thu & Lưu trữ Task
    - `[ ]` Verify thư mục root đã sạch.
    - `[ ]` Di chuyển Task này vào `tasks/archive/`.

## Ghi chú
- Source of Truth: `/home/vu/toolsauto`.
- Không xóa script, chỉ di chuyển vào kho lưu trữ để an toàn. (Trừ log).
