# ADR-044 — Link "📱 Mở trên điện thoại" trong tin video

- **Ngày**: 2026-09-11
- **Trạng thái**: **ĐÃ DUYỆT** — Owner: *"anh muốn từ điện thoại"* → *"tools mình có làm hỗ trợ
  được gì không"* → *"em triển khai thử đi"*.
- **Liên quan**: ADR-027 (tin video), ADR-030 (đường dẫn Drive không bấm được), ADR-042 (Đã đăng)

## Bối cảnh

Đăng từ điện thoại là **Chia sẻ** (share sheet) video vào app Facebook/TikTok/Threads. Video
≤ 50 MB đã về Telegram nên chia sẻ được ngay. Video lớn hơn (như #984: 148 MB) thì Telegram
không chở nổi, tin chỉ có dòng Drive **không bấm được** — Owner phải tự lần vào app Drive.

Web của tool đã có nút tải file cho mọi kích thước, nhưng đang nghe ở `127.0.0.1` nên điện
thoại không với tới, và tin Telegram không có link.

## Đội mũ

**Kỹ thuật.** Ba mảnh: (1) web nghe trên mạng nhà — `start.ps1 -Lan` ⇒ `0.0.0.0`; có màn đăng
nhập sẵn nên không mở toang. (2) Ô Thiết lập `PUBLIC_BASE_URL` (ví dụ `http://192.168.1.10:8002`)
— tool **không tự đoán IP**: đoán sai là link chết mà không ai biết. (3) Tin video thêm dòng
`📱 Mở trên điện thoại` trỏ tới route tải file **có `Content-Disposition: attachment`** để Safari
lưu vào Files thay vì phát inline (phát inline thì share sheet không thấy file).

**Phản biện.** Ngoài nhà link chết ⇒ ghi rõ trong ô Thiết lập: dùng Tailscale nếu cần; không hứa
"mọi nơi". Chưa đặt ô ⇒ **không in link** — không in link giả. Bảo mật: route nằm sau đăng nhập
như mọi route khác; lần đầu Safari hỏi đăng nhập một lần.

**UX.** Link chỉ có ý nghĩa khi video **không** về được Telegram; nhưng in luôn cả khi có video
(rẻ, và Owner có thể muốn lấy bản gốc chất lượng đầy đủ thay vì bản Telegram nén).

**Kinh doanh.** Đây là thứ làm bước cuối cùng của vòng còn *một chạm* mà không đụng tài khoản
Facebook (không API, không giả lập). Rẻ nhất trong ba mức đã bàn; hai mức kia (Bot API riêng
2 GB, link Drive API) để sau khi mức này chạy thật.

## Quyết định

| Việc | File |
|---|---|
| Ô `PUBLIC_BASE_URL` (mục Tích hợp) + alias `/caidat diachi` | `core/settings.py`, `telegram_bot/command_handler.py` |
| Route `/viral/{id}/phone` — file `_reup` dạng attachment, tên theo tiêu đề | `viral_intake/router.py` |
| Tin video có dòng `📱 Mở trên điện thoại` khi ô đã đặt | `notifier/formatting.py`, `notifier/service.py` |
| `start.ps1 -Lan` ⇒ nghe `0.0.0.0` + in địa chỉ LAN | `start.ps1` |

## Proof

Test: tin có `href` khi có địa chỉ, KHÔNG có link khi chưa đặt; `_phone_url` ghép đúng route và
bỏ `/` cuối; route `/viral/{id}/phone` qua `TestClient` trả `attachment; filename*=…"1 - Muốn
giàu.mp4"` (marker đã bóc), 404 khi chưa có file; `/caidat diachi …` ghi được. **1055 passed.**
Chưa có proof mở từ điện thoại thật — cần Owner chạy `start.ps1 -Lan` và đặt địa chỉ.

## Hết hiệu lực

Sau proof: đặt ô → tin có link; chưa đặt → không có link; route trả attachment với tên tiêu
đề; toàn suite xanh; Owner mở được link từ điện thoại cùng Wi‑Fi.
