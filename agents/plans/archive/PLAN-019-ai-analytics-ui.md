---
Status: Done (Archived)
Created: 2026-04-26
Archived: 2026-04-26
Context: PLAN-019-ai-analytics-ui.md
---

# PLAN-019: Xây dựng UI cho AI Log Analyzer (Observability Hub)

## 1. Mục tiêu
Tích hợp giao diện theo dõi các sự cố hệ thống (Incident Groups) và báo cáo AI vào màn hình System Logs (`/app/logs`), giúp người dùng không phụ thuộc 100% vào Telegram mà có thể phân tích và tương tác trực tiếp trên Dashboard.

*Đã hoàn tất trước (Pre-requisite):* Đã đổi worker `ai_reporter.py` sang dùng `9Router` (via `pipeline.generate_text`) thay cho GeminiAPIService độc lập.

## 2. Thiết kế giải pháp (Solution Design)

### 2.1. Cập nhật giao diện `app_logs.html`
- Thêm Tabs Navigation ở phần đầu của content (Sử dụng HTMX để load nội dung cho từng tab).
- Các Tabs bao gồm:
  1. **AI Analytics (Default):** Gọi HTMX tới `/app/logs/ai-analytics`
  2. **Domain Events:** Gọi tới logic Domain Events hiện tại.
  3. **PM2 Logs:** Giao diện Stream log thô hiện tại.

### 2.2. Xây dựng Fragment `ai_analytics_tab.html`
Tạo file UI fragment mới hiển thị:
- **Card 1: AI Health Report**: Giao diện hiển thị báo cáo. Cung cấp nút `[ Generate Live Report ]` gọi tới endpoint `/app/logs/ai-report/live` qua HTMX để chạy AI report ngay lập tức.
- **Card 2: Top Incidents Table**: Hiển thị query từ bảng `incident_groups` (Sắp xếp theo `occurrence_count` giảm dần).
  - Có các cột: *Error Signature, Platform, Count, Last Seen, Sample, Status*.
  - Ở cột Action, có nút **Acknowledge** (gọi POST qua HTMX) để đổi status từ `open` sang `acknowledged`.

### 2.3. Cập nhật Backend (`dashboard.py`)
Thêm các Router mới:
1. `GET /app/logs/ai-analytics`: Trả về view HTML cho Tab chứa danh sách `incident_groups` và ô chứa report.
2. `GET /app/logs/ai-report/live`: Sử dụng hàm `_build_prompt` và `pipeline.generate_text` để sinh Markdown báo cáo sức khỏe từ `incident_groups`, trả về UI.
3. `POST /app/logs/incident/{id}/ack`: API để cập nhật trạng thái `status = 'acknowledged'` cho nhóm lỗi.

---

## 3. Các bước thực hiện (Execution Steps)

1. **Bước 1: Backend Router & Logic**
   - Import `IncidentGroup` và `SessionLocal` vào `dashboard.py`.
   - Viết các hàm route `/app/logs/ai-analytics`, `/app/logs/ai-report/live`, và `/app/logs/incident/{signature}/ack`.
   
2. **Bước 2: UI Templates**
   - Chỉnh sửa `app/templates/pages/app_logs.html` để có Tabs UI. (Wrap lại phần PM2 streaming vào 1 div riêng).
   - Viết `app/templates/fragments/ai_analytics_tab.html`.

3. **Bước 3: Tích hợp Markdown Rendering (Frontend)**
   - Do AI report trả về Markdown, UI cần render bằng thư viện marked (nếu đã có trong template) hoặc parse thành HTML cơ bản (thực tế backend `pipeline.generate_text` trả về plain text/Markdown, ta có thể dùng filter hoặc thẻ `<pre>` hoặc parse qua Markdown module nếu server-side render).

---

## 4. Anti Sign-off Gate ⛔
**Checklist xác nhận trước khi qua Phase 6:**
- [x] UI `/app/logs` có Tabs rõ ràng, không phá vỡ tính năng PM2 / Domain Events cũ.
- [x] Tab AI Analytics hiển thị đúng bảng danh sách IncidentGroups.
- [x] Nút "Generate Live Report" gọi được 9Router (pipeline) và trả về text báo cáo trên UI.
- [x] Nút "Acknowledge" hoạt động tốt (đổi trạng thái lỗi và load lại dòng).
- [x] Log test chứng minh 9Router thay thế API trực tiếp trong worker/ai_reporter.py.

**Chữ ký Anti (Status):** [x] APPROVED / [ ] REJECTED
