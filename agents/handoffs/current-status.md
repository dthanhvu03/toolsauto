# Current Status

## Phiên 2026-09-09 (j) — ADR-034: dán link vào chat Telegram là xong

Owner: *"mọi thứ để ở tele thì tốt biết mấy"*. Không bê cả web vào chat — chat dở ở bảng biểu
và cấu hình, giỏi ở "một việc một nút". Chỉ chuyển **luồng hằng ngày**.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| Dán **link video** vào chat ⇒ tạo material + xử lý nền, xong bắn video kèm caption | `test_link_video_tao_material_va_xu_ly_nen` |
| Dán **link kênh** ⇒ thêm nguồn tự quét | `test_link_kenh_tao_nguon_va_khong_xu_ly_video` |
| Nút **"➕ Thêm cả kênh này làm nguồn"** — đường duy nhất thêm kênh không liệt kê được (ADR-028) khi đang ở chat | `test_link_video_kem_nut_them_kenh` |
| Bóc link lẫn trong chữ (bấm Chia sẻ từ app TikTok gửi kèm mô tả) + bỏ dấu câu cuối | 4 test |
| Mọi nhánh hỏng ⇒ báo rõ, không im, không ném | 3 test |
| **Vá lỗ có sẵn**: poller chỉ lọc `message`, không lọc `callback_query` theo chat id | 2 test |
| Bot nhắn **"đã sẵn sàng"** mỗi lần Maintenance khởi động | `test_maintenance_chao_sau_khi_poller_chay` |
| Toàn suite | **744 passed, 16 skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ |

Trước bản này `_handle_message` có đúng một dòng `if not text.startswith("/"): return` — **mọi
tin không phải lệnh đều bị vứt**, kể cả link Owner gửi vào.

**Ranh giới module giữ nhờ hook**: `telegram_bot` không import `viral_intake` (ADR-007 chặn
feature gọi feature). Thêm 3 hook ở `bootstrap_hooks`: `viral.add_link`,
`viral.add_source_from_material`, `viral.process_one`.

### System State

Luồng hằng ngày không cần mở máy: thấy video hay → Chia sẻ vào chat bot → bot tải, cắt, viết
caption, gửi lại video + caption chạm-là-chép. Bảng 100 video và trang Thiết lập vẫn ở web,
cố ý.

### Unfinished + Blockers

- **Chưa thử trên bot thật** — máy dev không có token. Owner khởi động lại bằng
  `start.ps1 -Stack`, thấy tin **"🤖 Bot đã sẵn sàng"** là bộ nhận lệnh sống.
- **Chưa làm nút chọn mốc cắt trong Telegram** (dải khung hình + 12 nút) — việc tiếp theo.
- Video > 50 MB vẫn không gửi kèm file được (giới hạn Bot API).
- Nợ cũ: gộp hai hàm làm sạch tiêu đề trùng nhau; bỏ `import ViralService as _VS` thừa.

### Next Action

1. **Owner: `git pull` + `start.ps1 -Stack`** → chờ tin "🤖 Bot đã sẵn sàng" → thử dán một link
   TikTok vào chat.
2. Chạy được thì báo em làm nốt **nút chọn mốc cắt trong Telegram**.
3. Đăng bài đầu tiên lên Page "Mê Câu Cá".

---

## Phiên 2026-09-09 (i) — ADR-033: lệnh Telegram phải làm đúng điều nó nói

Owner muốn thao tác hết trong Telegram cho khỏi mở máy. Trước khi thêm nút mới, đã **gọi
thẳng từng lệnh** — kết quả: **2 lệnh gãy, 3 lệnh nói dối**.

| Trước | Sau |
|---|---|
| `/status` ❌ `WorkerService.get_status` không tồn tại | ✅ đọc `SystemState.worker_status` |
| `/pause` ❌ `JobStatus.PAUSED` không tồn tại | ✅ đặt chuỗi `"PAUSED"` như web vẫn làm |
| `/retry` in "đang thử lại" rồi **không làm gì** | ✅ gọi thật `JobService.retry_job` |
| `/discovery` in "hoàn tất" mà **không quét** | ✅ gọi hook `viral.force_discovery`, chạy nền |
| `/viral` chỉ ghi `WorkerState` — nguồn ADR-019 **không đọc chỗ đó** | ✅ ghi cả RuntimeSetting lẫn WorkerState |
| không có `/help` | ✅ liệt kê đúng 9 lệnh đang chạy |

Hai lệnh gãy vì code đổi mà lệnh không đổi theo; ba lệnh kia **báo thành công cho việc không
xảy ra** — cùng họ "nhãn nói dối" ADR-023, nhưng tệ hơn vì khẳng định là xong.

**Gốc rễ: không có test nào cho lệnh Telegram.** Nay có 25 test **gọi thật**, không đọc code.

### System State

Toàn suite **726 passed, 16 skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ. Bot chạy
long-polling trong tiến trình **Maintenance** — chỉ sống khi khởi động bằng `start.ps1 -Stack`.

### Unfinished + Blockers

- **Chưa thử trên bot thật**: máy dev không có `TELEGRAM_BOT_TOKEN`, nên mọi thứ kiểm bằng
  client giả. Owner gõ `/help` trong Telegram là biết bộ nhận lệnh có sống không.
- **Chưa làm nút chọn mốc cắt trong Telegram** — cố ý để sau, làm trên nền đã sạch.
- Nợ cũ: gộp hai hàm làm sạch tiêu đề trùng nhau; bỏ `import ViralService as _VS` thừa.

### Next Action

1. **Owner: `git pull` + khởi động lại bằng `start.ps1 -Stack`**, rồi gõ `/help` trong Telegram.
   Có trả lời = bộ nhận lệnh sống ⇒ em làm tiếp nút chọn mốc cắt.
2. Đăng bài đầu tiên lên Page "Mê Câu Cá".

---

## Phiên 2026-09-09 (h) — ADR-032: chọn mốc cắt bằng một cú bấm

ADR-031 cho chọn mốc nhưng thao tác vẫn phiền: xem hết video 9 phút, gõ số giây, tải lại cả
trăm MB. Owner hỏi *"có cách nào tiện không em"*. Bỏ cả ba chỗ phiền.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| **Dải 12 khung hình** trích từ video GỐC, bấm một khung là đặt mốc + cắt lại | ffmpeg thật: 12 jpg có nội dung; video 573s ⇒ khung số 8 rơi vào giây 332 (chỗ có cá) |
| Số giây nhúng trong **tên file** ⇒ đọc lại được kể cả khi video gốc đã dọn, không cần cột DB | `test_doc_lai_duoc_giay_tu_ten_file…` |
| **Giữ file gốc** `viral.keep_source_days` (mặc định 7) ⇒ cắt lại **tức thì**, không tải lại | `test_processor_dung_lai_file_goc_truoc_khi_tai` |
| Tìm file gốc **không nhầm** với bản `_reup` đã cắt | `test_tim_file_goc_bo_qua_ban_da_cat` |
| Dọn file gốc quá hạn, **không đụng** bản `_reup` | `test_don_file_goc_qua_han…` |
| Đọc cài đặt hỏng ⇒ **xoá** chứ không giữ (không phình đĩa âm thầm) | `test_doc_o_cai_dat_hong_thi_XOA…` |
| **Ô chọn mốc ra khỏi khối gấp "Reup lại?"** — thành khối riêng "✂️ Chọn đoạn cắt" | render thật |
| Toàn suite | **701 passed, 16 skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ |

**Lỗi thật chỉ lộ khi chạy ffmpeg thật:** `probe_duration` suy ffprobe bằng
`resolve_ffmpeg().replace("ffmpeg","ffprobe")` — thay cả **tên thư mục**, ra đường dẫn không
tồn tại. Hàm nuốt lỗi trả 0 ⇒ **cả dải khung hình im lặng biến mất**, không lỗi không log.
Test giả không bắt được. Repo vốn có `ffmpeg_path.ffprobe_bin()`; đã đổi + cấm kiểu `replace`.

**Nguyên tắc rút ra (lần thứ hai trong ngày):** mọi thứ đụng ffmpeg **phải có ít nhất một test
chạy ffmpeg thật**. Lần trước là `_fast_trim_fallback` thiếu `-ss` (ADR-031) — cũng chỉ lộ khi
chạy thật.

### System State

`/app/viral` mỗi dòng video có khối **"✂️ Chọn đoạn cắt"**: mở ra thấy 12 khung hình có ghi
phút, bấm một khung là tool đặt mốc và cắt lại ngay (dùng file gốc còn trên đĩa, không tải
lại). Vẫn có ô gõ giây tay cho ai muốn chính xác hơn 1/12 video.

### Unfinished + Blockers

- **12 video cũ chưa có khung hình** — chúng xử lý trước bản này nên chưa trích. Bấm
  "Cắt lại" một lần (sẽ tải lại) là tool trích khung luôn, từ đó về sau bấm khung là xong.
- **Tốn đĩa**: mỗi video gốc 50-150 MB × số video đang chờ. Owner siết bằng ô
  `viral.keep_source_days`, đặt 0 là về hành vi cũ.
- Nợ cũ chưa dọn: gộp hai hàm làm sạch tiêu đề trùng nhau; bỏ `import ViralService as _VS` thừa.

### Next Action

1. **Owner: `git pull` + khởi động lại web.** (Không có migration mới ở ADR-032.)
2. Với một video: mở **"✂️ Chọn đoạn cắt"** → bấm **"Cắt lại"** một lần để tool tải lại và
   trích khung → từ lần sau chỉ cần **bấm vào khung có cá**.
3. Cân nhắc bật **phụ đề** (`reup.subtitle_enabled`) — đang tắt, mà đây là thứ giữ chân người
   xem lướt không bật tiếng.
4. Đăng bài đầu tiên lên Page **"Mê Câu Cá"**.

---

## Phiên 2026-09-09 (g) — ADR-031: chọn mốc cắt, đừng đăng 90 giây móc mồi

**Phát hiện lớn nhất phiên này**, tìm ra bằng đo chứ không đoán: video nguồn dài 6-11 phút,
tool giữ **90 giây ĐẦU**. Bóc khung hình video 573s có 2,2 triệu view: giây 45 còn **móc mồi
tôm**, giây 320 mới có **con cá**, giây 545 trống trơn. Tức tool đang xuất bản cảnh móc mồi và
cắt bỏ đúng đoạn tạo ra kết quả. Owner xác nhận: *"video có 1p2 mấy giây là hết rồi"*.

**Đã thử và loại phương án tự dò**: đo năng lượng âm thanh từng giây cả video — phẳng 59-81%,
cửa sổ "ồn nhất" chỉ hơn cửa sổ hiện tại **3 điểm phần trăm**. Không có tín hiệu. Nếu dựng
heuristic theo âm thanh thì đã dựng một thứ không chạy được.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| Cột `viral_materials.clip_start_sec` + migration `p3d0e1f2a3b4` | `alembic heads` = 1 head |
| Cắt đúng từ mốc — **chạy ffmpeg thật** trên video đồng hồ 400s | `clip_start=300` ⇒ khung giây 2 hiện **302**; bỏ trống ⇒ hiện **2** |
| `MAX_REELS_DURATION` hardcode ⇒ ô `reup.max_duration_sec` (mặc định 90) | 3 test |
| Đặt mốc ⇒ status về `REUP` để đường xử lý **tải lại** | `test_dat_moc_thi_ve_REUP…` |
| Giá trị sai ⇒ từ chối, không đổi status | 2 ca |
| UI: ô "Bắt đầu từ giây" + nút "Đặt mốc & tải lại" trên dòng material | render thật |
| Toàn suite | **680 passed, 16 skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ |

**Lỗi thật tìm ra khi chạy thử, kiểu tệ nhất:** bản vá đầu chỉ sửa lượt mã hoá chính. Lượt đó
thất bại ⇒ rơi xuống `_fast_trim_fallback()` — nhánh dựng lệnh ffmpeg **riêng**, chỉ có `-t`,
**không có `-ss`**. Đặt mốc giây 300, hệ thống báo **thành công**, file vẫn là 90 giây đầu.
Sai âm thầm. **Mock argv không bao giờ bắt được** vì mock luôn cho lượt chính thành công —
phải chạy ffmpeg thật với video có đồng hồ mới lộ. Đã vá + khoá bằng test.

### System State

Bỏ trống mốc ⇒ hành vi y như trước. Đặt mốc ⇒ phải **tải lại** video gốc (file gốc đã xoá sau
lần xử lý trước; bản `_reup` chỉ còn 90 giây đó). `find_duplicate` có `exclude_id` nên tải lại
không tự coi là trùng.

### Unfinished + Blockers

- **12 video "sẵn sàng đăng" hiện đang là 90 giây móc mồi.** Owner nói sẽ xoá video trên laptop
  rồi làm lại — đúng hướng. Đừng đăng chúng lên Page mới.
- Chưa có **dải khung hình bấm-chọn** (bước 2, cố ý hoãn): hạ tầng hiện chỉ trích 1 khung ở
  giây 1 (`ensure_reup_thumbnail`). Chỉ làm nếu ô nhập giây chứng minh đúng hướng.
- Nợ cũ chưa dọn: gộp hai hàm làm sạch tiêu đề trùng nhau; bỏ `import ViralService as _VS` thừa.

### Next Action

1. **Owner: `git pull` + khởi động lại web + `alembic upgrade head`** (có migration mới).
2. Với mỗi video: mở link gốc xem lướt, thấy đoạn hay ở phút mấy thì gõ số giây vào ô
   **"Bắt đầu từ giây"** rồi bấm **"Đặt mốc & tải lại"**. Ví dụ phút 5 = `300`.
3. Xong mới đăng lên Page **"Mê Câu Cá"** — lứa bài đầu là lứa Facebook đánh giá Page.
4. Anti: quyết PLAN cho khối badge page header (`layouts/app.html`).

---

## Phiên 2026-09-09 (f) — ADR-029: chạy đúng yt-dlp đã ghim, Sức khỏe báo đúng cái đang chạy

Vá nốt ba thứ còn nợ sau khi Owner hỏi "em vá hết chưa" — câu trả lời lúc đó là **chưa**.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| `yt_dlp_binary()` đảo thứ tự: **venv → `python -m yt_dlp` → PATH → tên trần** | `tests/test_yt_dlp_path.py` (7 test). Máy dev nay chọn `venv\Scripts\yt-dlp.exe` |
| Trang Sức khỏe báo phiên bản **của binary đang chạy** + đường dẫn | `test_installed_lay_tu_binary_chu_khong_phai_goi_trong_venv` |
| Cảnh báo `mismatch` khi binary lệch gói trong venv | 2 test; đây chính là thứ đã cắt ngắn được buổi mò lỗi sáng nay |
| Đo phiên bản: timeout 10 s, không bao giờ ném, nhớ tạm 5 phút (3 lượt gọi ⇒ 1 tiến trình con) | 2 test |
| `generate_caption_for_material` bọc trọn: DB/đĩa hỏng ⇒ `(False, msg)` + `rollback`, session còn dùng được | `test_j1`, `test_j2` |
| `offsite.copy_out` bắt `Exception` thay vì chỉ `OSError` | — |
| Toàn suite | **666 passed, 16 skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ |

**Lỗi tìm ra trong chính bản vá này khi review:** `mismatch` tính **sau** lượt đọc
`requirements.txt`, mà đường đó `return` sớm khi đọc hỏng ⇒ cảnh báo đáng giá nhất biến mất
đúng lúc có thứ khác cũng hỏng. ADR sinh ra để chống "nhãn nói dối" mà suýt tự đẻ một cái. Đã
đưa `_version_key` lên cấp module, tính `mismatch` ngay sau khi đo, có test khoá.

**Không đụng `scan_source`** dù nó cũng hứa "không raise" và cũng hở: `scan_all` đã bọc sẵn
`try/except` + `rollback` cho từng nguồn, có ghi chú rõ. Người viết trước đã lường đúng.

### System State

Tool luôn chạy bản yt-dlp đi theo trình thông dịch của chính nó (tức bản ghim trong
`requirements.txt`); một bản lạ trên PATH không còn cướp được nữa, và nếu có thì trang Sức
khỏe cảnh báo đỏ kèm đường dẫn. Ba hàm từng hứa "không bao giờ ném lỗi" nay đúng như lời hứa.

### Unfinished + Blockers

- **Chưa thử trên máy Owner.** Máy dev chỉ có một bản yt-dlp nên `mismatch` chưa bao giờ bật
  thật; ca lệch được kiểm bằng test giả. Owner pull về, mở trang Sức khỏe là thấy dòng
  "Đang gọi: …" — nếu nó trỏ vào `Python312\Scripts` chứ không phải `venv` thì báo em.
- Nợ còn lại, đều nhỏ và đã ghi: gộp hai hàm làm sạch tiêu đề trùng nhau; bỏ
  `import ViralService as _VS` thừa trong `processor.py`.
- Cố ý không làm: link Drive bấm được (cần Drive API), tự cập nhật yt-dlp từ trang web.

### Next Action

1. **Owner: `git pull` + khởi động lại web** → mở **Sức khỏe hệ thống**, xem dòng
   *"Đang gọi: …"* dưới ô yt-dlp. Phải là đường dẫn trong `venv` của dự án.
2. Việc kinh doanh vẫn treo nguyên: đăng bài đầu tiên lên Page **"Mê Câu Cá"** (12 video sẵn
   sàng), thêm ảnh bìa, thêm 2-3 kênh nguồn vì `@thacaukechuyen` đang chiếm 100%.
3. Anti: quyết PLAN cho khối badge page header (`layouts/app.html`).

---

## Phiên 2026-09-09 (e) — ADR-030: bản chép Drive đặt tên theo tiêu đề, xếp theo tháng

Owner hỏi ba việc: gửi kèm đường dẫn video vào Telegram, đặt tên file khớp tiêu đề, chia thư
mục theo tháng.

