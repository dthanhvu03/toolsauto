# ADR-060 — Lớp thuyết minh lại cho video reup (tách giọng → nhận ngôn ngữ → dịch → đọc lại)

- **Ngày**: 2026-10-27
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-10-27 ("triển khai" 4 bước: Demucs, Whisper tự nhận
  ngôn ngữ, AI dịch từng câu, đọc lại khớp thời gian rồi trộn lên nền đã tách)
- **Liên quan**: ADR-016 (lớp phụ đề + âm thanh), ADR-006 (AI qua `AIUseCases`), ADR-041 (`split.py` nhận `ask_ai`)

## Bối cảnh

Owner so tool với ReShort (AI thuyết minh đa ngôn ngữ). Tool đã có phụ đề Whisper và TTS, nhưng:

- Whisper bị ép `language="vi"`, video nước ngoài ra phụ đề sai.
- Không tách được giọng khỏi nhạc nền.
- Không dịch.
- TTS chỉ đọc câu hook ngắn, không đọc lại lời thoại.

## Quyết định

1. Module mới `app/features/viral_intake/dub_layer.py`, cùng nguyên tắc ADR-016:
   - hàm thuần, không biết DB;
   - `apply()` không raise; hỏng thì `ok=False`, không để lại file ra, ReupProcessor giữ video bước trước.
2. Các bước: bóc audio 44,1 kHz → Demucs `htdemucs` tách giọng/nền → Whisper `language=None` trên phần giọng →
   trùng ngôn ngữ đích thì bỏ qua → AI dịch theo lô 30 câu → edge-tts từng câu → trộn bằng numpy → mux `-c:v copy`.
3. **Khớp thời gian**:
   - mỗi câu được nói tới đầu câu sau (hoặc hết video), chừa 0,25 giây nghỉ;
   - prompt dịch ghi trần ký tự theo khe (`LANGUAGES[..][3]` ký tự/giây);
   - gọt khoảng lặng edge-tts tự chèn (~0,2 giây đầu, ~0,9 giây cuối mỗi file) trước khi tính tốc độ;
   - câu dài hơn khe thì tăng tốc `atempo` tối đa 1,2×;
   - vẫn dài thì câu sau lùi lại, không cắt chữ; chỉ cắt + fade khi chạm hết video.
   - Vì sao: Owner nghe bản đầu (tối đa 1,5×, không nghỉ, không gọt lặng) thấy "đọc nhanh, cụt cuối câu".
     Whisper nghe lại thì đủ chữ; lỗi là các câu dính nhau và bị tăng tốc vì khoảng lặng thừa.
4. **Demucs chạy ở tiến trình riêng** (`demucs_separate.py`, gọi qua `sys.executable -m`):
   - torch + model chiếm khoảng 1 GB, máy chỉ có 7 GB, worker sống lâu;
   - tiến trình thoát là trả RAM, crash cũng không kéo worker theo;
   - đọc/ghi WAV bằng `wave` + numpy, không dùng `torchaudio.save` (backend I/O đổi liên tục).
5. Demucs hỏng hoặc chưa cài → vẫn thuyết minh, nền là audio gốc ở 0,15 (giọng gốc nghe lí nhí).
6. AI và TTS được **tiêm vào** (`translate`, `synthesize`), như `split.py` nhận `ask_ai`:
   - lớp không import AI hay `audio_layer`;
   - ReupProcessor nối `AIUseCases.generate_text(purpose=DUB_TRANSLATE)` và `audio_layer.synthesize_voice`;
   - ngôn ngữ khác tiếng Việt chỉ dùng edge-tts (piper dự phòng chỉ có giọng Việt).
7. Phụ thuộc một chiều duy nhất: `dub_layer` → `subtitle_layer.transcribe_segments` (đường Whisper + bộ lọc câu
   bịa). `transcribe_words` gọi hàm mới với `language="vi"`, hành vi cũ không đổi.
8. Thứ tự trong `_apply_post_layers`: **thuyết minh → phụ đề → âm thanh**.
   - Thuyết minh thành công thì phụ đề đốt luôn câu đã dịch (`segments=`), không chạy Whisper lần hai.
   - Bỏ qua (cùng ngôn ngữ…) thì phụ đề chạy như cũ.
9. Settings nhóm "Reup — lớp thêm", **mặc định tắt**:
   - `reup.dub_enabled`;
   - `reup.dub_target_lang` (13 ngôn ngữ: vi en ja ko zh es th id fr de pt ru hi);
   - `reup.dub_voice_gender`;
   - `reup.dub_background_volume`.
10. Phụ thuộc:
    - torch **CPU** 2.5.1 + torchaudio 2.5.1 + demucs 4.0.1, cài tay (ghi trong `requirements.txt` dạng chú thích)
      để `pip install -r` không kéo torch CUDA ~2,5 GB;
    - cài vào venv làm sympy hạ từ 1.14.0 xuống 1.13.1 (onnxruntime vẫn chạy);
    - edge-tts nâng lên 7.3.1, vì 7.2.8 bị Microsoft trả 403 (lỗi này cũng làm hỏng voice-over hook của ADR-016).

## Proof (27/10, video thật `viral_1319`, 34,6 giây, tiếng Việt → tiếng Anh)

- Whisper `medium` nhận `vi`, xác suất 1,00. AI dịch qua Gemini 3.5 Flash (9Router 404 nên tự chuyển dự phòng).
- 5/5 câu đọc bằng `en-US-AriaNeural`; file ra 34,55 giây, đúng bằng file vào. Phụ đề tiếng Anh đốt đúng vị trí (xem
  bằng mắt khung giây 12).
- Whisper `base` nghe lại file ra: `en`, xác suất 0,99. Giọng Việt gốc đã bị thay.
- Thời gian:
  - Demucs CPU 93 giây (sau khi đã có model; lần đầu tải 84 MB);
  - toàn lớp 312 giây, gồm 56 giây nạp Whisper `medium` (trong worker là singleton, đã nạp sẵn).
- Test: `tests/test_dub_layer.py` mới; 220 test lớp phụ đề/âm thanh/thuyết minh + 218 test reup/viral/settings qua.
  Import-linter không thêm vi phạm (2 contract đã vỡ từ trước).

## Ngoài phạm vi

- Không nhân bản giọng người gốc (voice clone). Không lip-sync.
- Không chọn ngôn ngữ theo từng Page (một ngôn ngữ đích cho cả hệ thống).
- Không xuất nhiều phiên bản ngôn ngữ từ một video.
- Font Be Vietnam Pro không có chữ Nhật/Hàn/Trung: phụ đề các ngôn ngữ đó nhờ libass tìm font hệ thống, chưa kiểm.
- Không dùng GPU. Torch CUDA trên GTX 1650 4 GB sẽ nhanh hơn nhiều nhưng phải tải thêm khoảng 2,5 GB.

## Rủi ro

- edge-tts không có ToS chính thức, Microsoft đổi token là hỏng (vừa xảy ra với 7.2.8). Khi đó lớp trả
  `tts failed`, video giữ bản trước.
- Gọi AI mỗi video (1 lần mỗi 30 câu).
