# ADR-021 — AI viết caption cho video `READY` (không cần tài khoản, không cần job)

- **Ngày**: 2026-09-08
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-08 ("thì cho AI viết khi không
  có tài khoản cũng được mà em")
- **Liên quan**: ADR-018 (READY), ADR-014 (list model + `ai check`), ADR-006 (chiến lược AI fallback)

## Bối cảnh

Owner đăng tay: tải file `_reup.mp4` từ dòng **Sẵn sàng đăng tay** rồi đăng lên Facebook.
Đã kiểm chạy được (Chrome thật, `viral_68_reup.mp4` 20 MB). **Thiếu đúng một mảnh: caption.**

AI viết caption hiện gắn vào `Job` (`ai_generator` nhặt job `DRAFT`), mà job chỉ sinh khi có
tài khoản. 0 tài khoản ⇒ material dừng ở `READY` ⇒ **không bao giờ có caption**. Owner phải
tự gõ, hoặc dùng tạm tiêu đề gốc của video.

Nhưng `ContentOrchestrator.generate_caption(video_path, style, context, page_name,
page_niches, affiliate_keywords) -> dict` nhận **đường dẫn file**, không cần job. Nên chạy
được thẳng trên `_reup.mp4` của material.

## Quyết định

1. Caption lưu **trên material**, không mượn job:
   `ViralMaterial.ai_caption` (Text), `ai_hashtags` (Text, JSON list),
   `ai_caption_at` (Integer epoch), `ai_caption_error` (Text) — đều nullable.
2. `ViralService.generate_caption_for_material(db, material_id, *, style=None) -> (ok, msg)`:
   - lấy file qua `find_reup_path` (không có ⇒ báo lỗi rõ, không chạy AI);
   - `context` = `title` đã bóc sạch dấu `### BOOST_CONTEXT: … ###` và `[AI_GENERATE]`;
   - gọi `ContentOrchestrator().generate_caption(...)`; caption rỗng ⇒ ghi `ai_caption_error`;
   - luôn ghi `ai_caption_at`.
3. **Chặn sớm khi chưa có key** — quan trọng cho trải nghiệm: trước khi chạy, kiểm nhanh có
   provider nào khả dụng không (`GEMINI_API_KEY` dạng `AIza…`, hoặc `OPENROUTER_API_KEY`,
   hoặc 9Router bật). Không có ⇒ **trả lỗi ngay**
   *"Chưa cấu hình key AI — vào .env đặt GEMINI_API_KEY (dạng AIza…) rồi chạy `python manage.py ai check`"*.
   Không có bước này thì mỗi lần bấm sẽ chạy Whisper ~2 phút rồi mới rơi xuống fallback —
   người dùng tưởng tool treo.
4. `POST /viral/{id}/caption` chạy **nền** (`BackgroundTasks`, session riêng) vì Whisper +
   AI mất hàng chục giây tới vài phút; trả toast ngay + trigger làm mới bảng.
5. UI trên dòng material có file `_reup`:
   - chưa có caption ⇒ nút **"Viết caption"**;
   - có rồi ⇒ hiện caption (rút gọn, bấm mở rộng) + hashtag + nút **Sao chép** (caption +
     hashtag) + nút **Viết lại**;
   - có `ai_caption_error` ⇒ hiện lỗi rút gọn, tooltip đầy đủ.
6. Không đụng `ai_generator` / luồng job. Có tài khoản thì đường cũ vẫn y nguyên.

## Phạm vi

| Việc | File |
|---|---|
| 4 cột | `app/core/database/models/viral.py` |
| Migration | `alembic/versions/<new>_material_caption.py` (head hiện tại `l0a7b8c9d0e1`) |
| Service + kiểm key sớm | `app/features/viral_intake/service.py` |
| Endpoint nền | `app/features/viral_intake/router.py` |
| Nút + hiện caption + sao chép | `app/templates/fragments/viral_row.html` |
| Test | `tests/test_material_caption.py` (mới) |

## Ngoài phạm vi

- Không sửa `ContentOrchestrator` / `native_fallback` / `ai_generator`.
- Không tự sinh caption hàng loạt, không tự chạy theo lịch — chỉ khi Owner bấm.
- Không thêm provider AI mới (Groq vẫn cắm qua `OPENROUTER_BASE_URL` như ADR-014).
- Không gắn caption vào job khi sau này có tài khoản (PLAN riêng nếu cần).

## Hết hiệu lực

Sau proof: bấm "Viết caption" trên 1 material `READY` → có `ai_caption` trong DB và hiện
trên UI với nút Sao chép; và khi chưa có key thì báo lỗi **ngay**, không chạy Whisper.
