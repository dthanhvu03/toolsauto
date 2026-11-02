# 📖 Sổ tay Các Câu Lệnh Vận Hành Hệ Thống (Cheat Sheet)

Tài liệu tổng hợp toàn bộ các câu lệnh thường dùng để kiểm tra, khởi động, dừng, xem log và debug các dịch vụ trong hệ thống **ToolsAuto** (Cashback Bot, Shopee MCP Bridge, Xe Tết Live TikTok, PM2).

---

## 1. 🤖 Cashback Bot (Telegram & Zalo)

Các bot hoàn tiền mua sắm được cài đặt dưới dạng Linux Service (`systemd`) trong WSL2, tự động chạy ngầm 24/7.

### Trạng thái & Khởi động lại dịch vụ
```bash
# Kiểm tra trạng thái cả 2 bot
systemctl status cashback-bot cashback-zalo --no-pager

# Khởi động lại cả 2 bot (sau khi cập nhật code)
sudo systemctl restart cashback-bot cashback-zalo

# Dừng bot tạm thời
sudo systemctl stop cashback-bot cashback-zalo

# Bật lại bot
sudo systemctl start cashback-bot cashback-zalo
```

### Xem Log thời gian thực
```bash
# Xem log trực tiếp của Bot Telegram
journalctl -u cashback-bot -f

# Xem log trực tiếp của Bot Zalo
journalctl -u cashback-zalo -f

# Xem 50 dòng log gần nhất của cả 2 bot
journalctl -u cashback-bot -u cashback-zalo -n 50 --no-pager
```

### Chạy Unit Tests
```bash
cd /home/vu/toolsauto

# Chạy toàn bộ test deal và Zalo
.venv/bin/pytest tests/test_cashback_deals.py tests/test_cashback_deal_feed.py tests/test_cashback_zalo.py

# Chạy test toàn bộ module cashback
.venv/bin/pytest tests/test_cashback_*.py -q
```

---

## 2. ⚡ Shopee MCP Bridge (Cổng 9224 - Rút gọn link `s.shopee.vn`)

Cầu nối giao tiếp với Chrome/CloakBrowser để chuyển đổi link Shopee Affiliate sang dạng shortlink chính thức `https://s.shopee.vn/XXXXX`. Dịch vụ này chạy ngầm qua **PM2** trong WSL.

### Quản lý tiến trình PM2
```bash
# Xem danh sách & trạng thái
pm2 status shopee-mcp

# Xem log rút gọn link trực tiếp
pm2 logs shopee-mcp --lines 30

# Khởi động lại bridge
pm2 restart shopee-mcp

# Lưu lại cấu hình PM2 (để tự bật lại sau khi reboot WSL)
pm2 save
```

### Kiểm tra sức khỏe Bridge (Health Check)
```bash
# Từ trong WSL
curl -s http://192.168.112.1:9224/health
# Hoặc trên Windows PowerShell:
# Invoke-RestMethod http://127.0.0.1:9224/health

# Kết quả đúng chuẩn: {"status":"ok","server":"shopee-mcp","version":"0.3.0"}
```

---

## 3. ⚙️ Hệ Thống Tự Động Đăng Bài & Worker (PM2)

Các worker mạng xã hội (Facebook, Buffer, TTS giọng đọc, Gateway) do daemon PM2 quản lý:
- `Maintenance`: Xử lý video, tải nguồn, hẹn lịch Buffer
- `Web_Dashboard`: Dashboard quản lý đăng bài
- `9Router_Gateway`: Gateway định tuyến
- `VieNeu_TTS`: Server sinh giọng đọc tiếng Việt cho game/video

```bash
# Xem bảng điều khiển tất cả tiến trình
pm2 list

# Xem log của một dịch vụ cụ thể
pm2 logs Maintenance --lines 50
pm2 logs VieNeu_TTS --lines 50

# Khởi động lại toàn bộ các dịch vụ
pm2 restart all

# Phục hồi danh sách dịch vụ đã lưu
pm2 resurrect
```

---

## 4. 🎮 Game Xe Tết (Live TikTok Stream)

Game tương tác livestream xe khách về quê Tết (Three.js WebGL overlay + backend Python WebSocket).

### Khởi động Server Game
```bash
# Chạy server game cổng 8810 (dùng venv riêng)
cd /home/vu/toolsauto
/home/vu/venv-xetet/bin/python -m xe_tet.server

# Hoặc chạy ngầm ghi log ra file
nohup /home/vu/venv-xetet/bin/python -m xe_tet.server > xe_tet_server.log 2>&1 &
```

### Build Giao Diện Overlay (Frontend Three.js)
```bash
cd /home/vu/toolsauto/xe_tet/overlay

# Cài đặt thư viện (nếu có cập nhật package.json)
npm install

# Build mã nguồn sang thư mục dist/
npm run build
```

### Chạy Kiểm Thử Game Xe Tết
```bash
cd /home/vu/toolsauto

# Chạy toàn bộ 144 unit tests của Xe Tết
/home/vu/venv-xetet/bin/pytest xe_tet/tests

# Chạy test e2e mô phỏng chuyến xe
/home/vu/venv-xetet/bin/pytest xe_tet/tests/test_game.py
```

### Đường dẫn Web & Debug
- **Màn hình Overlay đưa vào TikTok LIVE Studio / OBS**: `http://127.0.0.1:8810/`
- **Chế độ đo FPS (hiển thị thông số đồ họa)**: `http://127.0.0.1:8810/?fps=1`
- **Trang điều khiển thủ công (Control Panel)**: `http://127.0.0.1:8810/control`

---

## 5. 🗄️ Dữ Liệu & Cấu Hình Quan Trọng

| File / Thư mục | Mô tả |
|----------------|-------|
| `/home/vu/toolsauto/.env` | Chứa toàn bộ token bot, API key, Shopee Affiliate ID (`17315920094`) |
| `/home/vu/toolsauto/data/cashback.sqlite` | Database SQLite lưu trữ ví tiền, đơn hàng, người dùng bot |
| `C:\Users\Admin\.shopee-mcp\chrome-profile` | Profile trình duyệt Chrome lưu phiên đăng nhập Shopee Affiliate |
| `/home/vu/toolsauto/run_shopee_mcp.sh` | Script khởi chạy cầu nối shopee-mcp được PM2 gọi |

---

## 6. 🚀 Lệnh Git Thường Dùng

```bash
cd /home/vu/toolsauto

# Kiểm tra file đã chỉnh sửa
git status

# Xem sự thay đổi chi tiết
git diff

# Commit và đẩy lên nhánh hiện tại (feat/xe-tet)
git add .
git commit -m "feat/fix: nội dung thay đổi"
git push origin feat/xe-tet
```
