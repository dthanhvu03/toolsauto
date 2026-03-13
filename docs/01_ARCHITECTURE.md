# Architecture: FastAPI + HTMX + Tailwind + Worker

## Core Components

1. **FastAPI App (Dashboard & API)**

- Giao diện Admin với HTML (Jinja2 templates) + TailwindCSS
- Sử dụng HTMX cho các tương tác động (SPA-like feel): load bảng Jobs, Accounts, cập nhật trạng thái Worker.
- Routes chính: `/` (dashboard), `/jobs/...`, `/accounts/...`, `/worker/...`, `/health`
- Link Tracking endpoint: `/r/{code}` (chuyển hướng + đếm click affiliate)
- Webhook cho Telegram: `/telegram/callback` (xử lý inline buttons)

2. **Database (SQLite + SQLAlchemy)**

- Sử dụng SQLAlchemy ORM thao tác với file SQLite (`data/auto_publisher.db`).
- Có Alembic dùng để quản lý database migrations.
- Các bảng chính: `accounts`, `jobs`, `job_events`, `system_state`.

3. **Worker Service (`worker.py` - 24/7 Background Process)**

- Vòng lặp polling liên tục để xử lý luồng công việc tự động.
- Xử lý các loại Job:
  - **DRAFT AI Jobs**: Gọi `ContentOrchestrator` & `Gemini RPA` để tạo caption tự động.
  - **PENDING Publish Jobs**: Đẩy bài qua các Adapters.
- Các dịch vụ đi kèm chạy ngầm trong Worker:
  - `CleanupService`: Xóa dọn các tệp tin tạm, media đã đăng thành công tránh rác ổ cứng.
  - `MetricsChecker`: Quét cập nhật lượt views (sau 24h) từ các post đã đăng.
  - `TelegramPoller`: Lắng nghe lệnh từ Bot Telegram (inline button clicks).
  - Quản lý trạng thái an toàn: Panic Mode (Safe mode), Crash Recovery.

4. **Adapter Layer (`adapters/`)**

- `Dispatcher`: Trạm trung chuyển định tuyến job cho đúng adapter tương ứng.
- **Facebook Adapter**: Dùng Playwright với persistent profile để đẩy video Reels, post bài.
- **Gemini RPA**: Dùng `undetected_chromedriver` ghép nối session vào Web UI của Gemini để mượn sức mạnh AI tạo nội dung/phân tích video tự động (Bypass API Key).

## Process Model

- Khuyên dùng `tmux` để chạy độc lập 2 process:
  1. `uvicorn app.main:app --host 0.0.0.0 --port 8000` (Web UI)
  2. `python worker.py` (Background Worker)

## Cơ Cấu Thư Mục

```text
auto_publisher/
├── app/                  # Chứa toàn bộ logic FastAPI, Services, Models
│   ├── adapters/         # Logic auto publish lên MXH (Facebook...)
│   ├── database/         # Models ORM, Core DB setup
│   ├── services/         # Layer business logic (Queue, Job, Account, Metrics, Telegram...)
│   └── templates/        # Jinja2 HTML templates, HTMX fragments
├── content/              # Thư mục chứa media người dùng đẩy lên
├── data/                 # CSDL SQLite lưu tại đây
├── docs/                 # Tài liệu hệ thống
├── profiles/             # Các thư mục profile Chrome/Firefox (UserDataDir) của Playwright
├── debug_steps/          # Nơi lưu screenshot mỗi khi RPA lỗi để fix bug
├── logs/                 # Ghi log file
├── worker.py             # Script chạy background worker
└── main.py               # (Linker) Chạy file gốc của ứng dụng (trỏ vào app.main)
```
