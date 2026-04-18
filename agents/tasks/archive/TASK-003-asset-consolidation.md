# TASK-003: Quy hoạch & Đồng bộ Tài nguyên (Media, Profiles, Workers)

## Mục tiêu
Loại bỏ tình trạng phân tán dữ liệu (Videos, Profiles, Thumbnails) đang nằm rải rác ở cả thư mục gốc và thư mục `content/`. Xác lập một cấu trúc lưu trữ duy nhất, chuẩn hóa để Worker vận hành ổn định.

## Trình thực thi (Performer)
- [x] **@Codex** (Lead - Refactor & Migration)
- [ ] **@Claude** (Quality Control & Documentation)
- [ ] **@Antigravity** (Orchestrator)

## Trạng thái
- `[x]` Finished (Phase 1, 2, 3 completed; storage layout active)

## Checklist
- `[x]` Audit & Phân tích chuyên sâu (Deep Audit)
    - [x] So sánh nội dung `profiles/` vs `content/profiles/` (Xác định bản mới nhất).
    - [x] So sánh nội dung `thumbnails/` vs `content/thumbnails/`.
    - [x] Kiểm tra dung lượng và cấu trúc `reup_videos/` và `outputs/`.
- `[x]` Thực thi Hợp nhất (Consolidation)
    - [x] Merge dữ liệu từ thư mục phụ vào thư mục Chính (theo `app/config.py`) bằng `rsync -ahP`.
    - [x] Move các thư mục legacy root vào `storage/archive_legacy/` sau khi backup/migrate hoàn tất.
- `[x]` Chuẩn hóa Cấu hình (Standardization)
    - [x] Cập nhật `app/config.py` để bổ sung layout `storage/` + cơ chế cutover `STORAGE_LAYOUT_MODE` (legacy/storage).
- `[x]` Kiểm tra & Nghiệm thu (Verification)
    - [x] Chạy thử truy xuất đường dẫn `storage/` từ `config.py` ✅.
    - [x] Kiểm tra thực tế file vật lý tại nhà mới ✅.
    - [ ] Lưu trữ Task vào `archive/`.

## Ghi chú
- Dữ liệu hiện có khoảng 5.3GB. 
- Thư mục gốc (`/home/vu/toolsauto/`) hiện đang chứa các bản mới nhất của Profiles và Thumbnails (April 2026).
- Thư mục `content/` đang chứa nhiều bản cũ (March 2026).
- Snapshot audit (2026-04-18): `profiles` 25M, `content/profiles` 4.2G, `thumbnails` 16M, `content/thumbnails` 133M, `reup_videos` 105M, `outputs` 4.0K.
- Phase 1 đã xong ở mức code/config: thêm nhóm biến `STORAGE_*` và giữ alias tương thích ngược; default mode là `legacy` để không gián đoạn worker trước Phase 2 migration.
- Phase 2 Migration (2026-04-18) đã thực thi:
  - `rsync -ahP content/profiles/ storage/profiles/`
  - `rsync -ahP profiles/ storage/profiles/`
  - `rsync -ahP content/thumbnails/ storage/media/thumbs/`
  - `rsync -ahP thumbnails/ storage/media/thumbs/`
  - `rsync -ahP reup_videos/ storage/media/reup/`
  - `rsync -ahP data/ storage/db/`
- Verify hậu migrate:
  - Dung lượng đích: `storage/profiles` 4.3G, `storage/media/thumbs` 144M, `storage/media/reup` 105M, `storage/db` 6.6M.
  - File count: `storage/profiles` 95503, `storage/media/thumbs` 514, `storage/media/reup` 12, `storage/db` 11.
  - Dry-run `rsync --ignore-existing --stats` cho tất cả nguồn trả về `Number of regular files transferred: 0` (không thiếu file theo path).
- Cutover đã bật: `.env` đặt `STORAGE_LAYOUT_MODE=storage`, và `venv/bin/python` xác nhận config đang trỏ vào `storage/...`.
- Phase 3 Cleanup (2026-04-18) đã thực thi bằng `mv`:
  - `profiles/` -> `storage/archive_legacy/profiles/`
  - `thumbnails/` -> `storage/archive_legacy/thumbnails/`
  - `reup_videos/` -> `storage/archive_legacy/reup_videos/`
  - `data/` -> `storage/archive_legacy/data/`
  - Verify: root legacy folders đã biến mất; `storage/profiles`, `storage/media`, `storage/db` vẫn còn nguyên.
