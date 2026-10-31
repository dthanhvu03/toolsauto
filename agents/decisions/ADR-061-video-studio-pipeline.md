# ADR-061: Studio — hệ edit video gồm các module một việc, nối bằng hàng việc

## Status
Accepted. Owner giao trực tiếp ngày 2026-10-30: «tách hết ra để mỗi module làm 1 việc của nó và nối lại quy trình… em quyết toàn bộ đi». Kế hoạch: PLAN-106.

## Context
- Mọi bài đều đăng qua Buffer. Tool cũ (Playwright, đa nền tảng) còn khoảng 25k dòng chết. Mô hình dữ liệu vẫn xoay quanh Facebook (`Job`, `Account`, `target_page` mang 2 nghĩa).
- Phần edit nằm trong một hàm khoảng 680 dòng (`viral_intake/processor.py::_process_viral_materials`) và `ReupProcessor`:
  - mỗi lớp edit encode lại một lần;
  - Whisper chạy tới 3 lần cho 1 video;
  - không có bản xem trước để duyệt, không sửa tay được.
- Owner muốn edit tự động theo mẫu, có duyệt / chỉnh tay, nhận 3 nguồn (reup, tự quay, AI), điều khiển bằng web + Telegram, và xây song song với hệ cũ.

## Decision
1. **Feature mới `app/features/studio/`, mỗi bước 1 package làm đúng 1 việc:** intake, analyze, compose, render, caption, review, publish (sau thêm script, voice, visuals).
   - Các bước không import nhau, không import feature khác. Nối với feature khác chỉ qua `feature_hooks`.
   - Kiểm bằng import-linter.
2. **Nối các bước bằng hàng việc `studio_tasks`.**
   - Mỗi lần chuyển bước là 1 dòng.
   - `pipeline.py` là chỗ duy nhất biết thứ tự (`FLOWS`).
   - Worker nhận việc theo làn (`heavy` / `light`) bằng `FOR UPDATE SKIP LOCKED`, chạy bước, rồi xếp bước sau.
   - Thử lại theo `max_attempts`. Việc treo quá 30 phút thì trả lại hàng.
3. **Dự án = spec JSON (`ProjectSpec`).**
   - Mẫu edit = hàm sinh spec. Sửa tay = sửa spec rồi render lại.
   - Render = 1 lệnh ffmpeg `filter_complex`, 1 lượt encode.
4. **Phân tích lưu cache theo asset** (`studio_analysis`). Phụ đề, dub, chia đoạn, caption đọc lại, không chạy Whisper lần hai.
5. **Đích duy nhất là kênh Buffer** (`studio_channels`).
   - Giai đoạn chuyển tiếp: dự án đã duyệt tạo 1 dòng `viral_materials` READY để dùng luồng Buffer sẵn có.
   - Bỏ cầu nối này khi dọn code cũ.
6. **Reup giữ ghi nguồn.**
   - Studio không có bước cắt watermark và không có lọc đổi tốc độ / màu / zoom để né nhận diện trùng.
   - Asset lưu `credit`; kênh có tuỳ chọn hiện «Nguồn: @…».

### Bổ sung P2 (31/10)
7. **Lồng tiếng là bước riêng (`dub`), ra 2 asset audio** (giọng đọc + nền đã tách giọng gốc) cùng mốc giây với video gốc, ghi vào phân tích `dub`.
   - Spec thêm `Clip.audio`: tiếng của clip lấy từ các asset audio này thay tiếng gốc. Mẫu `reup_dub` dùng nó; trình edit chỉnh được âm lượng giọng và nền riêng.
   - Dịch / đọc hỏng thì thử lại theo hàng việc; lần cuối vẫn hỏng thì giữ tiếng gốc, không làm hỏng dự án.
8. **Code dùng lại từ hệ cũ được port, không import.** Studio không được import `viral_intake`, mà Whisper + bộ lọc câu bịa, TTS, Demucs, lõi dub đều nằm ở đó.
   - Phần dùng chung lâu dài sang `app/core/media/` (`speech.py`, `tts.py`); phần riêng của dub sang `studio/dub/`.
   - Bản cũ không sửa (hệ cũ đang đăng thật) và bị xoá ở P6. Tới lúc đó có 2 bản: sửa bộ lọc câu bịa thì sửa cả hai.
9. **Hệ cũ nhường kênh bằng cờ `studio_channels.take_reup`** (mặc định tắt). Video reup tải + chống trùng xong, có đúng 1 kênh đích và kênh đó bật cờ → hook `studio.take_reup` chuyển file sang hộp thư Studio. Material đổi sang `ViralStatus.STUDIO`, hệ cũ không xử lý tiếp. Phần con của video chia phần vẫn đi đường cũ.
10. **Caption là bước riêng sau render**, dùng lại `ContentOrchestrator.generate_caption`. AI hỏng chỉ ghi chú, người duyệt viết tay.

### Bổ sung P4.1 (31/10)
11. **Biến thể A/B (lật gương, LUT, xáo đoạn) chỉ cho nội dung của mình** (`origin` upload / ai / brand). Asset reup bị bỏ qua ở
    mẫu, chặn ở lưu spec và ở API biến thể. Lý do: cùng D1 — biến đổi ngẫu nhiên trên video của người khác là để né nhận diện
    trùng / bản quyền, Studio không làm việc đó. LUT cố định theo kênh là tông màu nhận diện, dùng cho mọi nguồn.

## Ngoại lệ phân vai
Claude Code làm cả backend cho PLAN-106 (P1–P6), giữ 3 ràng buộc của ADR-010:
- có PLAN trước khi code;
- đúng scope của PLAN;
- migration chỉ thêm, không DROP / DELETE production khi chưa hỏi Owner.

Anti review từng bước sau khi xong. Hết PLAN-106 thì quay lại phân vai gốc.

## Consequences
- Được:
  - mỗi bước test riêng được và thay riêng được, ví dụ đổi engine TTS chỉ đụng `voice/`;
  - thêm nguồn mới chỉ cần thêm 1 flow trong `pipeline.py`;
  - render tách khỏi Maintenance.
- Mất:
  - có 2 hệ chạy cùng lúc cho tới P6, phải có cờ theo kênh để không cùng đẩy 1 kênh;
  - thêm 2 process PM2.
- Hàng việc trên Postgres là đủ cho 1 máy. Không dùng Redis / Celery.
