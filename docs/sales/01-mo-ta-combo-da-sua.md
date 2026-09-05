# Combo Page Master — mô tả đã hiệu chỉnh theo đúng thực lực

> **Bản nháp cho Owner chỉnh giọng văn.** Nội dung đã đối chiếu với code thật
> ngày 2026-09-05. Mọi dòng trong phần "Làm được" đều có bằng chứng chạy thật hoặc
> test xanh. Xem `docs/sales/00-doi-chieu-thuc-luc.md` để biết căn cứ từng mục.

---

## Tool này là gì

**Xưởng sản xuất nội dung cho Page Facebook.** Nó lo phần tốn thời gian nhất — tìm
video đang viral, tải về, xử lý, viết caption — để bạn chỉ còn việc duyệt và đăng.

---

## Làm được gì

### Sản xuất nội dung (phần mạnh nhất)
- **Tìm video viral trên TikTok theo từ khoá** — tự chấm điểm kênh theo lượt xem
  trung bình và tần suất đăng, chỉ giữ kênh đáng theo dõi
- **Tải video từ TikTok, YouTube, Facebook, Instagram** khi bạn dán link
- **Xử lý video**: ghép intro/outro thương hiệu, tạo ảnh thumbnail, xử lý tránh
  trùng bản gốc
- **AI viết caption** (Google Gemini)

### Đăng bài Facebook
- **Reels** (video)
- **Bài feed** (chữ thuần, hoặc chữ kèm ảnh)
- **Tin (Story)** — ảnh hoặc video
- **Tự động comment** dưới bài vừa đăng — nơi đặt link, vì Facebook giảm hiển thị
  bài có link trong nội dung
- **Comment kèm ảnh**

### Điều phối
- Hàng đợi và hẹn giờ đăng
- Nghỉ giữa các bài (cooldown), giới hạn số bài mỗi ngày
- Quản lý nhiều tài khoản, mỗi tài khoản một profile trình duyệt riêng
- Bảng điều khiển web: tạo bài, duyệt trước khi đăng, xem log
- Thông báo qua Telegram

---

## Chưa làm được — nói trước để bạn không mua nhầm

| Mục | Tình trạng |
|---|---|
| **Gắn giỏ hàng / gắn sản phẩm vào bài** | **Chưa có.** Đang khảo sát xem Facebook có cho phép không |
| **Link rút gọn đếm lượt click** | **Đang sửa.** Tính năng chưa dùng được, sẽ thông báo khi xong |
| Tìm video trên **Douyin** | **Không hỗ trợ.** Douyin chặn theo vùng, cần hạ tầng riêng |
| Tìm video trên **YouTube / Facebook theo từ khoá** | Chưa có. Hai nguồn này hiện **chỉ tải được khi bạn dán link** |
| Link bấm được **trong Story** | Chưa kiểm chứng Facebook có cho phép hay không |

---

## Bạn cần biết trước khi dùng

Tool điều khiển trình duyệt thật, đăng nhập bằng chính tài khoản Facebook của bạn.
Điều này có hai hệ quả:

1. **Không cần xin quyền API của Facebook** — cài là chạy
2. **Facebook có thể khoá tài khoản** — như với bất kỳ hình thức tự động hoá nào

Rủi ro số 2 **giảm được gần hết bằng cách thiết lập đúng cấu trúc**, và điều này
đúng kể cả khi bạn đăng bài hoàn toàn thủ công.

**Bắt buộc làm trước khi chạy tool:** xem
`docs/sales/02-checklist-thiet-lap-an-toan.md` — 5 bước, khoảng 15 phút.

Điểm quan trọng nhất: **đừng để một tài khoản cá nhân làm admin duy nhất của Page.**
Nếu tài khoản đó bị khoá, mọi Page nó quản lý sẽ mất theo và không lấy lại được.
Làm đúng checklist thì mất tài khoản cũng **không mất Page**.

---

## Khuyến nghị cách dùng

**Người mới bắt đầu:** dùng tool cho phần sản xuất nội dung, tự bấm đăng. Đăng một
bài mất khoảng 2 phút, mà bạn tiết kiệm được 20–30 phút mỗi video ở khâu tìm và xử
lý. Cách này gần như không có rủi ro tài khoản.

**Khi đã chạy ổn định và Page đã nằm an toàn trong Business Manager:** bật tự động
đăng để tăng quy mô.
