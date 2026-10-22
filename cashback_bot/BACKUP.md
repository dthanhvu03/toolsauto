# Khôi phục Cashback SQLite

Lệnh tạo bản sao, không sửa file đang chạy:

```bash
python -m cashback_bot.backup
```

File nằm ở `CASHBACK_BACKUP_DIR` (mặc định `./data/backups`), tên `cashback-YYYYMMDDTHHMMSSZ.sqlite`. Bản sao được tạo bằng SQLite Backup API rồi kiểm tra `integrity_check`. Số bản giữ lại là `CASHBACK_BACKUP_KEEP` (mặc định 14).

Chưa có lịch tự chạy. Khi cần, gọi lệnh trên bằng tay hoặc một cron bên ngoài. Không bật cron trên production từ task này.

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
