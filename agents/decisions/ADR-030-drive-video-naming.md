# ADR-030 — Bản chép Drive: tên theo tiêu đề, thư mục theo tháng, và báo vị trí trong tin Telegram

- **Ngày**: 2026-09-09
- **Trạng thái**: **ĐÃ DUYỆT** — Owner giao trực tiếp 2026-09-09: *"em triển khai từng mục đi"*
- **Liên quan**: **ADR-012 / ADR-023 (chép Drive)**, ADR-024 (bỏ qua bản y hệt), ADR-027 (tin Telegram)

## Bối cảnh

Owner hỏi ba việc: gửi kèm đường dẫn video vào Telegram, đặt tên file khớp tiêu đề, và chia
thư mục theo tháng để quản trị.

Hiện `copy_video_if_enabled` chép thẳng `src_path.name` vào một thư mục phẳng
`<root>/videos/`. Nghĩa là trên Drive Owner thấy `viral_949_a1b2_reup.mp4` — không đọc được
là video gì — và vài tháng nữa là vài nghìn file trong cùng một thư mục, app Drive trên điện
thoại mở sẽ ì.

**Điều phải nói rõ về "đường dẫn video":** Google Drive for Desktop **gắn một ổ đĩa**; tool
chỉ `shutil.copy2` vào một thư mục cục bộ. Nó **không hề biết** link `drive.google.com` của
file. Muốn link bấm được phải gọi **Google Drive API** (OAuth, file ID, đặt quyền chia sẻ) —
phạm vi và rủi ro khác hẳn, **không làm trong ADR này**. Thứ làm được ở đây là **đường dẫn
tương đối trong Drive** dạng chữ, đủ để Owner mở app Drive gõ tên là ra.

## Quyết định

1. **Tên file trên Drive theo tiêu đề, giữ ID ở đầu**: `949 - Nay tui đi câu mực nha anh em.mp4`.
   Giữ ID vì hai lý do cụ thể, không phải cho đẹp: kênh nguồn của Owner có **4 video cùng tên
   "Muốn giàu phải ra biển"** — bỏ ID là ghi đè lẫn nhau; và ID khớp số hiển thị trên web nên
   đối chiếu được.
2. **Làm sạch tên file ở `app/core/storage`**, vì đó là chuyện của hệ thống tệp: bỏ ký tự
   Windows cấm (`\ / : * ? " < > |`), bỏ ký tự điều khiển, gộp khoảng trắng, bỏ dấu chấm/khoảng
   trắng ở cuối (Windows từ chối), cắt phần tiêu đề còn **80 ký tự**. **Giữ dấu tiếng Việt** —
   Windows và Drive đều chịu được UTF-8, mà bỏ dấu thì mất hẳn cái dễ đọc Owner đang cần.
   Tiêu đề rỗng sau khi làm sạch ⇒ lùi về tên file gốc.
3. **`app/core` KHÔNG được biết chuyện của viral.** Import-linter chặn cứng
   `app.core -> app.features`. Nên `offsite` nhận `material_id` + `title` **đã sạch marker**;
   việc bóc `[AI_GENERATE]` và `### … ###` do `processor` làm bằng `_clean_title_for_context`
   sẵn có của feature.
4. **Thư mục theo tháng**: `videos/YYYY-MM/`, lấy theo thời điểm chép. Chỉ áp cho `kind="video"`
   — `backups` giữ nguyên thư mục phẳng vì lệnh khôi phục đang trông vào đó.
5. **Giữ nguyên cơ chế bỏ qua bản y hệt của ADR-024** (cùng tên + cùng dung lượng ⇒ không chép
   lại). Đổi cách đặt tên mà làm gãy chỗ này thì mỗi lần "Reup lại" tốn thêm 30 MB băng thông.
   Có test riêng cho đúng ca đó.
6. **Tin Telegram mang thêm dòng vị trí trong Drive** khi có chép:
   `📂 videos/2026-09/949 - Nay tui đi câu mực nha anh em.mp4`. Nói rõ trong tin đây là **vị
   trí trong Drive**, không phải link bấm được — nhãn đúng với thứ nó là, không hứa hão
   (bài học ADR-023).
   `notify_material_ready(mat, media_path, drive_path=None)`; không có thì tin y như cũ.

## Phạm vi

