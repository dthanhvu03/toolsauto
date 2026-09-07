# ADR-019 — Bảng "Nguồn" tách khỏi account; quét tự động kênh TikTok + YouTube Shorts

- **Ngày**: 2026-09-07
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-07 ("oke em triển khai đi nhé")
- **Liên quan**: ADR-017 (dán link), ADR-018 (READY không account), PLAN-042/043

## Bối cảnh

Quét kênh TikTok hiện đọc `Account.competitor_urls` của **account active** (`scan.py:138-140`).
0 account active ⇒ quét chết theo. Kiểm thật 2026-09-07 bằng yt-dlp `--flat-playlist`, không
cookie:

| Kênh | Liệt kê + `view_count` |
|---|---|
| TikTok `@kênh` | ✅ |
| YouTube `@kênh/shorts` | ✅ (2,8M / 10M / 7,7M…) |
| Facebook Page `/reels/`, `/videos/`, gốc | ❌ Unsupported URL |
| Instagram profile | ❌ Unable to extract (cần đăng nhập) |

Sweep nền chỉ gom material NEW theo `scraped_by_account_id == acc.id` ⇒ material không
thuộc account (dán tay, hoặc từ nguồn mới) **không bao giờ được nhặt tự động**.

## Quyết định

1. Bảng mới `viral_sources` — nguồn **độc lập với account**:
   `id, platform (tiktok|youtube), url (unique, chuẩn hoá), handle, min_views (null = dùng
   setting `viral.min_views`), max_videos (null = `viral.max_videos_per_channel`),
   target_page (nullable), enabled (bool, default true), last_scanned_at, last_found,
   last_error, created_at, updated_at`.
2. `SourceService` (`app/features/viral_intake/sources.py`) — **hợp đồng cố định** để UI và
   backend làm song song:
   - `list_sources(db) -> list[ViralSource]`
   - `add_source(db, url, *, min_views=None, max_videos=None, target_page=None) -> (ok, msg, source_id)`
     — detect platform bằng `intake.detect_platform`-style cho **kênh** (TikTok `@handle`,
     YouTube `@handle` / `/channel/…` / `/c/…`; tự thêm `/shorts` cho YouTube); từ chối FB/IG
     với message nêu rõ "chỉ dán từng link video".
   - `set_enabled(db, source_id, enabled) -> bool`
   - `delete_source(db, source_id) -> bool`
   - `scan_source(db, source) -> (found, skipped, error|None)` — yt-dlp `--flat-playlist
     --dump-json --playlist-end N`; lọc `view_count >= min_views`; tạo `ViralMaterial(NEW,
     platform, url video chuẩn hoá, title, views, scraped_by_account_id=None,
     target_page=source.target_page)`; trùng url (kể cả biến thể `www.`) bỏ qua; cập nhật
     `last_scanned_at/last_found/last_error`.
   - `scan_all(db, *, only_due=True) -> dict(found, scanned, errors)` — mỗi nguồn tối đa 1
     lần/giờ (`viral.source_scan_interval_min`, default 60); giữ rate-limit tracker của
     `tiktok_scraper` nếu có.
3. `maintenance`: gọi `feature_hooks "viral.scan_sources"` mỗi vòng (cạnh
   `_scrape_tiktok_competitors` cũ — **giữ** cũ để không phá account có `competitor_urls`).
4. Sweep `_process_viral_materials` (nhánh `only_material_id is None`): thêm một lượt gom
   `NEW` có `scraped_by_account_id IS NULL` (trần `per_acc_fetch`), xử lý như material
   thường → không account thì `READY` (ADR-018). ≤15 dòng.
5. UI `/app/viral`: khối "Nguồn tự động" (collapsible): bảng nguồn (nền tảng, handle, min
   views, bật/tắt, lần quét cuối, tìm thấy, lỗi), form thêm (URL kênh, min views, Page đích),
   nút "Quét ngay" từng nguồn và tất cả (chạy nền, toast). Router `/viral/sources`,
   `/viral/sources/add`, `/viral/sources/{id}/toggle`, `/viral/sources/{id}/delete`,
   `/viral/sources/{id}/scan`, `/viral/sources/scan-all`.
6. Migration Alembic mới, `downgrade` drop bảng. Không đụng `competitor_urls`.

## Phạm vi

| Việc | File |
|---|---|
| Model + export | `app/core/database/models/viral.py`, `models/__init__.py` |
| Migration | `alembic/versions/<new>_viral_sources.py` |
| Service quét | `app/features/viral_intake/sources.py` (mới) |
| Hook + maintenance | `app/bootstrap_hooks.py`, `app/features/system_panel/workers/maintenance.py` |
| Sweep gom NEW không account | `app/features/viral_intake/processor.py` (≤15 dòng) |
| Setting | `app/core/settings.py`: `viral.source_scan_interval_min` |
| Router + UI | `app/features/viral_intake/router.py`, `app/templates/fragments/viral_sources.html` (mới), `app/templates/pages/app_viral.html` |
| Test | `tests/test_viral_sources.py`, `tests/test_viral_sources_ui.py` |
| Proof | thêm 1 kênh YouTube thật + 1 TikTok thật → `scan_all` → ≥3 material NEW; sweep → `READY` |

## Ngoài phạm vi

- Không quét Facebook/Instagram (yt-dlp không liệt kê được).
- Không di trú `competitor_urls` sang bảng mới (làm sau nếu Owner muốn).
- Không tự tải hết kênh: trần `max_videos` mỗi lần quét.
- Không lo bản quyền hộ Owner — UI ghi: "YouTube của người khác rủi ro bản quyền cao hơn TikTok; ưu tiên kênh brand/seller."

## Hết hiệu lực

Sau proof: kênh YouTube thật → material NEW → sweep → READY có file, không cần bấm tay.
