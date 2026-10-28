# PLAN-097 — Bot bán hàng số (store_bot) + API đại lý

- Executor: Claude Code (chủ bot giao trực tiếp 28/10/2026: "thêm tool mới ngoài cashbot, đặt thư mục ngang cashbot", mẫu FatCat Store)
- Trạng thái: code xong, chờ chủ bot cài `.env` + chạy thật

## Scope
- `store_bot/` (ngang `cashback_bot/`), DB riêng `data/store.sqlite`, không đụng cashback.
- Khách: xem sản phẩm, mua bằng số dư (giao hàng ngay; nhiều thì gửi file .txt), nạp tiền VietQR mã `NAPxxxxxx`, xem lại đơn.
- Admin `/admin`: sản phẩm (thêm/giá/sửa/ẩn), nhập kho dán nhiều dòng hoặc .txt, đăng kênh "🆕 HÀNG MỚI VỀ!" + nút 🛒 Mua ngay (deep link `?start=buy_<id>`), duyệt nạp, cộng/trừ tiền, thống kê.
- Khóa API đại lý: chỉ lưu SHA-256, giảm mặc định 2%, tích chặn từng sản phẩm, cấp lại thì thu hồi khóa cũ (giữ danh sách chặn).
- API FastAPI `/api/v1/{me,products,orders}`, `request_id` chống trừ tiền hai lần; webhook SePay tự cộng nạp (tắt khi không có khóa).

## Bước 2 (28/10): lấy hàng từ FatCat Store
- Chủ bot là đại lý FatCat (@Zusem10, khóa `FATCAT_API_KEY`). Chủ bot chọn: bán bằng giá lẻ FatCat (giá đại lý ÷ 0,98), bán tất cả món FatCat mở cho khóa, tự cập nhật.
- `upstream.py` (client theo https://api.fatcatstore.click/docs), `fulfill.py` (lấy hàng / đồng bộ), DB thêm cột `products.upstream_*`, `orders.status/refunded/upstream_*`, bảng `order_items` (ALTER tự chạy trong migrate).
- Đơn FatCat: trừ ví khách + ghi `pending` trong 1 giao dịch → gọi `/api/buy` với request_id ngẫu nhiên → complete / partial (hoàn phần thiếu) / rejected 4xx (hoàn đủ, báo admin) / chưa rõ (timeout, 202, 429, 5xx: luồng nền gọi lại 10 giây/lần cùng request_id, báo admin sau 15 phút).
- Đồng bộ 3 phút/lần; tăng ≥ 5 hoặc từ 0 có lại → đăng kênh, mỗi món cách nhau ≥ 20 phút; lần đồng bộ đầu không đăng.

## Không làm
- Không tự gọi Telegram / SePay thật, không sửa `.env`, không cài systemd.

## Proof bước 2
- 40 test qua (thêm 10: giá lẻ, đồng bộ / ẩn món, đăng kênh 1 lần, mua đủ, thiếu → hoàn, 402 → hoàn + báo admin, nguồn chậm → gọi lại cùng request_id giao đúng 1 lần, API đại lý không dưới giá vốn + 202, map mã HTTP).
- Chạy thử trên bản sao DB thật + GET thật FatCat (không gọi /api/buy): migrate 2 lần không lỗi; 10 món, giá bán khớp kênh FatCat (155.000đ, 20.666đ); ví FatCat 20.803đ.

## Proof
- `tests/test_store_bot.py` 30 test qua (gồm 8 luồng mua đồng thời 1 món cuối: đúng 1 người mua được, tiền khớp).
- `ruff check store_bot` sạch. Chạy thử `python -m store_bot.api_server` với DB tạm: `/health` 200, `/api/v1/products` không khóa 401, `/docs` 200.
