# 🏗️ Đánh Giá Kiến Trúc Tổng Thể & Nợ Kỹ Thuật: ToolsAuto

**Ngày đánh giá:** 2026-04-27
**Người đánh giá:** Antigravity (Agentic AI)

---

## Phần 1: Đánh Giá Tổng Quan Các Tầng (Layers)

**Mô hình hiện tại:** Monolithic kết hợp Micro-workers.
- **Lõi điều khiển (Control Plane):** FastAPI (Backend) + Jinja2/HTMX (Frontend).
- **Hệ thống thực thi (Workers):** Tách rời các tiến trình chạy ngầm qua PM2 (FB_Publisher, Threads_NewsWorker, AI_Generator).
- **Trình duyệt tự động:** Playwright kết nối với Xvfb/VNC trên Linux VPS.
- **Cơ sở dữ liệu:** SQLite / PostgreSQL dùng SQLAlchemy ORM.

### 1. Backend (FastAPI + Workers)
- **Điểm sáng:** Thiết kế Modular cực kỳ tốt (`routers/`, `services/`, `adapters/`). Việc sử dụng **Generic Adapter** (đọc step từ Database thay vì hardcode) là một bước ngoặt, biến dự án thành nền tảng No-code Automation. Cơ chế Graceful Shutdown và Suicide Timer cho các browser worker rất chuyên nghiệp.
- **Điểm yếu:** Còn phụ thuộc vào time.sleep() ở một số luồng legacy thay vì DOM Mutability wait của Playwright. Giao tiếp giữa các worker thông qua Database dẫn đến nguy cơ Lock DB khi scale lớn.

### 2. Frontend (HTMX + Tailwind + Jinja2)
- **Điểm sáng:** Sự kết hợp hoàn hảo cho dự án Solo-Dev. Không cần viết API JSON, không cần quản lý State phức tạp bằng React/Vue nhưng vẫn đạt được độ mượt mà của SPA (Single Page Application).
- **Điểm yếu:** Đôi khi xảy ra lỗi Race Condition giữa Javascript thuần và HTMX (ví dụ sự kiện `load` bị lỡ nhịp). Việc quản lý Asset (CSS/JS) vẫn còn viết inline nhiều thay vì tách ra thư mục `static/`.

### 3. Database (SQLAlchemy)
- **Điểm sáng:** Việc chia nhỏ models (Domain-driven) và việc đưa Runtime Settings (Config nóng) lên DB là quyết định rất chính xác.
- **Điểm yếu:** Các bảng `job_events` và `incident_logs` thiếu cơ chế Data Retention (tự động dọn rác sau 30 ngày), dễ làm phình to ổ cứng VPS.

### 4. DevOps (PM2 + Github Actions)
- **Điểm sáng:** Dùng PM2 để quản lý Python process là một "Hacking" rất thông minh. Luồng CI/CD (`deploy.yml`) đã được thiết lập rất chặt chẽ.
- **Điểm yếu:** Thói quen thỉnh thoảng tự gõ lệnh `git pull` tay trên VPS phá vỡ luồng tự động của CI/CD (không chạy DB Migration), gây lỗi sập ngầm.

---

## Phần 2: 5 Vi Phạm Tiêu Chuẩn Code Thế Giới (Technical Debts)

Dưới góc nhìn của **SOLID Principles**, **Clean Architecture**, và **DRY**, dưới đây là 5 "Món nợ kỹ thuật" cần lên kế hoạch cấu trúc lại (Refactor) ở các Phase tiếp theo để hệ thống đạt chuẩn Enterprise:

### 1. Vi phạm nguyên tắc OCP (Open-Closed Principle)
- **Vị trí:** `app/adapters/dispatcher.py` (hàm `_inject_cta`)
- **Vấn đề:** Đang tồn tại mã cứng `if platform == "facebook": ...`. Theo chuẩn thiết kế, khi thêm nền tảng mới (Tiktok, Threads), không được phép chui vào file dispatcher để viết thêm lệnh `if... else`.
- **Khắc phục:** Dùng đa hình (Polymorphism) hoặc đẩy toàn bộ Logic Fallback CTA xuống Database.

### 2. Mô hình God Object (Anti-pattern phân quyền)
- **Vị trí:** `app/adapters/facebook/adapter.py`
- **Vấn đề:** Class `FacebookAdapter` cũ (trước Generic Adapter) đang ôm đồm quá nhiều việc (Đăng Reel, đăng Page, xử lý Business Suite, xử lý Checkpoint...). Vi phạm nguyên tắc **Single Responsibility**.
- **Khắc phục:** Tách nhỏ thành các Strategy chuyên biệt hoặc chuyển hoàn toàn 100% về `GenericAdapter` (No-code).

### 3. Database Polling (Anti-pattern giao tiếp)
- **Vị trí:** `app/workers/publisher.py`
- **Vấn đề:** Các bot dùng vòng lặp `while True: sleep(10)` để liên tục query Database tìm việc mới. Khi Scale lên hàng chục bot, DB sẽ quá tải (CPU Spikes).
- **Khắc phục:** Cần chuyển sang kiến trúc **Event-Driven / Message Queue** (Redis, RabbitMQ) để chủ động Push Job cho worker thay vì để worker Pull liên tục.

### 4. Magic Strings rải rác
- **Vị trí:** Xuyên suốt dự án.
- **Vấn đề:** Chuỗi ký tự như `"facebook"`, `"POST"`, `"DONE"` được gõ thẳng vào code. Nguy cơ lỗi chính tả làm gãy logic ngầm mà IDE không cảnh báo được.
- **Khắc phục:** Định nghĩa tất cả thành `Enum` (ví dụ: `Platform.FACEBOOK`, `JobStatus.DONE`).

### 5. Vi phạm DRY (Don't Repeat Yourself) ở luồng Bắt Lỗi
- **Vị trí:** Các file Playwright Adapters.
- **Vấn đề:** Luồng Try/Catch bắt lỗi Playwright Timeout, chụp màn hình, log lỗi... bị lặp lại ở quá nhiều hàm.
- **Khắc phục:** Tạo các **Python Decorators** (VD: `@playwright_safe_action`) bọc quanh các hàm thao tác UI để tái sử dụng logic bắt lỗi 1 lần duy nhất.

---

## 🎯 Kết luận
Đây không phải là "Code rác mỳ ý". Dự án hiện tại là một nền móng (Foundation) rất thực dụng và mạnh mẽ. Những điểm vi phạm trên là **Sự đánh đổi (Trade-off) có chủ ý** ở Phase 1 để ra mắt sản phẩm nhanh. 
Mục tiêu tiếp theo là mở một **"Refactoring Sprint"** để giải quyết triệt để 5 vấn đề này, biến dự án thành một hệ thống SaaS Automation hoàn hảo không tì vết.
