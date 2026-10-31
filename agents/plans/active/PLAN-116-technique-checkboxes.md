# PLAN-116: Chọn kỹ thuật bằng ô tick cho mọi video (mặc định bật hết) + sửa tiến trình hiện nhầm dự án đã bỏ

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-116 |
| **Status** | Approved — anh yêu cầu 31/10 («bật hết các tính năng lên cho mọi video… tạo checkbox để chọn các kĩ thuật», «sao bỏ qua chỗ lồng tiếng», «đã chạy id 10 mà vẫn hiển thị #9») |
| **Executor** | Claude Code (ngoại lệ ADR-061 Studio) |
| **Created** | 2026-10-31 |

---

## Vấn đề
- **Lồng tiếng bị bỏ qua:** chỉ mẫu `reup_dub` mới lồng tiếng. Video #10 tiếng Trung chạy mẫu `basic` → «bỏ qua» lồng tiếng,
  và không có phụ đề (phụ đề chỉ đốt khi lời thoại đúng tiếng Việt).
- **Không chọn được kỹ thuật:** chỉ có «hook» và «đã có chữ sẵn»; còn lại phụ thuộc mẫu.
- **Tiến trình ở bảng Studio:**
  - ẩn video xong (#10 đã có thẻ) nhưng vẫn giữ 2 việc cũ của #9 (dự án anh đã bỏ) → nhìn như hệ thống hiện sai dự án;
  - bước «Duyệt» của dự án đã bỏ vẫn có dấu ✓.

## Thiết kế
- **Lồng tiếng thành tham số dùng được ở mọi mẫu:** `params.dub = true` → bước `dub` chạy (đã có sẵn) và bước `compose` gắn
  tiếng lồng + phụ đề câu đã dịch (tách thân `reup_dub` thành `with_dub`, `reup_dub` = `basic` + `with_dub`).
  - Video đã là tiếng Việt / không có lời → `dub` tự bỏ qua, video giữ nguyên tiếng gốc.
- **Bộ kỹ thuật cho mỗi lần đưa video vào** (trang «Lấy từ TikTok» và ô tải lên), **mặc định bật hết**:
  - ☑ Phụ đề tiếng Việt;
  - ☑ Lồng tiếng Việt (+ chọn giọng VieNeu);
  - ☑ Câu hook mở đầu (ô chữ; để trống = không có);
  - ☑ Nhạc nền (chọn từ «Nguyên liệu» loại audio; chưa có nhạc thì ô bị khoá kèm hướng dẫn);
  - ☑ Ghi nguồn (video sưu tầm: luôn bật);
  - ☐ Lật gương, ☐ Tông màu LUT: **chỉ video tự quay**. Với video sưu tầm (TikTok, «Video sưu tầm») hai ô này bị khoá kèm lý do —
    giữ đúng ADR-061 mục 11, không áp kỹ thuật chống trùng lên video của người khác.
- **Server kiểm lại** (`entry.technique_params`): chỉ nhận các khoá trên, đúng kiểu; nhạc phải là asset audio có thật; LUT phải
  có file; video sưu tầm gửi lật / LUT → báo lỗi.
- **Tiến trình bảng Studio:** ẩn cả việc của dự án đã bỏ (anh tự bỏ, không cần báo). Ở trang «Lấy từ TikTok» vẫn hiện đủ.
  Bước «Duyệt» của dự án đã bỏ hiện «đã bỏ» (✕ xám), không còn ✓.

## Scope
`compose/templates.py` (`with_dub`), `compose/__init__.py`, `entry.py` (`technique_params`, `take_links`, `accept_file`),
`router.py` (body / form), `setup.overview` (+ danh sách LUT), `progress.py`, SPA (`TechniquePicker`, `StudioTiktokPage`,
`UploadBox`, `JobsPanel`), test.

## Out of Scope
- Lật gương / LUT / biến thể cho video sưu tầm (ADR-061 mục 11).
- Logo / intro / outro theo lô (vẫn theo kênh).
- Tự viết câu hook bằng AI.

## Validation
- pytest: `with_dub` ở mẫu basic; `technique_params` (nhận / chặn); lô TikTok mặc định → lồng tiếng chạy; tiến trình ẩn dự án đã bỏ.
- ruff, lint-imports, tsc + build, trình duyệt thật.

## Rollback
Không migration. Tham số mới vắng mặt thì như cũ.

## Execution Notes
- ✅ **Code xong (31/10), commit cục bộ — cần restart Web_Dashboard + Studio_Heavy + Studio_Light.** Không migration.
  - `compose/templates.py`: `with_dub(inp, spec)`; `reup_dub` = `with_dub(basic)`; `compose` áp `with_dub` khi `params.dub` (mọi mẫu).
  - `entry.technique_params`: nhận `subtitles / dub (+dub_lang vi, vieneu_voice) / hook / music_asset_id (+music_volume, phải là
    audio trong kho đã phân tích) / mirror / lut (phải có file)`; video sưu tầm gửi lật / LUT → lỗi. Dùng ở `take_links`
    (`techniques`) và `accept_file` (form `techniques` JSON; `has_text` cũ vẫn nhận).
  - `setup.overview` + `luts`. `progress`: dự án đã bỏ → bước Duyệt `cancelled` «đã bỏ».
  - SPA: `TechniquePicker` (7 ô, mặc định bật Phụ đề / Lồng tiếng / Nhạc nền (bài đầu tiên nếu có) / Ghi nguồn; Lật gương / LUT
    khoá với video sưu tầm, tắt sẵn với video tự quay vì lật cả chữ) ở trang «Lấy từ TikTok» (khung riêng + tóm tắt ở thanh
    đáy) và ô tải lên; `JobsPanel` ẩn việc của dự án đã bỏ ở bảng Studio.

**Verification Proof**:
```
$ unshare -n pytest (10 file Studio + process_control) → 161 passed; ruff ok; lint-imports 2 contract Studio KEPT; tsc + build ok
# Trình duyệt thật (web tạm, pipeline thật, Whisper giả trả tiếng Trung, dub giả như test): khung Kỹ thuật mặc định
#   [Phụ đề ✓, Lồng tiếng ✓, Nhạc nền ✓ (#1 tự chọn), Ghi nguồn ✓ khoá, Lật gương khoá]; chọn giọng Thái Sơn → tóm tắt
#   «Phụ đề · Lồng tiếng (Thái Sơn) · Nhạc nền · Ghi nguồn»; 2 video Đăng tay → Lồng tiếng «zh→vi, 1/1 câu» (mẫu basic),
#   spec có nhạc nền, «Xong — chờ anh duyệt»; ô tải lên: video của tôi → lật gương mở, video sưu tầm → khoá; 390 px ok; 0 lỗi JS.
# Phát hiện khi thử: nhạc chưa phân tích (has_audio trống) → render hỏng «track … không có tiếng» → nay chặn ở server + ẩn ở web.
```
