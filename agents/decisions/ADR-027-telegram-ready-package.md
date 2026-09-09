# ADR-027 — Video xong là bắn một tin Telegram đủ dùng: file + caption bấm-là-copy

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-09: *"khi đã hoàn tất 1 video
  đã có caption và video được xào chẻ thì bắn về tele cho anh, anh chỉ việc bấm nút tải và
  sao chép caption thôi"*; chọn phương án **"Tự viết, rồi bắn 1 tin gộp"** khi được hỏi.
- **Liên quan**: **ADR-022 (thay hành vi thông báo READY)**, **ADR-021 (caption thủ công →
  thêm đường tự động)**, ADR-018 (READY không account)

## Bối cảnh

Owner đăng tay: chờ thông báo, tải video, dán caption. Hôm nay luồng đó **chưa khép kín**:

| Hiện tại | Vấn đề |
|---|---|
| Tin 1 (ADR-022): video `READY`, có kèm file, chữ *"Mở /app/viral rồi bấm Tải file"* | Đã có file rồi mà vẫn bảo mở web |
| Tin 2 (ADR-022): caption viết xong | **Chỉ tới sau khi Owner tự bấm "Viết caption" trên web** |

Caption **không hề tự chạy**: `generate_caption_for_material` chỉ có đúng một nơi gọi là
`router.py:51` — nút trên UI (ADR-021 mục 4). Nên khoảnh khắc "video xong **và** có caption"
không bao giờ tự tới; gộp tin thôi thì Owner vẫn phải mở web mỗi video, đúng thứ cần bỏ.

Hai chi tiết kỹ thuật quyết định thiết kế:

1. **Telegram cắt caption tin có media ở 1024 ký tự** — `telegram_client.send_video` làm
   `caption[:1024]`. Nhét caption vào tin kèm video mà dài quá thì Owner **copy ra một caption
   cụt đuôi** mà không hề biết. Tệ hơn: cắt giữa thẻ HTML ⇒ Telegram trả 400 ⇒ mất cả tin.
2. **Chữ trong `<code>` là bấm-là-copy** trên Telegram. Đây là thứ biến "sao chép caption"
   thành một cú chạm, không cần nút, không cần web.

## Quyết định

1. **Tự viết caption ngay sau khi video xào chẻ xong**, trong nhánh `READY` của
   `processor.py`, **trước** khi phát thông báo. Chạy thẳng (không nền): processor vốn đã
   tải + ffmpeg hàng phút, thêm Whisper + AI ở đây không đổi bản chất, và tin nhắn **phải**
   đợi caption mới gộp được.
2. **Ô bật/tắt** `viral.auto_caption_on_ready` (bool, **mặc định BẬT**) ở `/app/settings`,
   mục "Quét TikTok & Viral". Tắt ⇒ quay về đúng hành vi ADR-022 hôm nay.
3. **`generate_caption_for_material(..., notify: bool = True)`** — processor gọi với
   `notify=False` để **không** bắn tin caption rời; mọi caller cũ không truyền gì nên hành vi
   giữ nguyên. Không tách hàm mới: cùng một việc, khác mỗi chuyện có phát tin hay không.
4. **Một tin, không phải hai**: `material_ready_message` nhận thêm caption. Caption + hashtag
   nằm trong **một khối `<code>` duy nhất** — một cú chạm là copy đủ cả hai, dán thẳng vào
   Facebook. Bỏ câu *"Mở /app/viral rồi bấm Tải file"*: file đã đính kèm ngay trong tin.
5. **Không bao giờ để khối copy bị cắt.** `notify_material_ready` đo tin trước khi gửi: nếu
   gửi kèm video mà tin vượt 1024 ký tự ⇒ **video đi với phần đầu ngắn**, rồi **tin thứ hai**
   chở nguyên khối caption (tin chữ được 4096). Đo trên chuỗi HTML thô — dài hơn text sau khi
   Telegram bóc thẻ, nên ngưỡng này **thận trọng về phía an toàn**: thà tách sớm một nhịp còn
   hơn để Owner dán ra caption thiếu đuôi.
6. **Caption hỏng không được chặn thông báo**: AI lỗi / chưa có key ⇒ vẫn bắn tin video như
   cũ, kèm một dòng nêu vì sao chưa có caption. Việc chính (material đã `READY`, file đã có)
   đã commit xong — thông báo là việc phụ, giữ nguyên nguyên tắc ADR-022 mục 2.

## Phạm vi