**Đã nói rõ giới hạn trước khi làm:** Drive for Desktop chỉ **gắn ổ đĩa**, tool `copy2` vào
thư mục cục bộ nên **không biết link `drive.google.com`**. Muốn link bấm được phải gọi Drive
API (OAuth, file ID, quyền chia sẻ) — tách hẳn, không làm trong ADR này. Thứ làm được là
**đường dẫn tương đối** dạng chữ, đủ để mở app Drive gõ tên là ra.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| Tên bản chép: `949 - Nay tui đi câu mực nha anh em.mp4`, giữ dấu tiếng Việt | `test_chep_video_dat_ten_theo_tieu_de_va_xep_thu_muc_thang` |
| Giữ **ID ở đầu** vì kênh nguồn có 4 clip trùng tên "Muốn giàu phải ra biển" | `test_giu_id_o_dau_vi_kenh_nguon_co_nhieu_video_trung_ten` |
| Lọc ký tự Windows cấm, cắt tiêu đề dài, rỗng ⇒ lùi về tên gốc | 9 ca parametrize |
| Thư mục `videos/YYYY-MM/`; `backups` giữ phẳng | 2 test |
| **Cơ chế bỏ qua bản y hệt (ADR-024) còn nguyên** | `copy2` gọi **0** lần ở lần chép thứ hai |
| Tên file **gốc trên máy** không đổi | khẳng định trong cùng test |
| Tin Telegram thêm dòng `📂 Trong Drive: …`, **không** gọi là "link" | `test_i1`, `test_i2`, `test_i4`, `test_i5` |
| `app/core` vẫn không import `app/features` | `lint-imports`: 2 hợp đồng giữ, 0 vi phạm |
| Toàn suite | **641 passed, 16 skipped, 0 failed** |

