# PLAN-106 — Studio: dựng lại tool đăng bài thành hệ edit video (xây song song, Buffer vẫn đăng)

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-106 |
| **Status** | Approved — anh duyệt trực tiếp 30/10/2026: «tách hết ra để mỗi module làm 1 việc và nối lại quy trình… em quyết toàn bộ đi». Đang làm P1. |
| **Executor** | Claude Code (cả backend, xem ADR-061 §Ngoại lệ). Anti review từng PR sau. |
| **Created by** | Claude Code theo yêu cầu của anh |
| **Related ADR** | ADR-061. Liên quan: ADR-007, 016, 031, 036, 041, 060. |
| **Created** | 2026-10-30 |

---

## Goal
Thay tool đăng bài cũ (nhiều nền tảng, Playwright, giao diện xoay quanh Facebook) bằng **Studio**: một hệ edit video.
- **Mỗi module làm đúng 1 việc.** Một bản đồ quy trình nối các module lại với nhau.
- Nhận video từ 3 nguồn: reup TikTok/Douyin, video tự quay, video AI tạo.
- Tự áp **mẫu edit** theo từng kênh. Anh **duyệt / chỉnh tay** trên web hoặc Telegram, xong mới đẩy lên **Buffer**.
- Xây cạnh code cũ. Buffer vẫn đăng bình thường cho tới khi từng kênh chuyển sang Studio. Code chết xoá ở bước cuối.

---

## Context (khảo sát 30/10, chỉ đọc code + 1 truy vấn DB chỉ đọc)

### Luồng đang chạy
Mọi bước chạy trong **Maintenance**. Web_Dashboard phục vụ file `/buffer-media` cho Buffer. 9Router là tầng AI đầu tiên.
```
nguồn (yt-dlp quét / link Telegram) → viral_materials NEW
  → tải → dedup → ReupProcessor (lọc chống trùng + phụ đề Whisper [+ dub/âm thanh nếu bật])
  → READY → AI caption → slots.next_free_slot → Buffer CreatePost → sync «đã đăng» → POSTED
```
- DB 30/10: 0 tài khoản FB active, 0 job FB treo.
  - READY 306, FAILED 210, POSTED 151, BOOST_PENDING 31, DUPLICATE 9.
  - READY mới nhất ngày 25/10.

### Vì sao dựng lại, không vá
1. **Dữ liệu xoay quanh Facebook.** `Job` là bài FB, Buffer mượn dùng. `target_page` mang 2 nghĩa. `ViralMaterial` có FK sang `Account`. Luồng READY → Buffer chỉ là nhánh `if target_account is None` (`viral_intake/processor.py:722-745`).
2. **Một hàm khoảng 680 dòng làm mọi việc** (`_process_viral_materials`): tải, dedup, edit, Drive, FB fan-out. Mỗi lớp edit encode lại một lần, Whisper chạy tới 3 lần, không có bản xem trước.
3. **Cấu hình rải rác:** JSON, runtime settings, hằng số. Giờ đăng gắn cứng theo tên kênh (`buffer/slots.py:15-19`).
4. **Mọi việc nặng trong 1 vòng Maintenance**, chung với poller Telegram.
5. **Code chết khoảng 25k dòng**, khoảng 15 trang UI, khoảng 50 file test.

### Giữ nguyên
- `cashback_bot/`, `store_bot/`, trang `/cashback*` (`layouts/app.html`, `fragments/cashback_*`).
- Buffer client / key / cooldown / sync (`app/features/buffer/`).
- Auth, settings registry, `app/core/ai`, notifier, offsite Drive, observability, DB_Backup.

---

## Kiến trúc: mỗi module 1 việc, nối bằng hàng việc

```
           ┌──────────── pipeline.py (bản đồ quy trình: flow → các bước) ────────────┐
           │                                                                         │
 web/TG/   ▼                                                                         ▼
 Drive → intake → analyze → compose → render → caption → review ──(duyệt)──→ publish → (Buffer)
          asset    cache      spec      mp4      chữ      cổng                cầu nối
           └───────────── mỗi mũi tên = 1 dòng studio_tasks; worker nhận, chạy, xếp bước sau ─┘
 AI:  script → voice → visuals → compose → …  (P5)
```

