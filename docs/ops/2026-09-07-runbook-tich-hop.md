# Runbook tích hợp miễn phí — 2026-09-07

> Cho Owner, làm tay, theo đúng thứ tự trong `docs/research/2026-09-07-tich-hop-mien-phi.md`.
> Mỗi mục có thời gian ước lượng, lệnh copy-paste được (PowerShell, tại `D:\Zusem\toolsauto`).
> Không mục nào cần sửa code. Mục 5 (Graph API) chỉ là **spike** — đạt mới báo Anti viết PLAN.

Tổng: ~3 giờ 15 phút. Làm 1 → 4 trong một buổi; mục 5 để buổi riêng, đầu óc tỉnh.

---

## 1. Key AI (15 phút) — vá chuỗi caption đang chết 401

### 1.1 Gemini (chính)

1. Mở <https://aistudio.google.com/apikey> → **Create API key** → chọn/tạo project bất kỳ.
2. Key có dạng `AIza…` (39 ký tự). Copy.
3. Mở `.env` (tạo từ `.env.example` nếu chưa có), thêm/sửa dòng:

   ```
   GEMINI_API_KEY=AIza...
   ```

> **Lưu ý dữ liệu:** free tier Gemini → Google **dùng prompt để train và người thật có thể
> đọc**. Chỉ đưa ảnh/caption sản phẩm công khai. Không đưa số điện thoại khách, giá vốn,
> nội dung chat, cookie, hay bất cứ gì không muốn người lạ đọc.

### 1.2 Groq (dự phòng, OpenAI-compatible)

1. Mở <https://console.groq.com/keys> → **Create API Key** → copy (dạng `gsk_…`).
2. Groq cắm qua 3 biến `OPENROUTER_*` có sẵn (không thêm provider mới — ADR-014):

   ```
   OPENROUTER_BASE_URL=https://api.groq.com/openai/v1
   OPENROUTER_API_KEY=gsk_...
   OPENROUTER_MODEL=qwen/qwen3.8-27b
   ```

   Free tier Groq: 30 RPM, 1.000 RPD, 8K TPM → ~50 caption/ngày. Model đang *Preview*,
   nếu 404 model thì vào <https://console.groq.com/docs/models> chọn model vision khác.
   Groq **không train** trên dữ liệu.

### 1.3 Kiểm

```powershell
.\venv\Scripts\python.exe manage.py ai check
```

- In `OK` + model → xong.
- Exit code 1 / `401` → key sai hoặc dán thiếu ký tự. Kiểm lại `.env`, không có dấu ngoặc kép, không khoảng trắng cuối dòng.
- Đổi `.env` xong phải **restart stack** (worker đọc env lúc khởi động).

Ghi vào bảng cuối file: `1 | Gemini OK / Groq OK | ngày`.

---

## 2. Đếm click bằng Sub ID (0 code) — thay P0-2

Tool **không** làm link đếm click nữa. Số click lấy thẳng từ dashboard sàn — trùng với số sàn dùng để tính đơn.

### Quy ước đặt tên Sub ID

```
fb_<YYYYMMDD>_<mã bài>
```

- `<mã bài>`: `j<job_id>` nếu bài do tool đăng (vd `fb_20260907_j12`), `m<số>` nếu đăng tay (vd `fb_20260907_m3`).
- Chỉ chữ thường, số, gạch dưới. Không dấu, không khoảng trắng (sàn có thể cắt).
- Một bài = một Sub ID. Đăng lại bài cũ → Sub ID mới (ngày mới).

### Shopee Affiliate

1. <https://affiliate.shopee.vn> → **Tạo link** → dán URL sản phẩm.
2. Ô **Sub ID** (Sub_id1) → điền theo quy ước trên → **Tạo link** → dùng link này trong caption.
3. Xem: **Báo cáo** → **Báo cáo theo Sub ID** → cột *Lượt click*, *Đơn hàng*, *Hoa hồng*.
   (Hướng dẫn gốc: help.shopee.vn/portal/10/article/122906.)

