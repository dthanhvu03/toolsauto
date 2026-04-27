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
- **Vị trí cụ thể:** 
  - `app/adapters/dispatcher.py` -> Hàm `_inject_cta()` (Line 125-131): Hardcode logic `if platform == "facebook":`.
  - `app/adapters/dispatcher.py` -> Hàm `get_adapter()` (Line 40-42): Hardcode Dictionary `_DEDICATED_ADAPTERS = {"facebook": lambda: FacebookAdapter()}`.
- **Vấn đề:** Đang tồn tại mã cứng để rẽ nhánh logic cho Facebook. Theo chuẩn thiết kế, khi thêm nền tảng mới (Tiktok, Threads), không được phép chui vào file dispatcher để viết thêm lệnh `if... else` hay sửa Dictionary mặc định.
- **Khắc phục:** Dùng đa hình (Polymorphism) bằng Registry Pattern cho Adapter, và đẩy toàn bộ Logic Fallback CTA xuống Database.

### 2. Mô hình God Object (Anti-pattern phân quyền)
- **Vị trí cụ thể:** `app/adapters/facebook/adapter.py` -> Class `FacebookAdapter`.
- **Vấn đề:** Class này dài tới **2,373 dòng code** và chứa 44 phương thức khác nhau. Nó đang ôm đồm quá nhiều việc: Quản lý session (`open_session`), Đăng bài (`publish`), Lấy mã định danh (`_extract_page_id_from_current_page`), Chuyển đổi Profile (`_switch_to_personal_profile`), Bắt lỗi UI... Vi phạm nguyên tắc **Single Responsibility**.
- **Khắc phục:** Tách nhỏ thành các Strategy chuyên biệt theo miền (AuthStrategy, PublishStrategy, VerifyStrategy) hoặc chuyển hoàn toàn 100% về `GenericAdapter` (No-code).

### 3. Database Polling (Anti-pattern giao tiếp)
- **Vị trí cụ thể:** 
  - `workers/publisher.py` -> Vòng lặp `while RUNNING:` (Line 404). Gọi liên tục `QueueService.fetch_pending_jobs()` rồi `time.sleep()`.
  - `workers/threads_news_worker.py` -> Vòng lặp `while True:` (Line 38).
  - `workers/threads_auto_reply.py` -> Vòng lặp `while True:` (Line 139).
- **Vấn đề:** Các bot dùng vòng lặp vô tận với lệnh ngủ (Sleep) để liên tục query Database tìm việc mới. Khi Scale lên hàng chục bot, DB sẽ liên tục bị khóa (Lock) và quá tải (CPU Spikes).
- **Khắc phục:** Cần chuyển sang kiến trúc **Event-Driven / Message Queue** (Redis, RabbitMQ) để chủ động Push Job cho worker (theo mô hình Pub/Sub) thay vì để worker Pull liên tục.

### 4. Magic Strings rải rác
- **Vị trí cụ thể:** 
  - Khắp `app/routers/platform_config.py` (Ví dụ Line 380: Set tĩnh các action `"navigate", "click", "wait_visible"...`).
  - Khắp `workers/publisher.py` (Ví dụ Line 221: Ép kiểu `job_type = getattr(job, "job_type", "POST") or "POST"`).
- **Vấn đề:** Chuỗi ký tự như `"facebook"`, `"POST"`, `"DONE"` được gõ thẳng vào code. Nguy cơ gõ sai 1 chữ 's' làm gãy logic ngầm mà IDE không cảnh báo được.
- **Khắc phục:** Định nghĩa tất cả thành biến cục bộ hoặc các class `Enum` (ví dụ: `Platform.FACEBOOK`, `JobStatus.DONE`).

### 5. Vi phạm DRY (Don't Repeat Yourself) ở luồng Bắt Lỗi
- **Vị trí cụ thể:** 
  - `app/adapters/facebook/adapter.py`: Khối lệnh `try: ... except PlaywrightTimeoutError: ... except Exception:` bị sao chép lặp lại hơn **15 lần** giữa các hàm `publish`, `check_published_state`, `_click_locator`.
  - `app/adapters/generic/adapter.py`: Khối `try-except` bắt lỗi chung chung lặp lại 6 lần.
