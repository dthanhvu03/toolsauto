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
# Khuyến nghị: sau khi cấu hình Deploy key SSH (mục 5), đổi origin sang git@github.com:... để pull không cần PAT.

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

### Bước 0.9: Khởi động hệ thống bằng PM2 & Giữ log sạch sẽ

```bash
cd /root/toolsauto
# Cài plugin tự động xoay vòng log để tránh đầy ổ cứng
pm2 install pm2-logrotate

pm2 start ecosystem.config.js
pm2 save
pm2 startup    # Tự khởi động lại khi VPS reboot
```

### Bước 0.10: Kiểm tra hệ thống & Cấu hình HTTPS (BẮT BUỘC)

```bash
pm2 list                    # 4 process phải hiện "online"
curl http://localhost:8000   # Dashboard phải trả về HTML
```

> ⚠️ **BẢO MẬT TỐI QUAN TRỌNG:**
> Hệ thống hiện tại đã bật **Basic Authentication** (chặn bằng tài khoản `ADMIN_USERNAME` khai báo trong `.env`).
> Tuy nhiên, Basic Auth sẽ truyền username/password dạng dễ đọc nếu không đi qua HTTPS.
> **Anh BẮT BUỘC phải đặt VPS này đằng sau Nginx/Caddy có SSL, hoặc dùng Cloudflare Tunnel (HTTPS) trước khi mở public, nếu không thì pass cực dễ bị lộ.**

> ✅ **Xong bước Deploy cơ bản!** Giờ truy cập thông qua domain HTTPS đã được móc nối vào port 8000.

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

## 5. Quy trình Git khuyến nghị (dev hay dùng)

**Nguyên tắc:** Máy **dev** (hoặc CI) **push** lên GitHub; **VPS chỉ `git pull`**. Không cần Personal Access Token (PAT) có quyền **ghi** trên server — giảm rủi ro lộ token.

| Vị trí        | Việc làm                          | Xác thực GitHub                          |
| ------------- | --------------------------------- | ---------------------------------------- |
| Máy dev       | `git push origin develop`         | PAT hoặc SSH key **tài khoản** của bạn   |
| VPS           | `git pull origin develop`         | **Deploy key SSH (read-only)** hoặc PAT chỉ đọc |

GitHub **không** cho dùng mật khẩu tài khoản cho `git push`/`pull` qua HTTPS; nếu dùng HTTPS trên VPS thì ô Password phải là **PAT** (fine-grained: repo đúng + **Contents: Read-only** nếu chỉ pull).

### 5.1. Lần đầu: tạo SSH key trên VPS (chỉ để clone/pull)

```bash
ssh root@<IP_VPS>
ssh-keygen -t ed25519 -C "toolsauto-vps-readonly" -f ~/.ssh/github_toolsauto_deploy -N ""
chmod 600 ~/.ssh/github_toolsauto_deploy
cat ~/.ssh/github_toolsauto_deploy.pub
```

Copy **toàn bộ** dòng `.pub` (bắt đầu bằng `ssh-ed25519 ...`).

### 5.2. Thêm Deploy key trên GitHub (read-only)

1. Mở repo: `https://github.com/dthanhvu03/toolsauto` → **Settings** → **Deploy keys** → **Add deploy key**.
2. **Title:** ví dụ `vps-readonly`.
3. Dán **public key** ở bước 5.1.
4. **Không** tick **Allow write access** (chỉ cần pull).
5. Save.

### 5.3. Cấu hình SSH và remote (trên VPS)

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
cat >> ~/.ssh/config << 'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/github_toolsauto_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

Nếu repo đã clone bằng HTTPS, đổi sang SSH:

```bash
cd /root/toolsauto
git remote set-url origin git@github.com:dthanhvu03/toolsauto.git
ssh -T git@github.com
# Kỳ vọng: "Hi dthanhvu03! You've successfully authenticated..."
```

### 5.4. Mỗi lần cập nhật code trên VPS

