# PLAN-111: Nối VieNeu-TTS (GPU) vào bước lồng tiếng Studio

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-111 |
| **Status** | Approved — anh giao 31/10 («oke em rồi em nối vào cho anh nhé», sau khi nghe bản GPU) |
| **Executor** | Claude Code (ngoại lệ ADR-061: anh giao trực tiếp Studio, PLAN trước, đúng scope) |
| **Created** | 2026-10-31 |

---

## Goal
Bước `dub` đọc tiếng Việt bằng VieNeu-TTS v3 Turbo trên GPU (RTF ≈ 0,25, giọng tự nhiên hơn edge-tts) thay vì edge-tts
(endpoint không chính thức). Không có VieNeu thì lồng tiếng chạy y như cũ.

## Thiết kế
- **VieNeu ở venv riêng** (`/home/vu/venv-vieneu`: torch 2.8 + transformers 5 — không trộn vào venv dự án).
- **Server cục bộ** `app/features/studio/dub/vieneu_server.py`, chạy bằng python của venv VieNeu, **không import `app`**:
  - nạp model **một lần** (65–90 s), giữ trên GPU (~0,5 GB VRAM);
  - chỉ nghe `127.0.0.1:8790` (stdlib `http.server`, một luồng — model không chạy song song);
  - `GET /health` → `{"ok", "voices"}`; `POST /tts` `{"text", "voice"}` → WAV. Chữ tối đa 1500 ký tự.
- **PM2 app `VieNeu_TTS`** trong `ecosystem.config.js`.
- **Client** trong `app/core/media/tts.py`: engine `vieneu`.
  - `auto` (giọng Việt): vieneu → edge → piper. Server tắt hoặc lỗi thì rơi xuống engine kế, chờ tối đa vài giây.
  - Giọng: tên giọng edge tiếng Việt quy về giọng VieNeu theo giới tính (nữ: Ngọc Huyền, nam: Hải Đăng). Tên giọng VieNeu
    thì giữ nguyên.
  - URL đổi bằng biến môi trường `VIENEU_TTS_URL` (rỗng = tắt vieneu).
- Bước `dub` không đổi logic: vẫn gọi `tts.synthesize(..., engine="auto")` cho tiếng Việt; ngôn ngữ khác vẫn chỉ edge.

## Scope
- `vieneu_server.py` (mới), `app/core/media/tts.py` (engine vieneu), `ecosystem.config.js` (app mới), test, README Studio.
- Bật trên máy thật: `pm2 start ecosystem.config.js --only VieNeu_TTS && pm2 save`, `pm2 restart Studio_Heavy`.

## Out of Scope
- Chọn giọng VieNeu trên web (theo kênh / mẫu), clone giọng riêng, điều tốc độ đọc — làm sau nếu anh cần.
- Hệ cũ `viral_intake/audio_layer.py` (giữ nguyên tới P6).

## Validation
- Test: engine vieneu ghi file đúng; server tắt → edge; quy giọng; handler server với model giả.
- ruff, lint-imports. Chạy thật: server lên, `synthesize` một câu qua HTTP; lồng tiếng một video thật nếu có.

## Rollback
`pm2 stop VieNeu_TTS` (hoặc `VIENEU_TTS_URL=`) → `auto` tự về edge → piper. Không có migration.

---

## Execution Notes
- ✅ **Xong, chạy trên máy thật (31/10).**
  - `app/features/studio/dub/vieneu_server.py` (mới, không import `app`; numpy + `wave` ghi WAV), PM2 `VieNeu_TTS`
    (`HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1`: chỉ dùng cache, không tự tải code mới của model).
  - `app/core/media/tts.py`: engine `vieneu` đứng đầu `auto`; giọng edge Việt → Ngọc Huyền (nữ) / Hải Đăng (nam);
    gom phần WAV → đuôi đích của piper thành `_wav_to_output` dùng chung. Bước `dub` không sửa dòng nào.
  - Chỉ Studio dùng `app.core.media.tts` (hệ cũ dùng `viral_intake/audio_layer.py`, không đụng).

**Verification Proof**:
```
$ unshare -n pytest tests/test_studio_{graph,pipeline,ab_variants,api,dub_engine,vieneu}.py tests/test_audio_layer.py -q → 127 passed
$ ruff → All checks passed; lint-imports: 2 contract hỏng y như trước khi sửa, không dòng mới nào từ tts / vieneu
$ pm2 start ecosystem.config.js --only VieNeu_TTS → «nạp xong 48s trên cuda, 25 giọng, nghe 127.0.0.1:8790»; khởi động lại: 0 lần gọi huggingface.co
$ venv/bin/python: tts.synthesize(..., voice="vi-VN-HoaiMyNeural") → True 2.1s; NamMinh → True 1.0s; server log POST /tts 200 1.3s / 0.7s
$ nvidia-smi: 727 MiB / 4096 MiB khi server chờ (NVENC render vẫn dư chỗ)
$ pm2 restart Studio_Heavy && pm2 save
```
Chưa lồng tiếng trọn một video thật qua Studio (cần video tiếng nước ngoài + mẫu `reup_dub`, có gọi AI dịch) — anh thử trên web.
