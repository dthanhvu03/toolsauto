# ADR-016 — Lớp phụ đề đốt và lớp âm thanh (voice-over, nhạc nền) cho video reup

- **Ngày**: 2026-09-07
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-07 ("oke triển khai từng mục"),
  mục 6 / 10 / 7 trong `docs/research/2026-09-07-tich-hop-mien-phi.md`
- **Liên quan**: ADR-006 (AI), ADR-014, PLAN-044/045 (intro/outro/hook)

## Bối cảnh

Video reup hiện chỉ "khác gốc" bằng intro/outro/hook chữ/logo (`ReupProcessor`). Khảo sát
07/09 cho thấy ba lớp thêm được **hoàn toàn local, không key, giấy phép cho thương mại**:

| Lớp | Công cụ | Giấy phép | Đã có trong máy? |
|---|---|---|---|
| Phụ đề tiếng Việt đốt vào video | `faster-whisper` (word timestamps) → `pysubs2` (ASS) → `ffmpeg -vf ass=`; font Be Vietnam Pro | MIT / OFL | whisper + ffmpeg có; `pysubs2` + font cần thêm |
| Voice-over tiếng Việt | `edge-tts` (`vi-VN-HoaiMyNeural`, `NamMinhNeural`); dự phòng offline `piper-tts` `vi_VN-vais1000-medium` | edge-tts không có ToS chính thức; piper GPL-3 (chỉ ràng buộc khi phân phối) | cần `pip` |
| Nhạc nền | `ffmpeg amix` từ `storage/media/music/` | tuỳ track — Owner tự tải (Meta Sound Collection cần đăng nhập FB) | ffmpeg có; **nhạc chưa có** |

## Quyết định

1. Mỗi lớp là **một module riêng, hàm thuần** `apply(input_path, output_path, ...) -> bool`,
   không import lẫn nhau, không biết DB:
   - `app/features/viral_intake/subtitle_layer.py`
   - `app/features/viral_intake/audio_layer.py` (voice-over + nhạc nền)
2. `ReupProcessor.process()` gọi các lớp **sau** intro/outro/hook, qua một điểm nối duy nhất
   `_apply_post_layers()`. Mỗi lớp **mặc định TẮT**, bật bằng SettingSpec trong `/app/settings`
   nhóm "Reup - lop them". Tắt hết ⇒ hành vi hiện tại **không đổi byte nào**.
3. **Lớp lỗi không làm hỏng reup**: lớp nào thất bại thì ghi log warning, giữ video của bước
   trước, `ReupResult.success` vẫn `True` (cùng nguyên tắc ADR-012).
4. Whisper dùng lại singleton `ContentOrchestrator._get_whisper_model()` — không load model
   lần hai. Mở rộng enum `ai.whisper_model_size` thêm `large-v3-turbo` và
   `erax-ai/EraX-WoW-Turbo-V1.1-CT2` (fine-tune tiếng Việt, MIT).
5. Font: tải Be Vietnam Pro (OFL) vào `app/static/fonts/`, commit kèm LICENSE. ffmpeg trên
   Windows cần `fontsdir=` trong filter `ass`.
6. Mỗi lớp là **một lần re-encode** riêng (đơn giản hơn gộp filter graph). Chấp nhận cho video
   ≤90 s; ghi nợ "gộp một pass" nếu sau này chậm.
7. **Proof bắt buộc trước khi commit**: chạy trên ≥1 video thật trong `storage/media/reup/`,
   xem file ra (phụ đề đúng vị trí 9:16, giọng đọc nghe được).

## Phạm vi

| Việc | File |
|---|---|
| Lớp phụ đề + test | `app/features/viral_intake/subtitle_layer.py` (mới), `tests/test_subtitle_layer.py` (mới) |
| Lớp âm thanh + test | `app/features/viral_intake/audio_layer.py` (mới), `tests/test_audio_layer.py` (mới) |
| Điểm nối + settings | `app/features/viral_intake/reup_processor.py` (`_apply_post_layers`, ≤30 dòng), `app/core/settings.py` |
| Font | `app/static/fonts/BeVietnamPro-*.ttf` + `OFL.txt` |
| Phụ thuộc | `requirements.txt`: `pysubs2`, `edge-tts`, `piper-tts` |

## Ngoài phạm vi

- Không đổi intro/outro/hook. Không đổi `processor.py` (tải video). Không đụng AI caption.
- Không karaoke từng chữ (align tiếng Việt chưa tin được — stable-ts archive, WhisperX lỗi VI).
- Không tự tải nhạc. Không gọi TTS trả phí.
- Không gộp các lớp vào một filter graph.

## Hết hiệu lực

Sau khi 3 lớp có test xanh, proof trên video thật, và mặc định tắt được chứng minh bằng test
"tắt hết ⇒ output == input của bước trước".