| Module | Đúng 1 việc | Vào | Ra |
|---|---|---|---|
| `intake/` | đưa file vào kho, tính hash, chặn trùng | file / link / Drive / Telegram | `studio_assets` |
| `analyze/` | probe + transcript + khoảng lặng + cảnh, **1 lần mỗi asset** | asset | `studio_analysis` |
| `compose/` | mẫu + asset + kênh → spec | asset, kênh, mẫu | `studio_projects` (DRAFT) |
| `render/` | spec → mp4, **1 lượt encode** | project | file + RENDERED |
| `caption/` | AI viết caption + hashtag | project | caption (P2) |
| `review/` | cổng duyệt: kênh tự duyệt thì đi tiếp, không thì dừng ở REVIEW | project | APPROVED / REVIEW |
| `publish/` | chuyển video đã duyệt sang Buffer | project | SCHEDULED (P3) |
| `script/`, `voice/`, `visuals/` | kịch bản AI, giọng đọc, hình | đề tài | asset (P5) |

Khung chung (không làm việc edit nào):
- `contracts.py`: tên bước, trạng thái, `StageResult`. Đây là thứ duy nhất các bước dùng chung.
- `spec.py`: `ProjectSpec`, hợp đồng giữa compose, render và trình edit.
- `paths.py`: thư mục `storage/media/studio/`.
- `queue.py`: bảng `studio_tasks` (xếp, nhận việc bằng `SKIP LOCKED`, xong / lỗi / thử lại, trả việc treo).
- `pipeline.py`: module **duy nhất** biết thứ tự các bước.
- `worker.py`: tiến trình chạy việc theo làn.

**Luật ranh giới** (kiểm bằng import-linter):
- Các bước không import nhau. Mỗi bước chỉ dùng khung chung + `app.core`.
- Studio không import feature khác (`viral_intake`, `buffer`, `telegram_bot`). Cần nối thì đi qua `feature_hooks` (ADR-007).

**Làn:**
- `heavy` (analyze, render, voice, visuals) chạy ở PM2 `Studio_Heavy`, 1 việc mỗi lần, `nice`.
- `light` (các bước còn lại) chạy ở `Studio_Light`.
- Maintenance không đổi.

**Sửa tay = sửa spec + xếp lại việc `render`.** Quy trình chạy tiếp từ render. Caption đã có thì không viết lại.

### Dữ liệu (bảng mới, migration chỉ thêm)
| Bảng | Cột chính |
|---|---|
| `studio_assets` | kind (video/audio/image), origin (reup/upload/ai/brand), source_url, credit, path, duration, w, h, has_audio, sha256 (unique), `viral_material_id` |
| `studio_analysis` | asset_id + kind (probe/transcript/silences/scenes) unique, data JSON, created_at |
| `studio_templates` | name, kind (mã mẫu trong `compose/templates`), params JSON |
| `studio_channels` | buffer_channel_id (unique), tên, template_id, auto_approve (mặc định tắt), show_credit, slot_hours JSON, intro/outro/logo asset id, active |
| `studio_projects` | channel_id, template_id, asset_id chính, spec JSON, status, caption, hashtags, output_path, duration, error, các mốc thời gian |
| `studio_tasks` | stage, flow, status (QUEUED/RUNNING/DONE/FAILED), asset_id / project_id, payload JSON, attempts / max_attempts, run_after, claimed_by, claimed_at, error, created_at, finished_at |

Trạng thái dự án: `DRAFT → RENDERING → RENDERED → REVIEW → APPROVED → SCHEDULED → POSTED`. Ngoài ra có `FAILED` và `REJECTED`.

### Spec
```json
{
  "v": 1,
  "canvas": {"w": 1080, "h": 1920, "fps": 30, "fit": "blur_pad"},
  "clips": [{"asset": 812, "start": 3.2, "end": 41.0}, {"asset": 812, "start": 55.0, "end": 71.5}],
  "subtitles": {"enabled": true, "source": "transcript", "edits": {"14": "Câu đã sửa tay"}, "font_size": 64, "margin_v": 260},
  "texts": [{"text": "Mẹo 3 giây", "start": 0, "end": 3, "pos": "top", "size": 72}],
  "audio": {"original": 1.0, "tracks": [{"asset": 44, "volume": 0.12, "loop": true}]},
  "logo": {"asset": 52, "pos": "tr", "width": 0.16},
  "credit": "Nguồn: @tacgia"
}
```
- Intro / outro là clip đầu / cuối của `clips`.
- Dub (P2): sinh ra 2 asset audio (giọng Việt + nền tách bằng Demucs). Spec để `original: 0` và đưa 2 asset đó vào `tracks`. Không cần lớp riêng.

