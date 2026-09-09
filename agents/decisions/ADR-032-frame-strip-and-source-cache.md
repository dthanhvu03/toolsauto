# ADR-032 — Chọn mốc cắt bằng một cú bấm: dải khung hình + giữ file gốc

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner hỏi *"có cách nào tiện không em"* rồi giao
  *"oke em triển khai cho anh đi em"*
- **Liên quan**: **ADR-031 (mốc cắt — ADR này làm nó dùng được)**, ADR-024 (chống trùng)

## Bối cảnh

ADR-031 cho chọn mốc cắt, nhưng thao tác thật của Owner là: mở TikTok → **xem 9 phút** tìm
chỗ hay → nhớ số giây → mở web → mở khối gấp *"Reup lại?"* → gõ số → bấm → **tải lại 117 MB**
→ chờ. Ba chỗ phiền:

1. **Ô nằm trong khối gấp mang nhãn "Reup lại?"** — nhãn không liên quan gì tới việc chọn mốc.
   Owner không tìm ra, phải hỏi. Đây đúng cái bẫy ADR-025 vừa đi sửa: chôn chức năng sau một
   nhãn nói chuyện khác — và lần này chính bản vá ADR-031 đẻ ra nó.
2. **Phải xem hết video** mới biết chỗ hay ở đâu. Đây là phần tốn thời gian nhất.
3. **Đổi mốc = tải lại từ đầu**, vì file gốc bị xoá ngay sau khi cắt.

## Quyết định

1. **Giữ file gốc trong lúc chờ** — ô `viral.keep_source_days` (mặc định **7**; `0` = xoá ngay
   như trước). Có file gốc thì cắt lại là **tức thì**, không tải lại gì.
   Giá: ~117 MB mỗi video đang chờ (12 video ≈ 1,4 GB). Tool đã có sẵn *"Smart Cleanup xoá
   video ế quá hạn"* nên chỗ dọn tự động có sẵn, chỉ thêm một lượt quét file gốc quá hạn.
2. **Dùng lại file gốc khi xử lý lại** — trước lượt tải, nếu tìm thấy file gốc còn trên đĩa thì
   dùng luôn. **Preflight vẫn chạy** (chỉ ~2 giây, làm mới views/tiêu đề); chỉ bỏ lượt tải nặng.
   Cố ý không gộp hai thứ: bỏ preflight tiết kiệm 2 giây mà mất dữ liệu mới, không đáng.
3. **Dải 12 khung hình** trích từ **video GỐC** ngay lúc xử lý (trước khi có thể xoá), trải đều
   toàn video. Owner nhìn 12 ảnh là thấy khung nào có cá — **không phải xem video**.
   - Lưu thành **12 file jpg rời** (`viral_<id>_f00.jpg`…), không phải một ảnh ghép: ảnh ghép
     thì phải dựng lưới CSS chồng lên để bắt chỗ bấm, dễ lệch; 12 thẻ `<img>` rời thì mỗi cái
     tự là một nút, không có gì để lệch.
   - **Không đốt số giây vào ảnh** bằng `drawtext`: nó cần fontconfig, mà máy Owner đang báo
     *"Cannot load default config file"*. Số giây do HTML hiện, luôn đúng và luôn đọc được.
4. **Bấm một khung = đặt mốc + xử lý lại luôn**, dùng lại đúng route `clip-start` của ADR-031.
   Không thêm route đặt mốc thứ hai.
5. **Đưa ô nhập giây ra ngoài** khối gấp, đặt cạnh dải khung hình. Gõ tay vẫn giữ cho ai muốn
   mốc chính xác hơn 1/12 video.

## Phạm vi

| Việc | File |
|---|---|
| Ô `viral.keep_source_days` | `app/core/settings.py` |
| Tìm file gốc, trích 12 khung | `app/features/viral_intake/service.py` |
| Dùng lại file gốc, chỉ xoá khi hết hạn giữ, trích khung sau khi tải | `app/features/viral_intake/processor.py` |
| Phục vụ ảnh khung | `app/features/viral_intake/router.py` |
| Dải khung + ô nhập ra ngoài | `app/templates/fragments/viral_row.html` |
| Dọn file gốc quá hạn | `app/features/system_panel/workers/maintenance.py` |
| Test | `tests/test_frame_strip.py` (mới) |

