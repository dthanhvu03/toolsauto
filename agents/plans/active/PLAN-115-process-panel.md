# PLAN-115: Bảng tiến trình PM2 trên web — xem CPU / RAM, bật / tắt / khởi động lại

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-115 |
| **Status** | Approved — anh yêu cầu 31/10 («sao em không cấu hình bật tắt mấy cái này và hiển thị trên web») |
| **Executor** | Claude Code (vai UX; anh giao trực tiếp) |
| **Created** | 2026-10-31 |

---

## Vấn đề
- Máy lag vì thiếu RAM (7,8 GB, còn trống 0,7 GB). Muốn bật / tắt app (vd VieNeu_TTS giữ 1,4 GB) phải gõ `pm2` trong terminal.
- Trang SPA «Panel hệ thống» không có bảng PM2. Chỉ trang Classic có, mà danh sách app được phép điều khiển
  (`app/core/pm2_apps.PM2_SAFE_NAMES`) đã cũ:
  - **thiếu** Studio_Heavy, Studio_Light, VieNeu_TTS, DB_Backup;
  - còn tên các app FB / Threads đã bỏ.

## Thiết kế
- `app/core/pm2_apps.py`:
  - danh sách đúng theo `ecosystem.config.js` (test đối chiếu tên);
  - `APP_INFO` cho mỗi app: tên dễ hiểu, làm gì, tắt thì sao;
  - `PM2_LOG_MAP` thêm các app Studio.
- `app/core/process_control.py`:
  - `snapshot()`: `pm2 jlist` → từng app (trạng thái, CPU, RAM, uptime, số lần restart) + RAM máy (psutil) + VRAM GPU
    (nvidia-smi, có thì đọc);
  - `act(name, action)`: chỉ app trong danh sách, chỉ `start / stop / restart`, chạy `pm2 <action> <name>` (không qua shell)
    rồi `pm2 save` để máy khởi động lại vẫn giữ lựa chọn bật / tắt;
  - **Web_Dashboard không cho tắt từ web** (tắt là mất luôn trang), chỉ khởi động lại.
- API `GET /api/admin/processes`, `POST /api/admin/processes/{name}/{start|stop|restart}` (cookie đăng nhập chung của app).
- SPA «Panel hệ thống»:
  - bảng app: tên + mô tả, trạng thái, CPU, RAM (thanh so với RAM máy), chạy được bao lâu, số lần restart;
  - nút Bật / Tắt / Khởi động lại, hỏi lại trước khi tắt app quan trọng;
  - tự cập nhật mỗi 5 giây; ô RAM máy kèm gợi ý app nào đang giữ nhiều RAM.
- Bot cashback (systemd) **không** đưa vào — phần đó của phiên cashback, anh tự restart theo lệnh riêng.

## Scope
`pm2_apps.py`, `process_control.py` (mới), `admin_api/processes.py` (mới) + gắn vào router, SPA syspanel, test.

## Out of Scope
- Sửa `.wslconfig` (đã đề xuất riêng, chờ anh).
- VieNeu tự nhả model khi rảnh (PLAN riêng nếu anh muốn).
- Bỏ các nút cũ của hệ đăng bài trên trang này.

## Validation
- pytest với `pm2` giả: danh sách, chặn tên lạ / hành động lạ / tắt Web_Dashboard, có `pm2 save`; tên trong ecosystem đều nằm
  trong danh sách.
- ruff, lint-imports, tsc + build, trình duyệt thật (web tạm đọc PM2 thật, **không bấm tắt app thật**).

## Rollback
Bỏ route + bảng. `PM2_SAFE_NAMES` chỉ thêm tên, không đổi hành vi cũ.

## Execution Notes
- ✅ **Code xong (31/10), commit cục bộ — cần `pm2 restart Web_Dashboard`** (API + bản SPA mới). Không migration.
  - `app/core/pm2_apps.py`: thêm Studio_Heavy / Studio_Light / VieNeu_TTS / DB_Backup vào `PM2_SAFE_NAMES` (+ log map),
    `APP_INFO` (tên, làm gì, tắt thì sao, `can_stop`).
  - `app/core/process_control.py`: `snapshot()` (pm2 jlist + psutil + nvidia-smi), `act()` — whitelist tên / hành động, Web_Dashboard
    không tắt được; lệnh chạy **tách khỏi web** `setsid -f sh -c "pm2 <a> <n>; pm2 save"` (khởi động lại web từ chính nó không
    tự giết giữa chừng; tắt Studio_Heavy chờ render dở không treo request).
  - `admin_api/processes.py`: `GET /api/admin/processes`, `POST /api/admin/processes/{name}/{action}`.
  - SPA «Panel hệ thống»: ô RAM (WSL) / CPU / GPU + bảng `ProcessTable` (trạng thái, CPU, RAM có thanh, thời gian chạy, số lần
    restart, Tắt / Bật / Khởi động lại, hỏi lại kèm «tắt thì sao», «Đang tắt…» tới khi PM2 đổi trạng thái); bỏ 2 ô CPU/RAM cũ trùng.

**Verification Proof**:
```
$ unshare -n pytest tests/test_process_control.py → 9 passed (tên ecosystem ⊆ danh sách; chặn tên lạ / "VieNeu_TTS; rm -rf /" /
  hành động lạ / tắt Web_Dashboard; lệnh có `pm2 save`); test_overlap_cleanup + test_affiliate_on_post qua;
  test_admin_viral_sources_lists_channel hỏng vì cần Postgres thật (bị cắt mạng khi chạy test) — không liên quan.
$ ruff → All checks passed; lint-imports không vi phạm mới; tsc + npm run build ok
$ snapshot() trên PM2 thật (chỉ đọc): 7 app, VieNeu_TTS 1375 MB, DB_Backup stopped (can_start), Web_Dashboard can_stop=False
# Trình duyệt thật (web tạm: số liệu từ pm2 jlist thật đọc 1 lần, nút bật / tắt chỉ đổi trạng thái giả — KHÔNG đụng PM2 thật):
#   Tắt VieNeu → hỏi lại «Tắt thì: Lồng tiếng tự dùng giọng edge-tts…» → «Đang tắt…» → «Đã tắt» + nút Bật → Bật → «Đang chạy»;
#   lệnh gửi: "pm2 stop VieNeu_TTS; pm2 save", "pm2 start VieNeu_TTS; pm2 save"; Web_Dashboard không có nút Tắt;
#   cột thẳng hàng (x RAM = 736 cả 7 hàng); 390 px không tràn; 0 lỗi JS.
```
