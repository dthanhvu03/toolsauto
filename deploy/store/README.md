# Bot bán hàng (store_bot) — cài đặt

Hai tiến trình dùng chung một file SQLite (`data/store.sqlite`):

| Dịch vụ | Lệnh | Việc |
|---|---|---|
| `store-bot` | `python -m store_bot` | Bot Telegram: khách mua, nạp tiền; admin quản lý (`/admin`) |
| `store-api` | `python -m store_bot.api_server` | API cho đại lý + webhook SePay tự cộng tiền nạp |

Không dính gì tới `cashback_bot` (chỉ dùng chung hàm tạo mã VietQR).

**Nguồn hàng: FatCat Store** (khi có `FATCAT_API_KEY`). Bot tự lấy danh sách món FatCat mở cho khóa của bạn
(3 phút một lần), bán bằng giá lẻ FatCat (= giá FatCat cho bạn ÷ 0,98). Khách mua → bot trừ ví khách → gọi FatCat
mua bằng ví đại lý của bạn → giao hàng ngay. FatCat giao thiếu thì hoàn phần thiếu; từ chối (ví FatCat hết tiền, hết
hàng…) thì hoàn đủ và báo admin; nguồn chậm thì bot gọi lại cùng mã đơn tới khi có hàng (không bị trừ tiền hai lần).
Món FatCat tăng hàng (≥ 5, hoặc từ hết hàng có lại) → bot tự đăng "🆕 HÀNG MỚI VỀ!" lên kênh.
**Nhớ giữ ví FatCat đủ tiền** — xem số dư ở `/admin`.

## 1. Tạo bot và kênh

1. @BotFather → `/newbot` → lấy token.
2. Tạo kênh (nơi đăng "🆕 HÀNG MỚI VỀ!"), thêm bot làm **admin kênh** có quyền đăng tin.
3. Lấy ID Telegram của chủ shop (ví dụ nhắn @userinfobot).

## 2. Thêm vào `.env` (thư mục gốc project)

```env
STORE_BOT_TOKEN=123456:ABC...
STORE_ADMIN_IDS=111111111            # nhiều admin: 111,222
STORE_SHOP_NAME=FatCat Store
STORE_CHANNEL_ID=@tenkenh            # hoặc -100xxxxxxxxxx; bỏ trống = không đăng kênh

# Tài khoản nhận tiền nạp (bỏ trống cả 3 = tắt nạp tiền)
STORE_BANK_BIN=970422                # BIN ngân hàng 6 số (MB 970422, VCB 970436, TCB 970407, ACB 970416…)
STORE_BANK_ACCOUNT=0123456789
STORE_BANK_OWNER=NGUYEN VAN A
STORE_BANK_NAME=MB Bank
STORE_MIN_TOPUP_VND=10000

# API đại lý
STORE_API_PUBLIC_URL=https://api.tenmien.com   # hiện trong tin cấp khóa
STORE_API_HOST=127.0.0.1
STORE_API_PORT=8091
STORE_RESELLER_DISCOUNT_BPS=200      # mức giảm khi cấp khóa: 200 = 2% (hàng FatCat: = hoà vốn, bot không bán dưới giá vốn)
STORE_MAX_ORDER_QUANTITY=100

# Liên hệ ở nút ☎️ Hỗ trợ (trống Telegram = dùng @username admin)
STORE_SUPPORT_TELEGRAM=@tenhotro
STORE_SUPPORT_ZALO=09xxxxxxxx

# Tự cộng tiền nạp qua SePay (bỏ trống = admin bấm ✅ tay)
STORE_SEPAY_WEBHOOK_KEY=

# Nguồn hàng FatCat (bỏ trống = chỉ bán hàng tự nhập kho)
FATCAT_API_KEY=mb_...
FATCAT_DISCOUNT_BPS=200              # FatCat giảm cho khóa của bạn 2% → bán đúng giá lẻ FatCat
STORE_SYNC_SECONDS=180
STORE_RESTOCK_ANNOUNCE_MIN=5
```