### Giao diện (P4)
- **Web** (SPA `/app/studio`):
  - **Bảng duyệt:** cột Chờ duyệt / Đã duyệt / Đã hẹn / Đã đăng / Lỗi.
  - **Trình edit v1:**
    - cắt đầu / cuối và bỏ đoạn giữa trên dải khung hình;
    - sửa từng dòng phụ đề, chữ hook, âm lượng;
    - đổi mẫu / kênh, sửa caption, Render lại.
  - **Nguyên liệu**, **Mẫu / Kênh.**
- **Telegram:**
  - Dự án vào REVIEW → bot gửi video + caption, nút ✅ Duyệt / ✏️ Sửa trên web / 🗑 Bỏ.
  - Gửi link hoặc file (≤ 20 MB) → tạo dự án.

---

## Quyết định (anh giao em chốt, 30/10)
| # | Chốt | Lý do |
|---|---|---|
| D1 | Studio **không** có bước cắt watermark TikTok và lọc đổi tốc độ / màu / zoom để né nhận diện trùng. Asset reup lưu `credit`, kênh bật `show_credit` thì hiện «Nguồn: @…». | Cùng lý do gỡ `watermark_blur` 30/10. Giá trị của bản reup đến từ lớp edit thật: dub Việt, phụ đề, cắt gọn, hook. Hệ cũ vẫn chạy như cũ cho tới khi kênh chuyển. |
| D2 | Thí điểm: mọi kênh phải duyệt (`auto_approve` mặc định tắt). Kênh chạy ổn 1 tuần thì bật tự duyệt. | Hệ mới cần người nhìn trước khi lên page thật. |
| D3 | Hình cho video AI: Pexels API (miễn phí, giấy phép cho dùng thương mại) + thư viện clip / ảnh của anh. Ảnh AI tạo để sau. | Rẻ, rõ quyền dùng. Ảnh AI tốn tiền và chất lượng chưa đều. Cần anh tạo key Pexels ở P5. |
| D4 | Kênh thí điểm: **Uyển Nhi**. | Hết bài sau 02/11, không có nguồn, không đụng kho READY kênh khác. Tránh trnvp89 (key ZVsP sắp hết suất). |
| D5 | Claude Code làm cả backend, theo 3 ràng buộc của ADR-010. Ghi ở ADR-061. | Anh giao trực tiếp. |

---

## Các bước (mỗi bước có test, ghi proof bên dưới)

**P1 — Khung + các bước lõi**
- Models + migration (chỉ thêm bảng, **chưa chạy trên DB thật**).
- `contracts`, `spec`, `paths`, `queue`, `pipeline`, `worker`.
- Bước `intake` (từ file), `analyze`, `compose` (mẫu `basic`), `render`, `review`.
- Luật import-linter. Process PM2 `Studio_Heavy` / `Studio_Light` có trong `ecosystem.config.js`, **chưa bật**.

**P2 — Nguồn + mẫu**
- Reup: hệ cũ tải + dedup xong, nếu kênh đã chuyển sang Studio thì gọi hook `studio.intake` thay vì `ReupProcessor`.
- Upload web, thư mục Drive `Studio/Inbox/<kênh>`.
- Bước `caption`. Mẫu `reup_dub` (port `dub_layer` thành asset audio), `own_footage`.

**P3 — Cầu nối Buffer**
- APPROVED → tạo 1 dòng `viral_materials` READY trỏ tới file đã render, kèm caption + `target_page` = kênh.
- `schedule_reup`, `/buffer-media`, sync đã đăng chạy y nguyên, không sửa code Buffer.
- POSTED ở dòng đó → POSTED ở dự án.
- Kênh đã chuyển: hệ cũ không tạo READY cho kênh đó; giờ đăng đọc từ `studio_channels.slot_hours`.

**P4 — Giao diện:** SPA (bảng duyệt, trình edit v1, nguyên liệu, mẫu / kênh) + Telegram. Kiểm bằng trình duyệt thật ở 1440 px và 390 px.

**P4.1 — Biến thể A/B cho video tự quay (31/10, anh giao):**
- Spec: `Clip.hflip` (lật ngang từng đoạn), `Canvas.lut` (tên file `.cube` trong `storage/media/luts/`). Render: `hflip`
  trước khi khớp khung, `lut3d` sau khi nối (trước phụ đề / chữ để chữ không bị nhuộm). Thiếu file LUT → bỏ qua, không hỏng.
- Tham số mẫu chung: `mirror` (`off` / `on` / `random`), `lut` (`""` / tên file / `random`), `seed`. Chọn xong ghi thẳng vào
  spec → xem / sửa được trên trình edit, render lại ra đúng bản đó.
