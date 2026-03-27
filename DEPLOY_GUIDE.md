# 🚀 Auto Publisher - Hướng Dẫn Triển Khai & Vận Hành

---

## 0. Setup VPS Từ Đầu (Chỉ Làm 1 Lần)

> Áp dụng khi anh mua VPS mới tinh, chưa có gì cả.

### Bước 0.1: Mua VPS

- **Cấu hình tối thiểu:** 2 vCPU, 2GB RAM, 30GB SSD, Ubuntu 22.04/24.04
- **Nhà cung cấp gợi ý:** Vietnix, AZDIGI, DigitalOcean, Vultr
- Sau khi mua, nhà cung cấp sẽ gửi email chứa: **IP**, **Username** (thường là `root`), **Password**

### Bước 0.2: SSH vào VPS lần đầu

Mở Terminal (hoặc WSL trên Windows):

```bash
ssh root@<IP_VPS>
# Gõ password nhà cung cấp gửi → Enter
```

### Bước 0.3: Cập nhật hệ điều hành

```bash
apt update && apt upgrade -y
```

### Bước 0.4: Cài Python, Node, Git và các công cụ cần thiết

```bash
# Python + venv
apt install -y python3 python3-pip python3.12-venv git

# Node.js (v20+)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs

# PM2 (quản lý process chạy 24/7)
npm install -g pm2
```

### Bước 0.5: Cài Chrome, FFmpeg, Xvfb (màn hình ảo)

```bash
# FFmpeg (xử lý video) + Xvfb (màn hình ảo cho Chrome)
apt install -y ffmpeg xvfb wget gnupg2

# Google Chrome
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
echo 'deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main' > /etc/apt/sources.list.d/google-chrome.list
apt update && apt install -y google-chrome-stable

# Kiểm tra
google-chrome --version   # Phải hiện ra Chrome 14x.x.x
ffmpeg -version            # Phải hiện ra ffmpeg 6.x
```

### Bước 0.6: Tạo SWAP (RAM ảo) — Nếu VPS chưa có

```bash
# Kiểm tra SWAP hiện tại
free -h
# Nếu dòng Swap hiện 0 → cần tạo:
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
# Kiểm tra lại
free -h   # Swap phải hiện 4.0Gi
```

### Bước 0.7: Clone code và cài thư viện Python

```bash
cd /root
git clone https://github.com/dthanhvu03/toolsauto.git
cd toolsauto

# Tạo môi trường ảo Python
python3 -m venv venv
source venv/bin/activate

# Cài tất cả thư viện
pip install --upgrade pip
pip install -r requirements.txt

# Cài trình duyệt Playwright (dùng cho Facebook)
playwright install chromium --with-deps
```

### Bước 0.8: Tạo file cấu hình .env

```bash
cat > /root/toolsauto/.env << 'EOF'
WHISPER_MODEL_SIZE=tiny
WORKER_TICK_SECONDS=20
SAFE_MODE=false
COOKIE_SYNC_SECRET=vuxuandao2026
# GEMINI_API_KEY=your_key_here
EOF
```

### Bước 0.9: Khởi động hệ thống bằng PM2

```bash
cd /root/toolsauto
pm2 start ecosystem.config.js
pm2 save
pm2 startup    # Tự khởi động lại khi VPS reboot
```

### Bước 0.10: Kiểm tra hệ thống

```bash
pm2 list                    # 4 process phải hiện "online"
curl http://localhost:8000   # Dashboard phải trả về HTML
```

> ✅ **Xong!** Giờ mở trình duyệt vào `http://<IP_VPS>:8000` để dùng Dashboard.

---

## 1. Thông Tin VPS

| Hạng mục | Giá trị                   |
| -------- | ------------------------- |
| IP       | `14.225.218.116`          |
| User     | `root`                    |
| Port SSH | `22`                      |
| OS       | Ubuntu 24.04 (Kernel 6.8) |
| RAM      | 2GB + 2GB SWAP            |
| Disk     | 38GB (32GB trống)         |
| Python   | 3.12.3                    |
| Node     | v22.22.1                  |
| Chrome   | 146.0.7680.164            |

---

## 2. Truy Cập Dashboard

Mở trình duyệt, truy cập:

```
http://14.225.218.116:8000
```

---

## 3. Đăng Nhập VPS (SSH)

```bash
ssh root@14.225.218.116
# Nhập password khi được hỏi
```

---

## 4. Quản Lý Bot (PM2)

```bash
# Xem trạng thái tất cả workers
pm2 list

# Xem log realtime
pm2 logs              # Tất cả
pm2 logs web          # Chỉ web dashboard
pm2 logs ai-worker    # Chỉ AI worker
pm2 logs publisher    # Chỉ publisher
pm2 logs maintenance  # Chỉ maintenance

# Khởi động lại
pm2 restart all       # Restart tất cả
pm2 restart web       # Restart riêng web

# Dừng / Xóa
pm2 stop all          # Dừng tạm
pm2 delete all        # Xóa hết, cần start lại bằng ecosystem

# Khởi động từ config
cd /root/toolsauto
pm2 start ecosystem.config.js
pm2 save
```

---

## 5. Cập Nhật Code Mới (Thủ Công)

