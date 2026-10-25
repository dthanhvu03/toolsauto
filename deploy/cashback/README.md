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
- Chép ra ngoài máy: chưa có. Chủ bot chọn nơi lưu (ổ khác, cloud) rồi mới làm.