- Mẫu `ab_montage`: cắt theo mốc đổi cảnh (`scenes`), giữ đoạn đầu làm hook, xáo các đoạn giữa theo `seed`, cắt theo `max_len`.
- `POST /studio/api/projects/{id}/variants` (n ≤ 5): dựng n biến thể từ cùng asset, mỗi bản một `seed`; nút trên trình edit.
- **Giới hạn (giữ D1):** asset `origin=reup` không nhận lật gương, LUT ngẫu nhiên, xáo đoạn hay biến thể — mẫu bỏ qua, lưu
  spec lật đoạn reup bị từ chối, API biến thể từ chối. LUT cố định (tông màu kênh) dùng cho mọi nguồn.
- Không đụng `viral_intake` / `ReupProcessor`.

**P5 — Video AI:** `script` → `voice` (edge-tts, piper dự phòng) → `visuals` (D3) → compose `ai_faceless` → render.

**P6 — Chuyển kênh + dọn:**
- Thí điểm Uyển Nhi 7 ngày, rồi chuyển từng kênh.
- Xoá code chết theo đợt, mỗi đợt 1 commit:
  1. FB / Threads / IG / TikTok upload / story / engagement / fb_pro_tasks / insights / affiliates (FB) / strategic / dispatcher / workflow registry + UI + test;
  2. PM2 chết + `pm2_apps.py` / `process_scan.py`;
  3. nhánh FB trong `processor.py`, `ReupProcessor`, `Account`. DROP bảng phải hỏi anh;
  4. Buffer nhận dự án trực tiếp, bỏ cầu nối P3.
- Tách poller Telegram khỏi Maintenance.

---

## Out of Scope
- Lỗi Buffer đang có: race hàng chờ lúc tới giờ hẹn, job PENDING bỏ rơi, mức giữ 70%. Cần PLAN riêng.
- Đăng thẳng không qua Buffer.
- `cashback_bot/`, `store_bot/`, `/cashback*`.
- Trình dựng phim nhiều track kéo thả.

## Risks
| Risk | Mức | Cách xử lý |
|---|---|---|
| Render tranh CPU với Maintenance trên WSL | Med | Làn heavy 1 việc mỗi lần, `nice -n 19`; cache phân tích |
| Migration trên Postgres thật | Med | Chỉ thêm bảng, có `downgrade`; `pg_dump` trước khi chạy; anh bật |
| Hai hệ cùng đẩy 1 kênh | Med | Cờ theo kênh ở P3 |
| Test Buffer gọi API thật | High | Không chạy `test_buffer_cluster`, `test_challenger_m1_2`; test Studio không gọi mạng |
| Ổ đĩa đầy | Low | Thư mục work xoá trong `finally`; retention cho dự án REJECTED / POSTED |

## Validation Plan
- [x] P1: `pytest tests/test_studio_*.py` (lệnh ffmpeg + render thật 1 clip tạo bằng lavfi + chạy cả quy trình trên SQLite), `ruff`, `lint-imports`.
- [x] P1: `alembic upgrade head` / `downgrade -1` trên SQLite tạm.
- [x] P2: asset reup + file tự quay → REVIEW (test pipeline).
- [x] P3: APPROVED → dòng READY (test pipeline; Buffer không bị gọi).
- [x] P4: ảnh chụp 1440 px / 390 px (môi trường demo); nút Duyệt Telegram đổi đúng trạng thái (test).
- [ ] Thí điểm 7 ngày Uyển Nhi.

## Rollback
- P1–P5: không bật `Studio_*`, cờ kênh về hệ cũ. Bảng mới để nguyên, vô hại.
- P6: mỗi đợt xoá 1 commit, `git revert` được.

---

## Execution Notes
- ✅ **P1 (30/10) — code xong, chưa commit, chưa chạy migration trên DB thật, chưa bật PM2.**
  - Models `app/core/database/models/studio.py` (6 bảng) + migration `u8c5d6e7f8a9` (revises `t7b4c5d6e7f8`).
  - `app/features/studio/`: `contracts`, `spec`, `store`, `paths`, `queue`, `pipeline` (flows `upload` / `reup` / `brand` / `rerender`), `worker`; bước `intake`, `analyze`, `compose` (mẫu `basic`), `render` (`graph.py` thuần + `subtitles.py`), `review`.
  - `.importlinter`: thêm `studio` vào features-independent + 2 luật mới (các bước độc lập nhau; bước không import pipeline / queue / worker).
  - `ecosystem.config.js`: `Studio_Heavy`, `Studio_Light` (chưa bật).
  - Render 1 lượt gồm: nối nhiều clip, khung 9:16 (blur_pad / crop / pad), phụ đề từ transcript (dời theo đoạn cắt, sửa tay từng dòng), chữ hook có giờ, ghi nguồn, logo, nhạc lặp / trễ / âm lượng, ảnh tĩnh làm clip.
  - Chưa làm (để P2): caption, dub, Telegram, cầu nối Buffer.