Nhánh mặc định cho feature merge: **`develop`** (không dùng `main` trừ khi team thống nhất khác).

```bash
ssh root@14.225.218.116
cd /root/toolsauto
git fetch origin
git checkout develop
git pull origin develop
source venv/bin/activate
pip install -r requirements.txt   # Chỉ khi requirements.txt đổi
pm2 restart all
```

### 5.5. Máy dev: push (không làm trên VPS)

Trên laptop/WSL (đã login GitHub):

```bash
cd /path/to/toolsauto
git checkout develop
git pull origin develop
# ... sửa code, commit ...
git push origin develop
```

Sau đó trên VPS chỉ cần lặp **mục 5.4**.

### 5.6. Nếu bắt buộc pull bằng HTTPS trên VPS

Dùng **PAT fine-grained**: chọn đúng repo `toolsauto`, **Contents: Read-only**. Username = `dthanhvu03`, password = PAT. Xóa credential cũ nếu bị 403:

```bash
printf "protocol=https\nhost=github.com\n" | git credential reject
```

---


## 6. Cập Nhật Code Tự Động (CI/CD)

Workflow: **`.github/workflows/deploy.yml`**

- **Khi nào chạy:** mỗi lần **push** lên nhánh **`main`** hoặc **`develop`**.
- **Việc làm trên VPS (qua SSH):** backup DB → `git fetch` + `git reset --hard origin/<nhánh vừa push>` → `pip install` → `npm install` → `pm2 restart all`.

Như vậy anh **không cần SSH vào VPS để `git pull`** mỗi khi deploy — chỉ cần **`git push origin develop`** (hoặc `main`) từ máy dev; Actions sẽ kéo code và restart PM2.

**Mục §5** (Deploy key read-only để VPS `git pull` tay) vẫn hữu ích khi: sửa nhanh trên server, CI lỗi, hoặc cần pull khi không push.

### 6.1. Secrets trên GitHub

1. Vào `https://github.com/dthanhvu03/toolsauto/settings/secrets/actions`
2. **New repository secret**:

| Secret Name        | Bắt buộc | Value / ghi chú |
| ------------------ | -------- | ---------------- |
| `VPS_HOST`         | Có       | IP VPS, vd. `14.225.218.116` |
| `VPS_USER`         | Có       | User SSH, vd. `root` |
| `VPS_SSH_KEY`      | Có       | **Private key** (toàn bộ nội dung file, kể cả `BEGIN`/`END`) |
| `VPS_PROJECT_PATH` | Không    | Nếu code **không** nằm tại `/root/toolsauto` (root) hoặc `/home/<user>/toolsauto` — ghi đường dẫn tuyệt đối, vd. `/root/toolsauto` |