| Việc | File |
|---|---|
| Làm sạch tên, thư mục theo tháng, trả đường dẫn tương đối | `app/core/storage/offsite.py` |
| Truyền `material_id` + tiêu đề sạch, giữ kết quả để báo | `app/features/viral_intake/processor.py` |
| Dòng "vị trí trong Drive" trong tin | `app/core/notifier/formatting.py`, `app/core/notifier/service.py` |
| Test | `tests/test_offsite_video.py`, `tests/test_notify_jobless.py` |

## Ngoài phạm vi

- **Không gọi Google Drive API**, không link bấm được, không đặt quyền chia sẻ.
- Không đổi tên file **gốc trên máy** — `find_reup_path` và cả luồng xử lý dựa vào tên đó.
- Không dọn/di chuyển những file đã nằm sẵn trên Drive theo tên cũ.
- Không đụng `kind="backup"`, không đụng `check_root` / `get_root`.

## Hết hiệu lực

Sau proof: một material `READY` có tiêu đề tiếng Việt ⇒ trên Drive xuất hiện
`videos/<YYYY-MM>/<id> - <tiêu đề>.mp4`; chép lần hai không tốn thao tác ghi nào; tiêu đề có
`\ / : * ?` hoặc dài 300 ký tự vẫn tạo được file; tin Telegram có dòng vị trí đúng đường dẫn
tương đối; tắt Drive ⇒ tin y như trước.

## Proof (2026-09-09)

Tin Telegram dựng thật:

```
🎬 Video sẵn sàng đăng tay
📋 Material #949 | tiktok
📝 Nay tui đi câu mực nha anh em
👁 31,500 lượt xem
📁 viral_949_reup.mp4
📂 Trong Drive: videos/2026-09/949 - Nay tui đi câu mực nha anh em.mp4

✍️ Caption — chạm vào để chép: …
```

| Điều kiện hết hiệu lực | Kết quả |
|---|---|
| `videos/<YYYY-MM>/<id> - <tiêu đề>.mp4`, giữ dấu tiếng Việt | `test_chep_video_dat_ten_theo_tieu_de_va_xep_thu_muc_thang` |
| Ký tự `\ / : * ? " < > \|` và tên kết thúc bằng chấm ⇒ vẫn tạo được file | 3 ca `test_ten_file_giu_dau_tieng_viet_va_bo_ky_tu_cam` |
| Tiêu đề 300 ký tự ⇒ cắt, vẫn còn ID và đuôi file | `test_tieu_de_dai_bi_cat_nhung_van_giu_id_va_duoi_file` |
| Tiêu đề rỗng / toàn ký tự cấm ⇒ lùi về tên gốc, không bao giờ rỗng | 5 ca parametrize |
| Video trùng tên nhau không ghi đè | `test_giu_id_o_dau_vi_kenh_nguon_co_nhieu_video_trung_ten` |
| **Cơ chế bỏ qua bản y hệt của ADR-024 còn nguyên** | `test_ten_moi_van_giu_co_che_bo_qua_ban_y_het_cua_ADR_024` — `copy2` gọi **0** lần lần hai |
| Tên file **gốc trên máy** không đổi | khẳng định trong cùng test |
| `kind="backup"` giữ thư mục phẳng | `test_backup_khong_bi_doi_cho` |
| Đường dẫn dùng `/` kể cả trên Windows | `test_duong_dan_tuong_doi_dung_dinh_dang_hien_cho_nguoi_dung` |
| Tin nói **"Trong Drive"**, không hứa là "link" | `test_i1_…_chu_khong_hua_la_link` |
| Tắt Drive ⇒ tin y như cũ | `test_i2_khong_bat_drive_thi_tin_y_nhu_cu` |
| Tin bị tách (video >50MB) vẫn giữ dòng Drive ở phần đầu | `test_i4_…` |
| `app/core` vẫn không import `app/features` | `lint-imports`: **2 hợp đồng giữ, 0 vi phạm** |

**Toàn suite: 641 passed, 16 skipped, 0 failed.**

### Một lỗi thật do test bắt được

