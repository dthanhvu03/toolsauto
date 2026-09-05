# ADR-012 — Sao lưu ngoại vi sang Google Drive

- **Ngày**: 2026-09-05
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-05
  ("tận dụng ổ drive 5 TB này đi em, em cho làm ui ux và backend để cấu hình")
- **Liên quan**: PLAN-057 (backup), ADR-011 (đã hết phạm vi)

## Bối cảnh

Backup Postgres hiện nằm ở `storage/db/backups/` — **cùng ổ đĩa với dữ liệu**. Hỏng
ổ `D:` là mất cả dữ liệu lẫn backup, đúng thứ backup sinh ra để chống. Đây là lỗ
hổng lớn nhất còn lại sau PLAN-057.

Owner có Google Drive **5 TB** (đang dùng 24,6 GB) và đã cài Drive for Desktop
(chưa đăng nhập nên chưa có ổ nào được gắn).

## Quyết định

Sao chép **có chọn lọc** sang Drive, cấu hình được từ trang `/app/settings`.

| Đưa lên Drive | KHÔNG đưa lên Drive |
|---|---|
| Bản dump database (`.sql`) | Database Postgres đang chạy |
| Video đã xử lý xong | **Profile trình duyệt** |

**Vì sao cấm hai thứ bên phải:** Drive đồng bộ liên tục, mà DB và profile trình
duyệt ghi liên tục. Xung đột đồng bộ làm **hỏng dữ liệu**, và hỏng âm thầm. Profile
hỏng đồng nghĩa mất phiên đăng nhập — tức mất tài khoản lần nữa.

## Ba nguyên tắc bắt buộc

1. **Sao chép, không di chuyển.** Bản chính luôn ở máy. Drive chỉ là bản thứ hai.
2. **Drive lỗi không được làm hỏng việc chính.** Chưa gắn ổ, mất mạng, hết dung
   lượng — đều chỉ ghi log cảnh báo. Backup vẫn tính là thành công vì bản local đã
   có; job đăng bài vẫn chạy tiếp.
3. **Không tự đoán đường dẫn.** Owner nhập đường dẫn thư mục Drive; hệ thống kiểm
   tra tồn tại và ghi được trước khi bật.

## Phạm vi

| Việc | File |
|---|---|
| Hằng số cấu hình | `app/config.py` |
| 4 mục trong trang settings | `app/core/settings.py` |
| Hàm sao chép an toàn | `app/core/storage/offsite.py` (mới) |
| Nối vào lệnh backup | `manage.py` |
| Test | `tests/test_offsite_copy.py` (mới) |

**Không cần viết UI**: trang `/app/settings` tự sinh giao diện từ `SETTINGS` theo
`section`, đã có sẵn lưu hàng loạt.

## Ngoài phạm vi

- Không dùng Google Drive API / OAuth. Drive for Desktop gắn ổ như thư mục thường ⇒
  chỉ cần thao tác file. Đơn giản hơn hẳn và không phải giữ khoá bí mật nào.
- Không đồng bộ hai chiều. Một chiều: máy → Drive.
- Không đưa `STORAGE_DIR` lên Drive.

## Hết hiệu lực

Sau khi 5 mục trong bảng phạm vi hoàn thành và test xanh.