### AccessTrade

1. <https://pub.accesstrade.vn> → **Công cụ** → **Tạo link** (Deep link) → dán URL.
2. Ô `sub1` → điền theo quy ước; `sub2` để trống hoặc ghi nền tảng (`fb`).
3. Xem: **Báo cáo** → **Theo Sub ID** → cột *Click*.

### Đối chiếu với tool

Job id nằm ở cột đầu trang `/app/jobs` (hoặc `python scripts/query_jobs.py`). Cuối tuần: mở báo cáo Sub ID của sàn, dò `j<id>` → biết bài nào có click. Chưa cần bảng đối chiếu trong tool; khi nào có >30 bài/tuần mới tính.

---

## 3. healthchecks.io (30 phút) — "chết phải có người báo"

### 3.1 Tạo tài khoản + 3 check

1. <https://healthchecks.io/accounts/signup/> → đăng ký email (free: 20 check).
2. **Add Check** ×3, đặt đúng tên và số:

| Tên check | Period | Grace | Ai ping |
|---|---|---|---|
| `toolsauto-backup` | 1 day | 2 hours | `manage.py db backup` (Task Scheduler, giờ đặt trong `register_backup_task.ps1`) |
| `toolsauto-maintenance` | **xem config** `MAINT_LOOP_SLEEP_SEC` (mặc định 300 s → đặt 5 minutes) | 15 minutes | vòng lặp maintenance worker |
| `toolsauto-publisher` | 5 minutes | 10 minutes | vòng lặp fb_publisher (`/fail` khi account INVALID) |

   Với `toolsauto-maintenance`: nếu `.env` có `MAINT_LOOP_SLEEP_SEC` khác 300 thì Period = giá trị đó.

3. Mỗi check có URL dạng `https://hc-ping.com/<uuid>`. Copy cả 3.

### 3.2 Kênh báo

**Cách A — Telegram (khuyên dùng nếu đã có bot):**
Integrations → **Telegram** → bấm link mở bot `@HealthchecksBot` → **Start** → quay lại trang, bấm **Save**. Gán cho cả 3 check.

**Cách B — ntfy (không cần bot, không tài khoản):**
1. Cài app **ntfy** trên điện thoại (Android/iOS) → **Subscribe to topic** → đặt tên topic **khó đoán** (topic = mật khẩu), vd `toolsauto-7f3k9q2m`.
2. Thử từ laptop:

   ```powershell
   curl.exe -d "test" ntfy.sh/toolsauto-7f3k9q2m
   ```

   Điện thoại phải rung.
3. healthchecks.io → Integrations → **ntfy** → Topic = tên trên, Server = `https://ntfy.sh` → Save → gán cho 3 check.

### 3.3 Dán URL vào tool

1. Mở <http://127.0.0.1:8002/app/settings> → nhóm **Giam sat** (ADR-014 vừa thêm):
   - *Ping: db backup* ← URL check `toolsauto-backup`
   - *Ping: maintenance worker* ← URL check `toolsauto-maintenance`
   - *Ping: FB publisher* ← URL check `toolsauto-publisher`
2. Lưu. Không cần restart cho worker (đọc runtime settings); backup đọc lúc chạy.
3. Kiểm ngay:

   ```powershell
   .\venv\Scripts\python.exe manage.py db backup
   ```

   → trên healthchecks.io check `toolsauto-backup` chuyển **up** trong vài giây. Hai check còn lại lên **up** sau một vòng worker (≤5 phút).
4. Thử báo: tắt stack 15 phút → phải nhận thông báo `toolsauto-publisher is DOWN`. Bật lại → `is UP`.

Ghi vào bảng: `3 | 3 check up, đã nhận DOWN/UP | ngày`.

---

## 4. Tailscale (20 phút) — xem dashboard từ điện thoại, không mở port

