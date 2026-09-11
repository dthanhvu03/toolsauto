# ADR-041 — Chia video dài thành nhiều phần, cắt ở chỗ "đang gay cấn"

- **Ngày**: 2026-09-11
- **Trạng thái**: **ĐÃ DUYỆT** — Owner: *"xây luôn tính năng, và dùng thuật toán tối ưu nhất,
  tính toán đoạn hay nhất, xong cắt ra để đăng phần tiếp theo"*. Hỏi lại một câu, Owner chốt:
  **giữ cả video, chỉ chọn chỗ cắt** (không bỏ đoạn "chán").
- **Liên quan**: ADR-031/036 (mốc cắt hai đầu), ADR-032 (giữ file gốc + dải khung hình),
  ADR-024 (chống trùng — phải nới cho anh em cùng gốc), ADR-027/035 (tin Telegram), ADR-021
  (caption AI cho material READY)

## Bối cảnh

Một video kể chuyện 6–10 phút muốn đăng thành **Phần 1/3, 2/3, 3/3**. Hôm nay làm được bằng tay
(đặt mốc → xử lý → nhận → đặt mốc tiếp), ba phần = ba lượt bấm và tự nhẩm mốc. Owner muốn tool
tự tính chỗ cắt sao cho mỗi phần **dừng đúng lúc người xem muốn xem tiếp**.

## Đội mũ trước khi chốt

**Mũ dữ liệu — "thuật toán tối ưu nhất" là gì?** Không có thuật toán nào nhìn pixel hay sóng
âm mà biết đoạn nào *hay*. Đã đo ở ADR-031: âm thanh video của Owner phẳng, không có đỉnh.
Thứ duy nhất biết "đang gay cấn" là thứ **hiểu lời kể**. Tool đã có Whisper (`faster_whisper`,
dùng cho caption) — nó trả **lời thoại kèm mốc giây từng câu**. Đó là tín hiệu tốt nhất có sẵn:
biết *nói gì*, *lúc nào*, và *ngắt ở đâu* (khoảng lặng giữa hai câu).

**Mũ kỹ thuật — vì sao không gửi cả video cho Gemini?** Gemini nhận video, nhưng: file 50–100 MB
phải qua Files API (tải lên, chờ ACTIVE, xoá), thêm một đường AI mới không có dự phòng, và mốc
nó trả về thường lệch vài giây — vẫn phải "kéo về" ranh giới thật. Đường lời thoại đi qua
`AIUseCases.generate_text` **sẵn có ba tầng dự phòng** (9Router → Gemini native), input vài KB.
Chọn đường rẻ có dự phòng; ghi đường video làm việc sau nếu gặp video **không có lời**.

**Mũ phản biện — AI hỏng thì sao?** Không được im. Ba tầng, tầng nào cũng ra kết quả và **nói
rõ mình là tầng nào**:
1. Lời thoại + AI chọn câu kết mỗi phần (`by="ai"`).
2. Không AI ⇒ chia đều rồi **kéo mốc về khoảng lặng / đổi cảnh gần nhất** (`by="boundary"`)
   — vẫn không cắt giữa câu, chỉ không "chọn" được.
3. Không cả khoảng lặng ⇒ chia đều (`by="even"`), tin nhắn ghi rõ *"chia đều, chưa tính"*.

**Mũ "nhãn nói dối" (bài học cả tuần) — tool có được tự cắt không?** Không. Tool **đề nghị**
(mốc + lý do từng phần + dải khung hình), Owner bấm **một nút** mới cắt. Tính sai thì Owner
thấy trước khi tốn ffmpeg và trước khi đăng.

**Mũ kinh doanh — có nên chia không?** Đã nói thẳng ở phiên trước: Reels không có playlist,
người lạ trúng Phần 2 không tự về Phần 1 được. Owner biết và vẫn chọn. ADR này làm tính năng,
không làm thay quyết định đăng.

## Quyết định

### 1. Dữ liệu: phần con là một material bình thường, có cha

Thêm vào `viral_materials`: `parent_material_id`, `part_index`, `part_total`, `split_plan`
(JSON kế hoạch đã đề nghị, lưu trên **cha**). Phần con có `clip_start_sec`/`clip_length_sec`
riêng như ADR-036 ⇒ **đi nguyên đường xử lý cũ** (cắt, chống trùng ảnh, chép Drive, caption,
Telegram) — không dựng đường thứ hai.

Ba chỗ đường cũ phải biết "đây là phần con":

| Chỗ | Vì sao |
|---|---|
| Tải | **Không tải lại.** Lúc chia, file gốc của cha được **nối cứng** (`os.link`, không thì copy) thành `viral_<con>_phan<i>.mp4` ⇒ `find_source_path(con)` thấy ngay, tên file `_reup` không đụng nhau. Không preflight: URL của con là `<url cha>#phan<i>` (cột `url` unique). |
| Chống trùng (ADR-024) | Anh em cùng gốc **cố ý** giống nhau — bỏ qua `find_duplicate` cho phần con. Vẫn ghi `content_hash`/`phash` để lượt quét sau bắt được bản copy lạ. |
| Caption (ADR-021) | Ngữ cảnh thêm *"Đây là PHẦN i/N; chưa phải phần cuối thì mời xem tiếp"*. |

