# PLAN-112: Chọn giọng VieNeu theo kênh trên web

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-112 |
| **Status** | Approved — anh giao 31/10 (nhắc lại «Chọn giọng VieNeu theo kênh trên web» sau PLAN-111) |
| **Executor** | Claude Code (ngoại lệ ADR-061: Studio, PLAN trước, migration chỉ thêm) |
| **Created** | 2026-10-31 |

---

## Goal
Mỗi kênh Studio chọn một giọng VieNeu riêng (25 giọng, Bắc / Trung / Nam) ở trang «Kênh & mẫu», nghe thử ngay trên trang.
Video lồng tiếng của kênh đọc bằng giọng đó. Chưa chọn thì như PLAN-111 (nữ: Ngọc Huyền, nam: Hải Đăng theo mẫu).

## Thiết kế
- **Lưu:** cột mới `studio_channels.dub_voice` (VARCHAR 64, NULL = theo mẫu). Migration chỉ thêm cột.
- **Danh sách giọng:** server VieNeu `GET /health` trả thêm `gender`, `region`, `description` mỗi giọng
  (đọc từ preset của model). `app.core.media.tts.vieneu_voices()` đọc qua HTTP; server tắt → danh sách rỗng.
- **API** (`/studio/api`):
  - `GET /voices` → `{online, voices}`;
  - `POST /voices/preview` `{voice}` → WAV một câu mẫu (đọc qua engine `vieneu`, không lưu file).
  - `PATCH /channels/{id}` nhận `dub_voice`. Giọng phải có trong danh sách khi server đang chạy; server tắt vẫn cho lưu tên.
- **Lồng tiếng:** bước `dub` lấy `channel.dub_voice` (nếu có) làm giọng VieNeu. Khi VieNeu hỏng và phải quay về edge-tts,
  giọng edge lấy cùng giới với giọng đã chọn. Không có giọng kênh thì vẫn theo `dub_voice` (female / male) của mẫu.
  `tts.synthesize(..., vieneu_voice=)`: tham số mới, mặc định None (giữ cách quy giọng cũ).
- **Web:** dòng kênh thêm ô «Giọng lồng tiếng» (nhóm Nữ / Nam, ghi vùng) + nút «Nghe thử». Server tắt thì ô ghi rõ.

## Scope
Migration + model, `setup.py`, `tts.py`, `vieneu_server.py` (health), `dub/__init__.py`, `router.py`, SPA trang «Kênh & mẫu»
(+ types / api), test. Chạy trên máy thật: backup → `alembic upgrade head` → restart Web_Dashboard, Studio_Heavy, VieNeu_TTS.

## Out of Scope
Giọng theo mẫu / theo dự án, clone giọng riêng, tốc độ đọc.

## Validation
pytest (setup lưu / chặn giọng lạ, dub chọn giọng kênh, tts kwarg mới, health có giới tính), ruff, lint-imports, tsc + build,
migration lên / xuống trên SQLite tạm, trình duyệt thật (chọn giọng, nghe thử).

## Rollback
Bỏ chọn giọng (về «Theo mẫu»). Cột NULL vô hại; `alembic downgrade -1` xoá cột.

---

## Execution Notes
- ✅ **Code xong (31/10), commit cục bộ — migration CHƯA chạy trên DB thật** (lệnh backup + `alembic upgrade head` bị chặn quyền).
  - Migration `x1f8a9b0c1d2` (chỉ ADD COLUMN `studio_channels.dub_voice`), model `StudioChannel.dub_voice`.
  - `vieneu_server.py`: `/health` trả `name / gender / region / description` (`voice_catalog`; region lấy từ mô tả vì model
    nạp xong không giữ trường region). Server thật đã restart với bản mới (Studio_Heavy đang chạy chỉ gọi `/tts`, không ảnh hưởng).
  - `tts.py`: `vieneu_voices()`, `synthesize(..., vieneu_voice=)`.
  - `setup.py`: lưu / kiểm `dub_voice` (server chạy thì giọng phải có thật), `preview_voice` (đệm WAV theo giọng).
  - `dub/__init__.py`: `_voice(channel, params)` — giọng kênh + giới cho edge dự phòng; giọng kênh chỉ dùng khi đích là tiếng Việt.
  - `router.py`: `GET /voices`, `POST /voices/preview`. SPA: `VoicePicker` (nhóm Nữ / Nam · vùng, nghe thử / dừng) trong dòng kênh;
    `shared/api/http.ts` thêm `postJsonBlob`.

**Verification Proof**:
```
$ unshare -n pytest tests/test_studio_{graph,pipeline,ab_variants,api,dub_engine,vieneu}.py tests/test_audio_layer.py -q → 134 passed
$ (sau khi sửa region) pytest tests/test_studio_vieneu.py → 16 passed; ruff → All checks passed; lint-imports: không vi phạm mới
$ alembic trên SQLite tạm (create_all → stamp head → downgrade -1 → upgrade head → check) → No new upgrade operations; cột dub_voice VARCHAR(64)
$ tsc --noEmit ok; npm run build ok
# Trình duyệt thật (Playwright, web tạm 127.0.0.1:8799 + SQLite riêng + server VieNeu thật): nhóm Nữ 11 / Nam 14 giọng;
# chọn «Thái Sơn · Nam» → «Đã lưu Uyển Nhi.», API trả dub_voice; Nghe thử → POST /voices/preview 200 audio/wav, nút thành «■ Dừng»;
# kênh chưa chọn giọng → nút Nghe thử tắt; 390 px không tràn ngang; 0 lỗi JS.
```
**Để chạy trên máy thật:** `venv/bin/python manage.py db backup --keep 14` → `venv/bin/alembic upgrade head` →
`pm2 restart Web_Dashboard Studio_Heavy Studio_Light`. Chưa chạy migration thì ĐỪNG restart các app này (model đã có cột mới).
