# Cấu hình ToolsAuto — một map duy nhất

Mọi cấu hình đi qua **một trong ba lớp** dưới đây. Không tạo file JSON/state ở thư mục gốc repo.

## 1. `.env` (boot & secrets)

**Vị trí:** `d:\Zusem\toolsauto\.env` (copy từ [`.env.example`](../.env.example), không commit).

**Dùng cho:** mật khẩu admin, `SECRET_KEY`, `DATABASE_URL`, API keys, feature flags bảo mật, port local.

**Nạp:** `app/config.py` → `load_dotenv(BASE_DIR / ".env", override=False)`  
→ Đổi `.env` **phải restart** web/worker (process không tự reload env).

| Nhóm | Biến tiêu biểu |
|------|----------------|
| Auth | `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `SECRET_KEY` |
| DB | `DATABASE_URL`, `DB_PATH` |
| Security | `COOKIE_SYNC_SECRET`, `ALLOW_QUERY_LOGIN`, `SQL_CONSOLE_WRITES_ENABLED`, `SYSPANEL_DESTRUCTIVE_ENABLED` |
| Tích hợp | `TELEGRAM_*`, `GOOGLE_API_KEY` / `GEMINI_API_KEY` |
| Local | `WEB_PORT` (mặc định `8002`, dùng bởi `start.ps1`) |

Danh sách đầy đủ + default: [`app/config.py`](../app/config.py).

## 2. `app/config.py` (code defaults)

**Single import:** `import app.config as config` hoặc `from app.config import X`.

- Default từ env (hoặc hằng số) cho worker, FFmpeg, viral, CDN, Playwright, …
- **Registry runtime tunables** (metadata): [`app/core/settings.py`](../app/core/settings.py) → key `worker.*`, `publish.*`, `ai.*`, …

**Chỉnh qua dashboard (`/app/settings`):** ghi bảng Postgres `runtime_settings`; web/worker gọi `apply_runtime_overrides_to_config` / `load_runtime_settings_into_process` để đồng bộ vào `config` in-memory.

**Tích hợp (Telegram token/chat, Google API key):** sửa được trên Settings; ưu tiên DB override hơn `.env`. Secret để trống khi Lưu = giữ giá trị hiện tại. Reset = trở về snapshot `.env` lúc process start.

## 3. `storage/db/config/` (file JSON runtime)

**Thư mục:** `config.RUNTIME_CONFIG_DIR` = `storage/db/config/` (tạo tự động).

| File | Mục đích |
|------|----------|
| `gemini_cookies.json` | Cookie Gemini Web / extension sync |
| `gemini_cookies_invalid` | Flag cookie hết hạn |
| `ai_persona.json` | Persona AI Studio |
| `9router_config.json` | 9Router endpoint / model |
| `9router_runtime.json` | Trạng thái circuit / latency |
| `drm_evidence.json` | pHash DRM log |
| `tiktok_rate_limits.json` | Backoff scraper TikTok |

Lần đầu boot, `migrate_legacy_runtime_config_files()` copy từ vị trí cũ (root `gemini_cookies.json`, `data/config/*`, …) nếu có.

## 4. Storage layout (media & output)

**Điều khiển:** `STORAGE_LAYOUT_MODE` trong `.env` — mặc định code là **`storage`**.

| Biến `app/config.py` | `storage` (chuẩn) | `legacy` (cũ) |
|----------------------|-------------------|---------------|
| `CONTENT_DIR` | `storage/media/content/` | `content/` |
| `REUP_DIR` | `storage/media/reup/` | `reup_videos/` |
| `THUMB_DIR` (URL `/thumbnails`) | `storage/media/thumbs/` | `thumbnails/` |
| `PROFILES_DIR` | `storage/profiles/` | `profiles/` |
| `CONTENT_MEDIA_DIR` | `…/content/media/` | `content/media/` |
| `OUTPUTS_DIR` (dọn temp) | `…/content/outputs/` | `outputs/` |
| `THREADS_MEDIA_DIR` | `storage/media/threads/` | (luôn dưới `storage/media/`) |
| `DEBUG_STEPS_DIR` | `logs/debug_steps/` | cùng |
| `RUNTIME_CONFIG_DIR` | `storage/db/config/` | cùng |

**Quy tắc code:** không hardcode `content/media` hay `reup_videos/` — import từ `app.config`. Rebase path DB cũ: [`app/core/storage_paths.py`](../app/core/storage_paths.py).

## Ops khác (không phải app config)

| File | Vai trò |
|------|---------|
| [`ecosystem.config.js`](../ecosystem.config.js) | PM2 processes (VPS/Linux) |
| [`app/core/pm2_apps.py`](../app/core/pm2_apps.py) | Tên app + log map (single source) |
| [`.importlinter`](../.importlinter) | Boundary import |

## Quick start local

```powershell
copy .env.example .env   # điền ADMIN_*, SECRET_KEY, DATABASE_URL
.\start.ps1              # WEB_PORT / .env, http://127.0.0.1:8002
```

Chi tiết cây code: [TREE.md](TREE.md).
