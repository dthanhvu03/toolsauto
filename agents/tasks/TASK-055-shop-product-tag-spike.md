# TASK-055 — Khảo sát gắn giỏ hàng vào bài (spike, chưa code)

## Plan
PLAN-056 (phần giỏ hàng)

## Executor
Cần **Owner mở phiên trình duyệt thật** — không khảo sát được nếu chỉ đọc code.

## Vì sao chưa code

`grep -ri "product_tag|shopping|cart|giỏ hàng" app/` → **0 kết quả**. Không có gì để
sửa. Và luồng gắn sản phẩm phụ thuộc trạng thái của chính Page:

- Page phải bật **Shop / Cửa hàng** và đã duyệt
- Phải có sản phẩm trong catalog
- Bề mặt gắn sản phẩm khác nhau giữa composer feed, Reels và Meta Business Suite
- Một số khu vực/loại Page không có tính năng này

Viết selector mù cho một hộp thoại chưa từng nhìn thấy là cách chắc chắn nhất để ra
một tính năng "chạy trên máy em, hỏng ở máy khách".

## Việc phải làm khi có phiên

1. Mở Page nháp bằng đúng profile ToolsAuto đang dùng (`profiles/<account>`)
2. Trả lời: Page có mục **Cửa hàng** không? Catalog có sản phẩm không?
3. Mở composer soạn bài, chụp màn hình toàn bộ hộp thoại
4. Tìm nút gắn sản phẩm — ghi lại **nhãn tiếng Việt lẫn tiếng Anh** và `aria-label`
5. Bấm vào, ghi lại: hộp chọn sản phẩm mở dạng gì (dialog / panel), tìm sản phẩm
   bằng ô search hay danh sách, chọn xong nút xác nhận tên là gì
6. Làm lại y hệt trên **Reels** — Reels có thể không cho gắn sản phẩm
7. Ghi kết quả vào `agents/decisions/` dạng ADR nếu phát hiện giới hạn kiến trúc

## Đầu ra

Một PLAN mới (PLAN-057) với selector thật, hoặc một ADR ghi "Facebook không cho gắn
giỏ hàng qua bề mặt web tự động hoá được" — trường hợp đó phải **gỡ mục này khỏi mô
tả combo Page Master** trước khi bán tiếp.

## Không được làm

Không hứa với khách tính năng này trước khi có kết quả khảo sát.
