# TASK-019: Xây dựng UI cho AI Log Analyzer (Observability Hub)

## 1. Context
Hệ thống hiện tại đã có cơ chế lưu trữ lỗi cấu trúc (`incident_logs`, `incident_groups`) và worker `ai_reporter.py` để gửi báo cáo qua Telegram. Tuy nhiên, người vận hành cần một giao diện trực quan trên Web Dashboard để chủ động theo dõi và xử lý các lỗi này.

## 2. Objective
Nâng cấp trang `/app/logs` thành một **Observability Hub** toàn diện bằng cách thêm một Tab mới "AI Analytics" (hoặc "AI Health Reports").

## 3. Acceptance Criteria
- [x] Giao diện `/app/logs` có tab điều hướng giữa: "AI Analytics" (Mới), "Domain Events", "PM2 Logs".
- [x] Tab "AI Analytics" chia làm 2 phần:
      - **Daily AI Report**: Lấy báo cáo AI live (sử dụng `9Router` thông qua `pipeline.generate_text`) với định dạng Markdown.
      - **Top Incidents**: Bảng hiển thị top lỗi từ `incident_groups` kèm nút "Acknowledge".
- [x] Có tính năng đánh dấu lỗi đã xem (Acknowledge) qua HTMX.
- [x] Chỉnh sửa `workers/ai_reporter.py` để dùng 9Router thay vì gọi trực tiếp API Gemini (đã hoàn thành trong lúc lập plan).

## 4. Status
**Done** — APPROVED by Antigravity at PLAN-019 Sign-off Gate, archived by Claude Code (Phase 7).

## 5. Status History
- **2026-04-26**: `Planned` - Task created by Antigravity.
- **2026-04-26**: `Done` - Claude Code execute Phase 2-3 (3 routes + 2 templates + tabs refactor), 8/8 HTMX integration check pass, Anti APPROVED tại Sign-off Gate, Claude Code Phase 7 handoff & archive.
