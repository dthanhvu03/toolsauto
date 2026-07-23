# ToolsAuto

Hệ thống tự động đăng nội dung lên mạng xã hội (Facebook, Threads, …): dashboard admin (FastAPI + HTMX), job queue, worker Playwright (PM2), PostgreSQL.

## Bắt đầu đọc code

1. Map thư mục: [docs/TREE.md](docs/TREE.md)
2. Kiến trúc module: [agents/decisions/ADR-007-module-boundary.md](agents/decisions/ADR-007-module-boundary.md)
3. Feature cụ thể: `app/features/<name>/README.md`

## Chạy nhanh (local)

### Windows
```powershell
# một lần: venv + deps (đã có thì bỏ qua)
py -3 -m venv venv
.\venv\Scripts\pip install -r requirements.txt

# Postgres Docker (port 5434 tránh conflict PostgreSQL local :5432)
docker start toolsauto_postgres
# hoặc tạo mới:
# docker run -d --name toolsauto_postgres -e POSTGRES_USER=admin -e POSTGRES_PASSWORD=admin -e POSTGRES_DB=toolsauto_db -p 5434:5432 postgres:16-alpine

# .env: ADMIN_*, SECRET_KEY, DATABASE_URL=postgresql+psycopg2://admin:admin@127.0.0.1:5434/toolsauto_db
.\start.ps1          # mặc định http://127.0.0.1:8002 — login admin / admin (xem .env)
# Lưu ý Windows + Python 3.14: `pip install -r requirements.txt` có thể fail (uvloop/gRPC).
# Web tối thiểu đã cài vào venv; worker/AI full stack nên dùng Python 3.12 trên VPS.
```

### Linux / VPS
- Web: `uvicorn app.main:app` (cần `.env` với `ADMIN_*`, `SECRET_KEY`, `DATABASE_URL`)
- Workers: `ecosystem.config.js` + PM2 / `./start.sh`
- Tests: `pytest tests/ -q`

Chi tiết cấu hình: [docs/CONFIG.md](docs/CONFIG.md). Map code: [docs/TREE.md](docs/TREE.md).
