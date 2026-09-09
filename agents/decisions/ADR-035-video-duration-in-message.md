# ADR-035 — Tin Telegram phải nói video dài bao nhiêu và cắt từ đâu

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner nhận video thật qua bot rồi phản hồi:
  *"anh nhìn như này không biết video bao nhiêu phút hay như nào hết"*
- **Liên quan**: ADR-027 (tin video xong), ADR-031 (mốc cắt), ADR-030 (đường dẫn Drive)

## Bối cảnh

Luồng ADR-034 chạy thông: Owner dán link → nhận video kèm caption. Nhưng tin nhắn thiếu đúng
thứ cần để quyết định *"có phải chọn lại đoạn cắt không"*:

- **dài bao nhiêu** — tool cắt 90 giây, nhưng tin không nói
- **cắt từ đâu** — từ đầu hay từ mốc Owner chọn
- **gốc dài bao nhiêu** — để biết đang bỏ qua bao nhiêu phút

Và trên khung video Telegram hiện **`0:00`**: `send_video` không truyền `duration`/`width`/
`height`, nên Telegram không biết độ dài mà hiển thị.

Nghĩa là Owner phải **mở video ra xem** mới biết — đúng cái việc ADR-032 vừa bỏ công loại bỏ.

## Quyết định

1. **`media_info(path) -> {duration, width, height}`** đặt ở `app/core/media/thumbnail.py` —
   file này tự nhận là *"generic media helpers shared by notifier / processors"*, đúng chỗ.
   `ViralService.probe_duration` **gọi lại nó** thay vì giữ bản riêng: đã có sẵn một cặp hàm
   trùng việc trong repo (hai bộ làm sạch tiêu đề), không đẻ thêm cặp nữa.
2. **`send_video` tự đo và truyền `duration`/`width`/`height`.** Làm ở tầng client nên **mọi**
   chỗ gửi video đều được, không riêng tin này. Đo hỏng ⇒ bỏ qua ba tham số đó, gửi như cũ.
3. **Thêm một dòng vào tin**: `⏱ Dài 1:30 · cắt từ đầu (gốc 9:33)`.
   - *dài*: đo file đang gửi
   - *cắt từ*: `mat.clip_start_sec`, không có ⇒ "từ đầu"
   - *gốc*: chỉ hiện khi biết — file gốc còn trên đĩa (ADR-032 giữ 7 ngày). Không biết thì
     **không đoán**, bỏ luôn phần trong ngoặc.
4. **Tính ở `NotifierService`, không ở `formatting`.** `formatting` là hàm thuần dựng chuỗi;
   nhét subprocess vào đó thì mọi test dựng tin nhắn hoá thành test chạy ffmpeg.

## Phạm vi

| Việc | File |
|---|---|
| `media_info` | `app/core/media/thumbnail.py` |
| Bỏ bản đo trùng | `app/features/viral_intake/service.py` |
| Truyền duration/width/height | `app/core/notifier/telegram_client.py` |
| Đo rồi truyền số vào tin | `app/core/notifier/service.py` |
| Dòng `⏱` | `app/core/notifier/formatting.py` |
| Truyền độ dài gốc | `app/features/viral_intake/processor.py` |
| Test | `tests/test_notify_jobless.py` (thêm mục) |

## Ngoài phạm vi

- Không thêm cột DB cho độ dài — đo tại chỗ là đủ, và ADR-032 đã giữ file gốc.
- Không đụng mốc cắt, Drive, caption.

## Hết hiệu lực

Sau proof: tin có dòng `⏱ Dài m:ss · cắt từ …`; có `clip_start` ⇒ hiện đúng mốc; còn file gốc
⇒ hiện `(gốc m:ss)`, không còn ⇒ không hiện; Telegram không còn báo `0:00` vì `sendVideo`
mang theo `duration`.

## Proof (2026-09-09)

Tin dựng thật:

```
🎬 Video sẵn sàng đăng tay
📋 Material #976 | tiktok
📝 Muốn giàu phải ra biển nhen
👁 12,400 lượt xem
⏱ Dài 1:30 · cắt từ 5:32 (gốc 9:33)     ← dòng mới
📁 viral_976_reup.mp4
📂 Trong Drive: videos/2026-09/976 - ….mp4
```

`media_info` đo thật trên video 90 giây: `{'duration': 90.0, 'width': 576, 'height': 1024}`.

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Dòng `⏱` có đủ dài / mốc cắt / độ dài gốc | `test_k1` |
| Không có mốc ⇒ "cắt từ đầu" | `test_k2` |
| Không biết độ dài gốc ⇒ **bỏ hẳn ngoặc**, không đoán bừa | `test_k3` |
| Đo không được ⇒ bỏ hẳn dòng `⏱`, tin vẫn gửi | `test_k4`, `test_k7` |
| `m:ss` đúng ở 0, 9, 90, 573, 3661 giây | 5 ca parametrize |
| Đo ở `NotifierService`, `formatting` vẫn thuần | `test_k6` |
| `sendVideo` mang `duration`/`width`/`height` ⇒ Telegram hết hiện `0:00` | đo thật ở trên |

**Toàn suite: 758 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ.**

## Một test cũ phải sửa (đúng ý định, sai địa chỉ)

`test_khong_suy_duong_dan_ffprobe_bang_replace` của ADR-032 khẳng định `service.py` chứa
`ffmpeg_path.ffprobe_bin()`. ADR này **dời việc đo sang core**, nên câu đó sai địa chỉ. Ý định
gốc — *không chỗ nào được suy đường dẫn ffprobe bằng `replace`* — giữ nguyên và nay kiểm
**cả hai** file.
