# TASK-057 — Chạy thật 5 luồng đang ở mức B

- **Người làm**: Owner (cần trình duyệt + Page thật, Claude không làm thay được)
- **Thời gian ước tính**: ~30 phút
- **Chặn bởi**: phải dựng xong cấu trúc theo `docs/sales/02-checklist-thiet-lap-an-toan.md`
- **Mục đích**: nâng 5 mục từ **mức B → mức A** trong `docs/sales/00-doi-chieu-thuc-luc.md`

## Vì sao cần

5 tính năng của PLAN-052→056 đều **test xanh nhưng chưa chạm Facebook lần nào**.
Test xanh chỉ chứng minh code chạy đúng logic mình nghĩ — không chứng minh Facebook
còn giữ nguyên giao diện mà selector đang bám vào. Bốn luồng này viết tháng 8, đến
nay chưa từng gặp Facebook thật.

**Luật ở bảng đối chiếu: mức B chỉ lên A khi đã chạy thật.** Không có lượt chạy này
thì không được đưa vào bất kỳ mô tả bán hàng nào.

## Chuẩn bị

- [ ] 1 Page nháp (không phải Page đang kinh doanh)
- [ ] Tài khoản CHẠY đã có quyền **Biên tập viên** trên Page đó
- [ ] 1 ảnh `.jpg`, 1 video ngắn `.mp4` (~30s), 1 video dài `.mp4` (**>5 phút**)
- [ ] Bật stack: `.\start.ps1 -Stack`
- [ ] Mở sẵn cửa sổ log để đọc lỗi khi có

## Thứ tự chạy — rẻ và ít rủi ro trước

### 1+2. Bài feed qua hàng đợi, và lấy `post_url` — PLAN-052 + PLAN-053

Hai cái này **cùng một lần đăng**.

1. Tạo job **FEED**, chữ thuần, hẹn giờ quá khứ để nó chạy ngay
2. Chờ hàng đợi nhặt — **đây chính là thứ cần chứng minh**: trước PLAN-052 job FEED
   nằm `PENDING` vĩnh viễn, không bao giờ được claim

**Cần ghi lại:**
- Job có chuyển `PENDING → RUNNING → DONE` không? (PLAN-052)
- Log có bắt được `post_url` của bài vừa đăng không? (PLAN-053)
- Vào Page xem bài có thật không

⚠️ Rủi ro đã biết: PLAN-053 vá chỗ *bắt nhầm link bài của người khác khi cuộn feed*.
Nên phải **đối chiếu `post_url` trong log với link bài thật của mình**, không chỉ xem
có link hay không.

### 3. Comment kèm ảnh — PLAN-055

Dùng chính bài vừa đăng ở bước 1.

1. Tạo job **COMMENT** trỏ vào `post_url` đó, có `comment_image_path` là ảnh `.jpg`

**Cần ghi lại:** comment có lên không, **ảnh có đính kèm không** (đây mới là phần mới,
comment chữ thì đã chạy thật từ 30/07).

### 4. Đăng Story — PLAN-054

1. Tạo job **STORY** với ảnh
2. Nếu chạy được thì làm thêm một lần với video ngắn

**Cần ghi lại:**
- Tin có lên không
- **Chữ phủ lên tin có bấm được thành link không** — đây là câu hỏi mở từ lâu và
  quyết định có được quảng cáo "link aff trong story" hay không
- Tin đăng đúng **danh nghĩa Page**, không phải danh nghĩa cá nhân (PLAN-054 có
  chặn nhầm chỗ này — kiểm xem chặn có đúng không)

### 5. Video dài — PLAN-056

Làm **cuối cùng** vì lâu nhất và dễ gãy nhất.

1. Tạo job **POST** (Reels) với video **>5 phút**

**Cần ghi lại:**
- Có chờ đủ đến khi upload xong không, hay bỏ cuộc giữa chừng
- Có dừng sớm khi thấy preview không (tối ưu của PLAN-056)
- Tổng thời gian chờ — trần đang đặt là **420 giây**

⚠️ Nếu video dài hơn 7 phút mà chưa upload xong, job sẽ bỏ cuộc. Đó là **giới hạn có
chủ ý**, không phải lỗi.

## Sau khi chạy xong

1. Cập nhật `docs/sales/00-doi-chieu-thuc-luc.md`: mục nào chạy được thì đổi **B → A**,
   ghi **ngày + bằng chứng**
2. Mục nào gãy thì ghi lỗi cụ thể vào đây, **giữ nguyên mức B**, không tự nâng
3. Riêng "link trong Story": chạy được thì mới thêm vào mô tả; không thì **gỡ hẳn**,
   đừng để dạng "sắp có"

## Ghi kết quả

| Luồng | Kết quả | Ngày | Bằng chứng / lỗi |
|---|---|---|---|
| Bài feed qua hàng đợi (PLAN-052) | | | |
| Lấy `post_url` (PLAN-053) | | | |
| Comment kèm ảnh (PLAN-055) | | | |
| Story ảnh (PLAN-054) | | | |
| Story video (PLAN-054) | | | |
| Link bấm được trong Story | | | |
| Video dài >5 phút (PLAN-056) | | | |
