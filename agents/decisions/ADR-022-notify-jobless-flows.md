# ADR-022 — Thông báo Telegram cho luồng KHÔNG có job (READY, caption) + đăng ký notifier trong tiến trình web

- **Ngày**: 2026-09-08
- **Trạng thái**: **ĐÃ DUYỆT** — Owner báo trực tiếp 2026-09-08: Telegram trên máy Owner
  chạy tốt, nhưng "phần mới này chưa có"
- **Liên quan**: ADR-018 (READY), ADR-021 (caption), ADR-014 (ping healthchecks)

## Bối cảnh

Mọi thông báo hiện có đều gắn với **`Job`**: `notify_job_done`, `notify_job_failed`,
`notify_style_selection`, `notify_draft_ready`. Hai luồng làm hôm nay **không sinh job**:

- ADR-018: không có tài khoản ⇒ material dừng ở `READY`, Owner tải file đăng tay.
- ADR-021: caption viết thẳng trên material, không qua job.

⇒ Owner không nhận được gì khi video sẵn sàng hoặc khi caption viết xong. Với người đăng
tay thì đây chính là hai khoảnh khắc cần biết nhất.

**ĐÍNH CHÍNH (viết lại sau khi làm xong):** tiền đề ban đầu của ADR này — "tiến trình web
không đăng ký kênh nào" — **sai một nửa**. `app/main.py:55` đã đăng ký khi `.env` có token,
và hook `@app.on_event("startup")` nạp `runtime_settings` rồi gọi
`refresh_integration_notifiers()` → `NotifierService.replace(...)`. Tức web **đã** có kênh,
và đó mới là cơ chế thật. Phần đăng ký thêm trong `manage.py serve` (mục 4) là **lớp thứ ba**,
an toàn vì dedup theo `channel_key`, nhưng **không áp dụng khi chạy `--reload`** (uvicorn tạo
tiến trình con). Giữ lại vì nó bảo đảm cả đường `--no-reload` mà stack local dùng, nhưng
không được xem là cơ chế chính. Lý do thật khiến Owner không nhận thông báo chỉ là **mục 1-3**:
hai luồng mới không hề gọi `notify_*`.

## Quyết định

1. Hai hàm soạn tin trong `app/core/notifier/formatting.py`:
   - `material_ready_message(mat, media_path)` — nền tảng, tiêu đề, lượt xem, tên file,
     nhắc "tải file ở /app/viral để đăng tay".
   - `caption_ready_message(mat)` — caption + hashtag, nhắc bấm Sao chép; bản lỗi thì nêu
     lý do rút gọn.
2. Hai hàm phát trong `NotifierService`:
   - `notify_material_ready(mat, media_path=None)` — gửi kèm **video** nếu dưới ngưỡng
     Telegram (dùng lại `media_thumb.telegram_video_within_size_limit` như
     `notify_style_selection`), không thì gửi chữ.
   - `notify_caption_ready(mat, ok, reason="")`.
   Cả hai **không được làm hỏng việc chính**: bọc try/except, lỗi chỉ ghi log.
3. Nối:
   - `processor.py` nhánh ADR-018 (`target_account is None` → `READY`) → `notify_material_ready`.
   - `service.generate_caption_for_material` → `notify_caption_ready` ở cả nhánh thành công
     và nhánh lỗi.
4. **Đăng ký notifier trong tiến trình web**: `manage.py serve` gọi
   `NotifierService.register(TelegramNotifier(...))` sau khi đã áp runtime overrides
   (token có thể nằm trong `runtime_settings` chứ không phải `.env` — bài học ADR-021).
   Không có token ⇒ không đăng ký, ghi log info, mọi thứ khác chạy bình thường.

## Phạm vi

| Việc | File |
|---|---|
| 2 hàm soạn tin | `app/core/notifier/formatting.py` |
| 2 hàm phát | `app/core/notifier/service.py` |
| Nối READY | `app/features/viral_intake/processor.py` (≤5 dòng) |
| Nối caption | `app/features/viral_intake/service.py` (≤6 dòng) |
| Đăng ký kênh cho web | `manage.py` (`serve`) |
| Test | `tests/test_notify_jobless.py` (mới) |

## Ngoài phạm vi

- Không đổi thông báo của luồng job hiện có.
- Không thêm nút bấm Telegram cho material (callback handler gắn với job — PLAN riêng).
- Không gửi thông báo khi material vào `NEW`/`PROCESSING` (ồn, không đáng).

## Hết hiệu lực

Sau khi: bật stub notifier, chạy 1 material tới `READY` và 1 lượt viết caption → cả hai
đều phát đúng nội dung; và `serve` đăng ký kênh khi có token, bỏ qua êm khi không có.