## Ngoài phạm vi

- Không dựng trình phát video trong tool — bấm khung là đủ, xem video thì mở link gốc.
- Không tự chọn khung "hay nhất": ADR-031 đã đo và chứng minh không có tín hiệu để dò.
- Không đụng mốc cắt, chống trùng, lớp phụ đề/âm thanh.
- Không đổi hành vi mặc định của `MAX_REELS_DURATION` hay preset.

## Hết hiệu lực

Sau proof: xử lý một material ⇒ có 12 ảnh khung trải đều video gốc; bấm một khung ⇒
`clip_start_sec` bằng đúng giây của khung đó và material về `REUP`; xử lý lại ⇒ **không tải
lại** khi file gốc còn; đặt `keep_source_days = 0` ⇒ xoá ngay như trước.

## Proof (2026-09-09)

**Trích khung bằng ffmpeg thật**: video 60 giây ⇒ 12 ảnh jpg có nội dung, tên mang đúng số
giây. Mốc cho video 573 giây (video thật của kênh): `11, 57, 103, 148, 194, 240, 286, 332,
378, 424, 469, 515` — con cá ở giây ~320 rơi vào khung số 8 (giây 332).

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| 12 khung trải đều, tránh 2% đầu/cuối | `test_muoi_hai_moc_trai_deu_va_tranh_hai_dau` |
| Trích khung thật ⇒ 12 file jpg có nội dung | `test_trich_khung_that_bang_ffmpeg` |
| **Tìm file gốc không nhầm với bản `_reup`** | `test_tim_file_goc_bo_qua_ban_da_cat` |
| Số giây đọc lại được từ tên file, kể cả khi video gốc đã dọn | `test_doc_lai_duoc_giay_tu_ten_file…` |
| Xử lý lại **dùng file gốc có sẵn**, không tải lại | `test_processor_dung_lai_file_goc_truoc_khi_tai` |
| Trích khung **trước** khi có thể xoá gốc | `test_processor_trich_khung_truoc_khi_co_the_xoa_goc` |
| Đọc ô cài đặt hỏng ⇒ **xoá** chứ không giữ (không phình đĩa âm thầm) | `test_doc_o_cai_dat_hong_thi_XOA_chu_khong_giu` |
| Dọn file gốc quá hạn, **không đụng** bản `_reup` | `test_don_file_goc_qua_han_khong_dung_ban_da_cat` |
| `keep_source_days = 0` ⇒ không dọn gì ở đây (đã xoá lúc xử lý) | `test_dat_0_ngay_thi_khong_don_gi_o_day` |
| Mọi nhánh hỏng ⇒ trả rỗng/0, không ném | 4 test |

**Toàn suite: 701 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ.**

## Lỗi thật do chạy ffmpeg thật mới lộ

`probe_duration` suy đường dẫn ffprobe bằng
`resolve_ffmpeg().replace("ffmpeg", "ffprobe")`. Nó thay **cả tên thư mục**:
`…\Programs\ffmpeg\bin\ffmpeg.EXE` → `…\Programs\ffprobe\bin\ffprobe.EXE` — đường dẫn **không
tồn tại**. Hàm nuốt lỗi trả `0`, nên `source_frame_seconds(0)` trả rỗng và **cả dải khung hình
im lặng biến mất**: không lỗi, không log, chỉ là không có gì hiện ra.

Test giả (dựng sẵn file jpg) **không bắt được** — chỉ lượt chạy ffmpeg thật mới lộ. Repo vốn
đã có `ffmpeg_path.ffprobe_bin()`; đã đổi sang dùng nó và thêm test cấm kiểu suy bằng
`replace` quay lại.

Đây là lần thứ hai trong ngày một lỗi chỉ lộ khi chạy công cụ thật (lần trước:
`_fast_trim_fallback` không có `-ss`, ADR-031). Ghi lại thành nguyên tắc: **mọi thứ đụng
ffmpeg phải có ít nhất một test chạy ffmpeg thật.**