1. <https://tailscale.com/download> → cài trên **laptop** (Windows) và **điện thoại**, đăng nhập **cùng tài khoản** (Google/GitHub). Free Personal: 3 user, 100 thiết bị.
2. Trên laptop, PowerShell **Admin**:

   ```powershell
   tailscale status                 # phải thấy cả laptop lẫn điện thoại
   tailscale serve --bg 8002        # HTTPS trong tailnet → 127.0.0.1:8002
   tailscale serve status           # in URL https://<hostname>.<tailnet>.ts.net
   ```

   Lần đầu `serve` có thể yêu cầu bật **HTTPS certificates** trong admin console → <https://login.tailscale.com/admin/dns> → *Enable HTTPS*.
3. Điện thoại (bật Tailscale) → mở `https://<hostname>.<tailnet>.ts.net` → thấy dashboard.
4. Dashboard vẫn bind `127.0.0.1` — không đổi `.env`, không mở port router. Chỉ máy trong tailnet của Owner vào được.
5. Tắt khi không dùng:

   ```powershell
   tailscale serve reset
   ```

   `--bg` nghĩa là serve **tồn tại qua reboot** — muốn tắt hẳn phải `reset`.

Không dùng `tailscale funnel` (đó là mở ra Internet công cộng).

Ghi vào bảng: `4 | mở được từ 4G | ngày`.

---

## 5. Spike Graph API (2 giờ) — thay Playwright cho việc đăng Page

**Mục tiêu duy nhất:** chứng minh bằng thực nghiệm rằng app cá nhân, không App Review, ở Live mode, đăng được bài lên Page **và công chúng thấy**. Đạt → PLAN. Không đạt → ghi lỗi, không code.

**Trước khi bắt đầu — đọc kỹ:**

- Dùng **tài khoản Facebook dev MỚI**, không phải tài khoản đã khoá 31/07, không phải tài khoản đang chạy Playwright.
- Page thử phải nằm trong **Business Manager có ≥ 2 admin** — làm xong `docs/sales/02-checklist-thiet-lap-an-toan.md` trước.
- Không dán token vào chat, issue, commit. Script chỉ in 8 ký tự đầu; token đầy đủ nằm ở `storage/db/config/graph_api_tokens.json` (ngoài git).
- Script: `scripts/graph_api_spike.py` — chỉ `requests`, không đụng code tool. Mọi lệnh có `--dry-run` để xem request trước.

Đặt biến cho gọn (PowerShell, chỉ sống trong phiên):

```powershell
$py = ".\venv\Scripts\python.exe"
$APP_ID = "<app id>"          # lấy ở bước 5.2
$APP_SECRET = "<app secret>"  # Settings › Basic › App Secret › Show
```

### 5.1 Tạo app (tay, 10 phút)

1. Đăng nhập tài khoản dev mới → <https://developers.facebook.com/apps> → **Create App**.
2. Use case: *Other* → Type: **Business** → tên app (vd `ToolsAuto Publisher`), email liên hệ. Nếu hỏi Business portfolio → chọn BM đang chứa Page.

### 5.2 Settings › Basic (tay, 10 phút)

Điền đủ 3 thứ — thiếu một cái là không bật Live mode được ở 5.4:

- **Privacy Policy URL**: bất kỳ trang công khai (GitHub Pages / Notion public) ghi vài dòng "app cá nhân, không thu thập dữ liệu người khác".
- **App Icon**: PNG 1024×1024.
- **Category**: *Business and Pages*.

Copy **App ID** và **App Secret** vào 2 biến ở trên.

### 5.3 Token (30 phút)

1. <https://developers.facebook.com/tools/explorer> → chọn app vừa tạo → **User Token** → *Add a permission* tick 4 quyền:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `pages_manage_engagement`
   → **Generate Access Token** → duyệt popup (chọn Page thử) → copy token (chuỗi `EAAB…`).
