# PLAN-118: Sửa lồng tiếng hỏng với video dài (Demucs hết RAM → «không có lời thoại» sai) + nút «Lồng tiếng lại»

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-118 |
| **Status** | Approved — anh hỏi 31/10 («anh bật lồng tiếng rồi mà… sao không được») |
| **Executor** | Claude Code (ngoại lệ ADR-061 Studio — sửa lỗi) |
| **Created** | 2026-10-31 |

---

## Chẩn đoán (dự án #11, video 8:41 tiếng Trung, asset #4)
1. Bước `analyze` đã nghe ra lời thoại tiếng Trung đầy đủ (`transcript.lang = zh`, nhiều câu).
2. Bước `dub` (việc #63) chạy 14 phút:
   - Demucs bị hệ điều hành giết (`demucs exit -9`) vì giữ cả 8:41 phút × 4 lớp âm thanh float32 trong RAM (~1,5–2 GB), mà máy
     còn trống ~200 MB;
   - nhánh dự phòng gọi Whisper lần hai trên tiếng gốc → ffmpeg tách tiếng cũng hỏng ngay lúc máy cạn RAM («no audio track») → `[]`;
   - kết luận **sai** «không có lời thoại» (`source_lang: null`). Dựng lại đúng nhánh này lúc máy rảnh thì chạy bình thường.
3. Kết quả hỏng **bị lưu cố định** (`studio_analyses.dub` ok=false) → lần sau bước dub báo «đã lồng tiếng trước đó» và bỏ qua.
   Không có đường nào lồng lại (lấy lại link thì `intake` dừng vì trùng; flow `recompose` không có bước dub).
4. Tiến trình hiện bước «Lồng tiếng» màu xanh ✓ dù thật ra không lồng được.

## Thiết kế
1. **Không nghe lại khi đã có lời thoại:** `make_tracks(..., hint_segments, hint_lang)`.
   - Demucs hỏng → dùng luôn transcript của `analyze`, khỏi chạy Whisper lần hai.
   - Demucs được → vẫn nghe lại trên giọng đã tách (mốc giờ sạch hơn); ra rỗng thì lấy transcript của `analyze`.
2. **Demucs theo từng khúc 60 giây** (`separate.py`): đọc / tách / ghi tuần tự, chồng 1 giây giữa hai khúc (crossfade) → RAM chỉ cỡ một khúc,
   video dài bao nhiêu cũng vậy.
3. **Chỉ lưu cố định kết quả dub chắc chắn:** lồng được, «đã đúng ngôn ngữ đích», «không có tiếng», «không hỗ trợ ngôn ngữ».
   - Lỗi khác (Demucs / Whisper / dịch / đọc hỏng) lưu kèm `retry: true`; lần sau bước dub chạy lại.
   - Bản lưu cũ ok=false mà transcript có lời (như #11) cũng coi là chạy lại được.
4. **Nút «Lồng tiếng lại»** trên trình edit (video có lời, khác tiếng Việt):
   - flow mới `redub` = dub → compose → render → caption → review → publish;
   - giữ kênh / mẫu / caption / hashtag, bật `dub`;
   - dự án cũ thành REJECTED («thay bằng bản lồng tiếng lại»).
5. **Tiến trình:**
   - bước lồng tiếng không lồng được → trạng thái mới `warn` (vàng ⚠, kèm lý do), không còn ✓ xanh;
   - tóm tắt việc «Xong — chờ anh duyệt (chưa lồng được tiếng: …)».

## Scope
`dub/engine.py`, `dub/separate.py`, `dub/__init__.py`, `contracts`/`pipeline` (flow `redub`), `editor.py` + `router.py` (redub),
`progress.py`, SPA (`StudioEditorPage`, `JobsPanel`, types / api), test.

## Out of Scope
- Demucs chạy GPU: venv dự án là torch CPU. Venv VieNeu có torch CUDA, có thể làm sau nếu cần nhanh hơn.
- Giới hạn RAM WSL: đề xuất G ở PLAN-117.

## Validation
- pytest:
  - make_tracks dùng transcript gợi ý khi Demucs hỏng / nghe lại rỗng;
  - Demucs theo khúc ghép đúng độ dài, có crossfade, dùng model giả;
  - quy tắc lưu dub;
  - flow redub chạy hết, dự án cũ thành REJECTED;
  - tiến trình `warn`.
- ruff, lint-imports, tsc + build, trình duyệt thật.

## Rollback
Không migration. Bỏ nút + flow `redub` là về như cũ.

---

## Execution Notes
- ✅ **Code xong (31/10), commit cục bộ — cần restart Web_Dashboard + Studio_Heavy + Studio_Light.** Không migration.
  - `dub/engine.make_tracks(..., hint_segments, hint_lang)`: Demucs hỏng → dùng lời thoại của `analyze` (không nghe lại);
    tách được mà nghe lại rỗng → cũng lùi về gợi ý.
  - `dub/separate.py`: tách theo khúc `CHUNK_SEC=60`, chồng `OVERLAP_SEC=1` + crossfade tuyến tính, đọc / ghi WAV tuần tự.
  - `dub/__init__.py`:
    - `_FINAL_REASONS` + `data.retry`; bản lưu cũ ok=false mà có lời → chạy lại;
    - cập nhật đúng 1 dòng `dub` / asset (UniqueConstraint);
    - truyền transcript làm gợi ý.
  - `pipeline`: flow `redub`. `editor`: `_dub_state` (trong `detail`), `redub()` lấy đúng `params` từ payload việc của dự án
    (dự phòng: đoán từ spec), giữ kênh / mẫu / caption / hashtag; dự án cũ → REJECTED. `router`: `POST /projects/{id}/redub`.
  - `progress`: bước dub hỏng → `warn` + tóm tắt «⚠ Lồng tiếng: …»; nhãn nguồn «Lồng tiếng lại».
  - SPA: `JobsPanel` chip ⚠; trình edit khung vàng «Video nói tiếng … nhưng chưa lồng tiếng Việt (lần trước: …)» + nút «Lồng tiếng lại».

**Verification Proof**:
```
$ unshare -n pytest (11 file Studio + process_control) → 171 passed + 1 test cũ so dict đủ khoá (thêm "retry") → sửa → 3/3 dub passed
  test_studio_dub_long.py (11): tách theo khúc 0.3 s / 2.35 s ra đúng độ dài, sai số < 2e-3, mỗi lần ≤ 1 khúc + phần chồng;
  make_tracks dùng gợi ý (Demucs hỏng: 0 lần Whisper; nghe lại rỗng: 1 lần rồi lùi); quy tắc chạy lại 4 ca; lồng hỏng → warn →
  redub → dự án mới 2 audio + phụ đề dub + giữ hook, dự án cũ REJECTED, 1 dòng dub.
$ ruff ok; lint-imports 2 contract Studio KEPT; tsc + build ok
# Trình duyệt thật (web tạm, pipeline thật, dub giả: lần 1 hỏng, lần 2 được): «Xong — chờ anh duyệt — ⚠ Lồng tiếng: không có lời
#   thoại», chip ⚠; trình edit «⚠ Video nói tiếng Trung nhưng chưa lồng tiếng Việt (lần trước: không có lời thoại)» → «Lồng tiếng
#   lại» → dự án #2 «zh→vi, 1/1 câu», dubbed=True, 2 audio; dự án #1 REJECTED; 0 lỗi JS.
```
**Dự án #11 trên máy thật:** sau khi restart, mở trình edit #11 → «Lồng tiếng lại».