**Verification Proof (P1)**:
```
$ pytest tests/test_studio_graph.py tests/test_studio_pipeline.py -q
30 passed in 43.18s          # ffmpeg thật trên clip lavfi; Whisper mock; không mạng

$ ruff check app/features/studio app/core/database/models/studio.py alembic/versions/u8c5d6e7f8a9_studio_tables.py tests/test_studio_*.py
All checks passed!

$ lint-imports
Studio stages are independent KEPT
Studio stages do not reach up to pipeline / queue / worker KEPT
# 2 luật cũ BROKEN y hệt trên HEAD (telegram_bot → buffer → viral_intake; metrics_checker), không chuỗi nào qua studio

# migration trên SQLite tạm (bảng cũ create_all + stamp t7b4c5d6e7f8)
alembic upgrade head   → 6 bảng studio_*
alembic downgrade -1   → 0 bảng studio_*, version t7b4c5d6e7f8
alembic check          → No new upgrade operations detected.

# test cũ có dùng models, cắt mạng (unshare -n): 386 passed, 2 failed — đều ngoài Studio:
#   test_admin_api_lists::test_admin_viral_sources_lists_channel → cần Postgres thật (bị cắt mạng)
#   test_split_parts::test_caption_phan_con_duoc_bao_la_phan_may → "no such table: runtime_settings",
#     hỏng y hệt khi trả models/__init__.py về HEAD và khi có mạng
```
- Render thử 1 dự án đầy đủ (hook + phụ đề + logo + ghi nguồn), xem khung giây 1 và giây 4: nền mờ đúng, hook tắt sau 3 giây, phụ đề đủ dấu, logo góc phải trên, «Nguồn: @…» góc trái dưới.

**Bật P1 trên máy thật (chủ bot làm, khi muốn thử):**
1. `pg_dump` (hoặc chờ DB_Backup 03:00) → `venv/bin/alembic upgrade head`.
2. `pm2 start ecosystem.config.js --only Studio_Heavy,Studio_Light && pm2 save`.
- Chưa có cửa vào (web / Telegram / hook reup ở P2) nên bật lúc này worker chỉ chờ việc, không ảnh hưởng gì.

- ✅ **P2 (31/10) — code xong, chưa commit, chưa chạy trên máy thật.** Quyết định thêm ghi ở ADR-061 mục 7–10.
  - **Bước `dub`** (`studio/dub/`, làn heavy): video tiếng khác → 2 asset audio FLAC (giọng đọc + nền Demucs) cùng mốc giây video gốc, phân tích `dub` (câu đã dịch). Lời thoại đã là tiếng Việt thì bỏ qua, không chạy Demucs. Dịch / đọc hỏng thì thử lại; lần cuối vẫn hỏng thì giữ tiếng gốc.
  - **Spec**: `Clip.audio` (tiếng của clip lấy từ asset audio, cùng mốc giây), `subtitles.source = "dub"`. Graph render trộn trong cùng 1 lượt encode.
  - **Bước `caption`** (làn heavy, sau render): `ContentOrchestrator.generate_caption` + tên kênh. Đã có caption thì bỏ qua (render lại không viết lại). AI hỏng → ghi chú, dự án vẫn vào REVIEW.
  - **Mẫu**: `basic` chỉ đốt phụ đề khi lời thoại đúng `subtitle_lang` (vi); `reup_dub`; `own_footage` (cắt khoảng lặng thật từ `silencedetect`, gộp còn ≤ 60 đoạn, không ghi nguồn).
  - **Phân tích `transcript`** đổi thành `{"lang", "lines"}`, Whisper tự nhận ngôn ngữ + bộ lọc câu bịa (port sang `app/core/media/speech.py`).
  - **Cửa vào** (`studio/entry.py`):
    - `take_reup` — hook `studio.take_reup` gọi từ `viral_intake/processor.py` ngay sau chống trùng (+14 dòng). Nhận khi video có đúng 1 kênh đích, kênh bật `take_reup`, không phải phần con. Material → `ViralStatus.STUDIO`. Ghi nguồn lấy từ URL (`@handle` / tên nền tảng).
    - `accept_file` + `POST /studio/api/upload`, `GET /studio/api/tasks/{id}` (theo dõi cả chuỗi bằng `parent_id`).
    - `scan_inbox`: `<DRIVE_ROOT_DIR>/Studio/Inbox/<tên kênh>/`, `_Kho/` cho nguyên liệu. Worker light quét mỗi 60 giây, file phải đứng yên 2 phút.
  - **Port, không sửa code cũ**: `core/media/speech.py` ← `subtitle_layer`, `core/media/tts.py` ← `audio_layer`, `studio/dub/engine.py` ← `dub_layer` (bỏ mux), `studio/dub/separate.py` ← `demucs_separate`. Bản cũ xoá ở P6.
  - **Schema** (migration `u8c5d6e7f8a9` chưa chạy ở đâu nên sửa thẳng): `studio_channels.take_reup` (mặc định tắt), `studio_tasks.parent_id` + index.
  - Worker đọc cài đặt runtime từ DB lúc khởi động (key AI, thư mục Drive).
  - File ngoài studio bị sửa: `processor.py` (+14), `bootstrap_hooks.py` (+3), `main.py` (+2), `constants.py` (+1), `.importlinter`.
  - Chưa làm: chia phần video dài trong Studio, Telegram (P4), cầu nối Buffer (P3). Kênh chưa có chỗ tạo trên web — tới P3 / P4.