| Việc | File |
|---|---|
| Ô bật/tắt `viral.auto_caption_on_ready` | `app/core/settings.py` |
| Tham số `notify` | `app/features/viral_intake/service.py` |
| Gọi caption + phát tin trong nhánh READY | `app/features/viral_intake/processor.py` |
| Tin gộp + khối `<code>` | `app/core/notifier/formatting.py` |
| Tách tin khi quá 1024 | `app/core/notifier/service.py` |
| Test | `tests/test_notify_jobless.py` (thêm mục ADR-027) |

## Ngoài phạm vi

- Không đụng luồng **có account** (job + `notify_style_selection`) — y nguyên.
- Không đụng nút "Viết caption" / "Viết lại" trên web; bấm tay vẫn bắn tin caption như ADR-022.
- Không gửi video quá ngưỡng 50 MB của Bot API (vẫn gửi chữ như hiện nay) — nâng ngưỡng cần
  Local Bot API server, việc khác.
- Không thêm nút bấm (inline keyboard) trong Telegram: nút cần URL công khai tới máy chạy
  tool, mà tool chạy ở `127.0.0.1`. Đính kèm file + `<code>` đạt đúng yêu cầu mà không cần mở
  cổng ra ngoài.

## Hết hiệu lực

Sau proof: một material đi tới `READY` với ô bật ⇒ Owner nhận **đúng một** tin, kèm file
`_reup.mp4`, trong tin có khối `<code>` chứa caption + hashtag; tắt ô ⇒ đúng một tin không
caption như ADR-022; AI hỏng ⇒ vẫn một tin, có dòng nêu lý do; tin dài quá 1024 ⇒ hai tin và
khối caption **nguyên vẹn**.

## Proof (2026-09-09)

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Ô bật ⇒ **đúng một** tin, kèm `_reup.mp4`, có khối `<code>` caption + hashtag | `test_h9_bat_o_thi_tu_viet_caption_va_ban_DUNG_MOT_tin_gop` — 1 lời gọi AI, 1 tin, không có tin caption rời |
| Caption + hashtag trong **một** khối, không phải hai | `test_h1` — đếm `<code>` = 1, thân khối = `"Câu mở đầu\n\n#a #b"` |
| Chữ người lạ viết vẫn escape | `test_h2` — `&lt;vô địch&gt;`, `&amp;` |
| Có caption ⇒ bỏ câu "Mở /app/viral" (file đã đính kèm) | `test_h4` |
| Tắt ô ⇒ **không gọi AI**, tin y như ADR-022 | `test_h10` — `calls == 0`, tin có lại `/app/viral` |
| AI nổ ⇒ vẫn một tin video, kèm dòng nêu lý do | `test_h11`, `test_h5` |
| Tin > 1024 ⇒ **hai tin**, khối caption nguyên vẹn | `test_h7` — thứ tự `["video", "text"]`, caption 1200 ký tự còn đủ |
| Tin ngắn ⇒ vẫn một tin kèm video | `test_h8` |
| Bấm tay trên web vẫn bắn tin caption riêng (ADR-021/022 không đổi) | `test_h12` |

**Toàn suite: 612 passed, 16 skipped, 0 failed.**

### Một lỗi thật do suite bắt được

Bản đầu chỉ bọc `try/except` quanh **lời gọi AI**, không bọc lượt **đọc ô cài đặt**. Đọc
`runtime_settings` cũng đụng DB; hỏng ở đó thì ngoại lệ thoát ra vòng xử lý và **đánh
`FAILED` một video đã xử lý xong, đã commit `READY`** — đúng thứ mục 6 cấm. Ba test có sẵn
(`test_viral_ready_without_account` ×2, `test_material_dedup`) đỏ ngay vì bảng
`runtime_settings` không tồn tại trong SQLite của chúng.

Đã bọc cả lượt đọc cài đặt, thêm `db.rollback()` trong `except` (lỗi DB làm session hỏng,
không rollback thì vòng lặp sau dùng tiếp là hỏng theo), và thêm
`test_h13_doc_o_cai_dat_hong_thi_video_van_READY_va_van_co_thong_bao` khoá lại.

### Ghi chú

`processor.py` nay `import` `ViralService` và `settings` ở **đầu file** theo `RULES.md`; đã
kiểm không sinh vòng lặp import (`import app.main` chạy sạch). Chỗ import trong hàm ở dòng 38
và 837 là của bản cũ, để nguyên — ngoài phạm vi.
