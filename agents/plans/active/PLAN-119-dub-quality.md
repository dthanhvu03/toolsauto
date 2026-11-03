# PLAN-119: Chất lượng lồng tiếng — dịch theo câu, câu đọc Việt hoá, sửa chữ nghe nhầm, chuẩn độ to, trần bitrate

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-119 |
| **Status** | Approved — anh duyệt 31/10 («ok em vá giúp anh nhé») sau bản kiểm dự án #12 |
| **Executor** | Claude Code (ngoại lệ ADR-061 Studio) |
| **Created** | 2026-10-31 |

---

## Kiểm dự án #12 (video tiếng Anh 1:35, 23 câu) — trước khi sửa
- **Kỹ thuật ổn:**
  - VieNeu «Mai Anh» đọc 23/23 câu;
  - đầu câu lệch −0,34…+0,64 s so với bản gốc, không câu nào chồng nhau, nói 2,6–4,4 âm tiết/s (không bị tua);
  - phần nền không lọt giọng gốc (Whisper nghe nền: 0 từ tiếng Anh);
  - giọng to hơn nền ~9 dB.
- **Lỗi:**
  1. Dịch theo đoạn Whisper (một câu vắt qua 2 đoạn) → câu Việt bị chẻ («…từ năm 1880,» / «lâu nhất Wilkshire…», «Do đó» bị treo).
  2. Tên riêng / thuật ngữ tiếng Anh đọc bằng giọng Việt bị méo («tee box» → «tì bóc», «green» → «Rin»).
  3. Lỗi nghe nhầm của Whisper đi thẳng vào bản dịch («Wilkshire», «barf»).
  4. Video ra −20,7 LUFS: nhỏ hơn bản gốc 4 dB, nền tảng ~ −14.
  5. File ra 59,8 MB so với gốc 14,6 MB (mã lại video đã nén ra ~5 Mbps).

## Thiết kế
1. `engine.merge_sentences`: gộp đoạn Whisper thành câu.
   - Gộp khi đoạn trước chưa có dấu kết câu và cách đoạn sau ≤ 0,6 s; câu gộp ≤ 10 s.
   - Dịch, đọc và đặt thời gian theo câu.
2. Prompt trả `{"sub", "say"}` mỗi câu:
   - `sub` = phụ đề, giữ tên riêng;
   - `say` = câu giọng đọc: Việt hoá thuật ngữ, số / giờ / tiền / năm viết thành chữ, tên nước ngoài phiên âm ngắn.
   - Giọng đọc `say`, phụ đề lấy `sub`. AI trả mảng chuỗi kiểu cũ vẫn nhận.
3. Prompt nhắc: bản gốc từ nhận dạng giọng nói, sửa chữ / tên nghe nhầm theo ngữ cảnh.
4. `Audio.loudness` (mặc định −14 LUFS) → `loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000` sau khi trộn.
   - Bài không có tiếng nào thì bỏ qua (toàn im lặng qua loudnorm ra NaN → aac hỏng).
5. `encoder.MAXRATE = 3M` (+ `bufsize 6M`) cho cả NVENC lẫn x264.
- Kèm:
  - nút «Dịch & lồng lại» cho dự án đã lồng (`force_dub` — dùng bản dịch mới, bỏ qua kết quả lưu);
  - lỗi không phải GPU (vd NaN) khi chạy NVENC không còn tắt NVENC cho cả worker (`render._gpu_error`).

## Scope
`dub/engine.py`, `dub/__init__.py` (`force_dub`), `editor.redub`, `render/graph.py`, `render/encoder.py`, `render/__init__.py`,
`spec.Audio`, SPA trình edit, test.

## Out of Scope
- Whisper model lớn hơn (`small` / `medium`, GPU) cho bản gốc chuẩn hơn.
- Giọng đọc khác nhau theo người nói.
- Chuẩn độ to 2 lượt (đo rồi chỉnh tuyến tính).

## Rollback
Không migration. `Audio.loudness = None` tắt chuẩn hoá. Prompt / gộp câu là code thuần.

---

## Execution Notes
- ✅ **Code xong (31/10), commit cục bộ — cần restart Studio_Heavy + Studio_Light + Web_Dashboard.**

**Verification Proof**:
```
# Đo trên dự án #12 thật (render lại vào thư mục tạm, NVENC):
#   không trần: 59,8 MB · trần 4M: 45,7 MB (SSIM 0,986) · trần 3M: 36,1 MB (SSIM 0,981); loudnorm → −14,2 LUFS
# Dịch thật (AI hệ thống, 9Router lỗi auth 404 → Gemini dự phòng), lời gốc #12: 23 đoạn → 13 câu;
#   «Wilkshire» → «Wiltshire», «across the barf» → «thành phố Bath» (đúng: Kingsdown cạnh Bath);
#   say: «khu phát bóng», «hai trăm năm mươi bảng», «năm giờ rưỡi», «từ năm một nghìn tám trăm tám mươi»
#   (lần đầu ra «một tám tám không» → thêm ví dụ năm vào prompt → đúng)
$ unshare -n pytest (12 file Studio + process_control) → 180 passed; gồm test_studio_dub_translate (4) + graph (loudnorm / trần / video câm) + pipeline (lỗi không phải GPU giữ NVENC)
  + dub_long (lồng lại dù đã lồng ok); test render lại từng hỏng vì loudnorm trên video câm → đã sửa
```
**Áp vào #12 trên máy thật:** sau khi restart, mở #12 → «Dịch & lồng lại».