> **SSH key cho CI:** Tạo cặp key **riêng cho deploy** (khác Deploy key pull-only ở §5):
>
> ```bash
> ssh-keygen -t ed25519 -f ~/.ssh/github_actions_deploy -N ""
> cat ~/.ssh/github_actions_deploy.pub >> ~/.ssh/authorized_keys
> cat ~/.ssh/github_actions_deploy   # Copy toàn bộ → secret VPS_SSH_KEY
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

---

## 12. Cẩm Nang Xử Lý Sự Cố (VPS Deployment Troubleshooting)

> Tổng hợp các lỗi thực tế đụng phải khi đưa hệ thống từ Local lên Production VPS và cách đã fix.

### 12.1. Lỗi sai đường dẫn thư mục (Hardcoded paths)

- **Triệu chứng:** Không tìm thấy `gemini_cookies.json` hoặc log syspanel không tải được.
- **Nguyên nhân:** Lúc code ở máy nhà, đường dẫn bị ghim chết thành `/home/vu/...`. Trên VPS chạy bằng `root`, gốc là `/root/toolsauto`.
- **Cách fix:** Thay thế toàn bộ hardcode bằng biến động `BASE_DIR` tự bắt đường dẫn thư mục hiện hành.

### 12.2. Thiếu thư mục chứa file (Vô gia cư)

- **Triệu chứng:** Bot chập cheng không tải được video hay tạo profile Facebook, văng lỗi `FileNotFoundError`.
- **Nguyên nhân:** Khởi tạo VPS mới từ Git không đi kèm các thư mục data như `content/profiles`, `content/processed`.
- **Cách fix:** Viết thêm code logic tự động tạo thư mục rỗng nếu chưa tồn tại (`os.makedirs(..., exist_ok=True)`).

### 12.3. Lỗi 409 Conflict ở mạng Telegram

- **Triệu chứng:** Bot liên tục bắn log lỗi mạng Telegram 409 Conflict.
- **Nguyên nhân:** Cấu hình chạy PM2 đa quy trình khiến nhiều worker `maintenance` cùng tranh nhau gọi (poll) lệnh từ một con Telegram Bot.
- **Cách fix:** Khống chế số lượng worker làm nhiệm vụ lắng nghe Telegram về 1 mối duy nhất hoặc giới hạn instance PM2.

### 12.4. Tràn RAM tử vong (OOM Crash Loop)

- **Triệu chứng:** Worker `ai-worker` liên tục chết (`status: errored`), văng log `Killed`.
- **Nguyên nhân:** Mô hình AI `faster-whisper (medium)` ngốn quá 2GB RAM. VPS dung lượng nhỏ xíu không chịu nổi nhiệt bung nóc.
- **Cách fix:** Cài đặt giới hạn RAM trong cấu hình `ecosystem.config.js` (`max_memory_restart: '2.5G'`). Nếu vượt trần sẽ tự ép khởi động lại để cứu Server.

### 12.5. Rào cản Facebook "Circuit Open" (Continue As)

- **Triệu chứng:** Bot không chịu đăng bài, account văng về `INVALID` và báo lỗi `Circuit Open`.
- **Nguyên nhân:** Facebook hiện trang _"Tiếp tục dưới tên (Continue as)"_ thay vì vô thẳng News Feed, khiến luồng đăng bài bị kẹt cứng (không tìm thấy Header Navigation).
- **Cách fix:** Viết thêm nhánh code **Session Recovery** để tự dò tìm và ép táng siêu mạnh (force_click) vào đúng cái nút _"Tiếp tục"_ nhằm tự vượt qua rào.

### 12.6. Lỗi Checkpoint Facebook ẩn (Đòi hỏi mật khẩu)

- **Triệu chứng:** Cho dù bấm qua cửa ải Tiếp Tục, Facebook vẫn cạch mặt bắt gõ Mật khẩu để xác minh. Bot tự động thì không có pass.
- **Cách fix:**
  - Nâng cấp Nút **🔐 Login Đăng Nhập Thủ Công** trên Syspanel Web cho phép chạy thẳng với thông số máy Ảo `:99`.
  - Kết nối song song **Livestream VNC** để User nhìn thấy màn hình đang bị kẹt ở đâu và tự nhảy vào gõ mật khẩu bằng tay vượt chốt. Mở cửa xong là Bot tự lấy lại cookie.

### 12.7. Tính năng "Tẩy Trắng Cuộc Đời" và Truyền hình VNC

- Nhờ qua các kiếp nạn trên, hệ thống giờ sở hữu giao diện Syspanel VIP siêu cấp:
  1. Nút **Reset (Circuit Open)**: Tẩy rửa 1 click mọi án lưu đọng, reset bộ đếm fail về `0`, ép nick từ `INVALID` thành xanh lè `ACTIVE` và mở khóa Automation để đi tiếp. KHÔNG CẦN CHẠY LỆNH GÌ NỮA.
  2. Nút **📺 Bật/Tắt Livestream VNC (NoVNC)** vào System Actions: Cấu hình `x11vnc` ngầm để live video VPS về cho Web không độ trễ. Click vào tab `vnc_lite.html`, xem Bot thao tác như đang làm phim Netflix. Dễ như chạy Grab!
