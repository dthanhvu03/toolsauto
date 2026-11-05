# PLAN-157 — Audio→Doc: theo audio thật, chọn ngôn ngữ, ảnh tải lên + ảnh internet, mọi tham số chỉnh trên web

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-157 |
| **Status** | Done (code + test) — chờ chủ bot restart Web_Dashboard + bật worker Studio |
| **Executor** | Claude Code |
| **Related** | PLAN-156, ADR-064, ADR-065 |
| **Created** | 2026-11-05 |

## Context
Rà soát module Audio→Doc (PLAN-156, commit `27d34a7`) cho thấy:
- Kịch bản MU–Roma viết cứng (`doc/seed.py`): mốc giây, tóm tắt, gợi ý ảnh không theo audio tải lên.
- Preview cố định 60s, cảnh 7s, khung 1920×1080, phụ đề / Ken Burns / luật quyền — đều hardcode.
- Ngôn ngữ: Whisper tự nhận (`analyze` gọi `speech.transcribe(language=None)`), không chọn được.
- Ảnh chỉ tải lên tay; UI còn mặc định `RIGHTS_VERIFIED` + `owned` (ảnh tự qua cổng quyền).

Anh muốn: **thời gian theo đúng audio tải lên, chọn được ngôn ngữ, cảnh nào anh tải ảnh / cảnh nào lấy
từ internet, và mọi tham số chỉnh trên web — không sửa code.** Anh đã chốt: nguồn ảnh Wikimedia Commons,
Openverse, Pexels, Pixabay, Google Images; hệ thống **gợi ý ảnh, anh bấm chọn**; **AI rút từ khóa** từ lời đã chép.

Tận dụng sẵn có:
- Cấu hình: `app/core/settings.py` — `SETTINGS` + `SettingSpec` (kiểu, min/max, lựa chọn, `is_secret`,
  `keep_blank`), lưu DB + nhật ký, trang **/app/settings** tự vẽ form, `get()` đọc DB (cache 3s) → đổi là ăn ngay,
  không restart. Studio Reup đang dùng (`reup.*`).
- AI: `AIUseCases.generate_text(prompt, purpose=...)` (`app/core/ai/use_cases.py`) — cách `studio/dub/__init__.py` đang gọi.
- Whisper: `app/core/media/speech.transcribe(path, language=...)` đã nhận tham số ngôn ngữ.
- Lưu ảnh: `store.add_asset(...)` (trùng sha256 tự dùng lại).

## 1. Cấu hình trên web — `app/core/settings.py`
Section **«Studio — Audio→Doc»**, key `doc.*` (mặc định giữ hành vi hợp lý hiện tại):

- **Ngôn ngữ:** `doc.default_language` enum `auto` (mặc định), `vi`, `en`, `zh`, `ja`, `ko`, `th`, `id`, `fr`, `es`, `de`, `pt`.
- **Thời gian (theo audio):** `doc.preview_sec` (0 = toàn bộ audio, mặc định 0), `doc.shot_sec` (7), `doc.shot_min_sec` (2),
  `doc.shot_max_sec` (12), `doc.beat_pause_sec` (1.2 — khoảng lặng dài hơn → sang đoạn ý mới), `doc.beat_max_sec` (90).
- **Khung hình:** `doc.canvas` enum `1920x1080` / `1280x720` / `1080x1920`, `doc.fps` (30), `doc.fit` enum `crop` / `blur_pad`.
- **Phụ đề / tiếng:** `doc.subtitles` (bật), `doc.subtitle_font_size` (48), `doc.subtitle_margin_v` (80),
  `doc.subtitle_max_chars` (180), `doc.voice_volume` (1.0), `doc.credit` (trống = không ghi).
- **Hiệu ứng:** `doc.motions` (danh sách luân phiên), `doc.kb_zoom_max` (1.2), `doc.kb_zoom_per_sec` (0.045),
  `doc.kb_pan_zoom` (1.15), `doc.kb_upscale` (2.0, cảnh báo RAM).
- **Nguồn ảnh:** `doc.src_wikimedia` (bật), `doc.src_openverse` (bật), `doc.src_pexels`, `doc.src_pixabay`, `doc.src_google`
  (tắt tới khi có key); key `doc.pexels_key`, `doc.pixabay_key`, `doc.google_key`, `doc.google_cx` (`is_secret`, `keep_blank`);
  `doc.candidates_per_source` (6), `doc.image_min_width` (1280), `doc.search_timeout_sec` (10).
- **Từ khóa AI:** `doc.ai_keywords` (bật).
- **Luật quyền:** `doc.rights_ok` enum `verified_or_approved` / `approved_only`; `doc.rights_need_proof` (bật);
  `doc.auto_verify_licenses` (mặc định `cc0,pdm,cc-by,cc-by-sa,pexels,pixabay` — giấy phép tự coi là đã kiểm quyền).

Đọc qua một chỗ: **`doc/config.py` (mới)** — `DocConfig` (dataclass frozen) + `load(db)`. Các module khác chỉ nhận `DocConfig`.

