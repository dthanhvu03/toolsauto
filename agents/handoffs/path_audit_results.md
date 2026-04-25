# Path Audit Results — TASK-004 Phase 1

**Thực hiện bởi**: @Claude (Quality Control)  
**Ngày**: 2026-04-18  
**Phạm vi**: `app/`, `workers/` (loại trừ `venv`, `node_modules`, `storage`, `scripts/archive`)

---

## Tóm tắt

| Mức độ | Số lượng |
|--------|----------|
| 🔴 Critical (bypass config hoàn toàn) | 3 |
| 🟡 High (dùng BASE_DIR thay vì biến chuyên dụng) | 6 |
| 🟢 Archive (scripts/archive — thấp, không ưu tiên) | 26+ |

---

## 🔴 Critical — Cần sửa ngay

### 1. `app/routers/manual_job.py` — dòng 18–19
```python
# HIỆN TẠI (sai): tự định nghĩa lại BASE_DIR cục bộ thay vì import config
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANUAL_DIR = os.path.join(BASE_DIR, "content", "manual")
```
**Vấn đề**: Không import từ `app.config`, tự tính lại đường dẫn → không theo `STORAGE_LAYOUT_MODE`.  
**Fix**: `from app.config import CONTENT_DIR` → `MANUAL_DIR = CONTENT_DIR / "manual"`

---

### 2. `app/services/video_protector.py` — dòng 24, 82, 135
```python
# Dòng 24
EVIDENCE_FILE = BASE_DIR / "data" / "drm_evidence.json"

# Dòng 82
temp_dir = BASE_DIR / "content" / "temp" / "videoprotector"

# Dòng 135
temp_dir = BASE_DIR / "content" / "temp"
```
**Vấn đề**: Import `BASE_DIR` trực tiếp nhưng dùng `"data"` và `"content"` cứng — không qua routing của `STORAGE_LAYOUT_MODE`.  
**Fix**:
- Dòng 24: `config.DATA_DIR / "drm_evidence.json"`
- Dòng 82: `config.CONTENT_DIR / "temp" / "videoprotector"`
- Dòng 135: `config.CONTENT_DIR / "temp"`

---

### 3. `app/services/ai_pipeline.py` — dòng 95–96
```python
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/config/9router_config.json"))
RUNTIME_STATE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/config/9router_runtime.json"))
```
**Vấn đề**: Hardcode relative path `../../data/config/` thay vì `config.DATA_DIR`.  
**Fix**: `config.DATA_DIR / "config" / "9router_config.json"` và `config.DATA_DIR / "config" / "9router_runtime.json"`

---

## 🟡 High — Cần sửa trong sprint này

### 4. `app/routers/syspanel.py` — dòng 521–524
```python
backup_dir = os.path.join(str(BASE_DIR), "data", "backups")
backup_path = os.path.join(backup_dir, f"{db_name}_{ts}.sql.gz")
```
**Vấn đề**: Bypass `DATA_DIR` — khi switch sang `storage` layout, backup sẽ vẫn vào `data/backups` thay vì `storage/db/backups`.  
**Fix**: `config.DATA_DIR / "backups"`

---

### 5. `app/utils/logger.py` — dòng 32–37
```python
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logs_dir = os.environ.get("LOG_DIR", os.path.join(BASE_DIR, "logs"))
log_file = os.path.join(logs_dir, "app.log")
```
**Vấn đề**: Tự tính `BASE_DIR` cục bộ thay vì dùng `config.LOGS_DIR`.  
**Fix**: `from app.config import LOGS_DIR` → `logs_dir = os.environ.get("LOG_DIR", str(LOGS_DIR))`  
*Lưu ý*: Cẩn thận circular import — `logger.py` được import sớm; dùng `os.environ` fallback là an toàn.

---

### 6. `app/routers/insights.py` — dòng 665–668
```python
scraper_path = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "archive", "scrape_insights.py"
)
scraper_path = os.path.abspath(scraper_path)
```
**Vấn đề**: Relative traversal `../..` để tìm script — fragile nếu file được move hoặc chạy từ thư mục khác.  
**Fix**: `config.BASE_DIR / "scripts" / "archive" / "scrape_insights.py"`

---

### 7. `workers/maintenance.py` — dòng 323
```python
proc = subprocess.Popen([sys.executable, "scripts/archive/scrape_insights.py"])
```
**Vấn đề**: Relative path phụ thuộc CWD lúc chạy — nếu PM2 start từ thư mục khác sẽ `FileNotFoundError`.  
**Fix**: `str(config.BASE_DIR / "scripts" / "archive" / "scrape_insights.py")`

---

## 🟢 Archive (Thấp — Không sửa ngay)

Các file trong `scripts/archive/` và `maintenance/archive/scratch/` chứa 26+ dòng `"/home/vu/toolsauto/..."` hardcoded. Đây là scripts đã lưu trữ, không chạy trong production. Ghi nhận để tham khảo nhưng **không cần refactor**.

File tiêu biểu:
- `scripts/archive/final_verify.py:21`, `check_page_stats.py:8`, `debug_reels_url.py:10`, v.v.
- `maintenance/archive/scratch/analyze_dump.py:3`, `cleanup.py:1-3`

---

## Config Variables đã có sẵn (để @Codex tham khảo)

```python
# Từ app/config.py — dùng trực tiếp:
from app.config import (
    BASE_DIR,       # Path gốc project
    DATA_DIR,       # data/ hoặc storage/db/ (theo STORAGE_LAYOUT_MODE)
    CONTENT_DIR,    # content/ hoặc storage/media/content/
    REUP_DIR,       # reup_videos/ hoặc storage/media/reup/
    PROFILES_DIR,   # profiles/ hoặc storage/profiles/
    THUMB_DIR,      # thumbnails/ hoặc storage/media/thumbs/
    LOGS_DIR,       # logs/ (luôn cố định)
)
```

---

## Handoff cho @Codex

**Thứ tự ưu tiên sửa:**
1. `app/services/video_protector.py` (3 điểm)
2. `app/services/ai_pipeline.py` (2 điểm)
3. `app/routers/manual_job.py` (xóa local BASE_DIR, dùng CONTENT_DIR)
4. `workers/maintenance.py:323` (CWD-dependent subprocess path)
5. `app/routers/insights.py:665`
6. `app/routers/syspanel.py:521`
7. `app/utils/logger.py:34` (cẩn thận circular import)

**Lưu ý quan trọng:**
- Không sửa các chuỗi `"data"` xuất hiện trong JSON payload hoặc dict key (không phải đường dẫn file).
- `app/services/account.py:49` — `BASE_PROFILE_DIR = str(CONTENT_PROFILES_DIR)` ✅ đã đúng, không sửa.
- `workers/maintenance.py:125-128` — dùng `config.REUP_DIR` ✅ đã đúng.
