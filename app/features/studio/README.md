# Feature: studio

Hệ edit video thay cho tool đăng bài cũ (ADR-061, PLAN-106). Mỗi bước là một package làm đúng một việc;
`pipeline.py` nối các bước bằng hàng việc `studio_tasks`.

```
intake → analyze → dub → compose → render → caption → review → publish ──→ (luồng Buffer sẵn có)
asset    cache      tiếng   spec      mp4      chữ AI    cổng duyệt   dòng viral_materials READY
```

| Phần | File | Việc |
|---|---|---|
| Khung | `contracts.py` | tên bước, trạng thái, `StageResult`, `StageError` |
| | `spec.py` | `ProjectSpec` — bản mô tả một video ra |
| | `store.py` | đọc cache phân tích, mẫu đang áp, đưa file vào kho (`add_asset`) |
| | `paths.py` | `storage/media/studio/{assets,renders,work,inbox}` |
| | `taskqueue.py` | xếp / nhận (`SKIP LOCKED`) / xong / lỗi / trả việc treo; `parent_id` nối các bước |
| | `pipeline.py` | `FLOWS`, `STAGES` — chỗ duy nhất biết thứ tự |
| | `worker.py` | PM2 `Studio_Heavy` (`--lanes heavy`), `Studio_Light` (`--lanes light`, quét hộp thư Drive) |
| Cửa vào | `entry.py` | `take_reup` (hook từ hệ cũ), `accept_file` (upload web), `scan_inbox` (Drive) |
| | `router.py` | API cho SPA: upload, việc, dự án (bảng / chi tiết / spec / caption / đổi mẫu / duyệt / bỏ / video / ảnh bìa), asset, kênh, mẫu |
| Giao diện | `editor.py` | trình edit: chi tiết, lưu spec → render lại, đổi mẫu, dải khung hình, ảnh bìa |
| | `setup.py` | kênh (gắn kênh Buffer) + mẫu |
| | `notify.py` | chờ duyệt → Telegram (video + ✅ `sok:` / 🗑 `sno:` / ✏️ web) |
| Bước | `intake/` | file → `StudioAsset` (sha256; reup trùng cùng kênh thì dừng) |
| | `analyze/` | probe, transcript (`{"lang","lines"}`), khoảng lặng, cảnh — 1 lần mỗi asset |
| | `dub/` | lồng tiếng → 2 asset audio (giọng + nền Demucs), phân tích `dub` |
| | `compose/` | asset + kênh + mẫu → `StudioProject` (mẫu `basic`, `reup_dub`, `own_footage`) |
| | `render/` | spec → 1 lệnh ffmpeg (`render/graph.py`, hàm thuần) → mp4 |
| | `caption/` | AI viết caption + hashtag (đã có thì bỏ qua) |
| | `review/` | tự duyệt theo kênh (khi đã có caption), không thì dừng ở REVIEW |
| | `publish/` | APPROVED → `viral_materials` READY + file `REUP_DIR/studio/viral_<id>_p<dự án>_reup.mp4`; `status.py` đồng bộ SCHEDULED / POSTED |

Mẫu (`studio_templates.kind` + `params`):
- `basic`: cắt đầu / độ dài, phụ đề (chỉ khi lời thoại đúng `subtitle_lang`, mặc định vi), hook, nhạc.
- `reup_dub`: như basic + tiếng lồng Việt và phụ đề câu đã dịch; không lồng được thì y như basic.
- `own_footage`: video tự quay — cắt khoảng lặng ≥ `min_silence` (jump cut), không ghi nguồn.
- `ab_montage`: A/B cho video của mình — cắt theo cảnh, giữ hook, xáo đoạn giữa theo `seed`.
- Biến thể (`editor.make_variants`): gắn dự án gốc (`parent_project_id`), chung caption gốc, mỗi bản một kiểu (lật × LUT) chưa có
  trong nhóm, chặn khi lô trước chưa xong; duyệt 1 bản → bản khác REJECTED; Telegram 1 tin cho cả lô.
- Mọi mẫu: `mirror` (`off` / `on` / `random`), `lut` (tên file trong `storage/media/luts/` hoặc `random`), `seed`. Video reup
  không nhận lật / LUT ngẫu nhiên / xáo / biến thể (ADR-061 mục 11).

Cầu nối Buffer (P3, tới P6): Studio không gọi Buffer. `publish` tạo / cập nhật dòng READY (reup từ hệ cũ thì
dùng lại chính dòng `STUDIO` của nó), Maintenance (`sweep_unscheduled_ready`) tự lấy ô giờ theo `buffer/slots.py`
và hẹn lên Buffer. `studio_channels.slot_hours` chưa dùng — giờ đăng vẫn theo `slots.py` tới P6.

SPA: `frontend/src/features/studio/` — `/app/go/studio` (bảng duyệt), `/app/go/studio/:id` (trình edit),
`/app/go/studio-assets`, `/app/go/studio-setup`. Telegram: nút duyệt / bỏ và file video gửi vào chat đi qua hook
`studio.approve` / `studio.reject` / `studio.accept_local_file` (`app/bootstrap_hooks.py`).

Hộp thư Drive: `<DRIVE_ROOT_DIR>/Studio/Inbox/<tên kênh>/` → dự án cho kênh đó; `Studio/Inbox/_Kho/` → nguyên
liệu (logo, intro, nhạc). File phải đứng yên 2 phút (Drive đồng bộ xong) mới được nhận.

Code port từ hệ cũ (xoá bản cũ ở PLAN-106 P6): `app/core/media/speech.py` ← `subtitle_layer`,
`app/core/media/tts.py` ← `audio_layer`, `dub/engine.py` ← `dub_layer`, `dub/separate.py` ← `demucs_separate`.

Luật (import-linter): các bước không import nhau, không import `pipeline` / `taskqueue` / `worker`;
studio không import feature khác — nối qua `feature_hooks`.

Chạy tay toàn bộ việc đang có: `PYTHONPATH=. venv/bin/python app/features/studio/worker.py --once`.
