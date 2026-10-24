# Backup và khôi phục Cashback SQLite

## Tự động (Production Safety Hardening V1)

Bot tự backup **mỗi 24 giờ** trong vòng lặp chính (`poller._check_backup`). Không cần cron:

- Dùng SQLite Backup API, ghi ra `cashback-YYYYMMDDTHHMMSSZ.sqlite.partial`, kiểm tra `integrity_check` và đủ các bảng chính, rồi mới đổi tên. File 0600, thư mục 0700.
- Sau khi tạo, bot mở lại bản vừa tạo ở chế độ chỉ đọc để kiểm tra như lúc khôi phục.
- Giữ `CASHBACK_BACKUP_KEEP` bản (mặc định 14, sàn tối thiểu 3). Chỉ file đúng mẫu tên `cashback-<UTC>Z.sqlite` mới bị dọn; file khác trong thư mục không bao giờ bị xoá.
- Thành công: log `backup ok file=… tables=… links=…`, lưu `bot_state.backup_last_ok`.
- Thất bại: log `backup tự động thất bại`, báo admin (`backup_failed`), thử lại sau 1 giờ.

**Không cài thêm cron cho cùng việc này.** Nếu sau này muốn chạy khi bot tắt, thay bằng một dòng cron
`python -m cashback_bot.backup` và bỏ `_check_backup`; không chạy cả hai.

Chạy tay khi cần (ví dụ ngay trước khi triển khai):

```bash
cd /home/vu/toolsauto && umask 077 && .venv/bin/python -m cashback_bot.backup
```

Lệnh trả mã 1 nếu backup lỗi.

## Ngoài máy chủ

`OFFSITE_BACKUP = NOT CONFIGURED`. Backup hiện nằm cùng ổ đĩa với DB: hỏng ổ hoặc mất máy là mất cả hai.
Đề xuất (cần chủ bot duyệt nơi lưu): mã hoá bằng `age` hoặc `gpg` với khoá chỉ chủ bot giữ, rồi chép bản đã mã hoá
sang ổ ngoài hoặc dịch vụ lưu trữ. Không upload DB chưa mã hoá. Backup có số tài khoản ngân hàng khách khai.

## Khi database hỏng hoặc mất

1. Dừng process `python -m cashback_bot`. Không xóa file hỏng trước khi có bản sao.
2. Chọn bản `cashback-*.sqlite` mới nhất.
3. Phục hồi ra một file mới, không ghi đè `data/cashback.sqlite` đang mở:

```bash
python - << 'PY'
from pathlib import Path
from cashback_bot.backup import restore_database
restore_database(
    Path("data/backups/cashback-YYYYMMDDTHHMMSSZ.sqlite"),
    Path("data/cashback.restore.sqlite"),
    protected=Path("data/cashback.sqlite"),
)
PY
```

4. Mở `data/cashback.restore.sqlite` bằng công cụ đọc và kiểm tra số dòng `link_requests`.
5. Đổi tên file đang chạy sang `cashback.sqlite.broken`, rồi đổi tên bản restore thành `data/cashback.sqlite`.
6. Chạy lại bot. Offset và Sub ID nằm trong bản sao, không tạo lại link cũ.

Nếu `integrity_check` không phải `ok`, đừng dùng bản đó. Lấy bản cũ hơn.

Backup chứa Telegram user id và Sub ID. Giữ trong máy, không đưa vào git, không gửi ra chat.