Ca *"tiêu đề toàn ký tự cấm"* đỏ: kết quả ra `1 - \.mp4` — **dấu `\` không bị lọc**. Nguyên
nhân: lớp ký tự viết thành `[\/:*?"<>|…]`, mà trong regex `\/` chỉ là `/` đã escape, nên
backslash **không nằm trong lớp**. Trên Windows, một dấu `\` lọt vào tên file là biến nó thành
đường dẫn thư mục — lượt chép hỏng. Đã sửa thành `[\/:*?"<>|…]`.

### Hai test cũ phải sửa (hành vi đổi có chủ ý)

- `test_bat_co_thi_chep_sang_thu_muc_videos`: đích nay có thêm cấp `YYYY-MM`.
- `test_processor_goi_copy_video_mot_diem_chung_cho_ca_hai_nhanh`: khẳng định chuỗi
  `copy_video_if_enabled(media_path)` — lời gọi nay có tham số nên xuống nhiều dòng. Đổi mốc
  thành `copy_video_if_enabled(`; **ý định của test giữ nguyên** (phải gọi trước nhánh READY).

### Nợ ghi lại

`processor.py` dòng ~839 vẫn còn `from … import ViralService as _VS` trong hàm, nay thừa vì
`ViralService` đã import ở đầu file. Không dọn trong ADR này để giữ diff tối thiểu.

## Review nhiều mũ sau khi làm (2026-09-09)

Soi lại bản vừa commit `0f4d207`. Hai lỗi thật, cùng một họ, đã sửa; một hành vi đã ghi lại.

### Đã sửa — hợp đồng "không bao giờ ném lỗi" đang nói dối

1. `copy_video_if_enabled` hứa trong docstring *"KHÔNG BAO GIỜ ném lỗi"*, nhưng
   `safe_video_name(Path(src).name, …)` nằm **ngoài** `try`. Hàm này chạy **sau khi video đã
   xử lý xong**; một ngoại lệ thoát ra là hỏng cả lượt xử lý chỉ vì bản chép phụ. Đúng bẫy
   ADR-027 đã dính hai tiếng trước: bọc phần đắt tiền mà bỏ sót phần rẻ ngay cạnh.
2. `relative_to_root` được gọi **trong danh sách tham số** của `notify_material_ready`, tức
   chạy **trước khi** vào hàm đó — mọi `try/except` bên trong notifier không đỡ được. Một dòng
   chỉ để hiển thị mà có quyền đánh hỏng material đã commit `READY`.

Cả hai nay bọc trọn; `relative_to_root` hỏng thì lùi về tên file, không ném.
Test: `test_dung_ten_file_hong_thi_bo_qua_chu_khong_nem_loi`,
`test_duong_dan_tuong_doi_hong_thi_tra_None_chu_khong_nem_loi`.

### Đã kiểm — tên file dựng từ chữ người lạ viết

Tiêu đề lấy từ TikTok nay thành tên file, nên kiểm đường dẫn vượt cấp: `../../etc/passwd`,
`..\..\Windows\System32`, `..`, `....//....//x`, `/etc/passwd` — không ca nào thoát ra khỏi
thư mục tháng (`/` và `\` bị thay, `..` trơ lại bị `rstrip(". ")` ăn hết rồi lùi về tên gốc).
Trước đó **không có test nào khoá**, nên ai sửa regex sau này có thể mở lại lỗ mà không biết.
Test: `test_tieu_de_khong_the_thoat_ra_ngoai_thu_muc_dich` (5 ca).

### Ghi lại, không sửa — sang tháng thì có thêm một bản

Thư mục lấy theo **thời điểm chép**, mà cơ chế bỏ qua bản y hệt của ADR-024 chỉ so **trong
cùng thư mục**. Nên một video reup lại ở tháng sau sẽ có thêm một bản ở thư mục tháng mới.
Chấp nhận: reup lại là việc hiếm, đổi lại thư mục không phình vài nghìn file. Đã ghi thành
test để phiên sau không tưởng là lỗi: `test_sang_thang_moi_thi_chep_them_mot_ban`.
Cùng lý do đó, **đổi tiêu đề material** cũng sinh thêm một bản với tên mới.

### Nợ ghi lại, không dọn trong ADR này

- `_clean_title_for_context` (`features/viral_intake/service.py`) và `_clean_material_title`
  (`core/notifier/formatting.py`) **làm y hệt nhau**, hai bản regex song song. Không gộp được
  thẳng vì `core` không được import `features`; muốn gộp thì phải đưa lên `app/core`.
- `processor.py` còn `from … import ViralService as _VS` trong hàm, nay thừa.

**Sau review: 649 passed, 16 skipped, 0 failed. `lint-imports`: 2 hợp đồng giữ, 0 vi phạm.**
