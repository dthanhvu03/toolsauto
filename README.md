# ToolsAuto

Hệ thống tự động hóa nội dung đa kênh & dịch vụ trực tuyến:
- **Cashback Bot**: Bot Telegram & Zalo tự động tạo link hoàn tiền Shopee/TikTok (`cashback_bot/`).
- **Shopee MCP Bridge**: Cầu nối rút gọn shortlink Shopee Affiliate `s.shopee.vn` qua CloakBrowser.
- **Xe Tết Live Stream**: Game tương tác livestream 3D WebGL trên TikTok LIVE (`xe_tet/`).
- **Buffer & Media Workers**: Dashboard FastAPI + HTMX, worker Playwright tự động đăng bài đa nền tảng.

👉 **Xem hướng dẫn lệnh chi tiết tại: [docs/COMMANDS.md](docs/COMMANDS.md)**

---

## ⚡ Các Lệnh Vận Hành Nhanh

### 1. Cashback Bot (Telegram & Zalo - Systemd)
```bash
sudo systemctl restart cashback-bot cashback-zalo   # Khởi động lại 2 bot
journalctl -u cashback-bot -u cashback-zalo -f       # Xem log trực tiếp
.venv/bin/pytest tests/test_cashback_*.py -q        # Chạy kiểm thử cashback
```

### 2. Shopee MCP Bridge & Buffer Workers (PM2)
```bash
pm2 list                                             # Xem tất cả tiến trình PM2
pm2 logs shopee-mcp --lines 30                      # Xem log rút gọn link Shopee
pm2 restart all                                      # Khởi động lại tất cả worker
pm2 save                                             # Lưu danh sách tiến trình
```

### 3. Xe Tết Game Server (Cổng 8810)
```bash
/home/vu/venv-xetet/bin/python -m xe_tet.server     # Chạy server game
cd xe_tet/overlay && npm run build                   # Build lại overlay Three.js
# Màn hình live: http://127.0.0.1:8810/ | Điều khiển: http://127.0.0.1:8810/control
```

---

## Bắt đầu đọc code

1. **Sổ tay câu lệnh vận hành**: [docs/COMMANDS.md](docs/COMMANDS.md)
2. Map thư mục: [docs/TREE.md](docs/TREE.md)
3. Kiến trúc module: [agents/decisions/ADR-007-module-boundary.md](agents/decisions/ADR-007-module-boundary.md)
4. Feature cụ thể: `app/features/<name>/README.md`

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