2. Kiểm token là của ai, còn bao lâu:

   ```powershell
   & $py scripts\graph_api_spike.py whoami --token "<user token>" --app-id $APP_ID --app-secret $APP_SECRET
   ```

   Phải thấy `type: USER`, 4 scopes ở trên, `expires_at` ~1 giờ.
3. Đổi sang long-lived (60 ngày) và lưu:

   ```powershell
   & $py scripts\graph_api_spike.py exchange --token "<user token>" --app-id $APP_ID --app-secret $APP_SECRET --save
   ```

4. Lấy Page token (không hết hạn) và lưu:

   ```powershell
   & $py scripts\graph_api_spike.py pages --save
   ```

   In bảng `page_id | name | token(8) | tasks`. `tasks` phải có `CREATE_CONTENT` và `MANAGE`. Ghi lại `page_id`:

   ```powershell
   $PAGE = "<page_id>"
   ```

5. **Kiểm quan trọng nhất của bước 3** — Page token phải "Never":

   ```powershell
   & $py scripts\graph_api_spike.py whoami --token "<page token đầy đủ, mở file graph_api_tokens.json>" --app-id $APP_ID --app-secret $APP_SECRET
   ```

   Phải thấy `type: PAGE`, `expires_at: Never`, dòng `✔ Page token không hết hạn`.
   Nếu là ngày cụ thể → token lấy từ user token ngắn hạn; làm lại từ 5.3.3 (exchange trước, rồi `pages --save` với `--token <long-lived>`).

   Đối chiếu tay: <https://developers.facebook.com/tools/debug/accesstoken> dán Page token → *Expires: Never*.

### 5.4 Live mode + đăng bài chữ (15 phút)

1. App Dashboard → góc trên có công tắc **App Mode: Development** → gạt sang **Live**. Không nộp review. Nếu báo thiếu → quay lại 5.2.
2. Đăng bài:

   ```powershell
   & $py scripts\graph_api_spike.py post-feed --page-id $PAGE --message "spike graph api $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
   ```

   In `post id: <page>_<post>` và `URL: https://www.facebook.com/<page>_<post>`. Ghi lại post id:

   ```powershell
   $POST = "<post id>"
   ```

   Lỗi hay gặp: `code 200` = thiếu quyền `pages_manage_posts` hoặc token không phải Page token; `code 190` = token hết hạn/thu hồi; `code 10` = app chưa được cấp quyền cho Page này (kiểm popup ở 5.3.1 có tick đúng Page).

### 5.5 Kiểm công khai — TIÊU CHÍ ĐẠT (10 phút)

```powershell
& $py scripts\graph_api_spike.py verify-public --post-id $POST --app-id $APP_ID --app-secret $APP_SECRET
```

Script in hướng dẫn + `is_published`/`privacy` đọc bằng app token. **Nhưng tiêu chí đạt là mắt người:**

1. Mở **cửa sổ ẩn danh** (Ctrl+Shift+N), dán URL bài. Thấy nội dung bài → **ĐẠT**.
2. Chắc hơn: đăng nhập một tài khoản **không có role** trên app lẫn Page (mượn người nhà), mở cùng URL.
3. "Nội dung này hiện không khả dụng" → chưa đạt. Nguyên nhân theo thứ tự: app còn Development mode (5.4.1) → Page chưa publish (Page settings › *Page visibility*) → bài bị hạn chế quốc gia/tuổi.

Ghi kết quả vào bảng cuối file **ngay lúc này**, kể cả không đạt.

### 5.6 Mở rộng (chỉ khi 5.5 đạt, 30 phút)

Mỗi lệnh thử một khả năng tool đang cần. Chạy `--dry-run` trước nếu muốn xem request.

