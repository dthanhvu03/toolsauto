# ToolsAuto — Training điều phối (Owner)

Mục tiêu: biết **bật đúng process**, **đọc trạng thái**, **duyệt job**, và **xử lý blocker** mà không cần đụng code.

---

## 1) Lệnh khuyến nghị (PLAN-048)

```powershell
# Một lệnh: Web + Maintenance + FB Publisher (supervisor, singleton)
.\start.ps1 -Stack

# hoặc
.\venv\Scripts\python.exe manage.py stack --host 127.0.0.1 --port 8002
```

State: `storage/db/config/local_stack.json`. Không mở 2 stack cùng lúc (lock).

| Process | Lệnh tay (legacy) | Vai trò |
|--------|-------------------|---------|
| **Web** | `.\start.ps1` (không `-Stack`) | UI duyệt job, affiliates, settings |
| **Maintenance** | `python -m app.features.system_panel.workers.maintenance` | Viral ingest/scan, recover, metrics |
| **FB Publisher** | `python -m app.features.facebook.workers.publisher` | Claim PENDING → FFmpeg/DRM → đăng |

`start.ps1` **không** `-Stack` chỉ web. Publisher thiếu → approve cũng không đăng.

**Quy tắc:** mỗi loại worker chỉ **1 process**. Stack tự tránh spawn trùng nếu đã có instance.

Postgres: `docker start toolsauto_postgres` (port **5434**).

---

## 2) Pipeline nội dung (điều phối tay + auto)

```
TikTok / viral → (Maintenance) material + reup
       ↓
AI draft caption/style → Job DRAFT (chưa đăng)
       ↓
Owner APPROVE trên UI (hoặc Telegram)
       ↓
Job PENDING + schedule_ts đến hạn
       ↓
Publisher claim → process video (DRM watermark nếu ON) → đăng Reel
       ↓
DONE → (sau ~24h) Maintenance metrics views
       ↓
(Optional) Job COMMENT affiliate → Publisher comment
```

**Không auto-approve DRAFT** (PLAN-048 hướng D).

**Affiliate lookup:** AI nhận keyword nhưng kho chưa khớp → queue `PENDING_LOOKUP`. Owner dán link / thêm kho.

---

## 3) Checklist mỗi buổi

1. Postgres Up? Web mở được?
2. Đang chạy `start.ps1 -Stack` (hoặc đúng 1 maint + 1 publisher)?
3. Claim gate: dựa trên **Chrome ToolsAuto** (`storage/profiles`), không phải Chrome cá nhân.
4. Jobs: DRAFT chờ duyệt? PENDING? FAILED?
5. Lookup panel còn chờ tra Shopee?
6. Maintenance `FB backlog >= 10`? → ưu tiên duyệt/đăng, ingest tạm skip.

---

## 4) Đọc trạng thái nhanh

| Hiện tượng | Ý nghĩa | Việc Owner làm |
|------------|---------|----------------|
| Publisher `toolsauto=N` Pausing claim | Browser ToolsAuto thật sự cao | Đợi job xong / orphan purge hourly |
| Chrome máy 50+ nhưng vẫn claim được | Đúng (gate đã scoped) | Không cần đóng Chrome cá nhân |
| Job `PENDING` từ DRAFT chưa duyệt | Chờ Owner | Approve trên UI |
| `PENDING_LOOKUP` | Thiếu link affiliate | Dán URL / thêm kho |
| Maintenance skip heavy | Backlog FB ≥ 10 | Duyệt/đăng bớt |
| Account INVALID | Cookie chết | Verify login lại |

---

## 5) Settings hay đụng

- `DRM_ENABLED` + `FFMPEG_ENABLED` + `DRM_WATERMARK_TEXT`
- `SAFE_MODE`
- `worker.publisher.max_browser_instances` (default 15) — áp dụng cho **ToolsAuto** browsers

---

## 6) Bài tập điều phối (10 phút)

1. Chạy `.\start.ps1 -Stack` (tắt các web/maint/publisher tay trùng trước nếu cần).
2. Xem log `[STACK] ensure web=… maint=… publisher=… chrome_ta=…`
3. Approve 1 DRAFT (nếu muốn đăng) → chờ Publisher `CLAIM` / `DONE`.

**Đạt:** stack một lệnh + hiểu approve vẫn tay = điều phối OK.