## 2. Ngôn ngữ chọn được
- Form tải audio (`StudioDocPage`): ô **Ngôn ngữ audio** (Tự nhận + danh sách), mặc định theo `doc.default_language`.
- `router.doc_upload` / `entry.accept_audio_doc` nhận `language` → `payload["language"]`.
- `analyze/__init__.py`: `_compute("transcript", ...)` nhận `language` từ `task.payload` (không có → `None`, như cũ).
- DocState lưu `language` thật Whisper trả về; phụ đề giữ đúng ngôn ngữ đó; prompt từ khóa AI nhận ngôn ngữ nguồn.

## 3. Thời gian theo audio — `doc/seed.py` viết lại
- Xoá `_BEATS` (MU–Roma) — chuyển sang dữ liệu test nếu cần.
- **Cảnh** bám câu Whisper: gộp các câu liền nhau tới gần `shot_sec` (không dưới `shot_min_sec`); câu dài hơn `shot_max_sec`
  thì cắt đều; cảnh đầu từ 0, cảnh cuối tới hết `duration`; khoảng không lời gộp vào cảnh kề.
- **Đoạn ý** tách ở khoảng lặng ≥ `beat_pause_sec` giữa hai câu, hoặc khi dài quá `beat_max_sec`. `summary` = lời đã chép
  (cắt ~120 ký tự), `fact_status=UNVERIFIED`.
- Audio không có lời: chia đều theo `shot_sec`.
- Preview: `preview_sec=0` → toàn bộ audio; `>0` → cắt.

## 4. Ảnh: anh tải lên HOẶC chọn từ internet
**Schema** (`doc/schema.py`): `Shot.keywords: list[str]`, `Shot.candidates: list[Candidate]` (cache kết quả tìm);
`Candidate` = provider, url ảnh, url xem trước, trang nguồn, tác giả, giấy phép, link giấy phép, kích thước;
`ImageRef` thêm `provider`, `license_url`, `author`.

**Từ khóa AI — `doc/keywords.py` (mới):** trong bước `doc_plan` (nếu `doc.ai_keywords`), một lần gọi
`AIUseCases.generate_text` (thêm `AIPurpose.DOC_KEYWORDS`) cho cả bài → JSON `{shot_id: [2–4 từ khóa tiếng Anh + tên riêng]}`.
AI lỗi / tắt → từ khóa trống, anh tự gõ. Anh sửa từ khóa từng cảnh trên UI.

**Nguồn ảnh — `doc/images/` (mới):** mỗi nguồn một hàm `search(query, cfg) -> list[Candidate]` dùng `httpx`, timeout theo cấu hình:
- `wikimedia.py` — Commons API (`generator=search`, `prop=imageinfo`, `extmetadata` → giấy phép / tác giả). Không key.
- `openverse.py` — `api.openverse.org/v1/images`. Không key.
- `pexels.py`, `pixabay.py` — cần key.
- `google.py` — Custom Search JSON API (`searchType=image`, cần key + cx; 100 lượt/ngày miễn phí).
- `licenses.py` — chuẩn hoá tên giấy phép (`cc-by-sa-4.0` → `cc-by-sa`…); trong `auto_verify_licenses` → `RIGHTS_VERIFIED`
  (proof = trang nguồn + link giấy phép); NC/ND → `RIGHTS_RESTRICTED`; Google / không rõ → `RIGHTS_UNKNOWN`.
- `search.py` — gọi các nguồn đang bật song song, lọc `image_min_width`, gộp, lỗi một nguồn không làm hỏng nguồn khác.

**Tìm khi cần, không quét cả bài:** mở cảnh trên UI → nếu chưa có `candidates` thì gọi tìm, lưu vào DocState; nút «Tìm lại» với từ khóa mới.

**Service / API** (`doc/service.py`, `router.py`):
- `POST /doc/projects/{id}/shots/{shot}/search` `{keywords?}` → lưu từ khóa + candidates.
- `POST /doc/projects/{id}/shots/{shot}/pick` `{index}` → tải ảnh về (giới hạn dung lượng, kiểm content-type),
  `store.add_asset(origin="web", source_url=..., credit=...)`, gắn `ImageRef` với quyền tự điền theo `licenses.py`.
- Tải lên tay giữ nguyên (`/image`).

**UI** (`StudioDocPage.tsx`): mỗi cảnh hiện ô từ khóa + lưới ảnh gợi ý (nguồn, giấy phép, tác giả); bấm để chọn
hoặc «Tải ảnh của anh lên». Mặc định quyền khi tải tay: `RIGHTS_UNKNOWN`, giấy phép trống. Link tới Cài đặt.

