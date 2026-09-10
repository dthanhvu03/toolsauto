# ADR-038 — Bảy lỗi do code-review bắt trên dải ADR-025→037

- **Ngày**: 2026-09-10
- **Trạng thái**: **ĐÃ DUYỆT** — Owner: *"kiểm tra code đi"*
- **Liên quan**: **ADR-031/036 (lỗi #1 vô hiệu hoá chúng)**, ADR-032, ADR-034/035/037

## Bối cảnh

Chạy `/code-review` mức cao trên `e8b6c4b..HEAD` — **17 commit, 57 file, +6.450 dòng**. Bảy
lỗi, xếp theo mức nguy hiểm.

## Lỗi #1 — nghiêm trọng nhất: mốc cắt bị vô hiệu HOÀN TOÀN

`ReupProcessor.process` có chốt `skip_existing`: thấy `_reup.mp4` cũ là **trả lại ngay và báo
thành công**. `reprocess_reup` vốn truyền `force=True`; **đường chạy chính thì không**.

Mà xử lý lại để đổi mốc cắt thì file cũ **luôn** còn đó ⇒ tính năng chính của ADR-031/036
không làm gì cả, và vẫn báo thành công.

**Chứng minh bằng video có đồng hồ đếm giây:**

```
lần 1 (xử lý đầu)          -> mode = fast_trim
lần 2 (đặt mốc giây 120)   -> mode = skip_existing   ← trả lại file cũ
khung ở giây 2 của kết quả -> hiện "2"               ← vẫn từ đầu
sau khi vá                 -> hiện "122"             ← đúng mốc 120
```

**Vì sao mọi lượt chạy thật trước đó không bắt được:** chúng đều gọi
`ReupProcessor.process(..., force=True)` trực tiếp. Chạy thật vẫn có thể sai nếu **không chạy
đúng đường mà production đi**.

Vá: `force=bool(status in (REUP, FAILED) or clip_start_sec or clip_length_sec)`. Giữ nguyên
chốt `skip_existing` — nó vẫn đúng cho lượt quét thường.

## Sáu lỗi còn lại

2. **Bỏ qua kết quả xử lý** (`event_router`): `process_material` từ chối bằng **giá trị trả
   về** (sai trạng thái, thiếu ffmpeg, trùng nội dung), không bằng ngoại lệ. Owner nhận lời
   hứa *"sẽ gửi khi xong"* rồi **im lặng vĩnh viễn**.
3. **`media_info` lấy chiều cao làm thời lượng**: ffprobe in stream trước, format sau;
   container thiếu `duration` thì chỉ còn `[w, h]` mà code lấy phần tử cuối ⇒ clip 90 giây báo
   *"Dài 17:04"*.
4. **Bấm khung hình xoá mất độ dài đã đặt**: nút Telegram chỉ gửi mốc, mà chuỗi rỗng và `None`
   bị gộp làm một. Nay phân biệt: `None` = giữ nguyên, chuỗi rỗng = Owner xoá trắng ô ⇒ về số
   chung.
5. **File tạm nhận nhầm là bản gốc**: sau một lần crash, `…_reup.tmp.mp4` còn đó với mtime mới
   nhất nên **thắng ở bước sort** ⇒ bản "gốc" đem cắt lại hoá ra là bản đã cắt.
6. **Nút "Gửi lại" tải video ngay trên luồng poller** ⇒ callback hết hạn, bot đứng im suốt
   lượt tải. Nay chạy nền như `scan` và `xuly`.
7. **Chốt tách tin chỉ bật khi có caption AI**: riêng tiêu đề TikTok dài cũng đủ vượt 1024
   (đo thật: **1.369 ký tự**, không caption nào) ⇒ `send_video` cắt giữa thẻ `<i>` ⇒ Telegram
   trả 400 ⇒ **mất luôn cả tin lẫn video**.

## Một chỗ tự làm hỏng khi vá, test bắt lại

Gom `scan` và `gui` vào một nhánh chạy nền, tôi cho cả hai **im lặng khi thành công**. Nhưng
`scan` xong mà im thì Owner không biết có tìm được gì không. Test `test_nut_quet_chay_nen…`
đỏ ngay. Nay `scan` báo kết quả; `gui` vẫn im vì **chính video gửi tới đã là câu trả lời**.

## Proof

16 test mới trong `tests/test_review_fixes_20260910.py` khoá cả bảy.
Ba test cũ sửa theo ngữ nghĩa mới (ADR-036 chuỗi rỗng vs `None`; hai test nút Telegram).

**Toàn suite: 816 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ.**

## Bài học

Cả ngày đã có ba lỗi *"chỉ lộ khi chạy thật"*. Lỗi #1 thêm một tầng nữa: **chạy thật mà không
đúng đường production đi thì vẫn không thấy**. Gọi hàm trực tiếp với tham số mình tự chọn là
kiểm **ý định của mình**, không phải kiểm **đường mà hệ thống thật sự đi**.
