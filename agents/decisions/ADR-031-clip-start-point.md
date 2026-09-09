# ADR-031 — Chọn mốc bắt đầu cắt: đừng đăng 90 giây móc mồi

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner xác nhận triệu chứng (*"video có 1p2 mấy giây là hết rồi"*)
  rồi giao: *"vậy em vá đi em"*
- **Liên quan**: ADR-016 (lớp phụ đề/âm thanh), ADR-018 (READY), ADR-024 (chống trùng)

## Bối cảnh — đo, không đoán

Kênh nguồn `@thacaukechuyen`: **18 video, dài 389–652 giây** (6,5–11 phút). Tool giữ **90 giây
đầu** (`MAX_REELS_DURATION = 90`, cắt bằng `-t` ở `reup_processor.py`).

Bóc khung hình video 573 giây có 2,2 triệu view:

| Mốc | Trên màn hình |
|---|---|
| 45s | còn đang **móc mồi tôm** |
| 320s | **con cá đã câu được** — khoảnh khắc đáng lấy |
| 545s | ngồi không, mặt biển trống |

⇒ Tool đang xuất bản **cảnh móc mồi**, cắt bỏ đúng đoạn tạo ra 2,2 triệu view.

**Đã thử và loại bỏ phương án tự dò.** Đo năng lượng âm thanh từng giây cả video: phẳng lì
59–81%, không có đỉnh nào. Cửa sổ 90 giây "ồn nhất" chỉ hơn cửa sổ hiện tại **3 điểm phần
trăm** — nhiễu, không phải tín hiệu. Vlog POV có tiếng gió, sóng, máy nổ đều đều; cá cắn không
tạo đỉnh âm thanh. Nếu dựng heuristic theo âm thanh thì đã dựng một thứ **không chạy được**.

Lấy 90 giây **cuối** cũng sai — cuối video không có gì. Khoảnh khắc đáng lấy nằm **giữa**, và
không theo quy luật nào. ⇒ Chỉ còn cách **người nhìn và chỉ**, nhưng phải rẻ.

**Ràng buộc phát hiện khi khảo sát:** nút "Chạy lại" hiện có (`reprocess_reup`) chạy trên
**chính file `_reup` đã bị cắt còn 90 giây** — file tải gốc bị xoá sau khi xử lý. Nên không thể
cắt lại từ giây 300 nếu không **tải lại từ đầu**. Không giữ file gốc lại: 117 MB/video × 18
video ≈ 2 GB và còn tăng, trái nguyên tắc dọn file tạm trong `RULES.md`.

## Quyết định

1. **`viral_materials.clip_start_sec`** (Integer, nullable). `None`/0 ⇒ **y như hiện tại**, cắt
   từ đầu — không đổi hành vi mặc định.
2. **`ReupProcessor.process(..., clip_start=0.0)`** → cộng vào `-ss` sẵn có (đang dùng cho
   `head_trim` chống trùng). Một chỗ `-ss` duy nhất, không thêm lần re-encode nào.
3. **Cắt lại = tải lại.** Đặt mốc cho material đã xử lý ⇒ chuyển status về **`REUP`** rồi chạy
   lại đường xử lý bình thường (`_process_viral_materials` nhận `NEW/REUP/FAILED`). `REUP` là
   status đúng nghĩa: *"manual input, luôn xử lý bất kể views"*.
   Nút phải **nói rõ là tải lại**, không giấu — người dùng cần biết nó tốn thời gian và băng thông.
4. **Chống trùng không cản đường**: `find_duplicate` đã có `exclude_id`, nên tải lại cùng một
   video không tự coi mình là trùng. Không phải sửa gì.
5. **`MAX_REELS_DURATION = 90` đang hardcode ⇒ thành ô chỉnh được** `reup.max_duration_sec`
   (mặc định 90). Preset `reels_short` vẫn ghi đè bằng 45 như cũ.
6. **Không làm dải khung hình** trong ADR này. Bước 1 là ô nhập giây; dải khung hình bấm-chọn
   chỉ làm nếu bước 1 chứng minh đúng hướng. Hạ tầng hiện chỉ trích **1 khung ở giây 1**
   (`ensure_reup_thumbnail`), làm dải là việc gấp mấy lần.

## Phạm vi

