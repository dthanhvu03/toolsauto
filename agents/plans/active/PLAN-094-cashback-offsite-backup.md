# PLAN-094 — Backup cashback ra ngoài máy (Google Drive, rclone crypt)

| | |
|---|---|
| Executor | Claude Code (chủ bot duyệt 2026-10-26, mục D3) |
| Trạng thái | ✅ Code đã merge vào main 2026-10-26. Chờ chủ bot cài rclone và đăng nhập Google (README bước 1–7) |
| Không đổi | Không đụng tài khoản Google, mật khẩu mã hoá hay `.env` (chủ bot tự thêm `CASHBACK_OFFSITE_REMOTE`) |

## Cách chạy

- `cashback_bot/offsite.py` (`python -m cashback_bot.offsite`), chạy bằng `cashback-offsite.timer` mỗi ngày 03:30. Tách khỏi bot để việc tải lên không chặn vòng poll.
- Mỗi lần chạy:
  - kiểm tra bản backup mới nhất trong máy (`integrity_check`);
  - `rclone copyto` lên remote;
  - tải lại về thư mục tạm, so sha256 và `integrity_check`;
  - giữ `CASHBACK_OFFSITE_KEEP` bản mới nhất (mặc định 30), chỉ xoá file đúng mẫu tên backup.
- Ghi `bot_state`: `offsite_last_ok`, `offsite_last_file`, `offsite_last_error`.
- 🛠 Vận hành có dòng "Backup ngoài máy": đỏ khi chưa cài, có lỗi, hoặc quá 26 giờ chưa chép được.
- Lỗi rclone chỉ ghi dòng cuối của stderr, tối đa 200 ký tự.

## File

- `cashback_bot/offsite.py`
- `cashback_bot/insights.py` (check `offsite`)
- `deploy/cashback/cashback-offsite.service`, `cashback-offsite.timer`
- `deploy/cashback/README.md` (hướng dẫn cài, khôi phục)
- `tests/test_cashback_offsite.py`

## Proof

- `pytest tests/test_cashback_*.py`: 808 passed. `ruff check`: sạch.
- Test (rclone giả chép qua thư mục tạm):
  - chép, tải lại, dọn còn 30 bản, không đụng file khác mẫu tên;
  - bản tải lại hỏng thì báo lỗi;
  - chưa cài rclone, chưa có backup;
  - rclone lỗi chỉ giữ dòng cuối.