### 2. Thuật toán chọn chỗ cắt (`plan_cuts`)

```
lời thoại có mốc (Whisper) ──▶ AI: "N phần, mỗi phần kết ở câu nào để người xem muốn xem tiếp?"
                                │  trả JSON: chỉ số câu kết + một dòng lý do mỗi phần
                                ▼
                         mốc = cuối câu đó + nửa khoảng lặng sau nó   (không cắt giữa câu)
                                │
                                ▼
                    kiểm: tăng dần, mỗi phần ≥ 20 s, không phần nào > 60% video
                                │ hỏng ⇒ tầng 2
                                ▼
         chia đều ──▶ kéo về khoảng lặng (silencedetect) / đổi cảnh (scdet) gần nhất trong ±6 s
                                │ không có ⇒ tầng 3: chia đều
```

`plan_cuts` là **hàm thuần** (không DB, không ffmpeg, AI truyền vào) — test được từng nhánh.

### 3. Luồng Telegram

`/sansang` ⇒ nút **🧩 Chia phần** ⇒ hỏi *2 / 3 / 4 phần* ⇒ chạy nền (Whisper vài chục giây
tới vài phút) ⇒ gửi **ảnh lưới + danh sách phần** (mốc, lý do, tầng nào tính) + nút
**✅ Cắt N phần** ⇒ tạo N phần con, xử lý **lần lượt** (ffmpeg chạy song song là nghẽn máy), mỗi
phần xong bắn một tin như ADR-027 có dòng *"🧩 Phần i/N của #cha"*.

Trang web: cùng hai bước (đề nghị → xác nhận) trên trang Viral, cho ai không ở Telegram.

## Phạm vi

| Việc | File |
|---|---|
| Cột + migration | `models/viral.py`, `alembic/versions/r5f2a3b4c5d6_split_parts.py` |
| Khoảng lặng / đổi cảnh / lời thoại có mốc | `app/core/media/segments.py` (mới) |
| Kế hoạch chia + tạo phần con | `app/features/viral_intake/split.py` (mới) |
| Đường xử lý biết phần con | `processor.py` (tải, chống trùng), `service.py` (caption) |
| Tin Telegram có dòng phần | `notifier/formatting.py` |
| Hook + lệnh + nút | `bootstrap_hooks.py`, `command_handler.py`, `event_router.py` |
| Web | `viral_intake/router.py`, template trang Viral |
| Test | `tests/test_split_parts.py`, `tests/test_telegram_split.py` |

## Ngoài phạm vi

- **Video không có lời** ⇒ chỉ có tầng 2/3. Đường "Gemini xem video" để sau, khi gặp thật.
- Sửa mốc từng phần bằng tay trên Telegram (nút không đủ chỗ) — sửa trên web bằng ô ADR-036
  của từng phần con rồi bấm Xử lý.
- Tự đăng lên Page theo lịch — Owner đang đăng tay, chưa có account trong tool.

## Đo thật trên máy Owner (video 1:15 có nhạc nền, `viral_4_tikwm.mp4`)

| Tín hiệu | Kết quả | Thời gian |
|---|---|---|
| `silencedetect` (−30 dB) | **0 khoảng lặng** — nhạc nền lấp hết | 0.8 s |
| `scdet` (0.35) | 12 mốc đổi cảnh | 0.6 s |
| Whisper `medium` (CPU) | **28 câu** kèm mốc | **65.7 s ≈ 0.9× thời lượng** |

Hai hệ quả, đã sửa ngay:

1. **Cuối mỗi câu Whisper đưa thẳng vào tầng 2** làm ứng viên ranh giới. Nếu chỉ dựa
   `silencedetect` thì video có nhạc nền không bao giờ có ranh giới, tầng 2 thành vô dụng.
   Kết quả trên video này: cắt ở **0:24 và 0:51**, đều là cuối câu.
2. Lời hứa *"vài chục giây"* trong tin nhắn là sai — sửa thành *"khoảng bằng độ dài video"*.
   Video 8 phút ⇒ chờ ~7 phút. Chạy nền, Owner được báo trước.

AI tầng 1 chưa chạy được ở shell kiểm thử (key nằm trong DB, DB dev đang tắt); chuỗi dự phòng
hạ đúng về tầng 2 và ghi rõ. Đường gọi (`AIUseCases.generate_text`) là đường caption đang dùng
thật ở production.

## Một guard chứng minh được là cần

Bỏ `dup = None if is_part else find_duplicate(...)` rồi chạy test end-to-end: phần con bị đánh
**`DUPLICATE — Trùng nội dung với #1 (sha256 giống hệt)`** ngay lượt đầu. Không có guard thì
tính năng chết và báo "trùng" — nhãn nói dối kiểu mới.

## Hết hiệu lực

Proof: `plan_cuts` đủ ba tầng có test; `test_split_parts.py` (36) chạy **nguyên
`process_material`** cho phần con — không tải lại, không bị coi là trùng, cắt đúng mốc từng phần
trên file mang tên của nó; `test_telegram_split.py` (12) khoá bước duyệt; **961 passed, 16
skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ; `ruff` sạch; `alembic heads` một head.
Chưa có proof cắt thật N phần rồi nhận đủ N tin trên Telegram — cần DB dev bật; ghi ở handoff.