```bash
ssh root@14.225.218.116
cd /root/toolsauto
git pull origin main
source venv/bin/activate
pip install -r requirements.txt   # Chỉ cần nếu thêm thư viện mới
pm2 restart all
```

---

## 6. Cập Nhật Code Tự Động (CI/CD)

Đã cài sẵn Github Actions. Chỉ cần thêm 3 Secrets trên Github:

1. Vào `https://github.com/dthanhvu03/toolsauto/settings/secrets/actions`
2. Bấm **New repository secret**, thêm lần lượt:

| Secret Name   | Value                    |
| ------------- | ------------------------ |
| `VPS_HOST`    | `14.225.218.116`         |
| `VPS_USER`    | `root`                   |
| `VPS_SSH_KEY` | Nội dung Private Key SSH |

> **Lưu ý:** Để dùng SSH Key, anh cần tạo cặp key trên VPS:
>
> ```bash
> ssh-keygen -t ed25519 -f ~/.ssh/deploy_key -N ""
> cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys
> cat ~/.ssh/deploy_key   # Copy nội dung này làm VPS_SSH_KEY
> ```

---

## 7. Bơm Cookie Gemini (Chrome Extension)

Khi cookie hết hạn, anh có 2 cách:

### Cách 1: Dùng Chrome Extension (Ở bất kỳ đâu)

1. Mở Chrome trên Laptop → `chrome://extensions/`
2. Bật **Developer mode** → **Load unpacked** → Chọn thư mục `chrome_extension/gemini_syncer`
3. Vào `gemini.google.com`, đăng nhập tài khoản Google
4. Bấm icon Extension → Nhập:
   - **IP VPS:** `http://14.225.218.116:8000`
   - **Mã bảo mật:** `vuxuandao2026`
5. Bấm **Bơm Cookie Lên VPS** → Done!

### Cách 2: Chạy Script Trực Tiếp Trên VPS (Cần màn hình)

```bash
ssh root@14.225.218.116
cd /root/toolsauto
export DISPLAY=:0
source venv/bin/activate
python scripts/login_gemini_bypass.py
```

---

## 8. Cấu Hình File .env

File `.env` nằm tại `/root/toolsauto/.env`:

```env
# Whisper Model (tiny cho VPS 2GB RAM)
WHISPER_MODEL_SIZE=tiny

# Worker
WORKER_TICK_SECONDS=20
SAFE_MODE=false

# Gemini API Fallback (điền key để kích hoạt lốp dự phòng)
# GEMINI_API_KEY=your_key_here

# Cookie Sync Secret
COOKIE_SYNC_SECRET=vuxuandao2026
```

> Bỏ dấu `#` trước `GEMINI_API_KEY` và điền API key để kích hoạt chế độ dự phòng khi cookie hết hạn ban đêm.

---

## 9. Các Đường Dẫn Quan Trọng Trên VPS

| Đường dẫn                                | Mô tả                                |
| ---------------------------------------- | ------------------------------------ |
| `/root/toolsauto/`                       | Thư mục gốc project                  |
| `/root/toolsauto/data/auto_publisher.db` | Database chính                       |
| `/root/toolsauto/data/backups/`          | Backup DB tự động (khi CI/CD deploy) |
| `/root/toolsauto/gemini_cookies.json`    | Cookie Gemini hiện tại               |
| `/root/toolsauto/content/`               | Video chờ đăng                       |
| `/root/toolsauto/content/done/`          | Video đã đăng xong                   |
| `/root/toolsauto/logs/`                  | Log hệ thống                         |
| `/root/toolsauto/profiles/`              | Profile trình duyệt Facebook         |

---

## 10. Khắc Phục Sự Cố

### Bot không chạy sau reboot VPS

```bash
pm2 resurrect    # Khôi phục process đã save
```

### RAM đầy, hệ thống chậm

```bash
pm2 restart all   # Giải phóng RAM
free -h           # Kiểm tra RAM
```

### Gemini Cookie hết hạn

- Dashboard hiện 🔴 **Gemini: Expired**
- Dùng Chrome Extension bơm cookie mới (xem mục 7)

### Database bị lỗi

```bash
cd /root/toolsauto
cp data/backups/auto_publisher_YYYYMMDD_HHMMSS.db data/auto_publisher.db
pm2 restart all
```

---

## 11. Lệnh Telegram Bot

Gửi tin nhắn cho Bot trên Telegram:

| Lệnh           | Mô tả                         |
| -------------- | ----------------------------- |
| `/status`      | Xem trạng thái hệ thống       |
| `/health`      | Kiểm tra sức khỏe             |
| `/jobs`        | Danh sách job gần đây         |
| `/drafts`      | Job đang chờ duyệt            |
| `/failed`      | Job bị lỗi                    |
| `/pause`       | Tạm dừng worker               |
| `/resume`      | Chạy lại worker               |
| `/retry <id>`  | Thử lại job bị lỗi            |
| `/cancel <id>` | Huỷ job                       |
| `/sys`         | Thông tin hệ thống (RAM, CPU) |
| `/stats`       | Thống kê hiệu suất            |
| `/viral`       | Quản lý viral scan            |
| `/reup <url>`  | Reup video từ TikTok          |