- **Vấn đề:** Luồng bắt lỗi Playwright Timeout, chụp màn hình, log lỗi... bị lặp lại ở quá nhiều hàm. Sửa 1 luồng bắt lỗi phải đi tìm 15 chỗ để sửa.
- **Khắc phục:** Tạo các **Python Decorators** (VD: `@playwright_safe_action(timeout=5000, take_screenshot=True)`) bọc quanh các hàm thao tác UI để tái sử dụng logic bắt lỗi 1 lần duy nhất ở file Helper.

---

## Phần 3: Phân Tích Chuyên Sâu Từng Tầng (Layers)

Dự án hiện tại tổ chức theo mô hình Kiến trúc Đa tầng (Layered Architecture). Tuy nhiên, ranh giới giữa các tầng đang bị mờ nhạt và vi phạm một số nguyên tắc cơ bản:

### 1. Thư mục `app/routers/` (Tầng Controller)
- **Nguyên tắc bị vi phạm:** Fat Controller (Controller béo phì).
- **Thực trạng:** Tầng Router ĐÁNG LẼ chỉ được phép làm 3 việc: Nhận Request $\rightarrow$ Validate $\rightarrow$ Trả Response. Nhưng hiện tại:
  - `routers/platform_config.py` (38KB): Gọi trực tiếp Terminal Server qua Bash subprocess (`subprocess.run(["tmux", ...])`).
  - `routers/compliance.py` (28KB): Chứa hàng tá câu truy vấn SQL thô `db.execute(text("SELECT..."))` trực tiếp bên trong các route (như `/categories`, `/ai-suggest-keywords`).
- **Hậu quả:** Khó viết Unit Test cho logic mà không giả lập được HTTP Request.

### 2. Thư mục `app/schemas/` (Tầng Validation / DTO)
- **Nguyên tắc bị vi phạm:** Separation of Concerns (Thiếu quy hoạch tập trung).
- **Thực trạng:** Thư mục này gần như bị bỏ hoang (chỉ có 1 file `log.py` 629 bytes). Toàn bộ các class Pydantic Models kiểm tra dữ liệu đầu vào (như `KeywordCreateBody`, `KeywordUpdateBody`) đang bị viết "chui" rải rác ngay bên trong các file Router (Ví dụ `routers/compliance.py` dòng 42).
- **Hậu quả:** Bất kỳ Service nào cần xài lại Schema này đều phải đi `import` ngược từ Router, gây ra lỗi Import Vòng Tròn (Circular Import).

### 3. Thư mục `app/services/` (Tầng Business Logic)
- **Nguyên tắc bị vi phạm:** Single Source of Truth và God Service.
- **Thực trạng:** 
  - Tồn tại song song 2 đường gọi AI: `ai_pipeline.py` (hệ thống 9Router mới) và `gemini_api.py` (gọi trực tiếp kiểu cũ).
  - File `content_orchestrator.py` (nặng 45KB) đóng vai trò God Service, ôm đồm từ tạo caption, dịch thuật, chèn hashtag, đến kiểm tra từ khóa... Thậm chí nó phải import chéo cả `gemini_api.py` làm phương án dự phòng (fallback) rất lồng cồng.
- **Hậu quả:** Sửa 1 luồng AI sẽ phải đi rà soát và sửa song song cả 2 đường ống.

### 4. Thư mục `app/adapters/` (Tầng Giao Tiếp External)
- **Nguyên tắc bị vi phạm:** Tight Coupling (Phụ thuộc cứng).
- **Thực trạng:** File `dispatcher.py` chịu trách nhiệm điều phối Adapter nhưng lại tự ý rẽ nhánh bằng mã cứng `if platform == "facebook":`. Theo chuẩn thiết kế, Dispatcher phải "mù", chỉ cần gọi `WorkflowRegistry` để lấy interface ra chạy mà không cần quan tâm tên nền tảng.

---

## 🎯 Kết luận
Đây không phải là "Code rác mỳ ý". Dự án hiện tại là một nền móng (Foundation) rất thực dụng và mạnh mẽ. Những điểm vi phạm trên là **Sự đánh đổi (Trade-off) có chủ ý** ở Phase 1 để ra mắt sản phẩm nhanh. 
Mục tiêu tiếp theo là mở một **"Refactoring Sprint"** để giải quyết triệt để 5 vấn đề này, biến dự án thành một hệ thống SaaS Automation hoàn hảo không tì vết.
