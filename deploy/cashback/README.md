# Chạy hai bot cashback bằng systemd (PLAN-087)

Máy WSL đã bật `systemd=true` (`/etc/wsl.conf`). Hai unit có `Restart=always`: bot bị tắt (lỗi, hết RAM) thì sau 10 giây tự chạy lại.
Bot không tự chạy lại khi thoát mã 2 (thiếu cấu hình `.env`) hoặc mã 3 (đã có bot khác đang chạy).

## Cài lần đầu (chủ bot chạy, quyền root)

Hai bot đang chạy bằng `nohup` phải dừng trước. Nếu không, bản systemd thấy khoá file, thoát mã 3 và không chạy.

```bash
cd /home/vu/toolsauto
cp deploy/cashback/cashback-bot.service deploy/cashback/cashback-zalo.service /etc/systemd/system/
cp deploy/cashback/logrotate-cashback /etc/logrotate.d/cashback
systemctl daemon-reload
pkill -TERM -f 'python -m cashback_bot.zalo_bot'; pkill -TERM -f 'python -m cashback_bot$'; sleep 3
systemctl enable --now cashback-bot cashback-zalo
systemctl status cashback-bot cashback-zalo --no-pager
```

## Hằng ngày

| Việc | Lệnh |
|---|---|
| Restart cả hai bot sau khi đổi code (đã cài 2026-10-25) | `systemctl restart cashback-bot cashback-zalo` |
| Xem trạng thái | `systemctl status cashback-bot cashback-zalo --no-pager` |
| Dừng hẳn một bot | `systemctl stop cashback-zalo` (bot không tự chạy lại cho tới `start`) |
| Xem log | `tail -f logs/cashback_bot.log` / `logs/cashback_zalo.log` (vẫn là file cũ) |

Khi đã cài unit, tin báo admin (bot Zalo dừng, bot Telegram dừng, hai bot khác code) tự ghi lệnh `systemctl restart …` thay cho lệnh `nohup`.

## Gỡ (quay về nohup)

```bash
systemctl disable --now cashback-bot cashback-zalo
rm /etc/systemd/system/cashback-bot.service /etc/systemd/system/cashback-zalo.service
systemctl daemon-reload
```

## Log

`/etc/logrotate.d/cashback` xoay hai file log mỗi tuần, giữ 8 tuần, nén bản cũ. Dùng `copytruncate` vì bot giữ file mở.
Thử không ghi gì: `logrotate -d /etc/logrotate.d/cashback`.

## Backup

- Bot tự backup mỗi ngày: `data/backups/cashback-YYYYMMDDTHHMMSSZ.sqlite`.
- Backup chạy tay (`.venv/bin/python -m cashback_bot.backup`) có tên `cashback-manual-…` và được dọn riêng, nên không đẩy mất bản tự động.
- Mỗi nhóm giữ `CASHBACK_BACKUP_KEEP` bản (hiện 60).
- Chép ra ngoài máy (D3, PLAN-094): Google Drive qua rclone, **mã hoá trước khi gửi**. Hướng dẫn cài ở mục dưới.

## Backup ngoài máy (Google Drive, mã hoá)

`cashback-offsite.timer` chạy mỗi ngày lúc 03:30 (giờ máy). Mỗi lần chạy:
- chép bản backup mới nhất lên Drive;
- tải lại về để so khớp, xác nhận bản trên Drive mở được;
- giữ 30 bản mới nhất (`CASHBACK_OFFSITE_KEEP`).

Kết quả hiện ở `/admin` → 🛠 Vận hành, dòng "Backup ngoài máy". File trên Drive đã mã hoá: lộ tài khoản Google cũng không đọc được.

Bot không đụng tài khoản Google hay mật khẩu mã hoá. Mọi bước dưới đây do chủ bot tự làm.

**1. Cài rclone** (quyền root)
```bash
curl https://rclone.org/install.sh | bash
rclone version
```

**2. Nối Google Drive**: `rclone config`, rồi trả lời theo thứ tự:
- `n` (remote mới) → tên `gdrive` → loại `drive`.
- `client_id`, `client_secret`: Enter (bỏ trống).
- `scope`: chọn `drive.file` (rclone chỉ thấy file do nó tạo, không đọc được file khác trong Drive).
- `root_folder_id`, `service_account_file`: Enter.
- Advanced config: `n`.
- Auto config: `y`. rclone in ra một link. Nếu WSL không tự mở trình duyệt, chép link vào trình duyệt Windows, đăng nhập Google và cho phép.
- Shared drive: `n` → `y` (lưu).

**3. Thêm lớp mã hoá**: vẫn trong `rclone config`:
- `n` → tên `cashback-crypt` → loại `crypt`.
- `remote`: `gdrive:cashback-backup`.
- `filename_encryption`: `standard`; `directory_name_encryption`: `true`.
- Mật khẩu: chọn `y` rồi **tự gõ một mật khẩu dài**. Mật khẩu thứ hai (salt): chọn `g` để tạo ngẫu nhiên, rồi **chép lại**.
- Advanced config: `n` → `y` → `q` (thoát).

> ⚠️ **Ghi hai mật khẩu ở bước 3 ra chỗ khác** (sổ tay, trình quản lý mật khẩu), không để trên máy này. Máy hỏng mà mất mật khẩu thì bản trên Drive không mở được.
> File `/root/.config/rclone/rclone.conf` giữ quyền vào Drive. Không gửi file này cho ai, không commit: `chmod 600 /root/.config/rclone/rclone.conf`.

**4. Thử remote**
```bash
rclone mkdir cashback-crypt:
rclone lsf cashback-crypt:
```
Lệnh thứ hai không báo lỗi là được (thư mục còn trống).

**5. Khai remote cho bot**: chủ bot tự thêm một dòng vào `/home/vu/toolsauto/.env`:
```
CASHBACK_OFFSITE_REMOTE=cashback-crypt:
```

**6. Chạy thử một lần**
```bash
cd /home/vu/toolsauto && .venv/bin/python -m cashback_bot.offsite; echo "exit=$?"
rclone lsf cashback-crypt:
```
Kết quả đúng: `exit=0`, log có `backup ngoài máy ok file=…`, và `lsf` hiện tên file `cashback-…sqlite`.

**7. Cài lịch chạy mỗi ngày**
```bash
cp deploy/cashback/cashback-offsite.service deploy/cashback/cashback-offsite.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cashback-offsite.timer
systemctl list-timers cashback-offsite.timer --no-pager
```

**Khôi phục từ Drive** (khi máy hỏng, sau khi cài lại rclone với đúng hai mật khẩu ở bước 3):
```bash
rclone lsf cashback-crypt:
rclone copyto cashback-crypt:cashback-YYYYMMDDTHHMMSSZ.sqlite /tmp/restore.sqlite
.venv/bin/python -c "from cashback_bot.backup import restore_database; restore_database('/tmp/restore.sqlite', 'data/cashback-restored.sqlite')"
```
Kiểm tra `data/cashback-restored.sqlite`, dừng hai bot, rồi mới đổi tên file thành `data/cashback.sqlite`.