```powershell
# Ảnh
& $py scripts\graph_api_spike.py post-photo --page-id $PAGE --file "D:\anh-test.jpg" --message "spike photo"

# Lên lịch feed (10 phút → 30 ngày)
& $py scripts\graph_api_spike.py post-feed --page-id $PAGE --message "spike schedule" --schedule "2026-09-08T09:00+07:00"

# Comment kèm ảnh (link affiliate hay để ở comment)
& $py scripts\graph_api_spike.py comment --post-id $POST --message "link: https://shope.ee/xxxx" --image "D:\anh-test.jpg"

# Reels: 3–90 s, 9:16, >= 540x960, tối đa 30 Reels/24h/Page
& $py scripts\graph_api_spike.py post-reel --page-id $PAGE --file "D:\reel-test.mp4" --description "spike reel"
```

Reels: script in `[1/3] start`, `[2/3] upload`, `[3/3] finish` rồi poll `status` mỗi 10 s tối đa 5 phút. Không `ready` trong 5 phút → mở Page › *Content* xem còn đang xử lý hay báo lỗi, ghi vào bảng.

### 5.7 Thư viện

Đã chốt ở research: gọi thẳng `requests` (v25.0), **không** `facebook-sdk` (chết 2018). Script này chính là mẫu — khi viết PLAN, adapter lấy 3 hàm `graph()`, `post-feed`, `post-reel` làm khung.

### Sau spike

- **Đạt (5.5 thấy bài, ít nhất feed + photo ở 5.6 chạy):** báo Anti viết PLAN **"GraphApiPublisher"** — adapter đăng Page qua Graph API thay Playwright cho Page; giữ Playwright cho những gì API không có (Story có link/sticker, Group, profile). Đính kèm bảng kết quả dưới đây vào PLAN.
- **Không đạt:** ghi lỗi (message / code / error_subcode / fbtrace_id script in ra) vào bảng. **Không code.** Chờ Anti đọc lỗi rồi mới quyết định thử lại hay bỏ.

---

## Dọn ổ C: (10 phút)

PowerShell **Admin**:

```powershell
# 1. Docker: xoá image/container/cache không dùng. KHÔNG thêm --volumes (mất data Postgres).
docker system prune -a

# 2. pip cache
.\venv\Scripts\python.exe -m pip cache purge

# 3. Windows Disk Cleanup, chế độ dọn mạnh
cleanmgr /verylowdisk
```

4. Xem gì đang chiếm chỗ: cài **WizTree** (<https://diskanalyzer.com>) → quét C: → thường thấy `%LOCALAPPDATA%\Docker\wsl\data\ext4.vhdx`, `%LOCALAPPDATA%\pip`, `%TEMP%`, `storage\media` cũ.
5. Docker Desktop → Settings › General → tick **Start Docker Desktop when you sign in** (Postgres trong compose chỉ sống sau khi đăng nhập Windows — đây là giới hạn đã biết, ADR riêng nếu muốn Postgres chạy như Service).

Nếu `ext4.vhdx` vẫn lớn sau prune:

```powershell
wsl --shutdown
diskpart
# trong diskpart:
#   select vdisk file="C:\Users\Admin\AppData\Local\Docker\wsl\data\ext4.vhdx"
#   compact vdisk
#   exit
```

---

## Bảng kết quả

Điền ngay sau mỗi mục. Dán cả bảng này vào handoff khi báo Anti.

| Bước | Kết quả | Ngày | Ghi chú (lỗi: message / code / error_subcode / fbtrace_id) |
|---|---|---|---|
| 1. Key AI — `ai check` | | | |
| 2. Sub ID — link đầu tiên có click | | | |
| 3. healthchecks — 3 check up | | | |
| 3. healthchecks — nhận báo DOWN/UP | | | |
| 4. Tailscale — mở từ 4G | | | |
| 5.1 App Business tạo xong | | | |
| 5.2 Privacy/icon/category | | | |
| 5.3 Page token `expires_at: Never` | | | |
| 5.4 Live mode + post-feed có id | | | |
| **5.5 Tài khoản không role thấy bài** | | | |
| 5.6 post-photo | | | |
| 5.6 post-feed --schedule | | | |
| 5.6 comment --image | | | |
| 5.6 post-reel ready | | | |
| Dọn C: — dung lượng trước/sau | | | |
