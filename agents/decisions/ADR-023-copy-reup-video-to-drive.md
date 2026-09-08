# ADR-023 — Nối thật ô "Chép video đã xử lý" vào luồng reup

- **Ngày**: 2026-09-08
- **Trạng thái**: **ĐÃ DUYỆT** — Owner yêu cầu trực tiếp 2026-09-08: "các video phải vào
  thiết lập drive"
- **Liên quan**: **ADR-012 (bỏ dở đúng mục này)**, ADR-018 (READY), ADR-014

## Bối cảnh

ADR-012 ghi rõ trong bảng "Đưa lên Drive": **Video đã xử lý xong**. Hạ tầng cũng đã dựng
đủ: `offsite.SUBDIRS` có sẵn `{"video": "videos"}`, `copy_out(src, kind)` cam kết không
bao giờ ném lỗi, và `SettingSpec DRIVE_COPY_VIDEOS` ("Chép video đã xử lý") hiện trên
`/app/settings`.

**Nhưng không dòng code nào đọc `DRIVE_COPY_VIDEOS`.** Chỗ duy nhất gọi `copy_out` là
`manage.py db backup` với `kind="backup"`. Owner bật ô đó lên và chờ video xuất hiện trong
Drive — không bao giờ có.

Đây là **nhãn nói dối** — cùng loại lỗi với nhãn `.webp` hứa định dạng mà backend từ chối
(phiên 2026-09-05). ADR-012 tuyên bố hết hiệu lực khi "5 mục trong bảng phạm vi hoàn thành",
nhưng mục này chưa từng hoàn thành.

## Quyết định

1. `offsite.copy_video_if_enabled(src) -> Path | None`: kiểm `DRIVE_COPY_VIDEOS` (mặc định
   tắt) rồi gọi `copy_out(src, "video")`. Đặt cạnh logic Drive khác để người gọi chỉ còn
   một dòng, và để lần sau tìm là thấy.
2. Gọi trong `processor.py` **ngay sau khi file `_reup` hoàn tất**, tại một điểm chung cho
   **cả hai nhánh** — nhánh `READY` (không tài khoản, ADR-018) và nhánh tạo job. Video đăng
   tay càng cần lên Drive vì Owner tải bằng điện thoại.
3. Giữ nguyên ba nguyên tắc ADR-012: **chép chứ không di chuyển**; **Drive lỗi không làm
   hỏng việc chính** (chỉ ghi log, material vẫn `READY`/`DRAFTED`); **không đụng DB đang
   chạy hay profile trình duyệt**.
4. Sửa mô tả ô trong `settings.py` cho khớp thực tế: nói rõ chép **video `_reup`** sau khi
   xử lý xong, và cảnh báo video nặng tốn băng thông.

## Phạm vi

| Việc | File |
|---|---|
| Hàm có kiểm cờ | `app/core/storage/offsite.py` |
| Điểm gọi (≤4 dòng) | `app/features/viral_intake/processor.py` |
| Mô tả ô cho khớp | `app/core/settings.py` |
| Test | `tests/test_offsite_video.py` (mới) |

## Ngoài phạm vi

- Không chép video gốc chưa xử lý (chỉ bản `_reup`).
- Không dọn bản cũ bên Drive (nợ đã ghi từ ADR-012).
- Không chép thumbnail.
- Không đổi `copy_out` / `check_root` / `get_root`.

## Hết hiệu lực

Sau proof: bật `DRIVE_COPY_ENABLED` + `DRIVE_COPY_VIDEOS` trỏ vào một thư mục thật, chạy
một material tới `READY` ⇒ file `_reup.mp4` xuất hiện trong `<root>/videos/`; tắt cờ ⇒
không chép; thư mục Drive sai ⇒ chỉ ghi log, material vẫn `READY`.