| Việc | File |
|---|---|
| Cột + migration | `app/core/database/models/viral.py`, `alembic/versions/` |
| `clip_start` vào `-ss` | `app/features/viral_intake/reup_processor.py` |
| Truyền mốc khi xử lý | `app/features/viral_intake/processor.py` |
| Ô `reup.max_duration_sec` | `app/core/settings.py` |
| Đặt mốc + xử lý lại | `app/features/viral_intake/service.py`, `router.py` |
| Ô nhập + nút | `app/templates/fragments/viral_row.html` |
| Test | `tests/test_clip_start.py` (mới) |

## Ngoài phạm vi

- **Không giữ file gốc** sau khi xử lý (2 GB và còn tăng).
- Không dò tự động đoạn hay — đã đo và chứng minh không khả thi với nội dung này.
- Không dải khung hình bấm-chọn (mục 6).
- Không đụng lớp phụ đề, lớp âm thanh, chống trùng, hay luồng có account.

## Hết hiệu lực

Sau proof: đặt `clip_start_sec = 300` cho một material rồi xử lý lại ⇒ file `_reup` bắt đầu
từ giây 300 của bản gốc, dài đúng `max_duration`; bỏ trống ⇒ cắt từ đầu như trước; đổi ô
`reup.max_duration_sec` ⇒ độ dài đổi theo.

## Proof (2026-09-09)

**Chạy ffmpeg thật** trên video đồng hồ 400 giây (mỗi giây hiện số giây trên hình):

```
clip_start=  0  → khung ở giây 2 của output hiện "2"
clip_start=300  → khung ở giây 2 của output hiện "302"   ✅ cắt đúng từ giây 300
độ dài cả hai bản: 90.0s
```

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| Đặt mốc 300 ⇒ file bắt đầu từ giây 300 của bản gốc | khung hình hiện **302** |
| Dài đúng `max_duration` | 90,0 s |
| Bỏ trống ⇒ cắt từ đầu như trước | hiện **2** |
| `reup.max_duration_sec` đổi ⇒ độ dài đổi theo | `test_max_duration_lay_tu_o_cai_dat` |
| Ô cài đặt hỏng / giá trị vô lý ⇒ lùi về hằng số | 2 test |
| Mốc vượt độ dài video ⇒ bỏ qua, không ra file rỗng | `test_ca_hai_nhanh_deu_kiem_moc_vuot_do_dai` |
| Đặt mốc ⇒ status về `REUP`, xoá lỗi cũ | `test_dat_moc_thi_ve_REUP_de_duong_xu_ly_tai_lai` |
| Giá trị sai ⇒ từ chối, **không đổi status** | 2 ca parametrize |
| Một `-ss` duy nhất ở lượt chính, không thêm lần re-encode | `test_ma_nguon_cong_clip_start_vao_ss…` |

**Toàn suite: 680 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ. Alembic: 1 head.**

## Lỗi thật tìm ra khi chạy thử — và nó là kiểu tệ nhất

Bản vá đầu chỉ sửa **lượt mã hoá chính**. Chạy thử thì lượt đó thất bại và rơi xuống
`_fast_trim_fallback()` — nhánh dự phòng dựng lệnh ffmpeg **riêng**, chỉ có `-t`, **không có
`-ss`**. Kết quả: đặt mốc giây 300, hệ thống báo **thành công**, file vẫn là 90 giây đầu.

Sai **âm thầm** — không lỗi, không cảnh báo, Owner chỉ phát hiện khi mở file ra xem. Nếu chỉ
test bằng mock argv thì **không bao giờ bắt được**, vì mock luôn cho lượt chính "thành công".
Chạy ffmpeg thật với video có đồng hồ mới lộ ra.

Đã vá nhánh dự phòng (`-ss` đặt trước `-i`, dùng được với `-c copy`; đổi lại điểm cắt nhảy về
keyframe gần nhất, lệch vài phần giây) và khoá bằng
`test_nhanh_du_phong_fast_trim_cung_phai_ton_trong_moc`.

## Hai test em tự viết ẩu, đã sửa

- Đếm `'cmd += ["-ss"'` ⇒ dính luôn `trim_cmd` của nhánh dự phòng (chuỗi con). Đổi sang khớp
  cả biểu thức.
- Cắt khối hàm tại `return ReupResult` đầu tiên ⇒ rơi đúng dòng "không cần fallback" ở đầu
  hàm, hụt mất phần dựng lệnh. Đổi mốc cắt sang `subprocess.run(trim_cmd`.
