# Brief #1 — "Xưởng nội dung" (thiết kế lại trang Nội dung viral)

> Dán brief này vào Claude Design (template **UI mockups**, Design system **ToolsAuto Cave**),
> kèm 2 ảnh hiện trạng: `2026-09-07-viral-hien-tai-top.png`, `2026-09-07-viral-hien-tai-bang.png`.
> Mỗi lần chỉ một màn hình. Xuất HTML (`</>`) khi ưng → Claude Code chuyển sang Jinja/HTMX.

## Bối cảnh (nói với Claude Design)

Đây là công cụ **một người dùng** (chủ tool, không có khách), chạy local trên laptop, giao diện
tối theme "Cave" (nền than, điểm nhấn cam "torch"). Người dùng làm video affiliate tiếng Việt:
tool **tải video demo sản phẩm** từ TikTok / YouTube Shorts / Facebook / Instagram, **ghép
intro/outro/hook/phụ đề/giọng đọc** (gọi là *reup*), rồi người dùng **tải file về đăng tay**
lên Fanpage (tự động đăng đang tắt vì mất tài khoản). Mỗi ngày ~2–6 video.

Trang hiện tại tên "Nội dung viral" đang gánh 4 việc chồng lên nhau trong một cột:
1. Ô **dán link** video + checkbox "Xử lý ngay"
2. Khối **Nguồn tự động** (kênh TikTok/YouTube tự quét mỗi giờ) — bảng 10 cột
3. **Bộ lọc** + chip đếm trạng thái
4. **Bảng video** (20 dòng): ảnh, tiêu đề/URL, lượt xem, trạng thái, nút Tải file/Thumbnail/Xoá

## Nỗi đau thật (đã quan sát, không đoán)

- Không thấy ngay **"hôm nay có gì để đăng"** — video READY lẫn với 11 video cũ DRAFTED trong cùng bảng; phải bấm chip lọc.
- Luồng thật là một **dây chuyền có trạng thái**: Nguồn → Mới → Đang xử lý → **Sẵn sàng đăng tay** → (Đã đăng, đánh dấu tay). UI hiện là *bảng phẳng*, không cho cảm giác dây chuyền.
- Sau khi tải file về đăng tay, **không có chỗ đánh dấu "đã đăng"** → video READY tích mãi.
- Khối Nguồn tự động chiếm chỗ dù mỗi tuần chỉ mở 1 lần để thêm kênh.
- Các lớp thêm (phụ đề / giọng đọc / nhạc) bật ở trang Cài đặt, nhưng trên hàng video **không thấy lớp nào đã áp** → bật xong không biết có ăn không.
- Hàng video có "Lần thử 1/3" và "Reup lại?" — thuật ngữ kỹ thuật, người dùng không cần.
- Mỗi video cần tối đa 3 hành động: **Tải file**, **Xem trước**, **Đánh dấu đã đăng** (mới). Xoá và Reup lại là phụ, nên ẩn vào menu.

## Yêu cầu thiết kế

1. **Bố cục "bảng dây chuyền"** (kanban ngang hoặc 3 vùng dọc): *Mới / Đang xử lý* · *Sẵn sàng đăng tay* (nổi bật nhất, đếm to) · *Đã đăng hôm nay*. Mặc định mở vào **Sẵn sàng đăng tay**.
2. **Thẻ video** thay cho hàng bảng: thumbnail 9:16 nhỏ, tiêu đề 2 dòng, nền tảng (icon), lượt xem gốc, thời lượng, **chip lớp đã áp** (phụ đề / giọng / nhạc / intro), 3 nút chính; menu "…" cho Xoá / Reup lại / Mở link gốc.
3. **Thanh "Nạp video"** gọn ở đầu: ô dán link + nút; "Nguồn tự động" thu thành **một nút/ngăn kéo bên** (drawer) mở khi cần, có số nguồn đang bật + lần quét cuối.
4. **Trạng thái hệ thống một dòng** ngay dưới tiêu đề: worker đang chạy hay tắt, key AI ổn/hỏng, 3 nguồn · quét cuối 20 phút trước. Mỗi mục bấm được.
5. Giữ **theme Cave** (dùng design system đã chọn), tiếng Việt có dấu, mật độ vừa phải cho màn 1440 px; có biến thể 1024 px.
6. Không vẽ tính năng chưa có: không "lên lịch đăng", không "phân tích hiệu quả".

## Ràng buộc kỹ thuật (để bản mockup chuyển được sang code)

- Backend là FastAPI + Jinja2 + **HTMX** (không SPA). Mỗi vùng là một fragment nạp bằng
  `hx-get`, cập nhật bằng sự kiện `refreshViralTable` / `refreshViralSources`. Thiết kế theo
  "vùng có thể thay từng phần", tránh hiệu ứng cần state phía client phức tạp.
- Trạng thái thật: `NEW`, `PROCESSING`, `REUP`, `DRAFTED` (đã tạo job — luồng cũ), `READY`,
  `FAILED`. "Đã đăng" là trạng thái **mới cần thêm** — đề xuất tên `POSTED`.
- Thumbnail có sẵn (`/viral/{id}/reup-thumb`), file reup có sẵn (`/viral/{id}/reup-preview`).
- Số liệu mẫu để vẽ: 9 READY (4 YouTube, 4 TikTok, 1 Facebook), 0 NEW, 0 PROCESSING, 11 DRAFTED cũ, 2 nguồn tự động.

## Tiêu chí ưng

- Mở trang lên, **trong 2 giây** biết: có bao nhiêu video sẵn sàng, cần làm gì.
- Mỗi video: tải – xem – đánh dấu, không quá 2 cú bấm.
- Không mất tính năng nào đang có (dán link, nguồn, lọc, xoá, reup lại, thumbnail).
