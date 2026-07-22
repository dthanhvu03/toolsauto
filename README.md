# ToolsAuto

Hệ thống tự động đăng nội dung lên mạng xã hội (Facebook, Threads, …): dashboard admin (FastAPI + HTMX), job queue, worker Playwright (PM2), PostgreSQL.

## Bắt đầu đọc code

1. Map thư mục: [docs/TREE.md](docs/TREE.md)
2. Kiến trúc module: [agents/decisions/ADR-007-module-boundary.md](agents/decisions/ADR-007-module-boundary.md)
3. Feature cụ thể: `app/features/<name>/README.md`

## Chạy nhanh (local)

- Web: `uvicorn app.main:app` (cần `.env` với `ADMIN_*`, `SECRET_KEY`, `DATABASE_URL`)
- Workers: `ecosystem.config.js` + PM2 / `start.sh`
- Tests: `pytest tests/ -q`

Chi tiết docs: [docs/README.md](docs/README.md).
