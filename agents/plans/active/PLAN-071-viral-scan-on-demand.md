# PLAN-071: Nguồn tự động chỉ quét khi page sắp hết video

- Executor: Claude Code (Owner duyệt 2026-10-23 21:40 ICT, "oke thực hiện đi em")
- Status: Code xong; nguồn đang tắt theo lời Owner

## Bối cảnh

Lúc 23/10 21:35 ICT có 340 video READY, 44 video mới mỗi ngày. Lượng đăng thực tế thấp hơn nhiều:

- 2 page trên key mới đăng tổng cộng khoảng 8 bài/ngày.
- Page `6ad24d45…` (nguồn hoalexx2) có 261 video READY, nhưng key 2 và 3 đang khóa.
- Video quá 7 ngày bị dọn và đặt FAILED (176 FAILED).

Quét dư không tốn suất Buffer, nhưng tốn ổ đĩa, CPU, yt-dlp, và cuối cùng bị xóa.

Đã làm 21:37 theo lời Owner:

- Tắt cả 6 nguồn bằng `SourceService.set_enabled`. Backup ở `data/backups/viral-sources-before-pause-20261023T143732Z.json`.
- Nguồn 3, 4, 5 trỏ về mã kênh cũ (sót lúc đổi kênh ở PLAN-067). Đã đổi sang `6adb578c…9cde9b` / `…9cde9a`. Material 1709 (READY, mã cũ) cũng đổi theo.

## Scope

1. `app/core/settings.py`: thêm `viral.source_skip_ready_per_page`, kiểu int, mặc định 15, 0 = tắt.
2. `sources.py` `SourceService.scan_all`:
   - Đếm READY theo `target_page` bằng một query.
   - Nguồn có mọi page đích đều đã đủ ngưỡng thì bỏ qua vòng này và không ghi `last_scanned_at`, để vòng sau xét lại ngay.
   - Nguồn không có page đích thì quét như cũ.
   - Ghi `summary["paused"]`.
3. `command_handler.py`: thêm alias `/caidat dutru <n>`.
4. Test.

## Không làm

- Không bật lại nguồn. Owner tự bật bằng `/nguon` khi muốn.
- Không đổi quét tay (`/nguon` → quét, nút "Quét tất cả" trên web gọi `scan_source` hoặc `scan_all(only_due=False)`): bấm tay là Owner muốn quét, luôn quét.
- Không đổi TikTok competitor scan (không account nào có `competitor_urls`) và discovery.

## Rollback

Revert commit, hoặc `/caidat dutru 0`.

## Definition of Done

- Nguồn trỏ 1 page có ≥ 15 READY → không gọi `scan_source`, `last_scanned_at` giữ nguyên.
- Page < 15 → quét.
- Nguồn nhiều page: chỉ bỏ khi mọi page đều đủ.
- Ngưỡng 0 → quét như cũ.
- `only_due=False` (quét tay) → không bỏ.

## Proof

2026-10-23, Claude Code:

- `tests/test_viral_sources.py` thêm 3 test:
  - page đủ ngưỡng → bỏ quét, `last_scanned_at` giữ None; page thiếu, nguồn nhiều page (một page thiếu), nguồn không page vẫn quét;
  - `only_due=False` và ngưỡng 0 luôn quét;
  - setting đăng ký: int, mặc định 15, min 0.
- Sửa 1 assert dict cũ, thêm `"paused": 0`.
- `test_viral_sources.py` + `test_viral_sources_ui.py`: 85 passed.
- 35 file test có chữ caidat/SETTINGS/viral_intake: 14 fail, đều ở `test_material_caption.py` và `test_notify_jobless.py`. Chạy cùng bộ đó trên code trước khi sửa (`git stash`) thì 18 fail, nên các lỗi này có từ trước và phụ thuộc thứ tự chạy test. Chạy riêng 2 file thì 3 fail, có cả khi không có thay đổi của em.
- Restart 22:0x ICT. 6 nguồn đang tắt, nên chưa có log "Bỏ quét … đủ video".