**Verification Proof (P2)**:
```
$ unshare -n pytest tests/test_studio_graph.py tests/test_studio_pipeline.py tests/test_studio_dub_engine.py -q
57 passed in 80.53s   # ffmpeg thật (lavfi); Whisper / AI caption / Demucs / TTS giả; không mạng
#   có: reup_dub ra 2 FLAC + spec Clip.audio + render 6 s; dub bỏ qua khi đã tiếng Việt; dịch hỏng thử lại 3 lần rồi giữ
#   tiếng gốc; caption hỏng vẫn REVIEW; take_reup (cờ / 1 kênh / kênh tắt); hộp thư Drive (file đứng yên, _Kho, thư mục
#   lạ); upload đuôi lạ bị từ chối; own_footage cắt khoảng lặng thật bằng silencedetect: 12 s → 3 đoạn, 8,1 s

$ ruff check <mọi file đã sửa / thêm>          → All checks passed!
$ lint-imports                                  → 2 luật Studio KEPT (đã thêm dub, caption, cấm bước import entry);
                                                  2 luật cũ BROKEN y hệt HEAD, không chuỗi nào qua studio
# migration trên SQLite tạm (create_all bảng cũ + stamp t7b4c5d6e7f8):
#   upgrade → có take_reup, parent_id + ix_studio_tasks_parent_id; check → No new upgrade operations;
#   downgrade → 0 bảng studio_*; upgrade lại OK
$ unshare -n python -c "import app.main"        → hook studio.take_reup đã đăng ký; /studio/api/upload, /studio/api/tasks/{id}
$ unshare -n python -c "import app.features.system_panel.workers.maintenance"  → OK

# cả bộ test, cắt mạng: 3657 passed, 80 failed, 20 lỗi collect (file test cũ chết: app.services, Playwright, Postgres)
# 74 test hỏng (trừ 6 test cashback chưa commit của phiên khác) chạy lại trên worktree HEAD sạch: 73 hỏng y hệt.
# Test còn lại test_no_services_shim hỏng vì app/services/__pycache__ cũ (08/09, bị gitignore) chỉ có ở thư mục làm việc.
# 6 test cashback hỏng vì kiểm URL Shopee cần DNS (bị cắt mạng) — không liên quan Studio.
```

