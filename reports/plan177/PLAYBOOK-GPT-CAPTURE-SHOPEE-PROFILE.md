# Playbook GPT — Mở Shopee thường + bắt request bằng profile `shopee-mcp`

Dành cho agent GPT/Codex. Mục tiêu: mở **Shopee thường** (`shopee.vn`) bằng **đúng profile session** của bridge, bật DevTools Network, bắt XHR/Fetch liên quan sản phẩm / hoa hồng; **không** phá bridge production lâu dài.

## 0. Cứng — đọc trước khi đụng

1. **Một profile = một browser.** Đang chạy `shopee-mcp` thì **cấm** mở Chrome/Cloak cùng `user-data-dir`. Phải `pm2 stop` + kill Cloak + xóa lock trước.
2. Profile Windows: `C:\Users\Admin\.shopee-mcp\chrome-profile`
   WSL path: `/mnt/c/Users/Admin/.shopee-mcp/chrome-profile`
3. Binary Cloak (đúng stack bridge):
   `C:\Users\Admin\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe`
   (Nếu version đổi: xem thư mục `C:\Users\Admin\.cloakbrowser\chromium-*`.)
4. Bridge HTTP: Windows `127.0.0.1:9224` · WSL thường `192.168.112.1:9224`.
5. **Scrub bắt buộc** trước khi ghi báo cáo: Cookie, Authorization, CSRF, SPC_*, token, sessionid, SPC_F, raw header đầy đủ, PII. Chỉ giữ: URL path + query name (không value bí mật), method, status, **tên field số** (price/commission/rate/XTRA…), shape JSON (key list).
6. **Không** commit cookie/HAR thô. **Không** để route capture tạm trên npm `index.js` overnight (đã fail R&D trước — xem `RND-BRIDGE-CAPTURE-20261119.md`).
7. Xong lượt: **đóng hết** browser profile đó → `pm2 restart shopee-mcp` → `curl` health OK.
8. Live Shopee cần Owner đã cho phép (Gate B / POC). Không tự gọi Open API thiếu credential.

## 0b. Cách ưu tiên (Owner 19/11) — **không** stop bridge

Giữ `shopee-mcp` online. Trong session Cloak Affiliate sẵn có: `withPage` → `context.newPage()` → goto `https://shopee.vn/product/{shop}/{item}` → bắt `/api/v4/pdp/get_pc`.

Proof đã chạy: `CAPTURE-SHOPEE-REGULAR-20261119.md` — tab mới OK, nhưng `get_pc` trả **90309999** (anti-bot): session Affiliate ≠ buyer PDP sạch. Chỉ dùng §1–5 (stop profile + DevTools tay) nếu cần login buyer tay trên cùng profile.

## 1. Stop bridge (chỉ khi bắt buộc DevTools tay / login)

Trong WSL, cwd `/home/vu/toolsauto`:

```bash
pm2 stop shopee-mcp
# Giải phóng port + Cloak mồ côi + lock profile (cùng logic run_shopee_mcp.sh)
PROFILE_WSL="/mnt/c/Users/Admin/.shopee-mcp/chrome-profile"
pid="$(/mnt/c/Windows/System32/netstat.exe -ano 2>/dev/null | awk '/:9224/ && /LISTENING/ {print $NF; exit}' | tr -d '\r')"
[[ -n "${pid:-}" && "$pid" != "0" ]] && /mnt/c/Windows/System32/taskkill.exe /F /PID "$pid" 2>/dev/null || true
"/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe" -NoProfile -NonInteractive -Command \
  'Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like "*cloakbrowser*" } | Stop-Process -Force -ErrorAction SilentlyContinue' \
  >/dev/null 2>&1 || true
rm -f "$PROFILE_WSL/lockfile" "$PROFILE_WSL/SingletonLock" \
      "$PROFILE_WSL/SingletonSocket" "$PROFILE_WSL/SingletonCookie" 2>/dev/null || true
# Xác nhận không còn LISTENING :9224
/mnt/c/Windows/System32/netstat.exe -ano 2>/dev/null | awk '/:9224/ && /LISTENING/'
```

Không còn dòng LISTENING → mới mở browser tay.

## 2. Mở browser đúng profile (Windows)

**PowerShell (khuyến nghị — đúng Cloak như bridge):**

```powershell
$chrome = "$env:USERPROFILE\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe"
$profile = "$env:USERPROFILE\.shopee-mcp\chrome-profile"
# Nếu version chromium khác: Get-ChildItem "$env:USERPROFILE\.cloakbrowser\chromium-*"
& $chrome --user-data-dir="$profile" --remote-debugging-port=9333 "https://shopee.vn"
```

