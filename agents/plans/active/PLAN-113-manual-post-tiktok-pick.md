# PLAN-113: Studio — «Đăng tay» (không kênh Buffer) + lấy video từ link TikTok, chọn rồi dựng

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-113 |
| **Status** | Approved 31/10 («anh duyệt em»). Anh hỏi: «không chọn tài khoản Buffer được không… đăng tay», «dán link TikTok, chọn số video quét về, tự chọn rồi bấm render, chọn các kĩ thuật hiện có») |
| **Executor** | Claude Code (ngoại lệ ADR-061: Studio, PLAN trước, đúng scope) |
| **Created** | 2026-10-31 |

---

## Goal
1. **Đăng tay:** đưa video vào Studio mà không cần kênh Buffer. Duyệt xong thì không gửi Buffer; trên thẻ có nút
   «Tải video» + «Chép caption», đăng xong bấm «Đã đăng».
2. **Lấy từ TikTok:** trang Studio có ô dán link (kênh `@user` hoặc 1 video) + số video quét (1–30) → danh sách
   (tiêu đề, lượt xem, thời lượng) có ô tick → chọn kênh / «Đăng tay», mẫu, tuỳ chọn → «Tải & dựng».

## Thiết kế
- **Đăng tay = dự án không có `channel_id`.** Upload / lấy TikTok cho phép bỏ trống kênh. Bước `publish`: không kênh →
  ghi chú «đăng tay», giữ APPROVED (không lỗi). API + nút «Đã đăng» → POSTED. Tự duyệt không áp dụng (không kênh).
- **Quét:** `studio/source/` dùng `app.core.yt_dlp_path` (`--flat-playlist --dump-json --playlist-end N`), không import
  `viral_intake` (contract «features độc lập»). Chỉ đọc metadata, không tải. Gặp 429 thì báo, không thử lại liên tục.
- **Tải:** bước mới `fetch` (làn light, đầu flow `link`): tải 1 video bằng yt-dlp (≤ 500 MB, `--no-playlist`) vào `inbox/`
  → `intake` → như flow `reup` hiện có. Mỗi video một task, lỗi video nào chỉ hỏng video đó.
- **Kỹ thuật chọn được** = những gì Studio có cho video sưu tầm: mẫu (`basic` / `reup_dub` / mẫu anh tạo), «Đã có chữ sẵn»
  (tắt phụ đề), câu hook, giọng lồng tiếng (mẫu lồng tiếng), ghi nguồn `@kênh` tự điền.
  Video lấy từ link TikTok là **video sưu tầm (origin `reup`)** → lật gương / LUT / montage biến thể **không áp dụng**
  (ADR-061 mục 11, giữ nguyên).
- **Web:** trang «Lấy từ TikTok» trong nhóm Video (hoặc khối trên Studio): dán link → Quét → lưới video tick chọn →
  thanh dưới: kênh / Đăng tay · mẫu · tuỳ chọn · «Tải & dựng (n)». Thẻ dự án hiện tiến độ như upload hiện tại.

## Scope
`contracts.py` (Stage FETCH), `pipeline.py` (flow `link`), `studio/source/` (quét + bước fetch), `entry.py` (bỏ bắt buộc
kênh, `take_links`), `publish/` (đăng tay), `router.py` (scan, links, mark-posted), SPA (trang lấy TikTok, UploadBox
cho phép «Đăng tay», ProjectCard nút tải / chép / đã đăng), test. Không migration (kênh vốn nullable).

## Out of Scope
Quét định kỳ tự động (hệ cũ «Nguồn video» vẫn làm), lọc theo ngày, Facebook / YouTube (sau, cùng cách), tải bằng cookie.

## Validation
pytest (quét parse JSON giả, flow link với yt-dlp giả, đăng tay không vào Buffer, mark-posted), ruff, lint-imports,
tsc + build, trình duyệt thật trên web tạm. Quét thật 1 kênh TikTok công khai 3 video chỉ khi anh cho phép (gọi mạng TikTok).

## Rollback
Không migration. Ẩn trang; dự án đăng tay vẫn xem / tải được.

## Execution Notes
- ✅ **Code xong (31/10), commit cục bộ — CHƯA restart trên máy thật** (`pm2 restart` bị chặn quyền, chờ anh). Không migration.
  - Bước mới `fetch/` (Stage FETCH đứng đầu → hạng thấp nhất; làn light), flow `link` = fetch + `_EDIT`; `.importlinter` thêm fetch.
  - `source.py`: `scan` (yt-dlp `--flat-playlist --dump-json --playlist-end N`, ≤ 30, chỉ tiktok.com, báo 429 / riêng tư), `parse`.
  - `entry.py`: `accept_file` bỏ bắt buộc kênh (không kênh = đăng tay); `approve` bỏ chặn «chưa gắn kênh»; `take_links`
    (origin reup, credit `@kênh` từ link, params lô: `subtitles=False` / `hook` / `vieneu_voice`); `taken_urls`; `mark_posted`.
  - `publish/`: không kênh → «đăng tay — không gửi Buffer», giữ APPROVED. `dub._voice`: `params.vieneu_voice` → giọng kênh → mẫu.
  - `router.py`: `POST /tiktok/scan`, `POST /tiktok/take`, `POST /projects/{id}/posted`, `GET /projects/{id}/video?download=1`.
  - `notify.py` / Telegram: dự án không kênh ghi «đăng tay».
  - SPA: trang `StudioTiktokPage` (`/app/go/studio-tiktok`, sidebar SPA + Jinja «Lấy từ TikTok»), `UploadBox` thêm «Đăng tay»,
    `ProjectCard` nhãn «Đăng tay» + Tải video / Chép caption / Đã đăng, bảng Studio gom toast, `Toast` thêm `raised`.
  - Test cũ sửa theo luật mới: `test_upload_web_ghi_vao_hop_thu…`, `test_upload_su_tam_ghi_nguon_co_chu_san_va_khong_kenh_la_dang_tay`.

**Verification Proof**:
```
$ unshare -n pytest tests/test_studio_{graph,pipeline,ab_variants,api,dub_engine,vieneu,links}.py tests/test_audio_layer.py tests/test_viral_sources_page.py
  → 149 passed + 2 hỏng do luật cũ «bắt buộc kênh» → sửa test → 2 passed
$ ruff → All checks passed; lint-imports: 2 contract Studio KEPT (có fetch), không vi phạm mới
$ tsc --noEmit ok; npm run build ok
# Trình duyệt thật (Playwright, web tạm + SQLite riêng, pipeline thật với Whisper / AI giả, kết quả quét giả — chưa gọi TikTok):
#  bảng Studio: ô kênh có «Đăng tay»; thẻ «Đăng tay» ở cột Đã duyệt → Tải video = studio_1.mp4; Chép caption → clipboard
#  "Mẹo nhỏ hôm nay\n\n#meo #doisong"; Đã đăng → POSTED.
#  Lấy từ TikTok: quét → 8 thẻ; chưa chọn / chưa chọn kênh → nút tắt; mẫu lồng tiếng → hiện ô giọng, mẫu basic → ẩn;
#  chọn 7 + Đăng tay + hook → «Đã nhận 7 video», 7 việc fetch (params hook); quét lại → 7 «Đã lấy» từ server.
#  390 px & 1280 px không tràn ngang; lỗi JS duy nhất = ảnh bìa giả example.invalid (cố ý).
```
**Để chạy trên máy thật:** `pm2 restart Web_Dashboard Studio_Heavy Studio_Light && pm2 save`.
Chưa quét TikTok thật — chờ anh cho phép (gọi mạng TikTok, 1 kênh công khai, 3 video).