- ✅ **P3 (31/10) — cầu nối Buffer xong, chưa commit, chưa chạy trên máy thật.** Không sửa dòng nào trong `app/features/buffer/`.
  - **Bước `publish`** (làn light, cuối flow `reup` / `upload` / `rerender`, và flow `publish` riêng sau khi duyệt tay):
    dự án APPROVED → dòng `viral_materials` READY (`target_page` = kênh Buffer, `ai_caption` + `ai_hashtags` từ dự án)
    + file `REUP_DIR/studio/viral_<id>_p<dự án>_reup.mp4` nối cứng từ bản render. `find_reup_path` dò thư mục con
    nên `/buffer-media` phát được ngay; Maintenance `sweep_unscheduled_ready` tự lấy ô giờ và hẹn.
    Reup từ hệ cũ thì dùng lại chính dòng `STUDIO` của nó (không đẻ dòng mới); nguồn khác tạo dòng
    `platform="studio"`, `url="studio://project/<id>"`. Dòng đã có lịch Buffer (job DONE) thì từ chối đổi file / caption.
  - **Cổng duyệt:** tự duyệt chỉ khi đã có caption (AI hỏng → dừng ở REVIEW). `entry.approve` (sửa caption / hashtag
    cùng lúc) / `entry.reject`; API `GET /studio/api/projects`, `POST /studio/api/projects/{id}/approve|reject`.
  - **Đồng bộ ngược** (`publish/status.py`, worker light mỗi 5 phút, chỉ đọc DB): job Buffer DONE → SCHEDULED;
    material POSTED → POSTED.
  - Schema (migration chưa chạy ở đâu): `studio_projects.viral_material_id` + index.
  - **Chưa làm / lệch PLAN:** giờ đăng vẫn theo `buffer/slots.py` (đọc `studio_channels.slot_hours` thì phải sửa code
    Buffer — trái mục «không sửa code Buffer» của chính P3); để P6 khi Buffer nhận dự án trực tiếp.

**Verification Proof (P3)**:
```
$ unshare -n pytest tests/test_studio_pipeline.py -q
30 passed in 118.96s   # 7 test mới: tự duyệt → READY + find_reup_path thấy file (samefile = nối cứng);
                       # không caption thì REVIEW; duyệt tay sửa caption; duyệt thiếu caption bị chặn, bỏ dự án;
                       # reup hệ cũ dùng lại đúng dòng material; DONE → SCHEDULED, POSTED → POSTED;
                       # render lại thay file cũ, đã có lịch Buffer thì publish từ chối
$ lint-imports        → 2 luật Studio KEPT (thêm publish)
$ alembic upgrade / check / downgrade trên SQLite tạm → sạch, không drift
```

- ✅ **P4 (31/10) — giao diện Studio + Telegram xong, chưa commit, chưa chạy trên máy thật.**
  - **SPA** (module Video, `frontend/src/features/studio/`):
    - `Studio` `/app/go/studio`: upload video tự quay (chọn kênh), chip theo trạng thái (Đang làm · Chờ duyệt · Đã duyệt ·
      Đã hẹn · Đã đăng · Lỗi / bỏ) + thẻ ảnh bìa 9:16, Duyệt / Sửa / Bỏ ngay trên thẻ; tự hỏi lại 8 giây khi có việc chạy.
    - Trình edit `/app/go/studio/:id`: video bản dựng; caption + hashtag + kênh; **đoạn cắt** trên dải 16 khung (bấm 2
      điểm → «Bỏ khoảng này», hoặc gõ giây); **phụ đề** sửa / bỏ từng câu (khoá khi vừa đổi đoạn cắt); **chữ hook +
      âm lượng** (tiếng gốc, giọng lồng / nền, nhạc); **đổi mẫu** (dự án mới từ cùng asset); Lưu & render lại / Duyệt / Bỏ.
    - `Nguyên liệu`: lọc theo loại, xem trước, upload logo / intro / nhạc. `Kênh & mẫu`: thêm kênh từ danh sách Buffer,
      cờ Nhận reup / Tự duyệt / Ghi nguồn / Bật, mẫu mặc định, logo / intro / outro; tạo / sửa mẫu (tham số JSON có gợi ý).
    - Sidebar SPA + Jinja thêm 3 mục Studio.
  - **API** (`studio/router.py` → `editor.py`, `setup.py`): bảng dự án + đếm, chi tiết, `PUT …/spec` (kiểm spec, đổi đoạn
    cắt thì bỏ sửa tay phụ đề), `PATCH` caption / kênh, `recompose`, duyệt / bỏ, video (có Range), ảnh bìa, dải khung,
    asset, kênh, mẫu. Dự án đã sang Buffer thì khoá sửa.
  - **Telegram:** dự án vào chờ duyệt → bot gửi video + caption + ✅ Duyệt (`sok:`) / 🗑 Bỏ (`sno:`) / ✏️ Sửa trên web (khi
    có `PUBLIC_BASE_URL` https). Gửi file video ≤ 20 MB vào chat → dự án (chữ kèm theo = tên kênh). Qua hook
    `studio.approve` / `studio.reject` / `studio.accept_local_file`; `TelegramClient.download_file` (mới). Worker
    Studio đăng ký Telegram lúc chạy (không phải `--once`).
  - Sửa kèm: bước `review` không còn đánh hỏng dự án khi lưu 2 lần liền (2 lượt rerender) — lượt sau dừng nhẹ.