**Một lỗi thật do test bắt:** lớp ký tự viết `[\/:*?"<>|…]` — trong regex `\/` chỉ là `/`
nên **dấu `\` không bị lọc**, ra tên `1 - \.mp4`. Trên Windows một dấu `\` lọt vào tên file
là biến nó thành đường dẫn thư mục, hỏng lượt chép. Đã sửa.

**Hai test cũ phải sửa** (hành vi đổi có chủ ý, giữ nguyên ý định): đích có thêm cấp tháng; và
mốc `copy_video_if_enabled(media_path)` đổi thành `copy_video_if_enabled(` vì lời gọi nay
xuống nhiều dòng.

### System State

Bật Drive ⇒ mỗi video `_reup` vào `videos/<tháng>/<id> - <tiêu đề>.mp4`, và tin Telegram có
dòng vị trí. Tắt Drive ⇒ mọi thứ y như trước. Không migration, không đụng luồng có account.

### Unfinished + Blockers

- **Chưa chạy thật trên Drive của Owner** — máy dev chưa gắn ổ Drive, test dùng thư mục tạm.
  Owner phải cài Google Drive for Desktop rồi bật 2 ô ở `/app/settings` mới thấy tác dụng.
- **Không có link Drive bấm được** — cần Drive API, một ADR riêng nếu Owner thật sự cần.
- Nợ nhỏ: `processor.py` còn `import ViralService as _VS` trong hàm, nay thừa.
- ADR-029 (yt_dlp_path ưu tiên venv + trang Sức khỏe báo đúng binary) **vẫn chưa làm** — Owner
  chưa duyệt. Đã vá tạm bằng cách cập nhật yt-dlp toàn cục trên Windows lên 2026.08.19.

### Next Action

1. **Owner: `git pull` + khởi động lại web.**
2. Muốn dùng tính năng này thì cài **Google Drive for Desktop** (chọn chế độ *truyền phát*,
   không phải *sao chép*), rồi `/app/settings` bật **"Sao lưu ngoại vi"** + **"Chép video đã
   xử lý"** và điền đường dẫn thư mục Drive.
3. Việc kinh doanh đang treo: đăng bài đầu tiên lên Page **"Mê Câu Cá"** (12 video đã sẵn
   sàng), thêm ảnh bìa, và thêm 2-3 kênh nguồn vì `@thacaukechuyen` đang chiếm 100%.
4. Anti: quyết PLAN cho khối badge page header (`layouts/app.html`).

---

## Phiên 2026-09-09 (d) — ADR-028: kênh TikTok không liệt kê được bằng @handle

Owner báo nguồn `@thacaukechuyen` quét ra lỗi, bảng cắt còn `ERROR: [tiktok:user]… Una…`.

**Chẩn đoán bằng kiểm chứng, không đoán:**

| Giả thuyết | Kiểm | Kết luận |
|---|---|---|
| yt-dlp cũ | `pip index versions yt-dlp` | Đang **2026.8.19 = mới nhất**. Không phải. |
| TikTok chặn hết | quét `@tiktok`, `@charlidamelio` | `@tiktok` ✅, `@charlidamelio` ❌ giống hệt ⇒ **lỗi theo từng kênh** |

Nguyên văn: *"Unable to extract secondary user ID… try using `tiktokuser:channel_id`"*. Cách
gợi ý đó **chạy thật** trên đúng kênh của Owner. Nhưng `channel_id` chỉ lấy được từ một video
của kênh, mà `add_source` đang **từ chối thẳng link video**.

**Bẫy đã tự dẫm phải, ghi để không ai mất thêm một vòng:** `channel_id` dài **76 ký tự**; lần
thử đầu vô tình cắt còn 70 và `tiktokuser:` báo **đúng cùng một lỗi**. Thông báo đó không phân
biệt "kênh không liệt kê được" với "channel_id sai/cụt".

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| Ô "URL kênh" nhận thêm **link một video TikTok** → tự dò `channel_id` → nguồn `tiktokuser:<id>` | Chạy thật trên kênh Owner: `found=5`, views 2.000.000 → 17.600 |
| Link video sinh ra vẫn đúng dạng cũ `@handle/video/<id>` ⇒ chống trùng vẫn khớp | proof ở trên |
| Nguồn `@handle` cũ **không tốn lượt mạng nào** | `test_link_kenh_handle_van_di_duong_cu_khong_goi_yt_dlp` |
| FB/IG/YouTube vẫn từ chối như cũ | 3 ca parametrize |
| yt-dlp lỗi / quá 60s / video không có channel_id ⇒ toast đỏ tiếng Việt, không raise | 3 test |
| Cột Lỗi hiện hướng dẫn tiếng Việt thay vì nguyên văn cụt | `test_quet_gap_loi_secondary_user_id_…` |
| Bảng vẫn bấm sang kênh được dù `url` là `tiktokuser:` | render fragment ⇒ `https://www.tiktok.com/@thacaukechuyen` |
| Toàn suite | **621 passed, 16 skipped, 0 failed** |

**Một test cũ phải sửa:** `test_add_source_rejects_fb_ig_video_and_duplicate` khẳng định link
video TikTok bị từ chối — nay không còn đúng, và tệ hơn là test đó bắt đầu **gọi mạng thật**,
phá cam kết "không mạng" của file. Đã bỏ dòng đó, để lại cảnh báo tại chỗ.

### System State

Kênh TikTok liệt kê được bằng `@handle` ⇒ đường cũ y nguyên. Kênh không liệt kê được ⇒ Owner
dán link một video, tool lưu nguồn dạng `tiktokuser:<channel_id>`. Không migration, không đụng
YouTube / `scan_all` / lịch quét.

### Unfinished + Blockers

- **Nguồn `@thacaukechuyen` hiện tại trong DB của Owner vẫn hỏng** — ADR-028 cố ý **không** tự
  cứu: `channel_id` chỉ lấy được từ một video của kênh, mà nguồn đó `last_found=0` nên trong
  kho không có video nào để lần ra. Owner **xoá nguồn cũ rồi thêm lại bằng link video**.
- Không dùng cookie/đăng nhập để cứu các kênh khác — việc khác, rủi ro khác.
- Postgres máy dev vẫn không chạy; tool thật chạy trên `LAPTOP-T2HF25CD`.
- Nợ cũ: `tests/test_threads_world_news.py` lỗi collection từ commit `8326183`.

### Next Action

1. **Owner: `git pull` + khởi động lại web process.**
2. Vào `/app/viral/sources` → **Xoá** nguồn `@thacaukechuyen` đang lỗi → **Thêm** lại, dán
   link một video của kênh đó vào ô URL kênh (Min views 1.000, Max video 50) → **Quét**.
3. Video quét về sẽ tự có caption và bắn một tin Telegram kèm file (ADR-027).
4. Anti: quyết PLAN cho khối badge page header (`layouts/app.html`).

---

## Phiên 2026-09-09 (c) — ADR-027: video xong là bắn một tin Telegram đủ dùng

Owner: *"khi đã hoàn tất 1 video đã có caption và video được xào chẻ thì bắn về tele, anh chỉ
việc bấm nút tải và sao chép caption thôi"*.

**Chặn phải hỏi trước khi làm:** caption **không hề tự chạy** — `generate_caption_for_material`
chỉ có đúng một nơi gọi là nút trên web (ADR-021 mục 4). Nên khoảnh khắc "video xong VÀ có
caption" không bao giờ tự tới; chỉ gộp tin thì Owner vẫn phải mở web mỗi video. Đã hỏi, Owner
chọn **"Tự viết, rồi bắn 1 tin gộp"**.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| Tự viết caption ngay sau khi video xào chẻ xong, rồi bắn **đúng một** tin kèm file | `test_h9` — 1 lời gọi AI, 1 tin, không còn tin caption rời |
| Caption + hashtag trong **một** khối `<code>` (Telegram: chạm là chép) | `test_h1` — đếm `<code>` = 1 |
| Ô bật/tắt `viral.auto_caption_on_ready` (mặc định BẬT) ở `/app/settings` | `test_h10` — tắt ⇒ 0 lời gọi AI, tin về đúng dạng ADR-022 |
| AI nổ / chưa có key ⇒ vẫn có tin video, kèm dòng nêu lý do | `test_h11`, `test_h5` |
| Tin quá 1024 ký tự ⇒ tách 2 tin, khối caption **không bị cắt** | `test_h7` — caption 1200 ký tự còn đủ |
| Bấm tay trên web vẫn bắn tin caption riêng (ADR-021/022 y nguyên) | `test_h12` |
| Toàn suite | **612 passed, 16 skipped, 0 failed** |

**Suite bắt được một lỗi thật của bản đầu:** chỉ bọc `try/except` quanh lời gọi AI mà không
bọc lượt **đọc ô cài đặt** — đọc `runtime_settings` cũng đụng DB, hỏng ở đó là ngoại lệ thoát
ra và **đánh `FAILED` một video đã xử lý xong, đã commit `READY`**. Ba test có sẵn đỏ ngay.
Đã bọc cả lượt đọc, thêm `db.rollback()` trong `except`, và thêm `test_h13` khoá lại.

### System State

Luồng đăng tay giờ khép kín trong Telegram: video xào chẻ xong → AI viết caption → một tin có
file + caption chạm-là-chép. Luồng **có account** (job + `notify_style_selection`) không đổi.
Không migration. `processor.py` nay import `ViralService` và `settings` ở đầu file theo
`RULES.md` (đã kiểm không sinh vòng lặp import).

### Unfinished + Blockers

- **Chưa gửi thử qua Telegram thật.** Máy dev không có token và không nối được DB; test dùng
  `StubNotifier` ở tầng code. Ngưỡng 50 MB của Bot API vẫn nguyên: video nặng hơn thì chỉ
  nhận được chữ, không có file.
- **Ngưỡng tách tin đo trên chuỗi HTML thô** nên tách sớm hơn cần thiết một chút — cố ý
  nghiêng về phía an toàn, thà hai tin còn hơn caption cụt đuôi.
- Postgres máy dev vẫn không chạy (container `toolsauto_postgres` đã Exited); tool thật chạy
  trên `LAPTOP-T2HF25CD`.
- Nợ cũ: `tests/test_threads_world_news.py` lỗi collection từ commit `8326183`.

### Next Action

1. **Owner: `git pull` + khởi động lại web process**, để một video mới chạy tới `READY` rồi
   xem Telegram — phải nhận **một** tin có file `_reup.mp4` và khối caption chạm-là-chép.
2. Nếu thấy tốn AI quá thì tắt ô **"Tự viết caption khi video sẵn sàng đăng tay"** ở
   `/app/settings`, mục "Quét TikTok & Viral".
3. Việc treo từ phiên trước: sửa `Max video/lần` của `@thacaukechuyen` lên 50 (ADR-026 đã có
   nút Sửa), rồi Quét.
4. Anti: quyết PLAN cho khối badge page header (`layouts/app.html`).

---

## Phiên 2026-09-09 (b) — ADR-026: sửa tại chỗ nguồn video

Owner đặt `Max video/lần = 3` cho `@thacaukechuyen`, quét mãi vẫn "Tìm thấy 0" (đúng thiết
kế: chỉ ngó 3 video mới nhất, cả 3 đã có trong kho), rồi phát hiện **không có đường nào sửa
số đó**. Hợp đồng `SourceService` của ADR-019 thiếu hẳn `update` — bảng nguồn chỉ có
Bật/Tắt, Quét, Xoá.

**Phát hiện quyết định hình dạng UI:** hai cột `Min views` / `Max video` mang
`hidden xl:table-cell` ⇒ **màn < 1280px không hiện**. Owner dùng UltraViewer ở khung hẹp hơn
thế, nên nếu biến hai ô đó thành input tại chỗ thì Owner **vẫn không sửa được** — đúng cái
bẫy vừa gây ra ADR-025. Vì vậy ô sửa nằm ở **hàng `<tr>` riêng dùng `colspan`**, có test
khoá lại để phiên sau không "gọn hoá" ngược về cột.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| `SourceService.update_source()` — bổ khuyết hợp đồng ADR-019 | 8 test service trên SQLite thật |
| Sửa max 3 → 50 **không mất** `Quét cuối` / `Tìm thấy` | `test_update_source_changes_numbers_and_keeps_scan_history` |
| Ô trống = **về mặc định**, không phải giữ số cũ | `test_update_source_empty_means_back_to_default_not_keep_old` |
| 0 / 501 / chữ / âm ⇒ toast đỏ tiếng Việt, **không ghi gì** | 5 ca `test_update_source_rejects_bad_values_without_touching_db` |
| Route dùng `str` chứ không `Optional[int]` để lỗi ra toast, không 422 JSON | `test_update_bad_number_is_vietnamese_error_toast_not_422` |
| Xoá hết Page ⇒ sạch cả `target_page` legacy | `test_update_source_clearing_pages_also_clears_legacy_column` |
| Hàng sửa không nằm trong cột bị ẩn ở màn hẹp | `test_edit_row_is_not_inside_a_column_that_hides_on_narrow_screens` |
| Chạy thật ca của Owner (thêm nguồn → sửa max 3→50 → đọc lại DB) | `min_views=1000 max_videos=50` |
| Toàn suite | **599 passed, 16 skipped, 0 failed** |

**Một file ngoài phạm vi dự tính**: `tests/test_source_fanout_ui.py` — helper `_row` cắt slab
tới hàng nguồn kế tiếp nên nuốt luôn hàng sửa mới, làm assert "không in nguyên URL ra bảng"
(ADR-020) đỏ. Quy tắc đó **không bị vi phạm** — cột Page vẫn chỉ hiện tên rút gọn, URL đầy
đủ nằm trong textarea để sửa. Đã thu hẹp `_row` dừng ở `</tr>`; không đổi assert nào.

### System State

`/app/viral/sources` giờ sửa được Min views / Max video / Page đích tại chỗ, giữ nguyên
lịch sử quét. `url` / `platform` / `handle` vẫn không sửa được (đổi kênh thì xoá rồi thêm).
Không migration, không đụng `scan_source` / `scan_all` / lịch quét mỗi giờ.

### Unfinished + Blockers

- **Chưa xem trên trình duyệt thật ở máy chạy tool.** Máy dev `Admin-PC` không nối được DB
  (xem dưới), nên phần kiểm chạy trên SQLite tạm + app thật.
- **Postgres của ToolsAuto trên máy dev không chạy**: container `toolsauto_postgres` đã
  `Exited` từ 2026-09-08 tối; `DATABASE_URL` trỏ `127.0.0.1:5434` không ai lắng nghe. Tool
  thật của Owner chạy trên **máy khác** (`LAPTOP-T2HF25CD`, qua UltraViewer) nên phiên này
  không đọc được trạng thái runtime thật của Owner.
- Nợ cũ chưa ai dọn: `tests/test_threads_world_news.py` lỗi collection
  (`No module named 'app.services'`) từ commit `8326183`.

### Next Action

1. **Owner: `git pull` + khởi động lại web process**, mở `/app/viral/sources` → bấm **Sửa**
   ở hàng `@thacaukechuyen` → đặt Max video/lần = **50** → **Lưu** → bấm **Quét**. Nếu vẫn
   "Tìm thấy 0" thì hạ **Min views** (đang 1.000) rồi quét lại.
2. Anti: quyết có làm PLAN cho khối badge page header (`layouts/app.html`) không — treo từ
   phiên 2026-09-08 (c).

---

## Phiên 2026-09-09 (a) — ADR-025: "Nguồn video" thành trang riêng `/app/viral/sources`

Owner hỏi *"sao nguồn video nó nằm trong ui ux của nội dung viral vậy, lỗi?"* khi bấm mục
sidebar **Nguồn video** trên khung UltraViewer và rơi vào một khối đóng kín.

**Chẩn đoán**: không phải lỗi code. ADR-019 mục 5 cố ý đặt khối nguồn làm `<details>` trong
`/app/viral`, mục sidebar chỉ là link neo `#viral-sources-panel` (`b449d8c`, commit đó ghi
"mở sẵn khối"). Sau đó ADR-022 (`b1fa630`) đổi mặc định thành **đóng khi màn < 1280px**, mà
script nhớ trạng thái **không đọc `location.hash`** ⇒ màn hẹp bấm vào là ra khối đóng.
Hai thay đổi không được ghép lại với nhau.

Đã nêu 2 phương án: (A) vá 3 dòng ép mở khi có hash — chỉ chữa triệu chứng; (B) tách trang
riêng — đụng backend, cần ADR. **Owner chọn B**, rồi yêu cầu review nhiều góc trước khi làm.

**Review nhiều mũ đã sửa 3 lỗ trong bản thảo ADR đầu tiên** (giá trị thật của bước này):
1. Bản thảo nói "dựng theo đúng khuôn `app_viral`" — mà `app_viral` nhận
   `db: Session = Depends(get_db)` rồi **không dùng**, mở session DB mỗi lần vào trang cho
   không. Route mới **không nhận `db`** (có test khoá bằng `inspect.signature`).
2. Bản thảo quên hẳn vỏ trang, và bỏ sót mâu thuẫn tên gọi có sẵn: sidebar ghi
   **"Nguồn video"**, khối ghi **"Nguồn tự động"**. Là khối gấp thì không ai để ý; thành
   trang riêng thì bấm một đằng ra tiêu đề một nẻo. Chốt một tên **"Nguồn video"**.
3. `/viral/sources` (fragment) và `/app/viral/sources` (trang) khác nhau 4 ký tự ⇒ bắt buộc
   docstring hai chiều ở cả hai hàm.

**Commit**: `0ea0c86` trên `main`, 9 file, +355/-88. **Đã push lên `origin/main`** (`e8b6c4b..0ea0c86`).

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| Route `GET /app/viral/sources` (vỏ trang, không session DB) | `test_page_serves_and_keeps_the_same_source_endpoints`, `test_page_route_opens_no_db_session` |
| Trang mới `pages/app_viral_sources.html` — giữ nguyên form + ô nhiều Page + cảnh báo spam (ADR-020 mục 6) | `test_page_keeps_multi_page_field_and_spam_warning` |
| **Không đụng endpoint `/viral/sources*` nào** | `tests/test_viral_sources_ui.py` **17 test xanh, file không sửa một dòng** |
| `/app/viral` sạch: gỡ `<details>` (63 dòng) + IIFE `localStorage` (20 dòng) | `test_viral_page_no_longer_carries_the_sources_panel` |
| Luồng không đứt: `/app/viral` có link "Nguồn video" | `test_viral_page_still_links_to_the_sources_page` |
| Sidebar sáng đúng một mục mỗi trang (`p.startswith('/app/viral')` cũ làm sáng cả hai) | `test_sidebar_highlights_only_the_*` |
| Không còn link neo chết ở `layouts/app.html` + `app_tiktok_links.html` | `test_no_dead_anchor_left_anywhere` |
| Toàn bộ suite | **582 passed, 16 skipped, 0 failed** (2 phút 42) |

5 file sửa + 3 file mới — vượt ngưỡng "3 file/1 bug" của `RULES.md`. Ngưỡng đó cho **sửa
bug**; đây là thay đổi điều hướng có ADR, và 5 file là số tối thiểu để không sót link chết.
Đã ghi rõ trong ADR-025 mục "Ghi chú luật".

### System State

`/app/viral` giờ chỉ còn luồng video (ngắn hẳn trên màn hẹp, đúng tinh thần ADR-022).
`/app/viral/sources` là trang riêng, mở ra là thấy — **không còn trạng thái UI phụ thuộc
`localStorage` từng máy** ở khu vực này. Backend quét nguồn (`SourceService`, hook
`viral.scan_sources`, lịch mỗi giờ) **không đổi một dòng**; không migration, không DB.

### Unfinished + Blockers

- **Postgres của ToolsAuto không chạy** (phát hiện lúc kiểm tra, ngoài phạm vi ADR-025):
  `DATABASE_URL` trỏ `127.0.0.1:5434` nhưng **không có gì lắng nghe ở 5434** — máy chỉ có
  5432 (dịch vụ local) và 5433 (`sixmen_postgres`, dự án khác). Hệ quả: fragment
  `/viral/sources` trả 200 nhưng **0 dòng** (`list_sources` nuốt lỗi, trả list rỗng — hành
  vi có sẵn, không phải do phiên này). Instance ở cổng 8002 cũng đang trong tình trạng đó.
  **Chưa đụng vào** — cần Owner quyết bật lại DB hay sửa `DATABASE_URL`.
- **Instance 8002 đang chạy code cũ** — phải khởi động lại mới có route mới.
- Vì DB không nối được nên **chưa thấy dòng nguồn thật** trên trang mới; phần render dòng
  đã được 17 test fragment của ADR-019 phủ.
- Nợ sẵn có, không liên quan phiên này: `tests/test_threads_world_news.py` lỗi collection
  (`No module named 'app.services'`) từ commit `8326183`.
- Nợ đã ghi trong ADR-025: `app_viral` cũ vẫn còn `Depends(get_db)` thừa (ngoài phạm vi).

### Next Action

1. **Khởi động lại web process**, rồi mở `/app/viral/sources` trên đúng khung UltraViewer
   — bấm "Nguồn video" ở sidebar phải ra trang có bảng nguồn ngay, không phải khối đóng.
   (Đã kiểm qua app thật + middleware auth: cả hai trang 200, sidebar sáng đúng một mục.)
2. **Bật lại Postgres cho ToolsAuto** (hoặc sửa cổng trong `DATABASE_URL`) — không có DB
   thì cả tool đứng, không riêng trang này.
3. ~~Owner đóng khối "Nguồn tự động" một lần cho máy nhớ~~ — **thành thừa**, khối đó không
   còn tồn tại.
4. Anti: quyết có làm PLAN cho khối badge page header (`layouts/app.html`) không — vẫn treo
   từ phiên 2026-09-08 (c).

---

## Phiên 2026-09-08 (c) — UX: /app/viral gọn lại cho màn hẹp (chỉ template, không đổi backend)

Owner dùng tool qua UltraViewer, khung hẹp hơn bản dựng 1440px: trang `/app/viral` phải cuộn
rất xa mới thấy bảng video, và **cuộn ngang cả trang**. Phiên này chỉ sửa 4 file template
(agent khác đang làm notifier — không đụng).

### ADR-024 — chống trùng nội dung (Owner: "cả 2")

Rà hiện trạng: tool chặn trùng **link** (`url` UNIQUE) và trùng **file ở tầng job** (sha256 +
2 unique index), nhưng **thiếu hẳn tầng giữa** — cùng video ở hai kênh nguồn ⇒ tải 2 lần,
ffmpeg 2 lần, Drive 2 bản.

**Điểm kỹ thuật quyết định thiết kế:** `sha256` chỉ bắt file giống hệt từng byte; video đăng
lại ở nền tảng khác luôn bị mã hoá lại ⇒ sha256 **gần như không bao giờ nổ**. Thứ bắt được là
**pHash** — và tool đã có sẵn `VideoProtector.extract_phash()` (imagehash), trước chỉ dùng cho
bằng chứng bản quyền. Nên dùng **cả hai**.

| Việc | Proof |
|---|---|
| Chép Drive bỏ qua bản y hệt (cùng tên + cùng cỡ) | test đếm `copy2` = **0** lần ở lần chép thứ hai |
| `dedup.py`: `hamming` / `phash_distance` (ghép khung theo **số giây**, lấy trung vị) / `find_duplicate` | 39 test; ca chốt sort: sort số ⇒ 0, sort chuỗi ⇒ 64 |
| Cột `content_hash` + `phash` + migration `n2c9d0e1f2a3` (1 head) | `alembic current` xác nhận |
| Chặn **trước** `ReupProcessor` ⇒ không tốn lần re-encode đầy đủ; trùng ⇒ `ViralStatus.DUPLICATE`, xoá file, không job, không Drive | |
| Ngưỡng `viral.phash_max_distance` (mặc định 8) chỉnh ở `/app/settings` | |
| UI: badge **"Trùng"** màu trung tính (không phải đỏ — đây không phải lỗi), dòng "trùng với #N", chip đếm, bộ lọc; hàng trùng không mời bấm Tải file/Viết caption | 20 test UI |

**PROOF Postgres thật, hai ca, đã dọn sạch (TRƯỚC == SAU):**
- **A — cùng file, URL khác:** #71 → `DUPLICATE`, *"Trùng nội dung với #70 (sha256 giống hệt)"*, `ReupProcessor.process` gọi **0 lần**.
- **B — video ĐÃ MÃ HOÁ LẠI** (`libx264 crf 34`, scale 0.8, 24 fps → 32,7 MB còn 5,6 MB, sha256 khác hẳn): #72 → `DUPLICATE`, *"(pHash cách 0)"*, ffmpeg reup **0 lần**. Đây là ca sha256 bó tay.

**Hai fixture test có sẵn phải vá** (code đúng, test giả lập sai): `test_viral_ready_without_account`
đếm nhầm lời gọi ffprobe của pHash; `test_viral_sources` cho mọi material cùng chuỗi byte
`b" "*2048` nên material thứ hai bị ADR-024 bắt trùng — đúng hành vi mong muốn.

Nợ ghi nhận: `extract_phash` vẫn chạy ffmpeg (1 ffprobe + 5 khung, ~1–9 s) — thứ tiết kiệm
được là lần re-encode đầy đủ; nhánh pHash nạp toàn bộ material vào bộ nhớ rồi so tuyến tính
(23 dòng thì vô hại, hàng nghìn thì phải chia bucket); **23 material cũ có `content_hash`/`phash`
NULL nên không tham gia so trùng**; pHash không đọc âm thanh nên video nhiều khung tối có thể
bị chặn oan — hạ ngưỡng về 0 trong cài đặt nếu gặp.

Suite: Windows **588 passed**; Linux **571 passed / 17 skipped**; lint 2 kept.


### Quét kênh TikTok trên laptop lỗi — do yt-dlp cũ, không phải kênh hỏng

Owner gửi ảnh: nguồn `@thacaukechuyen` báo `ERROR: [tiktok:user] … Unable to extract
secondary user ID`, tìm thấy 0. Chạy **cùng kênh đó** trên máy dev với yt-dlp
**`2026.08.19`** → ra 3 video bình thường. Kết luận: laptop còn bản cũ (`requirements.txt`
đã ghim `yt-dlp==2026.8.19` từ commit `11a143b`, nhưng ghim không tự cài).

**Owner làm trên laptop:** `git pull` rồi
`venv\Scripts\python.exe -m pip install -r requirements.txt`, khởi động lại, bấm Quét lại.

**Vá để lần sau tự biết:** trang **Sức khỏe hệ thống** nay có ô **yt-dlp (tải video)** —
xanh khi khớp bản ghim, **đỏ + kèm câu lệnh cần chạy** khi cũ hơn, và đẩy `status` toàn hệ
xuống `degraded` kèm lý do. So sánh **theo số từng phần**, không so chuỗi (`"2026.8.19"` <
`"2026.3.3"` là sai khi so chuỗi — có test chốt riêng ca này). Đọc `requirements.txt` để lấy
bản ghim nên không phải sửa hai chỗ khi nâng cấp.

Vì sao đáng: TikTok/YouTube đổi cấu trúc liên tục, yt-dlp vá theo; bản cũ **gãy âm thầm** và
Owner chỉ thấy dòng lỗi khó hiểu ở cột Lỗi của nguồn.

Test: 5 test mới; Windows **527 passed**; Linux **510 passed / 17 skipped**; lint 2 kept.


### ADR-023 — ô "Chép video đã xử lý" là NHÃN NÓI DỐI, nay nối thật

Owner: *"các video phải vào thiết lập drive"*. Kiểm code: `DRIVE_COPY_VIDEOS` khai báo ở
`config.py` + có `SettingSpec` hiện trên `/app/settings`, `offsite.SUBDIRS` đã có sẵn
`{"video": "videos"}` — **nhưng không dòng code nào đọc cờ đó**. Chỗ duy nhất gọi
`copy_out` là `manage.py db backup`. ADR-012 ghi "Video đã xử lý" trong bảng *Đưa lên Drive*
nhưng người thực thi chỉ nối phần backup. Owner bật ô lên và chờ mãi không có gì.

Cùng loại lỗi với nhãn `.webp` (phiên 05/09): **UI hứa thứ backend không làm**.

| Việc | Proof |
|---|---|
| `offsite.copy_video_if_enabled()` — kiểm cờ rồi `copy_out(src, "video")`, không bao giờ ném lỗi | 7 test mới |
| Gọi tại **một điểm chung trước nhánh rẽ ADR-018** ⇒ cả video `READY` (đăng tay) lẫn video có job đều được chép. Có test đọc source chốt thứ tự này | |
| Mô tả ô sửa cho khớp thực tế (nói rõ chép bản `_reup`) | |
| **Proof thật**: bật cờ + trỏ thư mục giả → dán link → material #70 `READY` 15,5 s → `videos/viral_70_…_reup.mp4` **32,7 MB**; bản gốc còn nguyên (chép chứ không di chuyển); cài đặt đã trả về như cũ | |

Suite: Windows **522 passed**; Linux **505 passed / 17 skipped**; lint-imports 2 kept.


### ADR-022 — Thông báo Telegram cho luồng KHÔNG có job + gọn UI màn hẹp

Owner báo: Telegram trên laptop chạy tốt nhưng hai luồng mới không báo gì; và UI khó dùng ở
màn hẹp (Owner xem qua UltraViewer). **Lưu ý: ảnh Owner gửi là máy `LAPTOP-T2HF25CD`, không
phải `Admin-PC` tôi đang làm** — material #940 ở đó, máy này cao nhất #69.

| Việc | Proof |
|---|---|
| `material_ready_message` / `caption_ready_message` + `notify_material_ready` / `notify_caption_ready`, escape HTML (parse_mode thật là HTML) | 29 test; in nguyên văn 2 mẫu tin |
| Nối vào nhánh READY (`processor.py`) và cả 3 nhánh caption (`service.py`), gồm nhánh chặn sớm thiếu key | proof: material #69 → stub nhận **video**; caption 264,7 s → stub nhận **chữ** |
| `manage.py serve` đăng ký kênh Telegram (đọc cả `runtime_settings`) | có token → 1 kênh, gọi lại → dedup; không token → 0 kênh, không nổ |
| **Gọn UI màn hẹp**: gốc là `<main class="flex-1">` bị `min-width:auto` kéo cả trang tràn — khoá bằng `main{min-width:0}`; khối Nguồn nhớ trạng thái (mặc định đóng khi <1280); giấu cột phụ; header xuống dòng từ `xl`; badge READY nhãn ngắn + `whitespace-nowrap` | 1024: scrollWidth **1193 → 1024**, bảng video từ y=973 → **y=634**; badge 1 dòng ở 900/1024/1280/1600 |

**ĐÍNH CHÍNH ADR-022:** tiền đề "web không đăng ký notifier" của tôi **sai một nửa** —
`app/main.py:55` đã đăng ký, và startup hook nạp `runtime_settings` rồi `replace(...)`. Đó mới
là cơ chế thật; phần thêm vào `serve` chỉ là lớp thứ ba (và không áp dụng khi `--reload`).
Lý do Owner không nhận thông báo chỉ là: hai luồng mới không hề gọi `notify_*`.

### Phát hiện: caption lúc hay lúc dở vì `OPENROUTER_MODEL = openrouter/free`

`openrouter/free` là **quay số ngẫu nhiên** trong các model free. Đo thật hôm nay: một lần
trúng `inclusionai/ling-3.0-flash-fin:free` → trả JSON caption chuẩn; `manage.py ai check`
lại trúng `nemotron-3.5-content-safety` (model **phân loại an toàn**) → pipeline nhận rác,
rơi xuống "Poorman's Logic" (mẫu chung chung, không đọc video). Ghim model cụ thể cũng chưa
cứu được: `google/gemma-4-31b-it:free` → **429**, `meta-llama/llama-4-maverick:free` → **404
hết free**. Hướng đáng làm: **thử lại 2-3 lần khi output không hợp lệ** (mỗi lần bốc model
khác) — cần PLAN riêng, chưa làm.

Nợ UI còn lại: ở <1280 cột Trạng thái chỉ ~78px; `w-[38%]`/`w-64` trong bảng không được
trình duyệt tôn trọng (table-fixed + border-collapse).

Suite: Windows **515 passed**; Linux **498 passed / 17 skipped**; lint-imports 2 kept.


### Nguyên nhân gốc của thanh cuộn ngang (đo bằng Chrome thật)

`<main class="flex-1 lg:ml-64">` trong `layouts/app.html` là flex item nên mặc định
`min-width: auto` ⇒ bảng rộng kéo cả trang ra **1193 px** ở khung 1024. Không được sửa
layout dùng chung nên khoá bằng một dòng CSS **trong chính trang viral**: `main { min-width: 0 }`.
Sau đó bảng cuộn trong đúng khung của nó, trang không còn cuộn ngang ở mọi bề ngang đã thử.

### Done This Session

| # | Việc | Proof |
|---|---|---|
| 1 | Khối "Nguồn tự động" bỏ `open` cứng → đọc/ghi `localStorage['viral.sourcesPanelOpen']`; chưa có lựa chọn thì **đóng khi `innerWidth < 1280`**, mở khi rộng. Listener gắn ở tick sau nên **mặc định không bị ghi vào localStorage** — chỉ lựa chọn của người dùng mới nhớ | Chrome thật: 1440 lần đầu `open=true, ls=null`; bấm đóng → `ls='0'`; reload vẫn đóng. 1024 lần đầu `open=false, ls=null`; bấm mở → reload vẫn mở |
| 2 | Bảng video giấu **Lượt xem + Tài khoản** dưới `xl` (`hidden xl:table-cell` ở cả `<th>` và `<td>`) | Đếm bằng JS: 1024 → 5 `th` = 5 `td`; 1280/1440 → 7 = 7 |
| 3 | Bảng nguồn giấu **Min views / Max video / Tìm thấy** dưới `xl` | 1024 → 7 = 7; 1280/1440 → 10 = 10. `colspan` dòng trống giữ nguyên 7 và 10 |
| 4 | Hàng nút lọc/thao tác: `flex-nowrap + overflow-x-auto` dưới `xl`, trả lại `flex-wrap` từ `xl` — không xuống 3 dòng nữa | `scrollWidth == clientWidth` (627) ở mọi khung ⇒ thực tế vẫn đủ chỗ, cuộn chỉ là lưới an toàn |
| 5 | Form thêm nguồn `flex-col md:flex-row`; textarea "Page đích" `w-full md:w-52`; ô dán link `flex-1 … sm:max-w-[24rem]` | ảnh 1024 panel mở: textarea không chiếm nguyên hàng, 2 nút nằm cạnh |

### Số đo trước/sau (Playwright Chrome thật, `channel="chrome"`)

| Khung | `scrollWidth` trước | sau | Bảng video bắt đầu ở y= trước → sau |
|---|---|---|---|
| 1024×768 | **1193** (cuộn ngang cả trang) | **1024** | 973 → **634** (−339 px, header bảng lọt màn hình đầu) |
| 1280×800 | 1280 | 1280 | 845 → 845 (panel mở theo đúng ngưỡng 1280) |
| 1440×900 | 1440 | 1440 | 845 → 845 (không đổi — đúng chủ ý) |

Kiểm thêm 800 / 900 / 1152 / 1366: `scrollWidth == innerWidth`, `th` hiện == `td` hiện,
bảng nằm gọn trong khung (`tableW <= boxW`).

Test: `test_viral_sources_ui` + `test_source_fanout_ui` + `test_material_caption_ui` +
`test_viral_router_background` = **76 passed**; subset `-k "viral or source or material"`
= **204 passed** — **không phải sửa dòng test nào** (test cũ chỉ assert tên cột/`hx-*`,
mà cột chỉ bị ẩn bằng CSS chứ vẫn còn trong HTML).

### Nợ / điểm chưa chắc

- Ở khung < 1280, badge trạng thái "Sẵn sàng đăng tay" xuống 4 dòng ngắn vì cột Trạng thái
  bị ép còn ~78 px. Thử `whitespace-nowrap` thì bảng phình 729 px > khung 670 ⇒ cắt mất cột
  Thao tác nên đã bỏ. Chấp nhận: chiều cao dòng vẫn do ảnh thumbnail 80 px quyết định.
- Cột `w-[38%]`/`w-64` trong bảng video **không được trình duyệt tôn trọng** (border-collapse
  + table-fixed, tối thiểu theo nội dung thắng). Đã thử chỉnh `w-[32%]`/`w-40` cho màn hẹp:
  không đổi gì nên revert để diff sạch. Muốn kiểm soát bề ngang cột phải đổi cách dựng bảng.
- `layouts/app.html` (ngoài phạm vi được giao): ở 1024, chip **"Panel hệ thống"** bị nút
  "Sức khỏe hệ thống" đè lên. Trước đây nó nằm ngoài màn hình (phải cuộn ngang mới thấy) nên
  không lộ. Cần một PLAN riêng cho khối badge ở page header.
- `tests/test_threads_world_news.py` **lỗi collection có sẵn trên `main`** (`import
  app.services.ai_runtime` — module đã bị dời từ commit `8326183`). Không liên quan phiên này,
  phải `--ignore` khi chạy subset.

### Next Action

1. Owner mở `/app/viral` trên đúng khung UltraViewer, đóng khối "Nguồn tự động" một lần —
   từ đó máy đó nhớ luôn.
2. Anti: quyết có làm PLAN cho khối badge page header (`layouts/app.html`) không.

---

## Phiên 2026-09-08 (b) — ADR-021 backend: AI viết caption cho material READY

Phần backend của ADR-021 (UI do agent khác làm song song: `router.py`, `viral_row.html`,
`tests/test_material_caption_ui.py` — phiên này KHÔNG đụng 3 file đó).

### Phát hiện lớn: tool ĐÃ CÓ nhà cung cấp AI chạy được (OpenRouter)

`manage.py ai check` sau vá: **`[OK] openrouter … nvidia/nemotron-3-super-120b-a12b:free -> OK`**.
Key OpenRouter nằm trong bảng `runtime_settings` (Owner lưu qua `/app/settings`), **không**
nằm trong `.env`. Suốt phiên tôi khuyên "phải có key Gemini mới viết được caption" — **sai**.
Gemini vẫn hỏng (key dạng `AQ.Ab…` không phải `AIza…`), nhưng chuỗi fallback dùng OpenRouter
và caption ra thật.

**Bản vá:** `ai_provider_ready(db)` và `manage.py ai check` nay **áp `apply_runtime_overrides_to_config(db)`
trước khi đọc key**. Trước đó cùng một hàm cho hai kết quả khác nhau tuỳ tiến trình gọi — web
(có áp override lúc khởi động) thấy key, CLI/script thì không.

### Tiến trình web không ghi log ứng dụng — đã vá

`manage.py serve` chỉ gọi `uvicorn.run(...)`, **không** gọi `setup_shared_logger("app")` như các
worker. Hệ quả: mọi việc nền chạy trong web (dán link, quét nguồn, viết caption) không để lại
dấu vết nào — `app.log` trống, stdout chỉ có access log. Chính vì mù log mà tôi chẩn đoán sai
"việc nền không chạy" trong khi thực ra nó đang chạy Whisper 120 giây; tôi chỉ chờ 16 giây.

### Proof caption đầu-cuối qua web thật

Bấm `POST /viral/68/caption` → log hiện đủ 3 bước (collage cache hit → Whisper `medium` 120,4 s
→ AI 41,9 s) → **135 giây** có caption thật trong DB:
*"Món crab cực sang lại bị comment 'looks like cat food'? Haha…"*. Đúng nội dung video.

Nợ ghi nhận: caption mất ~2 phút/video vì Whisper `medium` chạy CPU. Muốn nhanh thì đổi
`ai.whisper_model_size` sang `small`, hoặc bỏ transcript khi video ngắn — cần PLAN riêng.

Suite: Windows **486 passed**; Linux **469 passed / 17 skipped**; lint-imports 2 kept.


### ADR-021 — AI viết caption cho video READY (không cần tài khoản, không cần job)

Owner đăng tay: tải `_reup.mp4` rồi đăng. Thiếu đúng một mảnh là caption, vì AI viết caption
gắn vào `Job`, mà job chỉ sinh khi có tài khoản. `ContentOrchestrator.generate_caption()` nhận
**đường dẫn file** nên chạy thẳng trên material được.

| Việc | Proof |
|---|---|
| 4 cột `ai_caption` / `ai_hashtags` / `ai_caption_at` / `ai_caption_error` + migration `m1b8c9d0e1f2` | `alembic heads` = 1 head |
| `ai_provider_ready()` — kiểm **hình dạng key, không gọi mạng** | test chặn `socket.connect` chứng minh |
| `generate_caption_for_material(db, id, *, style=None)` | 24 test |
| Nút **Viết caption** / khối caption + chip hashtag + **Sao chép** + **Viết lại** / dòng lỗi + **Thử lại** | 22 test UI |
| **Chặn sớm khi thiếu key**: máy này key sai dạng (`AQ.Ab…`) → trả lỗi trong **0,044 s**, KHÔNG chạy Whisper | proof Postgres phần 1 |
| Đường có key (giả orchestrator) → lưu caption + hashtag, đọc lại từ DB đúng | proof phần 2, đã dọn về NULL |

### Hai test flaky lộ ra khi chạy full suite — đều là LỖI THẬT, đã vá

1. **Giờ hẹn fan-out không tăng dần** (`processor.py`). Mỗi Page tự bốc mốc nền riêng rồi mới
   cộng giãn cách ⇒ Page sau có thể hẹn **trước** Page trước, thậm chí **trùng đúng một giây** —
   hỏng đúng thứ giãn cách của ADR-020 sinh ra để tránh. Với ≥3 Page còn thêm lỗi
   `randint(1800,5400)×idx` không đơn điệu. Vá: mốc nền bốc **một lần** cho cả material, giãn
   cách **cộng dồn**. Test mới chốt bằng bất biến "mốc nền bốc đúng 1 lần" — đã chứng minh
   **đỏ trên code chưa vá** (`assert 4 == 1`), xanh sau vá.
2. **`test_viral_sources_ui`** dựng `SOURCES` ở cấp module nên `last_scanned_at` đông cứng từ
   lúc nạp file; suite chạy quá 60 s là nhãn đổi "5 phút trước" → "6 phút trước" (Linux 61 s đỏ,
   Windows 40 s xanh). Vá: làm mới mốc theo từng test.

Suite sau vá: Windows **486 passed** (chạy 2 lượt); Linux **469 passed / 17 skipped** trong
**64,9 s** — vượt mốc 60 s cũ mà vẫn xanh. lint-imports 2 kept.


### Done This Session

| # | Việc | Proof |
|---|---|---|
| 1 | 4 cột nullable trên `ViralMaterial`: `ai_caption`, `ai_hashtags` (JSON list), `ai_caption_at` (epoch), `ai_caption_error`; property `ai_hashtags_list` (JSON hỏng / không phải list ⇒ `[]`) | `tests/test_material_caption.py` (g) 5 tham số |
| 2 | Migration `m1b8c9d0e1f2` (`down_revision=l0a7b8c9d0e1`), `downgrade()` drop đúng 4 cột | `alembic upgrade head` trên Postgres thật; `alembic heads` = **1 head** (`m1b8c9d0e1f2`) |
| 3 | `ai_provider_ready() -> (bool, str)` trong `service.py` — chỉ soi hình dạng key/cờ, **không gọi mạng**: Gemini `AIza…` ⇒ OK; có giá trị nhưng sai dạng ⇒ nói rõ *"key thật bắt đầu bằng AIza…"*; OpenRouter key ⇒ OK; 9Router `enabled` (đọc thẳng `9router_config.json`, lặp guard `if/*` thiếu key) ⇒ OK; không gì ⇒ hướng dẫn `.env` + `manage.py ai check` | (a) 5 test + test chặn `socket.connect` |
| 4 | `ViralService.generate_caption_for_material(db, id, *, style=None)` — thứ tự chặn rẻ→đắt: material tồn tại → có `_reup` → có key AI → mới gọi `ContentOrchestrator`. Ghi `ai_caption_error` + `ai_caption_at` ở mọi nhánh lỗi, xoá lỗi khi thành công, **không bao giờ raise** (lỗi cắt 300 ký tự + `logger.exception`) | (b)–(h), 24 test xanh |
| 5 | Context bóc `[AI_GENERATE]` + mọi cụm `### … ###` (khớp cách `processor.py` làm sạch title) | (h) assert đúng chuỗi truyền vào orchestrator |

### PROOF trên Postgres thật (material #68 READY, đã dọn về NULL)

1. **Đường thật hiện tại** — key `.env` là `AQ.Ab…`: `generate_caption_for_material(db, 68)`
   trả `False` + *"Key Gemini sai dạng — key thật bắt đầu bằng AIza…"* trong **0,044 s**
   (Whisper một mình đã hàng chục giây ⇒ chứng minh chặn sớm thật); `ai_caption_error` +
   `ai_caption_at=1788860451` đã ghi vào DB.
2. **Đường có key** (giả `ai_provider_ready` + giả `generate_caption`): `True`, đọc lại DB ra
   `ai_caption` đủ câu, `ai_hashtags='["#tuida","#picnic","#dochoihe"]'`, `ai_caption_at` →
   2026-09-08 16:40:51, `ai_caption_error=None`.
3. **Dọn**: UPDATE 1 dòng về NULL; toàn bảng còn **0** dòng dính 4 cột mới; `viral_materials`
   vẫn `DRAFTED 11 / READY 10` — không đụng dữ liệu khác.

Test: `tests/test_material_caption.py` **24 passed**; subset `-k "viral or material or source"`
**199 passed**; lint-imports **2 kept**.

### Nợ / điểm chưa chắc

- `ai_provider_ready` chỉ đọc `app.config` (config.py đã gộp `GEMINI_API_KEY`/`GOOGLE_API_KEY`
  lúc import, `settings._push_config_value` ghi đè thẳng vào config). Ai `export` key **sau**
  khi process khởi động mà không qua `/app/settings` thì hàm này không thấy.
- Key `AIza…` đúng dạng **không** đảm bảo còn hạn/còn quota — đúng chủ ý (không gọi mạng);
  key hết hạn vẫn qua cửa này rồi mới hỏng ở tầng dưới và ghi vào `ai_caption_error`.
- `find_reup_path` có nhánh dò cuối đi qua `SessionLocal()` **toàn cục** (Postgres thật),
  không theo session truyền vào — test "không có file _reup" phải monkeypatch chính nó.
- `style` mặc định `"short"` vì **chưa có** `SettingSpec` `ai.caption_style`; muốn đổi mặc
  định phải thêm spec vào `app/core/settings.py`.
- Chưa chạy suite Linux cho phần này (chỉ Windows subset, theo yêu cầu không chạy full).

---

## Phiên 2026-09-08 — ADR-020 backend: một nguồn → nhiều Page (fan-out)

Phần backend của ADR-020 (UI do agent khác làm song song: `router.py`, `viral_sources.html`,
`app_viral.html`, `tests/test_source_fanout_ui.py` — phiên này KHÔNG đụng 4 file đó).

### Done This Session

| # | Việc | Proof |
|---|---|---|
| 1 | `ViralSource.target_pages` + `ViralMaterial.target_pages` (Text, JSON list) + `target_pages_list` (đọc `target_pages` → `[target_page]` → `[]`) và setter chuẩn hoá (strip/bỏ rỗng/bỏ trùng/giữ thứ tự, ghi luôn `target_page` = Page đầu) | `tests/test_source_fanout.py` (a) |
| 2 | Migration `l0a7b8c9d0e1` — 2 cột + **dựng lại 2 unique partial index** với `COALESCE(target_page,'')`, giữ nguyên mệnh đề WHERE (6 status) | `alembic upgrade head` trên Postgres thật, `alembic heads` = **1 head**; `indexdef` in ra đúng 2 index mới |
| 3 | Guard nới **đúng một nấc**: `assert_media_not_blocked(..., sibling_material_id=)` bỏ qua job cùng material ở CẢ hai phép dò; job upload tay (`viral_material_id IS NULL`) vẫn chặn (`OR viral_material_id IS NULL`) | (f) + `test_cross_account_media_guard.py` còn xanh |
| 4 | `add_source(..., target_pages=[...])`; `scan_source` chép danh sách sang material | (b) (c) |
| 5 | `processor.py`: vòng lặp tạo job theo Page, giãn giờ `random(1800,5400)×idx`, BOOST_CONTEXT tính **theo từng Page** (`_page_boost_context`), 1 Page hỏng chỉ bỏ Page đó, `notify_style_selection` cho từng job. **Không có `target_pages` ⇒ đường cũ y nguyên** (round-robin/keyword, 1 job) | (d) (e) (g) |

### Phần UI (agent song song) + kiểm chéo của coordinator

- Ô "Page đích" thành `<textarea name="target_pages">` mỗi dòng một Page, kèm cảnh báo đỏ
  *"Mỗi video sẽ đăng lên TẤT CẢ Page — nội dung trùng nhau, Facebook dễ đánh spam"*; cột bảng
  hiện `—` / tên Page rút gọn / chip **"2 Page"** + dấu `!` + tooltip liệt kê URL.
  `tests/test_source_fanout_ui.py` 15 test; test UI cũ **không phải sửa dòng nào**.
- Coordinator chạy **proof thứ hai, độc lập** (kênh khác, đường `download_and_queue` một
  material): cũng ra **2 job** cùng hash `7b9b570d`, khác Page, lệch **3021 s**; guard vẫn chặn
  material khác cùng hash; DB dọn về đúng trạng thái cũ.
- Suite: Windows **439 passed**; Linux container **422 passed / 17 skipped**; lint-imports 2 kept.

### Sự cố hạ tầng trong phiên — lần thứ 4

Docker Desktop **tự tắt** giữa lúc chạy proof (port 5434 refused, mất daemon). Bật lại Docker
→ container `unless-stopped` tự lên, dữ liệu nguyên vẹn, migration đã áp trước đó không hỏng.
Gốc đã biết từ khảo sát 07/09: Docker Desktop không chạy được trước khi đăng nhập Windows.
Hai mức xử lý, **chờ Owner quyết**: (a) bật "Start Docker Desktop when you sign in" — 2 phút;
(b) cài Postgres thẳng làm Windows Service `pg_ctl register -S auto` — bền hơn, cần ADR.

### PROOF trên Postgres thật (account giả tạm `PROOF-ADR020-TEMP`, đã dọn sạch)

Nguồn `tiktok.com/@tiktok` + 2 Page proof → `scan_source` 3,5 s → material #66 (2 Page) →
`process_all` 14,8 s → **2 Job**:

```
(id=485, page=…/proof_page_a, schedule_ts=1788860321, hash=88ab5826, viral_material_id=66)
(id=486, page=…/proof_page_b, schedule_ts=1788863202, hash=88ab5826, viral_material_id=66)
lệch giờ = 2881 s   |   mat.status = DRAFTED
```

Guard còn răng: material khác cùng hash → raise; thêm job thứ 2 **cùng Page** → DB từ chối
(`duplicate key … idx_jobs_viral_material_active`). Dọn xong: jobs vẫn `DONE 4 / DRAFT 7 /
FAILED 1 / PENDING 2`, materials `DRAFTED 11 / READY 9`, 2 nguồn cũ, 1 account cũ — **không để rác**
(xoá cả `viral_66_…_reup.mp4` và `thumbs/viral_66_reup.jpg`).

### Sự cố trong phiên

Docker Desktop tự tắt giữa phiên (port 5434 refused, `docker` CLI mất daemon) — **lần thứ 4**
kiểu này. Bật lại Docker Desktop → container `unless-stopped` tự lên, dữ liệu nguyên vẹn.

### Nợ / điểm chưa chắc

- Test fan-out chạy SQLite ⇒ **không** có 2 unique partial index của Postgres; tầng chặn cứng
  chỉ chứng minh được bằng proof trên DB thật (đã làm, xem trên).
- `downgrade()` chỉ chạy được sau khi xoá bớt job trùng Page (đã ghi cảnh báo + câu SQL kiểm tra
  trong migration).
- Guard vẫn chặn 2 material KHÁC nhau cùng hash — nếu Owner quét trùng 1 video từ 2 nguồn thì
  material thứ hai sẽ FAILED. Đúng ý ADR (chỉ nới cho fan-out), nhưng có thể lộ ra khi dùng thật.


## Phiên 2026-09-07 (b) — /design-sync: chuẩn bị bundle ToolsAuto Cave, CHỜ /design-login

Owner gọi `/design-sync` trong `design/toolsauto-cave`. DesignSync chưa được uỷ quyền
(cần Owner gõ `/design-login`), nên phiên này làm trọn phần local; upload để phiên sau.

### System State (design/toolsauto-cave)

- Thư viện là HTML + CSS tĩnh → đi đường **off-script** của skill: bộ sinh
  `.design-sync/build.mjs` → `ds-bundle/` (gitignored). `package-validate.mjs` (stage ở
  `.ds-sync/`, gitignored) **✓ bundle is complete**: 12/12 card render sạch, 3 @import
  resolve, anchor `_ds_sync.json` khớp bundle.
- **`components.css` mới**: tách class dùng chung (`.st-*`, `.pill-*`, `.pf-*`, `.src-*`,
  `.row-btn*`, `.icon-btn`, `.settings-*`, `.sec`/`.scard`, `.data-table`, `.toast`,
  `.busy-bar`, `.counts`/`.cnt-*`, `.shell`/`.page-head`, `.gemini`, `.health`) khỏi `<style>`
  từng card. Lý do: design agent chỉ nhận CSS đi qua `styles.css`; trước đó nó không thấy
  vốn class mà card minh hoạ. Đối chiếu pixel trước/sau: 5 card 0 px, 7 card < 1 % (khác
  biệt chủ ý khi hợp nhất: `.st` line-height 1.4, `.row-btn` 700 + min-width danger 88/job 44).
  Đổi tên markup: `.card`→`.scard` (forms), `.reset`→`.reset-link`, `.wrap`→`.data-table`,
  `.num/.txt/.sel-s/.ta/.key/.unit`→`.settings-*`.
- `.design-sync/` (commit): `config.json` (shape, componentNames ASCII, readmeHeader — CHƯA có
  `projectId`), `conventions.md` (header README cho design agent, mọi tên class/token đã grep
  đối chiếu với CSS build), `prompts/<Tên>.md` ×12, `NOTES.md` (re-sync + rủi ro), `build.mjs`.
- Render check cần `DS_CHROMIUM_PATH=%LOCALAPPDATA%\ms-playwright\chromium-1234\chrome-win64\chrome.exe`
  (Python Playwright của venv đòi headless-shell 1208 không có).

### Next Action (phiên sau, đúng thứ tự)

1. Owner gõ `/design-login` → `DesignSync(list_projects)` để chọn tên không trùng
   (đề xuất **"ToolsAuto Cave"**) → `create_project` → ghi `projectId` vào
   `.design-sync/config.json` NGAY → `list_files` (rỗng → đường incremental §3 base skill).
2. `finalize_plan` (localDir `./ds-bundle`, writes/deletes theo skill) → push: sentinel →
   base files (`_ds_bundle.js`, `styles.css`, `README.md`, `tokens/**`) + `components/**` →
   sentinel → `_ds_sync.json` cuối cùng → `list_files` xác nhận 31 file.
3. `report_validate` counts {total 12, bad 0, thin 0, variantsIdentical 0, iterations 1}.
4. Mời Owner mở project, soi DS pane; sửa card → `node .design-sync/build.mjs` → validate → re-upload.

---

## Phiên 2026-09-07 — Vá 2 lỗ hổng luồng code; hạ 2 mục "A" trong bảng thực lực

Owner hỏi "báo cáo dự án" → "luồng code như nào" → "triển khai vá theo thứ tự".
Đọc code thật thay vì kể lại handoff; tìm ra 3 việc, làm 2, việc 3 chỉ soạn PLAN.

### System State (2026-09-07)

- Postgres **đã bật lại** (`docker compose up -d`, healthy). Bị dừng tay 05/09 21:25,
  `unless-stopped` giữ nguyên trạng thái dừng — chính sách chạy đúng, không phải lỗi.
- Ổ `G:` (Drive) **vẫn chưa có** → backup ngoại vi 0 bản. Backup local: 3 file, đều 05/09.
- Ổ `C:` còn **8,1 GB** (giảm từ 8,6).
- DB: jobs `DRAFT`=7, `DONE`=4, `PENDING`=2, `FAILED`=1; `viral_materials` `DRAFTED`=11.
  **0 `AWAITING_STYLE`** — lỗ hổng (1) bên dưới chưa gây hậu quả vì xưởng chưa nhận
  material mới từ khi về local.
- Windows **278 passed**; Linux container `python:3.12-slim` **261 passed, 17 skipped**;
  import-linter 2 kept / 0 broken.

### Done This Session

| # | Việc | Proof |
|---|---|---|
| 1 | **ADR-013** — `ai_generator` vào stack local. `build_apps()` nay trả `['web','maintenance','fb_publisher','ai_generator']`. Thêm handler `SIGBREAK` cho worker (trước giờ chưa từng chạy dưới supervisor nên thiếu) | `tests/test_local_supervisor.py` 15 passed. Chạy thật `-m ai_generator` 10s rồi gửi `CTRL_BREAK_EVENT`: log "Received termination signal… Waiting for AI Job 9" — đường thoát êm hoạt động |
| 2 | Nút **Xử lý / Thử lại / Xử lý mới** ở `/app/viral` chuyển sang `BackgroundTasks`. Validate (tồn tại / PROCESSING / status / ffmpeg) vẫn đồng bộ → toast lỗi ngay; tải + ffmpeg xuống nền với `SessionLocal()` riêng. Tách `ViralService.check_processable()` để hai đường dùng chung 4 chuỗi lỗi. Trang bật polling 10s **chỉ sau khi** server bắn `viralBackgroundStarted`, tự tắt khi hết PROCESSING hoặc 30 phút | `tests/test_viral_router_background.py` 18 passed (mới). Full suite 278 |
| 3 | **PLAN-059** tách `facebook/adapter.py` — chỉ ĐỀ XUẤT, không execute | `agents/plans/active/PLAN-059-split-facebook-adapter.md` |
| 4 | Hạ **AI viết caption A→C**, **Telegram A→C** trong `docs/sales/00` | xem phát hiện bên dưới |
| 5 | Bổ sung handoff thiếu commit `7d27fff` của phiên trước | mục riêng bên dưới |

### Phát hiện quan trọng nhất phiên: chuỗi AI caption CHƯA TỪNG chạy được ở máy này

Khi chạy thử `ai_generator` 10 giây, nó nhặt job 9 ngay lập tức và toàn bộ chuỗi đổ:
- **Gemini 401 UNAUTHENTICATED** — `.env` chỉ có `GOOGLE_API_KEY` dài 53 ký tự, đầu
  `AQ.Ab…` — **không phải API key** (key thật dạng `AIza…`, 39 ký tự). Có vẻ là
  access token/cookie dán nhầm. `GEMINI_API_KEY` không có.
- 9Router tắt (`router_disabled`), thiếu `faster_whisper`, `OPENROUTER_API_KEY` không có.
- Telegram **404** — `.env` không có `TELEGRAM_BOT_TOKEN`/`CHAT_ID`.

Và bằng chứng trong DB: **cả 7 job `DRAFT` còn nguyên placeholder `[AI_GENERATE] …`**
— chưa job nào từng được AI viết caption. Bảng thực lực ghi "AI caption — A — 7 job
`DRAFT [AI_GENERATE]`" là lấy bằng chứng *đang chờ AI* làm bằng chứng *AI đã chạy*.
Trong 4 job `DONE`, chỉ job 7 (07/2026, VPS) có caption giống AI viết.

Job 9 bị tôi kill giữa chừng → kẹt `AI_PROCESSING`, đã trả về `DRAFT` bằng đúng câu
`UPDATE` mà `run_loop` dùng lúc khởi động. Không tốn tiền: không có key OpenRouter.

### Bổ sung phiên 2026-09-05 (e) — commit `7d27fff` chưa được ghi

1. Nhãn kéo-thả hứa `.webp` mà `accept` và `IMAGE_EXTENSIONS` đều không có → sửa
   **chữ cho khớp code**, không thêm `.webp`. Test riêng canh 5 định dạng.
2. `import-linter` vào CI: thực tế **0/2 contract đạt** (audit ghi "2 vi phạm"). Hợp
   thức `dispatcher → features` theo ADR-008; còn **2 nợ thật** ghi tên trong
   `.importlinter`. CI có bước "Check module boundaries".
3. Archive PLAN-046/057/058.

### Escalation — 3 lỗi ngầm trong adapter (TASK-059)

Agent đọc `adapter.py` tìm ra 3 `NameError`/`UnboundLocalError` bị `except Exception`
nuốt: `SessionLocal` chưa import (695), `al_lower` chưa gán (2500), `search_terms`
có thể chưa gán (463). Đường chuyển Page qua aria-label **chưa bao giờ khớp**, sống
nhờ fallback. Backend, ngoài vai — ghi `TASK-059`, KHÔNG sửa, cần account để chứng minh.

### Nợ mới ghi nhận

- Toast kết quả cuối (✅ tạo job #N / ❌ lỗi) không còn về tới người dùng sau khi
  chuyển nền — chỉ thấy qua trạng thái bảng + tooltip `last_error`. Muốn có lại cần SSE.
- Race validate→claim giữa nút bấm và `maintenance` là **lỗi có sẵn** (không atomic);
  hậu quả chỉ là toast "Đã nhận" rồi worker làm thay. Muốn atomic phải sửa processor.
- Polling có thể tắt sớm giữa hai video của một lô (khoảng trống PROCESSING rất ngắn).

### Khảo sát tích hợp miễn phí — `docs/research/2026-09-07-tich-hop-mien-phi.md`

Owner yêu cầu "lùng trên mạng xem có gì hay ho mà free". 5 agent, 5 hướng, mọi mục
mở trang gốc + ghi ngày kiểm. Xếp hạng theo *vá đúng chỗ đang hỏng ÷ công sức*:

1. Key Gemini `AIza…` + **Groq** dự phòng qua 3 biến `.env` (không sửa code) — 15 phút
2. **Xoá P0-2** thay vì sửa: đếm click bằng **Sub ID** Shopee Affiliate / `sub1` AccessTrade — 0 code
3. **healthchecks.io** (20 check free, kênh Telegram/ntfy) — 1 dòng ping cuối backup + mỗi vòng worker
4. **Tailscale serve** — dashboard trên điện thoại, không mở port
5. **Meta Graph API** đăng Page: cá nhân có role trên app **không cần App Review/Business
   Verification**; Reels/feed/story/comment+ảnh/lên lịch đều có endpoint. Playwright + cookie
   là *chính xác hành vi Meta cấm* trong Account Integrity. Bẫy: app Dev mode thì bài
   **công chúng không thấy**, phải Live mode → **spike bằng curl trước** (checklist 6 bước
   trong doc), đạt mới viết PLAN.
6. Phụ đề đốt `faster-whisper → pysubs2 → ffmpeg` (thư viện đã trong requirements — chỉ
   `faster-whisper` **chưa cài** trong venv); nhạc nền **Meta Sound Collection**; rclone
   thay Drive for Desktop; Postgres cài thẳng (Docker Desktop không sống trước logon).

Code lệch thực tế phát hiện thêm: `native_fallback.py:22-35` liệt kê `gemini-2.0-flash`
**đã bị Google shut down** — backend, cần vào PLAN.

Loại bỏ có lý do: Bitly Free (không click), ElevenLabs Free (không thương mại), F5-TTS VI
(NC), stable-ts (archive), GitHub Models (đóng), scraping TikTok/Shopee (ToS).

### Triển khai theo thứ tự khảo sát — mục 1→5 (Owner: "triển khai theo thứ tự từng mục")

| # | Việc | Tôi đã làm | Còn lại Owner |
|---|---|---|---|
| 1 | AI caption | **ADR-014**: bỏ `gemini-2.0-*` đã shut down khỏi `native_fallback.py`/`pipeline.py`; lệnh **`manage.py ai check`** (chạy thật: 401 + cảnh báo key không phải `AIza…` — đúng kỳ vọng); `.env.example` mẫu Groq qua `OPENROUTER_*`; **cài `faster-whisper 1.2.1`** vào venv | Lấy key Gemini `AIza…` (+ Groq `gsk_…`), dán `.env`, chạy `ai check` tới khi `[OK]` |
| 2 | Đếm click | **ADR-015** gỡ P0-2 theo phương án C+: `attach_affiliate_to_job` + comment người dùng gõ + `story_overlay_text` dùng **URL affiliate gốc**; xoá route `/r/{code}`, `track_redirect_click`, `_register_vercel_tracking` + 2 call site; UI bỏ tự điền `{tracking_url}`; **giữ cột** (`tracking_code` = Sub ID gợi ý). Trước đó link hỏng **đang được chèn thật** vào comment/Story — DB: 0 click, 0 comment nhiễm | Đặt Sub ID trong chính URL affiliate khi lưu link (Shopee `sub_id`, AccessTrade `sub1`) |
| 3 | Chết không ai biết | `app/core/observability/heartbeat.py` — ping healthchecks.io cuối `db backup` (+`/fail` ở 4 nhánh lỗi), mỗi vòng `maintenance`, mỗi vòng `fb_publisher` (kể cả PAUSED; `/fail` khi account bị vô hiệu). Không URL → im lặng, lỗi mạng chỉ warning. 3 ô ở `/app/settings` nhóm **"Giam sat"** | Tạo 3 check trên healthchecks.io, dán URL |
| 4 | Dashboard từ điện thoại | Runbook | Cài Tailscale, `tailscale serve --bg 8002` |
| 5 | Graph API | **`scripts/graph_api_spike.py`** 8 subcommand (whoami/pages/exchange/post-feed/post-photo/post-reel/comment/verify-public), `--dry-run`, token lưu `storage/db/config/graph_api_tokens.json` | Chạy 6 bước theo runbook, ghi bảng kết quả; **đạt bước 5 mới báo Anti viết PLAN** |

Runbook từng bước copy-paste: **`docs/ops/2026-09-07-runbook-tich-hop.md`**.
Mục 6–10 (phụ đề đốt, nhạc nền, rclone, Postgres service, TTS) **chờ PLAN từ Anti**.

Test: Windows **285 passed**; Linux **268 passed / 17 skipped**; lint-imports 2 kept.

Nợ ghi nhận: `health.py total_clicks` và `daily_summary_message` "0 clicks" còn nguyên (nhiễu nhỏ);
`models/jobs.py:61` comment `/r/{code}` cũ; `ai check` không ép timeout 20s (đi qua client thật
để giữ ADR-006); ping `/fail` của backup không đi được khi Postgres chết (URL đọc từ DB —
dead man's switch vẫn báo quá hạn).

### Mục 6 / 10 / 7 — ba lớp thêm cho video reup (ADR-016), mặc định TẮT

| Lớp | Module | Proof trên `viral_1_tikwm_reup.mp4` (73 s, 1080×1920) |
|---|---|---|
| Phụ đề đốt | `subtitle_layer.py` — faster-whisper (`language=vi`, word_timestamps, VAD) → pysubs2 ASS kiểu CapCut → `ffmpeg ass=…:fontsdir=`; font **Be Vietnam Pro** (OFL) commit trong `app/static/fonts/` | model `medium`: 28 segment, whisper ~110 s + burn 10,9 s; frame giữa xem bằng mắt: chữ trắng đậm viền đen, đáy giữa, dấu đúng; libass chọn đúng `BeVietnamPro-Bold` |
| Voice-over | `audio_layer.synthesize_voice` — edge-tts `vi-VN-HoaiMyNeural`/`NamMinhNeural`, dự phòng **piper** offline (`vi_VN-vais1000-medium` trong `storage/media/tts_models/`, gitignored) | edge 2,3 s → 4,9 s audio; piper chạy được (đọc nhanh, chưa nghe thử) |
| Nhạc nền | `audio_layer.mix_music` — `amix normalize=0`, lặp nhạc, fade cuối; chọn ngẫu nhiên từ `storage/media/music/` | voice + nhạc giả 20 s trộn vào 73 s video mất 3,0 s (`-c:v copy`), thời lượng khớp |

Điểm nối duy nhất `ReupProcessor._apply_post_layers()` sau intro/outro/hook; mỗi lớp đi
qua `_promote_temp` (quality gate); lớp lỗi → giữ video bước trước, `success` vẫn True.
Voice-over **đọc hook text** (caption AI chưa có lúc reup). 10 ô ở `/app/settings`
nhóm **"Reup - lop them"**. Enum Whisper thêm `large-v3-turbo` + `erax-ai/EraX-WoW-Turbo-V1.1-CT2`.

Nợ: `medium` sai vài từ ("mặt nạ xích") — đổi setting sang EraX là xong, chưa thử;
mỗi lớp một lần re-encode; piper chưa nghe; **nhạc chưa có** (Meta Sound Collection
cần đăng nhập FB); font trên Linux (fontconfig) chưa kiểm dù suite Linux xanh.
Gạch: yt-dlp format không cần — 11 material đều qua TikWM `play` (không watermark).

Test: Windows **311**; Linux **294 / 17 skipped**; lint 2 kept.

### ADR-017 + ADR-018 — dán link đa nền tảng; xưởng chạy KHÔNG cần account

**Đính chính:** đầu phiên tôi nói "xưởng nội dung ✅ chạy" — **sai**. `processor.py:463`
return sớm khi không có account Facebook ACTIVE ⇒ từ khi account bị khoá (05/09), **không
material nào được xử lý**. Và **không có ô dán link nào** — chỗ duy nhất tạo material là
quét kênh TikTok; 11 material đều một kênh `@rinabeauty859`.

| Việc | Proof |
|---|---|
| `intake.detect_platform` + `normalize_source_url` (TikTok/YouTube/FB/IG, bỏ tracking query, so trùng cả biến thể `www.`) | 12+ URL test |
| `POST /viral/add-link` + ô dán link trên `/app/viral`, checkbox "Xử lý ngay" → nền | TestClient |
| yt-dlp `2026.3.3` → **`2026.8.19`**; thử tải thật **4 nền tảng, không cookie, đúng cờ tool**: YouTube Shorts 1080×1920 .webm/vp9, TikTok kênh khác 720×1280 không watermark, FB Reel 720×1280, IG Reel 1080×1920 — **cả 4 tải được** | log scratch |
| `ViralStatus.READY` — không account → vẫn tải + reup, bỏ tạo Job, `READY`; UI badge teal + nút **Tải file** (`reup-preview` + `download`) + Thumbnail; `check_processable` từ chối READY; banner đếm | `tests/test_viral_ready_without_account.py` 7 test |
| **Proof đầu-cuối Postgres thật**: dán `facebook.com/reel/325542560591184` → #57 → tải 3,1 s → reup 5,9 s → `READY`, `viral_57_…_reup.mp4` 1080×1920 h264 16 MB, thumbnail, `GET /viral/57/reup-preview` 200 — **11,9 s tổng**. Material #57 giữ lại cho Owner | |

Nợ: material dán tay (`scraped_by_account_id=None`) **sweep nền không nhặt** — chỉ xử lý
qua nút "Xử lý ngay"/Process; READY → Job khi có account là PLAN sau; YouTube ra `.webm`
chưa qua pipeline trong tool; `--js-runtimes node` cho YouTube (yt-dlp cảnh báo extraction
không JS runtime sắp bỏ) cần Anti quyết vì Linux phải có node ≥22; "Tải file" **đã kiểm bằng Chrome thật 08/09**:
tải về `viral_68_reup.mp4` 20 MB, đúng tên (thuộc tính `download` ép tải dù endpoint trả
`inline` — cùng origin nên trình duyệt tôn trọng).

### ADR-019 — bảng Nguồn tách khỏi account; quét tự động TikTok + YouTube Shorts

Phát hiện: quét TikTok cũ đọc `Account.competitor_urls` của account **active** ⇒ cũng đã
chết theo account. Kiểm yt-dlp `--flat-playlist` không cookie: TikTok ✅, YouTube `/shorts` ✅
(có `view_count`), Facebook Page ❌ Unsupported, Instagram profile ❌ cần đăng nhập.

| Việc | Proof |
|---|---|
| Bảng `viral_sources` (migration `k9f6a7b8c9d0`, 1 head), `SourceService` (list/add/set_enabled/delete/scan_source/scan_all), hook `viral.scan_sources` trong `maintenance`, setting `viral.source_scan_interval_min` (60) | 27 test |
| Sweep gom thêm `NEW` có `scraped_by_account_id IS NULL` (14 dòng) — chạy cả khi 0 account → READY | test + proof |
| UI khối "Nguồn tự động" trên `/app/viral`: thêm/bật-tắt/xoá/quét từng nguồn/quét tất cả (nền), bảng trạng thái; 6 endpoint `/viral/sources…` | 20 test |
| **Proof Postgres thật, 0 account**: thêm `youtube.com/@albert_cancook` (≥1M view, max 5) + `tiktok.com/@mrwork93` → `scan_all` 13 s tìm 8 → sweep 76 s → **8/8 READY**, ffprobe 8 file h264 1080×1920; quét lại dedup 0. YouTube nguồn av01+opus `.webm` → reup ra mp4 OK (lần đầu) | material #58–#65 giữ lại |

Bug bắt trong proof: TikTok trả `uploader_id` số → URL `@7628…/video/…` lệch dạng scan cũ;
sửa ưu tiên `uploader` → `source.handle`, UPDATE 4 dòng, thêm test.

Test: Windows xem dưới; lint 2 kept. Nợ: `competitor_urls` cũ chưa di trú sang bảng Nguồn;
`sources.subprocess` và `processor.subprocess` cùng module nên test sweep phải seed trực tiếp.

### Rate limit hai tầng (bài Jack Nguyễn) → `docs/notes/2026-09-07-rate-limit-hai-tang.md`

Đối chiếu với doc Meta: đúng (BUC theo Page = 4800 × engaged users / 24h; Platform theo via).
Tách bạch: mất tài khoản 31/07 là Account Integrity, không phải rate limit. Áp vào tool:
`POSTS_PER_PAGE_PER_DAY` mặc định 0 → **2**; `Account.cooldown_seconds` mặc định 1800 →
**14400** (4 giờ); đã ghi cả hai vào DB thật; spike script poll Reel 10 s → **30 s** (Page
mới mỗi lời gọi đều đếm); runbook 5.6 + TASK-058 ghi "2 bài cách nhau ≥ 4 giờ".

### Tái cấu trúc UI/UX bằng Claude Design — vòng 3 bước (đã dựng bước 1, chờ đăng nhập)

Owner mở app Claude Design hỏi cách dùng. Chốt vòng: (1) đẩy theme Cave lên Claude Design
làm *design system* "ToolsAuto Cave" bằng tool **DesignSync** → mockup đúng màu/nút/font;
(2) Owner mockup từng màn hình theo brief; (3) Claude Code chuyển HTML xuất ra sang
Jinja/HTMX, một màn hình một PLAN, chụp Playwright so mockup.

| Đã có | Ở đâu |
|---|---|
| Thư viện component tự chứa: `tokens.css` + 12 card (Foundations 3 / Components 7 / Patterns 2), marker `@dsCard`, kiểm Playwright 0 lỗi | `design/toolsauto-cave/` (ảnh `_preview/` gitignored) |
| Brief màn hình #1 "Xưởng nội dung" + 3 ảnh hiện trạng | `docs/design/brief-01-xuong-noi-dung.md`, `docs/design/2026-09-07-*.png` |

**Chặn:** DesignSync cần `/design-login` một lần trong phiên tương tác — Owner chưa chạy.
Sau đó: `list_projects` → `create_project("ToolsAuto Cave")` → `finalize_plan` (localDir
`design/toolsauto-cave`) → `write_files` 14 file.

Lỗi UI thật lộ ra khi trích theme (ghi nợ, chưa sửa): nút torch ở trang viral
(`Quét ngay`, `Xử lý 1/3`, `Thêm`) bị `body.theme-cave .app-btn` đè specificity → hiện
xám; `showToast` gộp warning vào nhánh error; vài pill settings còn Tailwind sáng chưa bridge.
Đã vá trong phiên: `htmx.ajax` không `source` làm body kẹt `htmx-request` (indicator hiện
mãi — lỗi có sẵn), "Unknown" → "—", 33 chuỗi settings có dấu.

### Next Action

1. **Owner: đặt `GEMINI_API_KEY` thật (dạng `AIza…`) vào `.env`** — không có thì
   `ai_generator` chạy cũng vô ích. Xoá `GOOGLE_API_KEY` sai loại.
2. Owner: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` nếu muốn thông báo.
3. Owner: bật `start.ps1 -Stack` → xem `ai_generator` trong statuses → ADR-013 hết hiệu lực.
   Sau đó ≥1 job `DRAFT` có caption thật ⇒ nâng AI caption C→A.
4. Các việc cũ vẫn nguyên: Drive (stream, không mirror), đổi mật khẩu FB/IG/TikTok,
   dựng BM theo `02`, TASK-057, dọn ổ `C:`.
5. Anti: quyết PLAN-059 (chờ account) và TASK-059.
6. **Owner: spike Graph API 2 giờ** theo `docs/ops/2026-09-07-runbook-tich-hop.md` mục 5 (script `scripts/graph_api_spike.py`) — đây là thứ
   duy nhất có thể đưa tự động đăng quay lại mà không lặp lại 31/07.
7. **Owner: mở `/app/viral` → "Nguồn tự động" → thêm kênh của anh** (TikTok/YouTube brand hoặc seller), để `maintenance` tự quét mỗi giờ; 2 kênh proof (`@albert_cancook`, `@mrwork93`) là mẫu — xoá nếu không dùng.
8. Owner: bật thử `reup.subtitle_enabled` trên 1 video, xem có ưng kiểu chữ không; đổi Whisper sang EraX nếu sai nhiều.
9. Owner: healthchecks.io (3 check → dán `/app/settings`) + Tailscale — runbook mục 3, 4. `faster-whisper` đã cài.

---

## Phiên 2026-09-05 (e) — Sao lưu ngoại vi sang Google Drive (ADR-012)

### Đã xong, đã push — `fdb58bb`

Owner có Drive **5 TB** (dùng 24,6 GB), Drive for Desktop **đã cài nhưng chưa đăng
nhập** (chưa gắn ổ nào).

**Đóng lỗ hổng lớn nhất còn lại:** backup đang nằm **cùng ổ đĩa với dữ liệu** — hỏng
ổ `D:` là mất cả hai, đúng thứ backup sinh ra để chống.

Hai quyết định giúp việc nhỏ đi nhiều:
- **Không dùng Drive API/OAuth.** Drive for Desktop gắn ổ như thư mục thường ⇒ chỉ
  thao tác file. Không phải giữ khoá bí mật nào.
- **Không phải viết UI.** Trang `/app/settings` tự sinh giao diện từ `SETTINGS` theo
  `section`, đã có sẵn lưu hàng loạt ⇒ chỉ khai báo 4 `SettingSpec`.

Ba nguyên tắc, ghi trong docstring `app/core/storage/offsite.py`:
1. **Sao chép, không di chuyển** — bản chính luôn ở máy
2. **Drive lỗi không làm hỏng việc chính** — chưa gắn ổ / hết dung lượng chỉ ghi log
3. **TUYỆT ĐỐI không chép DB đang chạy hay profile trình duyệt** — Drive đồng bộ liên
   tục, hai thứ đó ghi liên tục ⇒ hỏng dữ liệu âm thầm; profile hỏng là mất phiên

Thêm `manage.py db drive-check`, sai đường dẫn thoát mã 1.

### Hai lỗi TỰ GÂY trong lúc làm — đều đã vá

1. **`.gitignore` nuốt mất module.** Dòng `storage/` không neo gốc nên chặn **mọi**
   thư mục tên `storage` ở mọi độ sâu. Commit `eeb75e3` đẩy lên **thiếu hẳn**
   `app/core/storage/` trong khi `manage.py` import nó ⇒ **CI đỏ**. Đổi thành
   `/storage/`, commit `fdb58bb` ⇒ **CI xanh**. Đã kiểm bằng clone sạch: 39 passed.
2. **Tiếng Việt làm chết lệnh trên Windows.** Console cp1252 ⇒ `typer.echo` tiếng
   Việt ném `UnicodeEncodeError`. Lỗi này **đã có sẵn từ trước** — thông báo lỗi
   `pg_dump` cũng tiếng Việt, tức backup thất bại thật thì Owner nhận traceback thay
   vì thông báo. `manage.py` nay ép stdout/stderr UTF-8 ⇒ vá luôn cái cũ.

### Trạng thái
- Windows **258 passed**; Linux container 39 passed; **CI xanh**
- Working tree sạch, `main` == `origin/main`
- Tính năng ở **mức B**: mới test bằng thư mục giả lập, **chưa chạy với Drive thật**

### Nợ mới tạo ra (ghi để không quên)
- Chưa dọn bản cũ bên Drive (local giữ 14 bản, Drive tích luỹ mãi)
- **Chưa cảnh báo khi Drive im lặng hỏng** — quên đăng nhập Drive thì backup vẫn báo
  thành công (đúng thiết kế) nhưng bản ngoại vi không có; chỉ phát hiện lúc cần khôi
  phục, tức muộn nhất. Đáng làm tiếp: kiểm hằng tuần + báo Telegram

### Next Action — khi Owner về nhà, dùng laptop

1. **Mở Google Drive for Desktop, đăng nhập** → có ổ (thường `G:`).
   ⚠️ Chọn chế độ **truyền phát (stream)**, KHÔNG chọn **sao chép (mirror)** — ổ `C:`
   chỉ còn **8,6 GB trống**, mirror sẽ làm đầy ổ hệ thống.
2. Tạo `G:\My Drive\ToolsAuto` → chạy `python manage.py db drive-check`
3. Vào `/app/settings`, nhóm **"Sao luu Google Drive"**: bật + dán đường dẫn + lưu
4. **Dựng 2 Page theo TASK-058**, thêm quản trị viên thứ hai **trước** khi đăng bài đầu
5. Chạy `TASK-057` (30 phút) để nâng 5 luồng từ mức B lên A

### Việc riêng, không liên quan Drive
**Ổ `C:` chỉ còn 8,6 GB trống.** Windows dưới 10 GB bắt đầu sinh lỗi lạ. Nên dọn sớm,
độc lập với mọi việc khác.

---

## Phiên 2026-09-05 (d) — Tài khoản Facebook chết; xoay lại chiến lược

### ⛔ Sự kiện lớn nhất: Owner mất tài khoản Facebook VĨNH VIỄN

- Bài cuối đăng được: **2026-07-31 09:03 UTC**. Từ đó im lặng hoàn toàn.
- Tổng đời tool: **4 bài** (3 POST + 1 COMMENT), trên **1 account**.
- **Mất theo 3 Page**: Mẹ Sún Riviu, Da Đẹp Lì Tu (`kids0810`), Chàng nông dân.
  Kiểm ở cửa sổ ẩn danh: không xem được.
- Nguyên nhân **chưa chứng minh được**, giả thuyết mạnh nhất: cookie phiên bị commit
  công khai lên GitHub 25/04, phơi ~3,5 tháng; account tên "FB Cookie Import"; chết
  đúng trong khoảng đó.

### Lỗ hổng lộ ra: tool KHÔNG BIẾT account chết

`login_status` vẫn `ACTIVE`, `login_error` rỗng, `last_login_check` **chưa từng chạy**.
Owner mất **5 tuần** mới biết, và chỉ vì Claude hỏi. Bật stack lên là tool sẽ mở
browser đăng nhập lại vào tài khoản bị khoá — làm tình hình nặng thêm.

**Đã xử lý ngay** (có backup trước, `toolsauto_db_20260905_172038.sql`):
`accounts.id=2` → `is_active=false`, `login_status='INVALID'`, ghi `login_error`.
Xác minh: **0 job claim được**. Không xoá gì, cả 14 job còn nguyên.
Hoàn tác: `UPDATE accounts SET is_active=true, login_status='ACTIVE', login_error=NULL WHERE id=2`

### Xoay chiến lược — Owner chốt hướng C (nghĩ lại cách tiếp cận)

Con số ép phải xoay: phần **không đụng Facebook** (xưởng nội dung) chạy sạch
**11/11, 0 lỗi**. Phần **đụng Facebook** (tự động đăng) chạy 3 ngày rồi mất tài sản.
Tự động đăng tiết kiệm ~6 phút/ngày; xưởng nội dung tiết kiệm 20–30 phút/video.

**Hướng đã chốt:**
1. Cấu trúc trước (Business Manager, ≥2 admin, tài khoản chạy tool chỉ Biên tập viên)
2. Dùng tool cho xưởng nội dung, **đăng tay**
3. Quay lại tự động đăng sau, khi Page đã an toàn trong BM

### Đính chính: tool CHƯA có khách nào

Claude suy sai từ "combo Page Master" / "trước khi bán tiếp" trong handoff, kết luận
đang có khách chịu rủi ro. Owner xác nhận **chỉ mình Owner dùng**. Handoff ghi *ý
định*, không phải *thực tế* — bài học: hỏi câu một nghĩa.

May mắn thật sự: sai lầm cấu trúc này trả bằng tài sản của Owner, **không phải của
khách**.

### Tài liệu mới — `docs/sales/`

| File | Dùng để |
|---|---|
| `00-doi-chieu-thuc-luc.md` | Mỗi lời quảng cáo truy về một bằng chứng. 4 mức A/B/C/D. **Luật: B chỉ lên A khi đã chạy thật, test xanh KHÔNG đủ** |
| `01-mo-ta-combo-da-sua.md` | Gỡ "giỏ hàng" (0 dòng code) + "link aff đếm click" (P0-2 hỏng); siết "tìm theo từ khoá" về TikTok; bỏ Douyin |
| `02-checklist-thiet-lap-an-toan.md` | **Owner làm cho chính mình trước** khi dựng lại Page |
| `03-kich-ban-nhan-khach-cu.md` | ⏸ CHƯA DÙNG TỚI — soạn sẵn cho khi có khách đầu tiên |

`TASK-057` — runbook 30 phút chạy thật 5 luồng mức B, có bảng ghi kết quả.

### Next Action

1. **Owner: dựng cấu trúc theo `02`** — BM, Page trong BM, ≥2 admin, tài khoản chạy
   tool chỉ Biên tập viên. 15 phút, miễn phí, chặn đúng lỗi đã mất 3 Page.
2. **Owner: chạy TASK-057** — 30 phút, nâng 5 mục B→A, biết chắc cái nào còn chạy.
3. Dùng tool cho xưởng nội dung, đăng tay.
4. Sau đó mới tính: phát hiện khoá tài khoản (backend, cần ADR), P0-2 affiliate,
   thêm nguồn video.

### KHÔNG còn là ưu tiên

- ~~Sửa `VPS_SSH_KEY`~~ — Owner ngừng VPS, chạy local
- ~~Thêm nguồn video~~ — chưa có Page thì thêm nguồn chỉ tăng hàng tồn
- ~~Nhắn khách~~ — chưa có khách

---

## Phiên 2026-09-05 (c) — PLAN-058: vá P0-1 concurrency (Việc 2)

Owner duyệt **ADR-011** 2026-09-05, siết phạm vi còn **P0-1** (bỏ TEST C/P0-2).

### Ba bất biến đã đóng, mỗi cái một bản vá

| | Bản vá | Proof |
|---|---|---|
| **A** 1 job → 1 worker | `AND status='PENDING'` ở qual NGOÀI (`queue.py`) | code cũ: *"worker thua vẫn claim được job 250 đang RUNNING"* → sau vá: xanh |
| **B** 1 (account,platform) → ≤1 RUNNING | migration `j8e5f6a7b8c9` partial unique index + bắt `IntegrityError` | sau vá A, chưa index: *"2 job cùng RUNNING"* — **đỏ đúng như AUDIT-001 dự đoán** → sau index: xanh |
| **C** không cướp job đang chạy | `WORKER_CRASH_THRESHOLD_SECONDS` 120 → **1200** | `WORKER_CRASH_THRESHOLD_SECONDS=120 pytest` → 2 failed (chốt bắt được hồi quy) |

Index trên DB thật:
`CREATE UNIQUE INDEX uq_jobs_one_running_per_account_platform ON public.jobs
(account_id, platform) WHERE status = 'RUNNING'`

Suite: Windows **248 passed**; Linux container **49 passed, 2 skipped**.
CI run `33940883613`: job `test` **success**.

### Bài học: test race đầu tiên XANH GIẢ

Bản đầu dùng `threading.Barrier` cho 2 session và **xanh trên code chưa vá** — cửa
sổ race chỉ vài trăm micro-giây, `SessionLocal()` kết nối lười nên sau barrier vẫn
lệch vài ms. Nếu tin nó thì đã tuyên bố "đã vá" trong khi chưa chứng minh gì.

Đã đổi sang dựng **tất định** đúng trạng thái race tạo ra: T1 `UPDATE → RUNNING`
chưa commit, T2 chạy `claim_next_job` rồi chặn ở khoá dòng (A) hoặc khoá index (B),
T1 commit. Không phụ thuộc lịch OS.

**Lệch có chủ ý so với §19**: TEST B đặt `schedule_ts` **lệch** thay vì bằng nhau.
Hoà khoá sắp xếp thì claim chọn dòng nào là không xác định ⇒ test chập chờn.

### ⚠️ Hạn chế — P0-1 CHƯA được bảo vệ trên CI

TEST A/B mang `pytest.mark.integration`, tự skip khi không có Postgres. Runner
GitHub Actions **không có Postgres** ⇒ trên CI chúng **luôn skip**. Bất biến chỉ được
kiểm khi chạy tay trên máy có DB.

Cách đóng: thêm `services: postgres:16` vào job `test` trong `deploy.yml`. Đó là
`deploy.yml`, **ngoài phạm vi ADR-011** nên chưa làm — cần Owner cho phép.

### Next Action

1. **Owner: sửa `VPS_SSH_KEY`** — vẫn là thứ duy nhất chặn deploy (5 tuần).
2. **Owner: cho phép thêm `services: postgres` vào CI** để TEST A/B thật sự chạy.
3. **Owner: đổi mật khẩu + đăng xuất phiên FB/IG/TikTok** — nợ từ PLAN-051, chưa làm.
4. P0-2 affiliate + TEST C — đã tách khỏi ADR-011, cần quyết riêng.
5. Xoá `toolsauto_postgres_old_20260905` + volume `9a3acb1502…` sau vài ngày ổn.
6. Verify live 4 luồng PLAN-053→056.

---

## Phiên 2026-09-05 (b) — PLAN-057 xong; blocker cuối là SSH key

### Kết quả
- **CI test job XANH lần đầu kể từ 2026-07-29** (run `33937825138`, commit `9996f4c`).
- **PLAN-057 đóng cả 4 mục A/B/C/D.**
- Deploy vẫn chưa chạy được: `ssh: handshake failed: unable to authenticate`.
  Script deploy **chưa hề chạy** trên VPS. Secrets `VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY`
  tồn tại nhưng đặt từ **2026-03-27**. Claude Code không có quyền truy cập VPS lẫn
  private key ⇒ **chỉ Owner xử được**.

### Vá lỗi attribution trên Linux (lỗi có sẵn từ PLAN-048)
`process_scan.py` `.resolve()` mọi `--user-data-dir`; trên POSIX `"C:/..."` là tương
đối nên bị rebase lên CWD = thư mục dự án ⇒ browser người khác bị nhận là của
ToolsAuto ⇒ orphan purge được phép kill. Vá bằng `is_absolute_elsewhere()` (thu hẹp,
không xoá `.resolve()` vì test đường-dẫn-tương-đối cần nó).

Proof nhân quả trong container Linux: code cũ **5 failed**, code mới **47 passed**;
Windows **244 passed**. Thêm test có nhánh theo nền tảng để Windows cũng bắt được.

### Quy trình mới
Lỗi lọt lưới 5 tuần vì máy dev Windows. Nay **chạy suite trong container Linux trước
khi push**, không đẩy lên rồi chờ CI đoán.

### Backup — xong trọn
PM2 `DB_Backup` cron `0 3 * * *`; `--keep 14` retention; `deploy.yml` dump Postgres
**ngay trước migration** (bước cũ chỉ `cp` file SQLite legacy — cùng lỗi nhầm đích).

### Next Action
1. **Owner: sửa SSH.** `ssh` tay vào VPS rồi cập nhật `VPS_SSH_KEY`. Đây là thứ duy
   nhất còn chặn lần deploy đầu tiên sau 5 tuần.
2. **Owner: duyệt ADR-011** để sang Việc 2 (P0-1 concurrency).
3. **Owner: đổi mật khẩu + đăng xuất phiên FB/IG/TikTok** — nợ từ PLAN-051, vẫn chưa làm.
4. Xoá `toolsauto_postgres_old_20260905` + volume `9a3acb1502…` sau vài ngày chạy ổn.
5. Verify live 4 luồng PLAN-053→056.

---

## Phiên 2026-09-05 — PLAN-057: hạ tầng tự phục hồi (Việc 1)

Owner giao "nâng cấp hệ thống để chạy trơn tru" → chia 3 việc, làm theo thứ tự.
**Việc 1 (hạ tầng) xong 3/4 mục.** Việc 2 (P0-1) chờ duyệt ADR-011.

### System State (2026-09-05)

- Postgres nay chạy bằng **`docker-compose.yml`**, `restart: unless-stopped`,
  healthcheck, **named volume `toolsauto_pgdata`**. `docker inspect` xác nhận
  `healthy | restart=unless-stopped`.
- Container cũ **còn nguyên làm đường lùi**: `toolsauto_postgres_old_20260905`
  (đã dừng) + anonymous volume `9a3acb1502…`. **Chưa xoá.**
- Alembic `i7d4e5f6a7b8 (head)`. 26 bảng / 440 row. jobs=14, accounts=1.
- Test local: **243 passed**. Test trên CI (Linux): **5 failed, 223 passed, 15 skipped**.
- Stack vẫn TẮT. 4 luồng live PLAN-053→056 vẫn chưa verify thật.

### Done This Session

| Mục | Việc | Proof |
|---|---|---|
| **B** | Gỡ `\|\| true` khỏi `db upgrade head` | `deploy.yml:113`; migration hỏng nay làm deploy đỏ |
| **C** | `docker-compose.yml` + `restart: unless-stopped` | Chuyển anonymous→named volume: 26 bảng/440 row, `diff` rỗng. `down`→`up -d`: healthy, jobs=14 còn nguyên |
| **D** | `manage.py db backup` dùng `pg_dump` thật | Dump 115.081 bytes; **restore thật vào DB tạm: 26 bảng/440 row, `diff` rỗng**; thất bại nay thoát khác 0 |
| A (một nửa) | Python 3.10→3.12 + `--ignore` file test hỏng | CI qua được **Install dependencies** — bước đã chết từ 2026-07-29 |

Commit: `a9a5267` (code), `2dada07` (proof + ADR-011).

### Sự cố tự chứng minh

Đầu phiên Postgres **lại tắt** — lần thứ **3** (10 ngày → 13 ngày → qua đêm).
Chính là thứ mục C sửa.

### ⚠️ CHẶN — CI vẫn đỏ vì lỗi CÓ SẴN, không phải lỗi hạ tầng

Run `33936616449`: 5 test **xanh trên Windows, đỏ trên Linux** — mà **VPS chạy Linux**.

`process_scan.py:553` thêm ứng viên `Path(user_data_dir).resolve()`. Trên POSIX,
`.resolve()` giải đường dẫn **tương đối theo CWD**, mà CWD là thư mục dự án ⇒ browser
của **người khác** bị nhận nhầm là của ToolsAuto ⇒ orphan purge PLAN-048 **được phép
kill nó**. Đúng bất biến mà chính test đó lập ra để bảo vệ.

Chứng minh trong container `python:3.12-slim` (không suy đoán):
`C:/Users/.../User Data` → `/repo/C:/Users/.../User Data` → `within(project_root)=True`.

Nằm im từ PLAN-048 vì CI chết ở bước cài dependency nên **chưa từng chạy test trên
Linux**; máy dev Windows nên `.resolve()` không relativize ⇒ test xanh, che mất lỗi.

**Đã DỪNG theo quy tắc escalation** — `process_scan.py` là core logic, ngoài vai trò
Claude Code. **Không tự sửa, không dán `--ignore` để CI xanh giả.**

### Chờ Owner quyết — 3 việc

1. **Lỗi `process_scan` trên Linux**: cho Claude Code vá, hay chuyển Antigravity ra
   PLAN? Hướng vá tối thiểu: chỉ `.resolve()` khi đường dẫn đã tuyệt đối, hoặc giải
   tương đối theo project root tường minh thay vì theo CWD.
2. **ADR-011** (đã soạn, trạng thái ĐỀ XUẤT): xin ngoại lệ vá P0-1 concurrency —
   `queue.py` outer predicate, `config.py` ngưỡng recovery, migration partial unique
   index, + TEST A/B/C.
3. **Đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok** — nợ từ PLAN-051, cookie phiên
   thật đã phơi public 3,5 tháng và **đến giờ vẫn chưa vô hiệu hoá**.

### Next Action

1. Owner quyết 3 việc trên.
2. Sau khi vá `process_scan` → CI phải **xanh trên run thật** thì mục A mới đóng,
   và đó cũng là lần deploy đầu tiên kể từ 2026-07-29.
3. Lên lịch backup định kỳ (hiện mới có lệnh chạy tay đã chứng minh đúng).
4. Xoá `toolsauto_postgres_old_20260905` + volume `9a3acb1502…` sau khi chạy ổn vài ngày.
5. Verify live 4 luồng PLAN-053→056 (cần Owner mở trình duyệt).

---

## Phiên 2026-09-04 — kiểm tra dự án + đưa diff treo lên main

### System State (2026-09-04)

- Python 3.14.7 + venv: chạy tốt. Test suite **243 passed / 12.1s**
  (`--ignore=tests/test_threads_world_news.py`).
- `toolsauto_postgres` **đã tắt 13 ngày**, phiên này `docker start` lại. Alembic
  `i7d4e5f6a7b8` khớp DB.
- DB thật: 1 account · jobs: 7 DRAFT, 2 PENDING (#2, #4 — facebook/POST,
  `is_approved=false`), 4 DONE, 1 FAILED. **0 RUNNING.**
- Stack vẫn **TẮT**. Bốn luồng live PLAN-053→056 vẫn **chưa từng verify thật**.
- Working tree **sạch**, `main` == `origin/main`.

### Done This Session

| Việc | Proof |
|---|---|
| Kiểm tra lại toàn bộ kết luận audit sau 14 ngày | Cả 4 lỗi P0 + toàn bộ P1 **vẫn nguyên**, chưa vá dòng nào |
| Commit + push diff treo 2 tuần lên `main` | 3 commit `8ee49f8`, `5e9537d`, `12176de`; `ea57b4b..12176de main -> main` |

Ba commit đã đẩy:
- `8ee49f8` feat — PLAN-052→056 (24 file, +1908/−68), gồm migration
  `i7d4e5f6a7b8` và `story_composer.py`
- `5e9537d` docs(agents) — 5 PLAN, 6 TASK, ADR-010, AUDIT-001, handoff
- `12176de` chore(lint) — cấu hình Codacy CLI, `.gitignore` chặn `generated/`

**Không tách được 5 commit theo từng PLAN**: `facebook/adapter.py` (+405 dòng) và
`core/queue/job.py` bị PLAN-053/054/055/056 sửa đan xen, tách hunk sẽ tạo commit
trung gian không chạy được test.

### Rủi ro đã đóng trong phiên này

**Lệch pha migration.** Trước phiên này DB đang ở `i7d4e5f6a7b8` nhưng revision đó
**không tồn tại trong git** — deploy `main` sẽ khiến `alembic upgrade head` gặp
revision lạ, mà `deploy.yml` có `|| true` nuốt lỗi ⇒ deploy vẫn báo xanh trong khi
migration hỏng. Commit `8ee49f8` đóng khoảng lệch này.

### Còn nguyên — KHÔNG có gì được vá trong phiên này

- **P0-1a** `queue.py` outer predicate vẫn thiếu `AND status='PENDING'`
- **P0-1b** không có partial unique index nào trong `alembic/versions/`
- **P0-1c** `WORKER_CRASH_THRESHOLD_SECONDS=120` < `PUBLISHER_PUBLISH_DEADLINE_SEC=900`
- **P0-2** `tracking_url` vẫn ghi `/r/{code}` tương đối; route vẫn sau tường auth
- P1: `deploy.yml:30` vẫn `python-version: "3.10"`; 2 vi phạm import-linter;
  `manage.py db backup` vẫn `copy2(DB_PATH)` (backup nhầm SQLite); drift `.webp`
- **243 test xanh KHÔNG chứng minh gì cho P0** — TEST A/B/C (§19 của AUDIT-001)
  chưa ai viết.

### CI vẫn đỏ — lần thứ 6

Run `33844459654` (2026-09-04) fail y hệt: workflow cài Python **3.10.21** trong khi
`requirements.txt` ghim numpy 2.4.2 (cần ≥3.11). Push phiên này **chưa deploy được**.

### Nhánh chưa xử

`origin/develop`: đi sau main **78 commit**, đi trước **4 commit** (mới nhất
2026-05-05, ~4 tháng): sidebar accordion, refactor sidebar SaaS, fix worker crash /
imports / playwright `/dev/shm`, fix backlog count đa nền tảng. **Chưa merge** — cần
Owner quyết vì 4 commit này nằm trên base đã cũ 78 commit, merge mù dễ kéo lùi UI.

### Next Action

1. Sửa `deploy.yml:30` → Python 3.12 để mở lại CI (1 dòng, chặn mọi deploy).
2. Vá P0-1a + P0-1c (hai thay đổi nhỏ, độc lập), viết TEST A.
3. P0-1b partial unique index + bắt `IntegrityError` → TEST B (hiện 0 RUNNING nên
   tạo index được ngay, không cần dọn dữ liệu).
4. P0-2 cụm affiliate → TEST C; nếu chưa xong thì **gỡ "link aff đếm click" khỏi mô
   tả combo trước khi bán tiếp**.
5. Owner: đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (nợ từ PLAN-051).
6. Owner mở phiên trình duyệt verify live 4 luồng PLAN-053→056.
7. Quyết số phận `origin/develop`.

---

## Phiên 2026-08-21 (b) — AUDIT toàn diện repo (AUDIT ONLY, không sửa code)

Báo cáo đầy đủ: `agents/audit/AUDIT-001-repo-wide-2026-08-21.md`

### Đã làm
- Kiểm toán toàn repo: dependency graph bằng AST (282 file), schema + row count trên
  Postgres đang chạy, `EXPLAIN` câu SQL claim, chạy test suite (243 passed), đối chiếu
  ADR với code thật. **Không sửa file nào ngoài báo cáo.**

### Đã qua vòng FINAL VALIDATION (rev.2) — kết luận đã được siết lại

Vòng validation tập trung concurrency/transaction/recovery/security. Thay đổi quan
trọng nhất: **P0-1 không phải một lỗi mà là BA lỗi độc lập**, và **không bản vá đơn
lẻ nào đóng được cả ba**. Bản rev.1 nói "hai P0 vá bằng một dòng" — điều đó **sai**
và đã được gỡ.

### P0-1 — ba bất biến đồng thời, ba bản vá khác nhau

| | Bất biến | Trạng thái | Bản vá tối thiểu |
|---|---|---|---|
| **A** | 1 job PENDING → đúng 1 worker | ❌ **CONFIRMED vỡ** | `AND status='PENDING'` ở WHERE ngoài (`queue.py:44`) |
| **B** | 1 `(account, platform)` → tối đa 1 job RUNNING | ❌ **PLAUSIBLE vỡ** (MEDIUM) | **Partial unique index** + bắt `IntegrityError`. Bản vá của A **không** chạm tới B |
| **C** | Job đang chạy không bị recovery cướp | ❌ **CONFIRMED (cơ chế)** | `WORKER_CRASH_THRESHOLD_SECONDS` (120 s) phải **>** `PUBLISHER_PUBLISH_DEADLINE_SEC` (900 s) |

**Evidence mới thu được trong vòng này (read-only, không ghi DB):**

- `EXPLAIN` bản vá A trên Postgres thật: qual ngoài đổi thành
  `Filter: (status='PENDING' AND id=$0)` → EvalPlanQual của worker thua fail → 0 row.
  **A được đóng. HIGH.**
- `EXPLAIN` phương án `FOR UPDATE OF j SKIP LOCKED`: **plan hợp lệ**, xuất hiện nút
  `LockRows` giữa `Sort` và `Limit` → worker thua lấy ứng viên kế tiếp thay vì về tay
  không. Là cải thiện thông lượng, **không thay thế** bản vá A.
- B: khi hai worker chọn **hai row khác nhau** thì **không có xung đột khoá**, nên
  EvalPlanQual không bao giờ chạy → outer predicate vô tác dụng. Điều kiện kích hoạt:
  khoá sắp xếp hoà — `lpp.last_ts` luôn hoà trong cùng account, và
  `create_high_priority_manual_job` (`job.py:908`) đặt `schedule_ts = now - 999999`
  cho mọi job thủ công → hai job tạo cùng giây hoà tuyệt đối.
  **Chưa chạy thí nghiệm 2 session ⇒ giữ ở PLAUSIBLE, không nâng lên CONFIRMED.**
- C: `120 s` (ngưỡng recovery) < `900 s` (deadline job) < `420 s` (trần chờ upload
  một video, PLAN-056). Hai nhịp heartbeat lỡ liên tiếp (60 s × 2) đủ để job khoẻ bị
  đặt về PENDING rồi bị worker khác claim. Cửa chặn `check_published_state` chỉ chạy
  khi `tries > 0` và **không phủ hết job type** (Instagram trả thẳng `ok=False`;
  Facebook chỉ quét Reels, không quét feed/story).
- Truy vấn live: hiện **0 job RUNNING**, không cặp `(account_id, platform)` nào >1
  RUNNING ⇒ partial unique index tạo được ngay, không cần dọn dữ liệu. Cũng **chưa
  thấy dấu vết đăng trùng** trong 14 job hiện có — nhưng đó là "chưa xảy ra", không
  phải "không thể xảy ra".

### P0-2 — là một CỤM ba lỗi, không phải một dòng

(a) URL tương đối khi thiếu base URL · (b) `/r/{code}` sau tường auth ·
(c) `tracking_url` ghi rồi mất vì không commit. Ba tầng khác nhau; sửa đúng hai trong
ba vẫn để lại tính năng hỏng. **Điều kiện đóng: test end-to-end với client KHÔNG đăng
nhập** (TEST C, §19 của report).

### Ba test bắt buộc (đặc tả đầy đủ ở §19 của report)

- **TEST A** — 1 job PENDING, 2 session claim đồng thời → đúng 1 nhận được.
- **TEST B** — 2 job khác nhau **cùng account+platform**, `schedule_ts` bằng nhau,
  2 session claim đồng thời → tối đa 1 RUNNING. ⚠️ **TEST B đỏ sau khi vá A là đúng
  như dự đoán**, không phải bản vá hỏng. Nếu hoãn index: giữ `xfail` có ghi lý do,
  **không xoá test, không tuyên bố B đã đóng, và chỉ chạy 1 publisher**.
- **TEST C** — affiliate end-to-end tới `click_count`.

### Phát hiện mới trong vòng validation

- **`manage.py db backup` backup nhầm SQLite**, không phải Postgres (`manage.py:141`
  `copy2(DB_PATH)`) — nhưng vẫn in `Backed up: ...` thành công. Bẫy vận hành thật.
- **TD-18 nâng P2 → P1:** `serve_screenshot` đọc được `.env` ⇒ lộ `SECRET_KEY`, mà
  `SECRET_KEY` chính là khoá **ký cookie phiên** (`auth/router.py:11`). Nghĩa là lỗ
  này biến một phiên bị chiếm có thời hạn thành **quyền truy cập bền vững**. Lập luận
  cũ "admin đã có SQL console nên vô hại" là sai — SQL console không đọc được file.
- **`claim_next_verify_job`** (`threads/workers/verifier.py:259` + `:213`) là
  read-then-act không nguyên tử. Giảm nhẹ: worker này **không được supervisor nào
  khởi động** (không có trong `ecosystem.config.js`/`start.sh`/`start.ps1`/
  `local_supervisor.py`). Phải vá **trước khi** bật.

### Wording đã siết lại (evidence > assumption)

- ~~"Mất DB thì không restore được"~~ → **"Không có PostgreSQL recovery path nào được
  định nghĩa và kiểm chứng trong phạm vi hệ thống đang audit."** Snapshot hạ tầng của
  nhà cung cấp VPS nằm ngoài phạm vi — "không tìm thấy" ≠ "không tồn tại".
- ~~CSRF "đủ trên thực tế"~~ → **"Chấp nhận được dưới threat model một-admin hiện
  tại"**, kèm 4 giả định và điều kiện phải review lại (thêm user, thêm JSON API,
  tách subdomain, đổi `SameSite`, hoặc thêm GET có side-effect).

### Next Action — thứ tự đã chốt lại sau validation

**P0 (trước khi mở rộng tải / giao khách):**
1. TD-01a outer predicate → TEST A xanh.
2. TD-01c ngưỡng recovery ≥1200 s (> deadline 900 s).
3. TD-01b partial unique index + bắt `IntegrityError` → TEST B xanh (hoặc `xfail` +
   chỉ chạy 1 publisher).
4. TD-02 cụm affiliate → TEST C xanh; nếu chưa xong → **gỡ "link aff đếm click" khỏi
   mô tả combo trước khi bán tiếp**.
5. Owner đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (nợ từ PLAN-051).

**P1 (an toàn production):** bỏ `|| true` ở deploy · bump CI 3.12 · `lint-imports` ·
`pg_dump` theo lịch + **thử restore một lần** · sửa TD-23 (`manage.py db backup`) ·
TD-18 siết `serve_screenshot` · TD-09 bọc try/except từng bước maintenance · TD-08
vòng đời media dùng chung · verify live 4 luồng PLAN-053→056 · TASK-055 · review +
commit diff đang treo.

**P2 (kiến trúc):** SR-4 conftest + chuyển test theo 8 bước ưu tiên · ADR-009 →
SR-5 xoá tầng no-code · SR-2 port cho job type · TD-24 vá verifier trước khi bật.

### Phát hiện P1 đáng chú ý
- `alembic upgrade head || true` trong `deploy.yml:112` nuốt lỗi migration; **không có
  backup PostgreSQL tự động** (pipeline chỉ `cp` file SQLite legacy; `pg_dump` là nút bấm tay).
- ~49% test (13 file) là `read_text()` + `assert "chuỗi" in src`. `test_claim_mutex_is_per_platform`
  đang XANH trong khi mutex thực sự vỡ vì race ở trên.
- `import-linter` khai báo trong requirements + có `.importlinter` nhưng **không cài trong venv
  và không có trong CI** ⇒ chưa từng chạy. Đang có 2 vi phạm thật:
  `app/core/observability/metrics_checker.py:162` → `app.features.facebook`;
  `app/features/insights/router.py:149` → `app.features.viral_intake`.
- Job DONE xoá **cả file gốc** vô điều kiện; partial unique index chỉ chặn trùng trong cùng
  platform ⇒ job facebook xong trước xoá file, job threads cùng file fail với lý do sai.
- `maintenance.run_loop()` all-or-nothing: 12 việc trong một `try`, một scraper gãy chặn luôn
  `recover_crashed_jobs` + purge zombie + insights.
- UI `manual_job_form.html:140,146` quảng cáo `.webp` nhưng `JobService.IMAGE_EXTENSIONS`
  không có `.webp` ⇒ drift thật, chặn oan người dùng.

### Xác nhận lại bằng dữ liệu runtime
- 4 bảng tầng no-code (`platform_configs`, `platform_selectors`, `cta_templates`,
  `workflow_definitions`) đều **0 row** — ADR-009 vẫn đúng, vẫn chờ Owner chốt.
- Alembic head `i7d4e5f6a7b8` khớp DB. 26 bảng, `accounts`=1 row, `jobs`=14 row.

### Next Action — thứ tự đề xuất
1. Vá P0-1 (`AND status='PENDING'`) + viết test concurrency thật (2 session Postgres).
2. Vá P0-2 hoặc **gỡ "link aff đếm click" khỏi mô tả combo** cho tới khi chạy được.
3. Owner: đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (việc còn nợ từ PLAN-051).
4. Quick win 1 dòng: bỏ `|| true` ở deploy, bump CI lên Python 3.12, thêm `lint-imports`.
5. Lên lịch `pg_dump` + **thử restore một lần**.
6. Việc cũ chưa xong: verify live 4 luồng PLAN-053→056; TASK-055 khảo sát giỏ hàng;
   review + commit diff đang treo.

---

## Phiên 2026-08-21 — bổ sung tính năng còn thiếu của Combo 2 (PLAN-052 → 056)

Owner duyệt cho Claude Code execute cả backend đợt này — ghi ở **ADR-010**, hết hiệu
lực sau PLAN-056.

### System State (2026-08-21)

- **Máy chạy lại được**: Python 3.14.7 hoạt động (handoff 2026-08-11 ghi interpreter
  mất — nay đã khác). `pytest` chạy bình thường.
- Container `toolsauto_postgres` đang **BẬT** (port 5434), đã `alembic upgrade head`
  tới `i7d4e5f6a7b8`.
- Test suite: **243 passed** (baseline đầu phiên 175), `--ignore=tests/test_threads_world_news.py`.
- Stack vẫn **TẮT**. Chưa đăng thử bất cứ thứ gì lên Facebook trong phiên này.
- Diff chưa commit: 16 file sửa, 6 file mới (2 page/adapter, 4 test), 1 migration.

### Done This Session

| Việc | Proof |
|---|---|
| **PLAN-052** Hàng đợi nhận mọi job_type — job FEED trước đây nằm PENDING vĩnh viễn | `git stash` code cũ → 2 test FEED/STORY đỏ; code mới → 9/9 xanh (SQL thật trên Postgres) |
| **PLAN-053** Lấy `post_url` bài feed + auto-comment cho bài feed | 14 test; vá luôn rủi ro bắt nhầm link bài người khác lúc cuộn feed |
| **PLAN-054** Đăng Story + phủ link aff lên tin | 23 test; `story_composer.py` mới; chặn đăng nhầm danh nghĩa Page |
| **PLAN-055** Đính ảnh vào comment | 12 test; cột `comment_image_path` + migration; 4 adapter cùng chữ ký |
| **PLAN-056** Video dài: chờ upload theo dung lượng thật thay vì cứng 20s | 9 test; có trần 7 phút, dừng sớm khi thấy preview |
| **TASK-055** Giỏ hàng: chuyển thành khảo sát live, **không code mù** | Lý do + 7 bước khảo sát trong task |

### Lỗi có sẵn phát hiện được trong lúc làm

1. `claim_next_job` liệt kê cứng `POST`/`COMMENT` ⇒ **mọi job FEED không bao giờ chạy**.
   Bài feed của PLAN-049 lên được là do gọi adapter trực tiếp, không qua hàng đợi.
2. `_normalize_fb_text` chỉ NFD nên còn dấu tổ hợp — dùng để so tên Page sẽ **chặn oan**
   khi tên lệch dấu. Đã thêm `_identity_key` riêng cho phép so danh tính.

### Next Action — theo thứ tự

1. **Owner mở phiên trình duyệt** để verify live 4 thứ chưa từng chạy thật:
   - Đăng tin ảnh + tin video lên Page nháp (PLAN-054)
   - Chữ trên tin có bấm được thành link không → quyết định có bán mục "link aff story" hay không
   - Comment kèm ảnh dưới một Reels thật (PLAN-055)
   - Đăng bài feed thật, xem log có bắt được `post_url` không (PLAN-053)
   - Đăng video > 5 phút (PLAN-056)
2. **TASK-055**: khảo sát giỏ hàng. Nếu Facebook không cho → **gỡ mục đó khỏi mô tả
   combo Page Master trước khi bán tiếp**.
3. Review + commit diff đang treo.
4. Việc cũ chưa xong: bump `python-version` trong `deploy.yml` để mở lại CI (đỏ từ 2026-07-29).

### Cảnh báo bán hàng (chưa được hứa với khách)

- "Link aff bấm được trong story" — chưa kiểm chứng.
- "Gắn giỏ hàng" — chưa có dòng code nào, chưa khảo sát.
- "Tìm video theo từ khóa" — mới chỉ đúng với TikTok. **Douyin: 0%.** YouTube Short và
  Facebook Page chỉ tải được khi dán link.


## ⚠️ CẢNH BÁO BẢO MẬT (2026-08-11) — chờ Owner xử lý

`scratch/threads_cookies.json` chứa **cookie phiên thật** (FB `xs`/`c_user`,
IG `sessionid`, TikTok `msToken`) bị commit ở `a723c0f` ngày 2026-04-25 trên repo
**PUBLIC** `github.com/dthanhvu03/toolsauto` → phơi công khai ~3,5 tháng.

Đã xử (PLAN-051 §D): `filter-branch` purge cả 13 branch + force-push + gc.
**Nhưng object mồ côi vẫn tải được công khai theo SHA** (`gh api ...?ref=a723c0f`
→ 6908 bytes) cho tới khi GitHub tự GC.

Owner đã quyết: **giữ repo public, không mở ticket GC** — chấp nhận rủi ro còn lại.

Việc duy nhất còn lại và bắt buộc: **đổi mật khẩu + đăng xuất mọi phiên
FB/IG/TikTok**. Ai đã clone repo phải clone lại (mọi SHA đã đổi).

## System State (2026-08-11)

- **Máy không chạy được stack**: interpreter `pythoncore-3.14-64` biến mất,
  `venv\Scripts\python.exe` là stub trỏ vào đường dẫn đã mất → không chạy được
  `pytest` lẫn worker. Registry HKCU vẫn trỏ path cũ.
- Container `toolsauto_postgres` tắt 10 ngày, đã `docker start` lại để audit.
- **CI đỏ từ 2026-07-29**, 5 commit cuối trên `main` chưa từng deploy:
  workflow đặt Python 3.10 nhưng requirements ghim numpy 2.4.2 (cần ≥3.11).
- Hàng đợi tắc: 7 job DRAFT `[AI_GENERATE]` + 2 PENDING, tất cả `is_approved=false`;
  job #2 trỏ media đã bị xoá. `viral_materials` 11/11 kẹt DRAFTED.

## Done 2026-08-11 — audit tính năng + dọn nợ kỹ thuật (PLAN-051)

| Việc | Proof |
|---|---|
| Audit toàn bộ tính năng bằng DB thật + CI thật (không chỉ đọc doc) | Bảng row-count 26 bảng; `gh run list` 5 lần failure |
| Gỡ cookie phiên khỏi git index + `.gitignore` chặn `*cookies*.json` | `git ls-files \| xargs grep` secret pattern → rỗng |
| Xoá 731 dòng code chết (3 template, `gemini_api.py`, 2 shim) | grep 0 tham chiếu; ADR-006 §7 ghi closure |
| Sửa docstring `native_fallback.py` chỉ sai chỗ vision | vision nằm ở `call_native_gemini_vision` từ TASK-025 |
| ADR-009: `GenericAdapter` là code không thể chạm tới | `dispatcher.py:88` luôn ghi đè Registry cho cả 4 platform |

Diff đang chờ Owner review, **chưa commit**: 9 file, −750 dòng.

## Next Action (2026-08-11)

1. **Owner:** đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (vô hiệu cookie đã rò)
2. **Owner:** quyết repo private và/hoặc purge lịch sử git (thao tác phá huỷ)
3. Cài lại Python 3.14 + dựng venv → mở lại pytest
4. Bump `python-version` trong `deploy.yml` + xử `test_threads_world_news.py` → mở lại CI
5. Owner chốt ADR-009 trước khi động vào `GenericAdapter`

## System State (2026-07-31)

- PLAN-048 stack (supervisor + smart gate + orphan purge) đã qua vòng review/hardening
- **PLAN-049**: Facebook đăng được **bài feed** (chữ thuần / chữ + ảnh), không còn chỉ Reels
- FB **POST = Reels** vẫn chỉ video; **FEED** nhận ảnh/video/không media — hai loại tách bạch
- Job #6 (PNG vào Reels) bị chặn trước khi mở browser, tính là VALIDATION (không phạt account)
- Stack đang **TẮT**. Test suite: **161 passed**

## Done This Session — phần 2: luồng bài feed (PLAN-049)

| Việc | Proof |
|---|---|
| `JobType.FEED` + `assert_feed_media()` + rẽ nhánh dispatcher | `tests/test_facebook_feed_post.py` (17 pass) |
| `FacebookFeedComposer` — mở composer, gõ chữ, đính ảnh, Tiếp → Đăng | Đăng thật lên Page `kids0810`, owner đã xác nhận thấy bài |
| Form job thủ công chọn Reels / Bài feed, `accept` đổi theo | `test_media_ui_consistency` cập nhật theo chính sách mới |
| 2 lỗi chỉ lộ khi chạy live | Bước "Tiếp" của Page; `pre_post_delay()` thiếu tham số `page` |

Còn nợ: `post_url` của bài feed (Facebook Page không phơi permalink ra DOM). Chi tiết + hướng vá ghi trong PLAN-049.

## Done This Session (audit + fix 12 findings)

| Vùng | Thay đổi | Proof |
|---|---|---|
| Nhận diện process | `app/core/process_scan.py` mới — match cả `-m app.x.y` lẫn `app/x/y.py` (PM2), ancestry chống PID reuse, hydrate lazy | `tests/test_process_scan.py` (20 pass) |
| Orphan purge | Chỉ kill browser root có `--user-data-dir` nằm trong profile root chuẩn, không có ancestor worker sống, đã chạy > 120s | `tests/test_orphan_browser_purge.py` (13 pass) |
| Supervisor | State/lock tuyệt đối trong `storage/db/config/`, lock `O_CREAT|O_EXCL` + thu hồi stale, stop bằng CTRL_BREAK | `tests/test_local_supervisor.py` (10 pass) |
| Media gate | Một nguồn sự thật cho extension, caption-only manual job vẫn tạo được, upload bị từ chối không để lại file | `tests/test_facebook_media_gate.py` (14 pass) |
| Circuit breaker | `error_type=VALIDATION` không tăng `consecutive_fatal_failures` | như trên |
| Heartbeat | Mọi early return của publisher đều stop heartbeat (finally) | `tests/test_publisher_heartbeat.py` (3 pass) |
| ffmpeg | `app/core/media/ffmpeg_path.py` mới; thumbnail/DRM/orchestrator/reup đều resolve binary | `tests/test_ffmpeg_resolution.py` (10 pass) |
| UI | Form create/manual: video-only cả label, drag-drop lẫn `accept` | `tests/test_media_ui_consistency.py` (4 pass) |
| Hiệu năng | Quét process 8.3s → 0.02s (capture) + cache 30s cho đếm browser | đo trực tiếp trên máy (513 process) |

## Hardening vòng 2 (sau review)

| Rủi ro | Xử lý |
|---|---|
| Lệnh chỉ *nhắc tới* đường dẫn worker (`git diff`, `compileall`, editor) bị nhận là worker → supervisor không spawn | Parse argv thật (`-m` / positional script), argv[0] **và** tên process phải là interpreter |
| Browser mất ancestry khi job còn RUNNING → bị coi là orphan | Purge nhận `db`: profile của account có job RUNNING không bao giờ bị đụng; DB lỗi → tắt purge |
| PID reuse giữ lock | Lock ghi thêm `create_time`, lệch > 1s ⇒ stale |
| CTRL_BREAK khi không có process group riêng | Chỉ gửi khi `own_process_group=True`, còn lại dùng terminate |
| `count_chrome_processes` đổi contract | `ChromeProcessCounts` (NamedTuple): có tên field, vẫn unpack như tuple |
| Cache đếm browser bị đọc/ghi đa luồng | Bọc `threading.Lock` |

Full suite: `pytest tests -q --ignore=tests/test_threads_world_news.py` → **142 passed**.

Smoke process thật (Chromium thật, không đụng job production):
- Worker kiểu PM2 (script path) + Chromium của nó → **không** bị purge; orphan thật → bị kill (1/1)
- Topology Playwright thật `chrome ← node ← python worker` → attribution `worker`, an toàn
- Ancestry bị phá + job RUNNING trong DB thật → **không** bị kill; sau khi job DONE → mới purge được
- Lock: supervisor thứ 2 bị chặn bởi supervisor đang chạy thật (pid 33416)

## Unfinished + Blockers

- `tests/test_threads_world_news.py` hỏng từ trước — **đã chứng minh trên `origin/main`** (worktree sạch, cùng interpreter): cùng lỗi `ModuleNotFoundError: app.services`. Module bị xoá ở commit `fd87077` (refactor P028). Baseline không tính file này: 51 passed. Sửa cần dựng lại test theo module mới → tách task riêng.
- ~~Máy đang chạy 2 supervisor + 2 publisher...~~ **Đính chính:** đây KHÔNG phải trùng lặp. `venv\Scripts\python.exe` trong layout PyManager là **stub 3MB** re-exec interpreter thật (`AppData\Local\Python\pythoncore-3.14-64\python.exe`) làm process con **cùng cmdline** → mỗi worker hiện ra 2 pid. Đã sửa `ProcessSnapshot.find_pids` gộp chuỗi cha–con thành 1 instance (giữ nguyên 2 worker anh em thật, ví dụ FB_Publisher_1/2 của PM2).

## Next Action

- Restart `.\start.ps1 -Stack` và xác nhận log `[STACK] ensure web=... fb_publisher=... chrome_ta=`
- Hủy Job #6 hoặc thay media bằng .mp4