## 5. Dựng preview theo cấu hình
- `doc/service.build_preview_spec(db, state, cfg)`, `prepare_preview`, `detail`, `doc.run` lấy `cfg = config.load(db)`.
- `doc/rights.check_export(state, cfg)` theo `rights_ok` / `rights_need_proof`; bỏ `EXPORTABLE_RIGHTS` cố định.
- `spec.py`: `class Motion(_Strict)` (`zoom_max`, `zoom_per_sec`, `pan_zoom`, `upscale`), `ProjectSpec.motion` mặc định = số cũ.
  `render/graph._ken_burns` đọc `spec.motion`, tốc độ/frame = `zoom_per_sec / fps`.
- `ensure_placeholder_image`: bỏ kích thước điền tay.
- Bài dài (vd 9 phút ≈ 80 cảnh = 80 input ffmpeg): đo RAM khi render toàn bộ; nếu vượt ~1,5 GB thì gộp các cảnh liền nhau
  dùng cùng một ảnh thành một input.

## Giữ cố định trong code (ghi vào ADR)
Tên trạng thái quyền, tên chuyển động, giới hạn 255/500 ký tự (cột DB), đuôi ảnh jpg/png/webp, đường dẫn lưu theo `paths.ROOT`.

## Tài liệu
- **ADR-065** (mới): bổ sung ADR-064 — cho phép tìm ảnh web (5 nguồn), AI rút từ khóa, luật tự điền quyền theo giấy phép.
- **PLAN-157** trong `agents/plans/active/` (Executor: Claude Code, anh duyệt trực tiếp «all in one», >3 file backend).
- `current-status.md` khi bắt đầu và khi xong.

## Kiểm tra
1. Test (không gọi mạng thật — mock `httpx` và `AIUseCases.generate_text`):
   - seed: cảnh bám câu Whisper, đoạn ý tách ở khoảng lặng, tổng = thời lượng audio, không còn «Carrick».
   - ngôn ngữ: `payload.language="en"` → `transcribe(language="en")`; không có → `None`.
   - từ khóa: JSON AI hợp lệ → gắn vào cảnh; AI lỗi → trống, không làm hỏng bước.
   - mỗi nguồn ảnh: parse JSON mẫu → Candidate đúng giấy phép; một nguồn lỗi, nguồn khác vẫn trả.
   - licenses: CC-BY → VERIFIED, CC-BY-NC → RESTRICTED, Google → UNKNOWN; `auto_verify_licenses` đổi được.
   - pick: tải ảnh (mock) → asset `origin=web`, quyền tự điền; file quá lớn / không phải ảnh → DocError.
   - cấu hình: `config.load(db)` đọc override DB; `DocConfig` khác mặc định → canvas / phụ đề / motion / preview đúng.
   - graph: `ProjectSpec()` mặc định ra đúng chuỗi zoompan cũ.
2. Chạy có giới hạn RAM: `tests/test_studio_*.py` (2 lỗi sẵn `dub_long` được phép), test settings, `ruff`, `lint-imports`
   (contract studio phải KEPT), `npx tsc --noEmit`.
3. Đo render toàn bộ một audio dài (fixture 9 phút nếu có, 1080p) với `ulimit -v`, ghi RAM/thời gian vào PLAN.
4. Trên web (8000, sau khi anh restart Web_Dashboard): `/app/settings` có section mới; tìm ảnh thật **chỉ Wikimedia + Openverse**
   (không cần key) cho 1 cảnh — hỏi anh trước khi gọi mạng thật.
5. Ghi proof vào PLAN-157, commit + push `feat/xe-tet` khi anh bảo; báo anh restart Web_Dashboard + Studio worker.

## Proof (05/11/2026)
- Cấu hình: 38 key `doc.*` (section «Studio — Audio→Doc») + `studio.segment_render_over` (section «Xử lý video (FFmpeg)»). `doc/config.py` là chỗ đọc duy nhất.
- Thêm ngoài plan (cần cho bài dài): **dựng theo đoạn** trong `render/__init__.py`. Đo 80 cảnh Ken Burns 1080p (560s video):
  dựng cảnh 326s + ghép cuối 230s, **RAM ffmpeg tối đa 510 MB** (một lượt: ~40 MB/cảnh → ước 3,6 GB; đo thật 40 cảnh = 2,0 GB).
- Ken Burns mặc định ra đúng chuỗi filter cũ (`min(1+0.0015*on,1.2)`, scale 3840×2160, `d=1`).
- `tests/test_studio_audio_doc.py`: 24 qua (mạng giả bằng `httpx.MockTransport`, AI giả). `tests/test_studio_*.py` + settings: 185 qua trước khi thêm test dựng theo đoạn; 2 lỗi sẵn `test_studio_dub_long` (`separate.get_model`, không liên quan). `test_settings_ui_surface`, `test_config_central`, `test_studio_graph` 36 qua.
- ruff sạch; import-linter: 2 contract studio KEPT (2 BROKEN sẵn của buffer/viral_intake); `npx tsc --noEmit` sạch.
- Chưa làm: mở /app/settings + tìm ảnh thật trên web (cần restart Web_Dashboard; gọi Wikimedia/Openverse thật phải hỏi chủ bot).