**Verification Proof (P4)**:
```
$ unshare -n pytest tests/test_studio_api.py tests/test_studio_pipeline.py tests/test_studio_graph.py tests/test_studio_dub_engine.py
75 passed   # 11 test mới: bảng + chi tiết, lưu spec / bỏ sửa tay / render lại, sửa caption / khoá khi đã sang Buffer,
            # đổi mẫu, video Range 206 + ảnh bìa + dải khung, kênh & mẫu, tin Telegram + nút + cắt tin dài,
            # thông báo hỏng không làm hỏng duyệt, nút ✅ trên Telegram, gửi file vào bot → dự án gắn kênh, file > 20 MB bị từ chối
$ npx tsc --noEmit && npm run build → ok
$ lint-imports → 2 luật Studio KEPT (editor / setup / router / entry nằm trên các bước)
# Trình duyệt thật trên môi trường demo (SQLite + media tạm, ffmpeg thật, AI / Telegram giả, uvicorn 127.0.0.1:8799):
#   Studio / trình edit / Nguyên liệu / Kênh & mẫu ở 1440 px, board + editor + setup ở 390 px — 0 lỗi JS, 0 request lỗi.
#   Thao tác: bấm 2 điểm trên dải → «Bỏ khoảng này» → 2 đoạn, phụ đề khoá, Duyệt bị tắt → Lưu → PUT 200 → worker render
#   → bản mới 0:08 (10 s − khoảng bỏ), 4 câu phụ đề đúng chỗ, về «Chờ duyệt».
```

- ✅ **P4.1 (31/10) — biến thể A/B cho video của mình, đã commit.** Anh gửi 2 bản yêu cầu: bản đầu ghi mục đích «lách bản
  quyền» cho `ReupProcessor` → em từ chối (trái D1); bản sau là A/B test video tự quay → làm trong Studio, có giới hạn ADR-061 mục 11.
  - `Clip.hflip`, `Canvas.lut` (chỉ tên `.cube`, kiểm bằng regex — không nhận đường dẫn). Render: `hflip` trước khi khớp khung;
    `lut3d` sau khi nối, trước phụ đề / chữ. Thiếu file LUT → render bình thường, ghi chú «bỏ qua».
  - Tham số chung mọi mẫu `mirror` / `lut` / `seed`; mẫu mới `ab_montage` (cắt theo cảnh, giữ hook, xáo đoạn giữa, cắt `max_len`).
  - `POST /studio/api/projects/{id}/variants` (≤ 5) + khối «Biến thể A/B» trên trình edit. Mẫu chưa đặt `mirror` / `lut` thì chia
    đều: bản lẻ lật, bản chẵn không; LUT lần lượt từng file.
  - Trình edit: ô «Lật gương» từng đoạn, chọn «Tông màu (LUT)». Lật / âm lượng không còn khoá sửa phụ đề (chỉ đổi đầu / cuối
    đoạn mới khoá) — sửa cả server (`_cuts`).
  - Reup: mẫu bỏ qua lật / LUT ngẫu nhiên / xáo; lưu spec lật đoạn reup → 400; API biến thể → 400; nút biến thể ẩn. LUT cố định dùng được.

**Verification Proof (P4.1)**:
```
$ unshare -n pytest tests/test_studio_*.py -q
90 passed   # 15 test mới (test_studio_ab_variants.py): hflip trước fit (3 kiểu khung), lut3d trước chữ, tên LUT bị
            # chặn đường dẫn, mirror / lut theo seed, intro / outro không lật, reup bị bỏ qua, gộp cảnh ngắn,
            # ab_montage giữ hook + đủ đoạn + không start ≥ end + cắt max_len, render thật với LUT nhuộm đỏ (đo điểm ảnh
            # R>200) rồi xoá LUT → màu gốc, biến thể chia đều lật + lần lượt LUT, chặn reup, lật không mất sửa phụ đề
$ ruff / lint-imports (2 luật Studio KEPT) / tsc / npm run build → ok
# Trình duyệt (demo SQLite, 1 LUT mẫu): tích «Lật gương» + chọn LUT → PUT 200 (lut + hflip trong spec) → render có LUT;
# «Dựng biến thể» → POST 200, 4 dự án mới; lật gương không còn khoá phụ đề.
```
