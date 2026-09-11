# ADR-043 — `/tai <link>`: tải bản gốc về máy, không đi qua luồng reup

- **Ngày**: 2026-09-11
- **Trạng thái**: **ĐÃ DUYỆT** — Owner: *"anh đang xem video FB thấy hay quá muốn tải về máy chứ
  không có ý định reup, có cách nào tích hợp vào không, hoặc video nào cũng được"* → *"oke đội
  nhiều mũ và tư duy lên"*.
- **Liên quan**: ADR-034 (dán link = làm video), ADR-029 (yt-dlp ghim + tự khai bản), ADR-030
  (Drive theo tháng), ADR-042 ("Đã đăng" — kho sản xuất vs kho lưu)

## Đội mũ

**Mũ kinh doanh.** Đây là tiện ích cá nhân, không sinh bài đăng. Giá trị: Owner ở lại trong một
công cụ thay vì cài thêm app tải video lạ (thường kèm quảng cáo, đôi khi kèm mã độc). Chi phí:
thấp — **90% đường ống đã có** (yt-dlp, cookie tài khoản, gửi Telegram, chép Drive). Đáng làm
vì rẻ, không phải vì lớn.

**Mũ kỹ thuật — ranh giới quan trọng nhất:** *không* được đi qua luồng viral. Không tạo
`ViralMaterial`, không chống trùng, không cắt, không caption, không vào `/moi`/`/sansang`.
Trộn vào là kho sản xuất loạn — đúng thứ ADR-042 vừa phải tách ra. Nên: thư mục riêng
`storage/media/tai-ve/<tháng>/`, Drive riêng `videos/Tải về/<tháng>/`, **không ghi DB**.

**Mũ phản biện — chỗ sẽ gãy:**
1. *yt-dlp với Facebook không ổn định bằng TikTok.* Facebook đổi trang liên tục; có tuần bản
   ghim cũng gãy. ⇒ Tin lỗi phải **tự khai bản yt-dlp** (dùng lại cơ chế `/nguon` sáng nay),
   không im, không "lỗi chung chung".
2. *Video riêng tư / trong nhóm cần cookie.* Tool đã có cookie từ profile tài khoản Facebook
   ACTIVE. Nhưng `--cookies-from-browser` **thất bại khi Chrome đang mở profile đó** (khoá DB
   cookie). ⇒ Thử **không cookie trước** (video công khai — đa số), chỉ khi Facebook/Instagram
   từ chối mới thử lại với cookie. Không có tài khoản thì nói thẳng *"cần đăng nhập"*.
3. *Telegram giới hạn 50 MB.* Video Facebook dài dễ vượt. ⇒ Vượt thì **không cố gửi**, tin ghi
   rõ file nằm đâu (máy + Drive). Hứa gửi rồi lỗi 413 là nhãn nói dối.
4. *Đầy ổ.* "Video nào cũng được" + không dọn = ổ đầy sau vài tháng. ⇒ chặn 500 MB/video
   (`--max-filesize`), một lệnh = **một video** (`--no-playlist`; dán link kênh là từ chối),
   và ghi rõ chưa có dọn tự động — mở khi thấy số thật.

**Mũ dữ liệu.** Không ghi DB nghĩa là không đếm được "tháng này tải bao nhiêu". Chấp nhận:
thư mục theo tháng chính là sổ ghi; ngày nào cần số thì `ls` là ra. Thêm bảng cho một tiện ích
là trả giá bảo trì cho thứ chưa ai cần.

**Mũ pháp lý.** Tải video người khác về xem riêng — tool đã làm việc nặng hơn nhiều (reup).
Không có gì mới; ghi để không ai tưởng ADR này mở ra thứ gì.

**Mũ UX.** Vì sao **lệnh** `/tai` chứ không phải nút: dán link trần hiện **tự làm video ngay**
(ADR-034 — Owner chọn để đỡ bấm). Thêm nút "chỉ tải" là biến thành hỏi-rồi-mới-làm, chậm cả
luồng chính. `/tai link` tách bạch: *link trần = làm video, `/tai` = chỉ lấy về*. Web có ô
riêng cùng nghĩa cho ai không ở Telegram.

## Quyết định

| | |
|---|---|
| Lối vào | Telegram `/tai <link>`; web ô "Tải về máy" trên trang Viral |
| Nhận link | Mọi link `http(s)` — yt-dlp biết hơn 1.000 trang; nền tảng chỉ dùng để chọn cookie |
| Tải | `yt-dlp --no-playlist --max-filesize 500M` → `tai-ve/<tháng>/<tiêu đề>.mp4` (tên theo `safe_video_name` ADR-030, giữ dấu) |
| Cookie | Không cookie trước; Facebook/Instagram từ chối ⇒ thử lại với tài khoản ACTIVE cùng nền tảng |
| Sau tải | Chép Drive `videos/Tải về/<tháng>/` nếu đang bật; gửi file Telegram nếu ≤ 50 MB, không thì gửi đường dẫn |
| Lỗi | Dịch như `/nguon`, kèm bản yt-dlp đang chạy; không bao giờ raise ra poller |
| DB | **Không** |

## Ngoài phạm vi

Tải playlist / cả kênh; dọn tự động `tai-ve/`; tải bằng cookie khi Chrome đang mở profile
(yt-dlp không làm được — tin sẽ nói rõ); Threads/X (yt-dlp hỗ trợ kém, thử được nhưng không hứa).

## Proof

Chạy thật trên máy dev: link video TikTok công khai → `tai-ve/2026-09/Muốn giàu thì trước
tiên phải xuống biển.mp4`, **148,5 MB trong 15,9 s** ⇒ `sendable=False`, tin báo đường dẫn
(đúng ý: không hứa gửi rồi lỗi 413). Link **kênh** TikTok: yt-dlp với `--no-playlist` vẫn cố
lấy video đầu rồi hỏng bằng thông báo thô ⇒ chặn link kênh **trước** khi gọi yt-dlp
(`_known_host_but_not_video`, 8 ca đúng: kênh TikTok/YouTube/Facebook bị chặn; link video,
link rút gọn `vt.`, trang lạ như vimeo được thử).

`tests/test_fetch_original.py` (25): không tạo material, không đụng `REUP_DIR`, lệnh yt-dlp có
`--no-playlist` + `--max-filesize 500M`, lượt đầu KHÔNG cookie, Facebook đòi đăng nhập ⇒ thử
lại bằng cookie tài khoản ACTIVE, không tài khoản ⇒ nói rõ, có cookie vẫn bị từ chối ⇒ nói cả
lý do Chrome, > 50 MB ⇒ không `sendable`, trùng tên không ghi đè, chép Drive vào
`videos/Tải về/<tháng>/`; `/tai` gửi file khi nhỏ, chỉ báo đường dẫn khi to.

Một test cũ (`test_kinds_map_to_known_subdirs`) đổi kỳ vọng: thêm kind `download`.

**1030 passed, 16 skipped, 0 failed** · `ruff` sạch · `lint-imports` giữ. Không migration.

## Hết hiệu lực

Sau proof: `fetch_original` chạy thật trên máy dev với một link TikTok công khai ra file trong
`tai-ve/<tháng>/`; test khoá: không tạo material, không cookie ở lượt đầu, thử lại có cookie
khi Facebook đòi đăng nhập, vượt 50 MB thì không gửi, playlist bị từ chối; toàn suite xanh.
