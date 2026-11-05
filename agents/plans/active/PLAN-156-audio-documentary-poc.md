# PLAN-156 — Audio → Documentary Video Phase 0 POC

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-156 |
| **Status** | In progress — owner duyệt plan Cursor 05/11/2026 |
| **Executor** | Cursor (agent) |
| **Related** | ADR-064, ADR-061, BRD SM-MEDIA-BRD-ATDV-001 |
| **Created** | 2026-11-05 |

## Goal
POC: MP3 → transcript sửa được → beats/shots seed → upload ảnh + rights → preview 30–60s Ken Burns → khóa export khi `RIGHTS_UNKNOWN`. Không API trả phí, không image search web.

## Scope
- `app/features/studio/doc/` (schema, seed, plan stage, rights, manifest, service)
- Flow `audio_doc` trong pipeline
- `Clip.motion` + zoompan trong render graph
- API + trang SPA `/app/go/studio-doc`
- Fixture audio + tests

## Out of scope
Fact-check web, Pexels/Getty, NAS, 9:16, regen voice, full MVP FR.

## Validation
- Unit/integration: rights gate, seed beats, Ken Burns filtergraph có `zoompan`, render preview ngắn với ffmpeg.
- AC POC: AC-01 (duration), AC-02 (transcript raw/reviewed), AC-06 (rights lock), AC-07/08 rút gọn, AC-12.

## Proof
Ghi vào section này sau khi test chạy.
### Rà soát + sửa (Claude Code, 05/11/2026 — chủ bot yêu cầu «fix đi»)
- **Sự cố:** chạy test render của POC làm WSL hết RAM (7,7 GB, không swap; ffmpeg bị SIGKILL 137) → WSL khởi động lại, Cursor mất kết nối.
- **Ken Burns ngốn RAM:** `zoompan d=<số frame>` trên ảnh `-loop` ra frames² frame. Đổi `d=1` (1 frame vào → 1 ra, chuyển động theo `on`). Đo 9 clip × 7s 1080p: 2,8 GB → ~0,8 GB, 51s → 44s; clip 5s ra đúng 150 frame, frame đổi theo thời gian.
- **DocState hỏng khi sửa sai:** `update_shot` / `set_shot_rights` / `update_transcript` kiểm qua schema trước khi lưu (motion sai, ms âm/không phải số, thiếu mốc, rights sai → DocError 400, không lưu). `attach_image` kiểm `rights_status` trước khi ghi file (không còn asset mồ côi).
- **Chạy lại `doc_plan`** dùng lại dự án đã có, không tạo dự án trùng.
- **Frontend:** `StudioDocPage.tsx:77` lỗi TS → ép kiểu `DocDetail` trước khi đọc `shots`. `tsc --noEmit` sạch.
- **Proof:** `tests/test_studio_audio_doc.py` 8 qua (thêm 4 test); `tests/test_studio_*.py` 166 qua, 2 lỗi sẵn `test_studio_dub_long` (`separate.get_model` không tồn tại — file không đổi); `test_studio_pipeline` sửa kỳ vọng thêm `"motion": "static"`. ruff sạch; import-linter: 2 contract studio KEPT (2 BROKEN sẵn của buffer/viral_intake).
- **Còn lại cho Cursor:** docstring `queue_doc_preview` / `prepare_preview` còn ghi «rerender» (thực tế flow `doc_preview`); `detail` 404 dựa vào chuỗi «không có».