Ghi chú:
- Port debug **9333** (tránh đụng 9222 threads / 9224 bridge).
- URL mặc định **Shopee thường**. Affiliate (nếu cần so sánh): `https://affiliate.shopee.vn/offer/product_offer`.
- Nếu cửa sổ báo profile đang dùng → quay lại §1, kill chưa sạch.

**Không** dùng Chrome Google thường trừ khi Cloak không mở được; ưu tiên Cloak để khớp fingerprint/session bridge.

## 3. Bắt request (DevTools)

1. F12 → tab **Network**.
2. Bật **Preserve log**. Filter: `Fetch/XHR` (hoặc `Fetch/XHR` + `Doc`).
3. Clear network → thao tác trên **Shopee thường**:
   - Mở 1 trang product: `https://shopee.vn/product/{shopId}/{itemId}` hoặc slug `-i.{shop}.{item}`.
   - Đợi trang load xong; nếu có tab «Hoàn xu / Affiliate» trên UI thường thì click để kích hoạt call liên quan hoa hồng (nếu có).
4. Ứng viên cần tìm (tên có thể đổi — lọc theo keyword):
   - `commission`, `cashback`, `affiliate`, `offer`, `product/get`, `item/get`, `v4/pdp`, `v4/recommend`
   - Trên portal affiliate (nếu Owner bảo mở thêm): `/api/v3/offer/product/list`, `gql?q=…`
5. Với mỗi request hữu ích:
   - Copy **Request URL** (bỏ query token nếu có).
   - Copy **Request method**.
   - Copy **Response JSON key tree** (chỉ tên field) + giá trị **số** liên quan giá/%/commission nếu có.
   - **Không** Copy as cURL nếu cURL chứa Cookie — hoặc Copy rồi scrub tay trước khi lưu file.
6. Ghi artifact scrubbed vào:
   `reports/plan177/CAPTURE-SHOPEE-REGULAR-YYYYMMDD.md` (+ optional `.json` đã scrub).

## 4. Mẫu báo cáo (scrubbed)

```markdown
# Capture Shopee thường — YYYY-MM-DD
- Profile: shopee-mcp chrome-profile (Cloak)
- Bridge: stopped during capture; restarted after; /health = …
- Items thử: shopId/itemId (số), không tên PII

## Request A
- method / path: GET /api/v4/...
- status: 200
- numeric fields: price=…, … (hoặc «không có commission»)
- keys (top-level): […]

## Kết luận
- Có / không field dùng được cho native quote
- Next: map schema / bỏ qua
```

## 5. Đóng + bật lại bridge

1. Đóng **mọi** cửa sổ Cloak/Chrome đang dùng profile trên.
2. WSL:

```bash
cd /home/vu/toolsauto
pm2 restart shopee-mcp
sleep 3
curl -sS --max-time 5 http://192.168.112.1:9224/health
# Kỳ vọng: {"status":"ok",...}
pm2 status shopee-mcp
```

3. Nếu health fail: xem `pm2 logs shopee-mcp --lines 40`; thường do lock/profile còn mở → lặp §1 rồi `pm2 restart` lại.
4. **Không** để `pm2 stop` quên start — Cashbot shortlink `s.shopee.vn` phụ thuộc bridge.

## 6. Việc GPT không được làm trong lượt này

- Sửa npm `…\shopee-mcp\build\index.js` gắn route capture tạm (trừ Owner bảo + backup hash + restore trong cùng phiên).
- Restart `cashback-bot` / đụng ví / settlement / DB production.
- Báo số hoa hồng cho khách từ capture chưa map + chưa Owner chốt Phase 2.
- Lưu HAR/cookie vào git.

## 7. Context đã biết (đừng lặp sai)

- Portal GraphQL `productOfferLinks` chỉ trả **link**, không HH (`POC-GATE-B.md`).
- `productOfferV2` **không** có trên portal schema; Open API cần App ID/Secret.
- Capture qua hook bridge trước đó: product list bị cắt 220 ký tự / peer 403 / HTTP 500 — ưu tiên DevTools tay trên cửa sổ profile như playbook này.
- `payout_status=0` trên kỳ thanh toán = «Mới tạo / chờ xử lý» (đã map code); không liên quan lượt capture này.

## 8. Definition of Done lượt capture

- [ ] Bridge stop → browser profile mở → bắt ≥1 product page Shopee thường
- [ ] Artifact scrubbed dưới `reports/plan177/`
- [ ] Bridge `pm2` online + `/health` 200
- [ ] Không còn process Cloak orphan giữ profile
- [ ] Không cookie/token trong file đã commit / báo cáo