`STORE_DB_PATH` mặc định `./data/store.sqlite` (thư mục `data/` không bị git theo dõi).

## 3. Chạy

```bash
sudo cp deploy/store/store-bot.service deploy/store/store-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now store-bot store-api
tail -f logs/store_bot.log logs/store_api.log
```

Sau khi sửa code hoặc `.env`: `sudo systemctl restart store-bot store-api`.

## 4. Mở API ra ngoài

`store-api` chỉ nghe `127.0.0.1:8091`. Trỏ tên miền về đó bằng Cloudflare Tunnel hoặc nginx (HTTPS), rồi đặt `STORE_API_PUBLIC_URL`.

## 5. SePay (tuỳ chọn, để tiền vào là tự cộng)

1. Liên kết tài khoản ngân hàng ở sepay.vn.
2. Tạo webhook: URL `https://api.tenmien.com/webhooks/sepay`, xác thực **API Key**, đặt một chuỗi bí mật.
3. Ghi chuỗi đó vào `STORE_SEPAY_WEBHOOK_KEY`, restart `store-api` và `store-bot` (để tin nạp ghi "bot tự cộng").

Bot tìm mã `NAPxxxxxx` trong nội dung chuyển khoản và cộng **đúng số tiền thực nhận**. Tiền vào không có mã hoặc mã đã dùng → bot báo admin để xử lý tay (💵 Cộng/trừ tiền).

## 6. Dùng hằng ngày (admin, gõ `/admin`)

- **🔄 Đồng bộ FatCat**: lấy ngay danh sách / giá / kho mới nhất (bình thường 3 phút tự làm một lần). Món FatCat (🐱) chỉ có nút Ẩn/Mở bán và Đăng kênh; giá, tên, kho đi theo FatCat.
- **📦 Sản phẩm & kho** → ➕ Thêm sản phẩm (`Tên | Giá | Mô tả`) → vào sản phẩm → **➕ Nhập kho**: dán mỗi dòng một món (gửi nhiều tin hoặc file .txt), xong bấm **📢 Xong + đăng kênh**.
- **🔑 Khóa API đại lý** → ➕ Cấp khóa mới → gõ `@username` (người đó phải /start bot trước). Khóa chỉ hiện một lần.
  Trong từng khóa: 📦 Sản phẩm được bán (tích chặn), đổi mức giảm, cấp lại, thu hồi.
- **💳 Nạp chờ duyệt**: ✅ cộng / ❌ huỷ (khi không dùng SePay).
- **💵 Cộng/trừ tiền**: `@user 50000 lý do` hoặc `@user -20000 lý do`.

## 7. Tài liệu API cho đại lý

Gửi kèm khóa. Đại lý mua bằng **số dư của chính họ** trong bot (nạp như khách thường), giá đã trừ mức giảm.

```
Header: X-API-Key: sk_...      (hoặc Authorization: Bearer sk_...)

GET  /api/v1/me                 → số dư, mức giảm
GET  /api/v1/products           → [{id, name, description, price, list_price, stock}]
POST /api/v1/orders             body {"product_id": 1, "quantity": 2, "request_id": "id-cua-ban"}
                                → {order_id, total, items: [...], balance, replayed}
GET  /api/v1/orders/{order_id}  → xem lại đơn và hàng
```

- Hàng nguồn chậm: trả **202** + `"status": "pending"` → gọi lại cùng `request_id` sau ~10 giây để nhận hàng. `409 fulfillment_failed` = nguồn thiếu hàng, đã hoàn tiền.
- `request_id` (khuyên dùng): gửi lại cùng giá trị khi mạng lỗi sẽ nhận lại đơn cũ, không bị trừ tiền hai lần.
- Lỗi trả JSON `{"error": "...", "message": "..."}`: 401 sai khóa · 402 `insufficient_balance` · 403 `product_blocked` · 404 `product_not_found` · 409 `out_of_stock` / `product_inactive` · 400 `bad_quantity`.
- Trang thử API: `https://api.tenmien.com/docs`.
