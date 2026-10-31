## Phiên 2026-10-30 → 31 (studio) — PLAN-106 Studio P1–P4 + PLAN-108 dọn giao diện (đã merge main)

- Anh: mọi bài đã đăng qua Buffer, UI đăng bài cũ không cần nữa, «đập đi xây lại 1 hệ sinh thái edit video». Anh chốt: edit tự động theo mẫu + duyệt / chỉnh tay; 3 nguồn (reup, tự quay, AI); điều khiển bằng web + Telegram; **xây song song**, Buffer vẫn đăng bình thường.
- Khảo sát (chỉ đọc code + 1 truy vấn DB chỉ đọc): 0 tài khoản FB active, 0 job FB treo, nên luồng READY → Buffer không bị chặn. Vật liệu: READY 306, FAILED 210, POSTED 151, BOOST_PENDING 31, DUPLICATE 9; READY mới nhất 25/10. Code chết khoảng 25k dòng (FB / Threads / IG / TikTok upload / engagement…), khoảng 15 trang UI, khoảng 50 file test.
- `agents/plans/active/PLAN-106-video-studio.md`: module `app/features/studio/`, dự án = spec JSON, render 1 lượt, cache Whisper, worker `Studio_Render` riêng, cầu nối Buffer qua dòng `viral_materials` READY (không sửa code Buffer), 6 bước P0–P6, xoá code chết ở bước cuối.
- Anh: «tách hết ra để mỗi module làm 1 việc và nối lại quy trình… em quyết toàn bộ đi». Em chốt D1–D5:
  - D1: bỏ cắt watermark + lọc né trùng, giữ ghi nguồn;
  - D2: thí điểm phải duyệt;
  - D3: Pexels + thư viện của anh;
  - D4: kênh Uyển Nhi;
  - D5: Claude Code làm cả backend.
  Ghi ở **ADR-061** (`agents/decisions/ADR-061-video-studio-pipeline.md`); PLAN-106 chuyển Approved.
- **P1 xong (chưa commit):**
  - `app/features/studio/`: mỗi bước 1 package (intake / analyze / compose / render / review), nối bằng hàng việc `studio_tasks` + `pipeline.py`; worker theo làn heavy / light.
  - Models + migration `u8c5d6e7f8a9` (chỉ thêm 6 bảng), `.importlinter` 2 luật mới, PM2 `Studio_Heavy` / `Studio_Light` (chưa bật).
  - Proof trong PLAN-106: 30 test Studio qua, ruff sạch, luật import mới KEPT, migration lên / xuống / check sạch trên SQLite tạm, test cũ liên quan 386 qua + 2 hỏng ngoài Studio (1 cần Postgres thật, 1 hỏng sẵn trên HEAD).
- Không đụng: Buffer, Maintenance, viral_intake, cashback (working tree có thay đổi cashback của phiên khác — `cashback_bot/*`, PLAN-105 — em không sửa).
- **31/10 — P2 xong (chưa commit, chưa chạy trên máy thật).** Anh: «em làm tiếp đi».
  - Bước mới `dub` (lồng tiếng → 2 asset audio giọng + nền, spec `Clip.audio`) và `caption` (AI sau render). Mẫu `reup_dub`, `own_footage` (cắt khoảng lặng). `basic` không đốt phụ đề tiếng khác.
  - Cửa vào `studio/entry.py`: hook `studio.take_reup` từ `viral_intake/processor.py` (+14 dòng, ngay sau chống trùng; chỉ khi đúng 1 kênh đích bật `studio_channels.take_reup`, material → `STUDIO`), `POST /studio/api/upload`, hộp thư Drive `Studio/Inbox/<tên kênh>/` + `_Kho/`.
  - Port không sửa code cũ: `app/core/media/speech.py`, `tts.py`, `studio/dub/engine.py`, `separate.py` (bản cũ xoá ở P6). ADR-061 thêm mục 7–10.
  - Migration `u8c5d6e7f8a9` sửa thẳng (chưa chạy ở đâu): thêm `studio_channels.take_reup`, `studio_tasks.parent_id`.
  - Proof trong PLAN-106: 57 test Studio qua; ruff sạch; luật import Studio KEPT; migration lên / check / xuống sạch; cả bộ test cắt mạng 73/74 test hỏng y hệt worktree HEAD sạch, test còn lại do `app/services/__pycache__` cũ (gitignore) ở thư mục làm việc, 6 test cashback của phiên khác cần DNS.
  - Không có kênh nào bật `take_reup` (bảng chưa có trên DB thật) nên hệ cũ chạy y như trước.
- **31/10 (chiều) — PLAN-108 dọn giao diện + P3 cầu nối Buffer xong (chưa commit).** Anh: «dọn dẹp các ui ux… tổ chức lại theo module… rồi làm bước 3».
  - PLAN-108: gỡ 8 module chết (tài khoản FB, affiliate, kho kênh cũ, insights, nhiệm vụ FB, Threads, hub cấu hình, cấu hình nền tảng) ở cả SPA, API admin, router, Jinja; sidebar SPA + Jinja cùng 5 module (Tổng quan · Video · Buffer · Nội dung & AI · Hệ thống); Tổng quan viết lại theo kênh Buffer; Lịch đăng chỉ xem. 129 file, −14.255 dòng. Build lại `app/static/admin`.
  - P3: bước `publish` → dòng `viral_materials` READY + file nối cứng trong `REUP_DIR/studio/`, Maintenance tự hẹn lên Buffer; duyệt / bỏ qua API; đồng bộ SCHEDULED / POSTED. Không sửa code Buffer.
  - Proof trong PLAN-108 / PLAN-106: 115 test Studio + giao diện qua; ruff sạch; luật import Studio KEPT; migration sạch; chụp trình duyệt thật 1440 / 390 px; cả bộ test cắt mạng: test hỏng còn lại đều hỏng sẵn (so với lần chạy P2 + worktree HEAD).
  - **SPA mới đang hiện trên web thật** (file tĩnh), API vẫn là process cũ: anh cần `pm2 restart Web_Dashboard`.
- **31/10 (tối) — P4 xong (chưa commit):** SPA Studio (bảng duyệt, trình edit cắt đoạn / sửa phụ đề / hook / âm lượng / caption / đổi mẫu, Nguyên liệu, Kênh & mẫu) + Telegram (video chờ duyệt kèm nút ✅ / 🗑 / ✏️, gửi file video vào bot → dự án). 75 test Studio qua; chụp trình duyệt thật trên môi trường demo SQLite. Proof ở PLAN-106.
- **31/10 — đã commit (anh: «em commit cho anh luôn»):** nhánh `studio/plan-106-108` (từ main e4993eb), làm trong worktree `/home/vu/toolsauto-studio` để không đổi nhánh của thư mục chung (phiên cashback đang làm ở đây). `f4713b0` feat(studio) P1–P4 (67 file), `8154fca` refactor(ui) PLAN-108 (125 file). Không có file cashback / PROJECT.md. Chạy thử trong worktree: 60 test qua + 1 hỏng sẵn (cần Postgres). Anh: «cashback xong rồi, tới phần em» → đã bỏ bản chưa commit (192 file, so sha khớp nhánh) và **merge vào main** (merge commit, xung đột duy nhất ở file này, giữ cả hai phần). Đã push cùng P4.1.
- **VieNeu-TTS (anh hỏi):** Apache-2.0, v3 Turbo 0.1B, 25 giọng Việt có sẵn (Bắc / Trung / Nam, dùng thương mại được), clone giọng từ 3–8 giây, chạy CPU bằng ONNX (không cần torch), `pip install vieneu`. Máy i5-10300H không có VNNI → chỉ dùng fp32. Hợp làm engine giọng chính cho bước `dub` / P5 thay edge-tts (endpoint không chính thức). Cài thử bị chặn quyền — cần anh cho phép cài vào venv riêng để nghe thử + đo tốc độ.
- **31/10 (khuya) — P4.1 biến thể A/B (đã commit + push main theo lời anh):** bản yêu cầu «anti-duplicate lách bản quyền» cho ReupProcessor em từ chối (trái D1). Bản «A/B test video tự quay» làm trong Studio: `Clip.hflip`, `Canvas.lut` (`storage/media/luts/*.cube`), mẫu `ab_montage`, API + nút «Dựng biến thể»; reup bị chặn (ADR-061 mục 11). 90 test Studio qua. Không đụng viral_intake.
- **31/10 04:40–04:50 — Studio đã chạy trên máy thật (anh: «khởi động dự án giúp anh»):**
  - Backup `storage/db/backups/toolsauto_db_20261031_044048.sql` (7,1 MB) → `alembic upgrade head` (t7b4c5d6e7f8 → u8c5d6e7f8a9; xem trước SQL: chỉ CREATE TABLE / INDEX 6 bảng studio_*) → `pm2 restart Web_Dashboard Maintenance` (Maintenance đang rảnh, không có ffmpeg / yt-dlp chạy) → `pm2 start --only Studio_Heavy,Studio_Light` → `pm2 save` (dump có đủ 6 app).
  - Lỗi khi bật worker: PM2 chạy `worker.py` như script nên `studio/queue.py` che module chuẩn `queue` → sập lúc import (`LifoQueue`). Đổi tên thành `taskqueue.py` + test chạy worker đúng kiểu PM2 và chặn tên trùng module chuẩn. Commit + push.
  - Kiểm: `/login`, `/app/go/studio`, `/studio/api/projects|setup`, `/api/admin/overview` đều 200 (cookie ký nội bộ, chỉ đọc); 2 worker online, đã đăng ký Telegram.
- **31/10 05:20 — P4.2 rà soát BA / SA + sửa (anh: «làm cho anh… chỉ tập trung Studio»):** 8 dự án gần trùng do bấm biến thể 2 lần, chưa có LUT, mỗi bản gọi AI caption riêng, không gom nhóm. Đã sửa (gom nhóm, chung caption, mỗi bản một kiểu thật, chặn lô trùng, duyệt 1 bản → bản khác tự bỏ, 1 tin Telegram / lô, hàng việc làm xong từng dự án, form upload: kênh bắt buộc + sưu tầm/ghi nguồn + «đã có chữ sẵn»). Migration `v9d6e7f8a9b0` đã chạy (backup trước), 4 process restart. Dữ liệu: giữ #1 (lật) + #3 (không lật), còn lại REJECTED. 98 test Studio qua.
- **31/10 12:45 — PLAN-109 DocType kiểu Frappe (code xong, commit cục bộ, CHƯA lên máy thật):** anh chọn «Kiểu DocType như Frappe». Định nghĩa loại dữ liệu trên web (trường, kiểu, link, bảng con) → danh sách + form + API, không cần code / migration cho từng loại. 25 test, trình duyệt thật trên SQLite tạm. Lệnh backup + migration `w0e7f8a9b0c1` + restart web bị chặn quyền → anh tự chạy (xem PLAN-109). Bản build SPA đã hiện mục «Dữ liệu (DocType)» nhưng API chưa có tới khi restart web.
- **31/10 06:30 — P4.3 (anh giao 4 bước):** bước 1 anh đã tự chạy (kiểm bằng lệnh đọc: ổn); bước 2 tạo `storage/media/luts|bgm`; bước 3 NVENC tự dò + quay về CPU (GTX 1650, driver 516.40 quá cũ cho ffmpeg 6.1 — cần ≥ 522; CPU 18,9 s / video 19,6 s); bước 4 cài VieNeu bị chặn quyền. 128 test (Studio + DocType) qua. Commit cục bộ.
- **Next:**
  - **31/10 07:30 — sau khi anh `wsl --shutdown` (kiểm xong):** 6 app PM2 lên đủ (DB_Backup stopped như cũ), `cashback-bot`
    + `cashback-zalo` active, web cổng 8000 trả 200. `nvidia-smi`: GTX 1650, driver 621.01, 4 GB.
    - **NVENC chạy được.** Đo trên spec dự án #3 (19,6 s, 1088×1936): x264 14,7 s · NVENC 11,3 s (cổ chai là bộ lọc CPU —
      phụ đề / scale — nên chỉ nhanh ~25 %). NVENC cq 23 ra file 16,7 MB vs 6,7 MB → đổi `encoder.video_args` sang
      cq = crf + 7 (= 28): 8,9 MB, SSIM 0,991 so với bản x264. 96 test Studio qua, ruff sạch, `pm2 restart Studio_Heavy` + save.
    - **VieNeu GPU:** cài `vieneu[cuda]==3.8.3` (torch 2.8.0) vào `/home/vu/venv-vieneu`; `bench_gpu.py`: nạp 92 s (lần đầu,
      có tải code MOSS tokenizer từ HF — transformers `trust_remote_code`), RTF 0,24–0,27 sau lần làm ấm (CPU 4–6), VRAM 475 MiB.
      → Đủ nhanh để làm giọng lồng tiếng sản xuất. Chưa nối vào Studio (cần PLAN: worker gọi venv riêng, giữ model nạp sẵn).
    - Ghi nhận (không phải do phiên này, không sửa): Maintenance `drop_ready_without_file` 01:53 UTC 31/10 chuyển 261
      `viral_materials` READY → FAILED «Không còn file video» (226 tiktok, 35 facebook). Buffer vẫn gọi `/buffer-media/`
      của vài id trong số này (1449, 1450, 1505, 1506) → 404 → bài đó trên Buffer sẽ lỗi. Vì sao file mất chưa rõ — việc
      của phía Buffer / Anti.
  - Anh vào «Kênh & mẫu» thêm Uyển Nhi (D4), chọn mẫu; bật «Nhận reup» khi muốn video reup của kênh đi qua Studio.
  - P5: video AI (script → voice → visuals, cần key Pexels). P6: thí điểm Uyển Nhi 7 ngày rồi chuyển kênh + dọn code cũ. Giờ đăng theo `studio_channels.slot_hours` để P6.

---

## Phiên 2026-10-31 (admin-router) — PLAN-110: tách UI admin, nối AdminRouter, panel.py 1.725 → 477 dòng (đã commit)

- Chủ bot: «em làm bước 2 và bước 3 cho anh luôn nha». PLAN-110 (`agents/plans/active/`) ghi phạm vi + proof.
- **Bước 2:** `admin/ui/` = `keyboards.py` + `views.py` + `glossary.py`, `__init__` re-export (đường import cũ không đổi).
- **Bước 3:** `admin/routes.py` đăng ký 20 handler vào `AdminRouter`; tách khỏi panel: `handlers/shopee.py`, `simulation.py`, `policy.py`, `history.py`, `admin/common.py`. Luật giữ trạng thái chờ và thứ tự gõ chữ giữ y cũ (khai báo `keeps_state` từng handler).
- Kiểm tra: so bản cũ / mới cùng 196 nút + 12 lượt gõ → 220 phản hồi giống hệt; toàn bộ test cashback (chặn TCP) 1123 qua + 1 hỏng sẵn `test_b9`; ruff sạch.
- Không đụng: `app/features/studio/render/encoder.py`, `PROJECT.md` (phiên khác).
- **Next:** restart `systemctl restart cashback-bot cashback-zalo`; archive PLAN-110 khi đã chạy thật.

---

## Phiên 2026-10-31 (admin-pkg) — Gom admin_*.py vào package cashback_bot/admin (Bước 1)

- Commit b60296b trên origin/main (chủ bot: «em commit và push Bước 1»). Bản tái cấu trúc do phiên khác làm; phiên này review + kiểm lại.
- 20 file `admin_*.py` chuyển nguyên vào `cashback_bot/admin/` (`panel` = admin_policy cũ, `ui`, `notify/`, `handlers/`), chỉ đổi import + đường dẫn migration. File cũ là shim `sys.modules[__name__] = <module mới>` (giữ tên `_private`, `mock.patch` trên đường cũ vẫn tác dụng).
- `AdminRouter` / `BaseAdminHandler` / `AdminContext` mới là khung, **chưa nối vào `panel.py`** — hành vi bot không đổi.
- Kiểm tra: toàn bộ `tests/test_cashback_*.py` (chặn TCP) 1102 qua, 1 hỏng sẵn `test_b9`; ruff `cashback_bot` sạch; import `service` / `poller` / `zalo_bot` chạy.
- **Next:**
  - Chủ bot restart (`systemctl restart cashback-bot cashback-zalo`).
  - Bước 2 (tách `admin/ui/__init__.py` 1.193 dòng thành keyboards / views / glossary) và Bước 3 (nối Router, tách `panel.py` 1.725 dòng) cần PLAN của Anti. Bước 3 phải giữ: luật dọn trạng thái chờ hẹp hơn prefix (ví `c:wl:mv:` / `c:wl:vb:`; insights `c:in:cost`, `c:in:f`, `c:in:t:*`), thứ tự `consume_text` (`/tim` → cookie → mô phỏng → hỗ trợ → ví → giữ chân → insights → dự phòng → chia → số chính sách), adapter cho `ReconciliationAdmin.route(data)` / `AutoSyncAdmin.route(data, now, notice)`.

---

## Phiên 2026-10-31 (ux-4line) — Thẻ link 4 dòng, Zalo một tin, relay gọn link, bảng hoa hồng admin

- Commit ee9a1d6 trên origin/main (chủ bot yêu cầu).
- **Thẻ link:** 🛍️ tên · 🏷️ giá tham khảo · 💰 hoàn dự kiến (+ «có thể cao hơn») · 👉 bấm Mua. Món 0đ: «Món này hiện không có tiền hoàn», không có nút Lưu ý. Nút `🛡️ Lưu ý trước khi mua` = `u:tip:<cờ>` (2 = V1.2, t = TikTok, c = giá cao); `tip_reply` gửi **tin mới** (service `keep`), có: mua qua nút, món trong giỏ, đúng món, voucher, giá cao (nếu c), sàn báo đơn ~1 ngày, câu 🔒, chữ nhỏ V1.1/V1.2. Thẻ cũ `u:tip` vẫn mở được. Bỏ popup `TIP_ALERT`.
- **Zalo:** `render` gộp thẻ + dòng dẫn + URL vào một tin; bỏ câu «Bấm 🛒 Mua… bên dưới». `ZaloSender` truyền nhãn nút link: nút khác Mua/TikTok/Food dẫn bằng chính nhãn (vd «👉 🎟 Lưu mã trên Shopee:»).
- **sale_relay:** `post_html` bỏ link trùng nút khỏi chữ, link còn lại thành `<a>` «🔗 Lưu mã» / «🔗 Mua ngay» / «🔗 Link»; cắt bằng `fit_html`. Dùng cho kênh và tin khách.
- **Admin:** bảng link `<pre>`: Giá tham khảo ─ Hoa hồng (· từ shop / Shopee) · Phí · Thuế ─ Quỹ chia · Khách nhận · Biên lãi. Bảng đồng bộ cột `# Giá HH Phí/T Khách Biên TT`.
- Kiểm tra: toàn bộ `tests/test_cashback_*.py` (chặn TCP ra ngoài) qua hết trừ `test_b9` có sẵn; ruff `cashback_bot` sạch (3 lỗi lint test có sẵn từ HEAD: test_cashback_admin, admin_ui_ux, wallet).
- **Next:** chủ bot restart (`systemctl restart cashback-bot cashback-zalo`).

---

## Phiên 2026-10-31 (relay-perf) — sale_relay chạy nền, bớt HEAD/DNS, lưu mã vào voucher_posts

- Commit da06502 trên origin/main (chủ bot yêu cầu sửa mục 1–4 + gắn extract_voucher_codes).
- `tick` chỉ khởi động lượt quét trong luồng nền (khoá `_running`, không chạy chồng); `run_once` là lượt quét đồng bộ.
- `resolve_shopee_link`: an_redir lấy origin_link không gọi mạng; chỉ HEAD link rút gọn (s.shopee.vn, shp.ee, vn.shp.ee, shope.ee), tới trang shopee.vn thì dừng; `requests.Session` theo từng luồng; cache DNS + link chỉ trong một lượt quét (`_RUN`). Pool chung 4 luồng; thay link một lượt `re.sub`.
- `extract_voucher_codes` + `store_codes`: mỗi bài mới ghi mã vào `voucher_posts` (channel_id = `source_channel_id('nhomsansale')`, message_id = post_id*100+thứ tự, sent=0 nên voucher.tick không gửi lại; mã đã có trong 24 giờ thì bỏ). Bài một link: url = link đó; nhiều link: url trống. /magiam hiện các mã này.
- Test patch `requests.head` đổi sang `cashback_bot.sale_relay._head`. Kiểm tra: ruff sạch; toàn bộ `tests/test_cashback_*.py` (chặn TCP ra ngoài) 1098 passed, 1 failed `test_b9` có sẵn.
- **Next:** chủ bot restart (`systemctl restart cashback-bot cashback-zalo`) để chạy bản mới.

---

## Phiên 2026-10-31 (cb-review) — Review và commit phần cashback chưa commit của phiên khác

- Chủ bot yêu cầu «review lại cashback rồi commit và push». Commit 5b1a912 trên origin/main: shop_voucher (PLAN-105), sale_relay, WAL cho DB, escape HTML, URL nút an toàn, fcntl dự phòng, service.py CRLF → LF.
- Đã báo chủ bot trước khi commit, chủ bot chọn **giữ nguyên** cả hai:
  - `sale_relay`: mỗi 90 giây đọc t.me/s/nhomsansale, gọi HEAD s.shopee.vn để mở link rút gọn, thay affiliate của nhóm đó bằng affiliate chủ bot (sub_id `AUTOSALE`), đăng kênh ZT báo mã và gửi mọi khách nhận báo mã. Bỏ qua chế độ thử, giờ yên lặng, trần ngày của PLAN-107; không có cờ tắt; không có PLAN (docstring ghi PLAN-106 nhưng PLAN-106 là video studio). 31/10 02:00Z đã gửi 17 khách «Mã 25% Shopee vip». Đơn qua sub_id AUTOSALE không gán được cho khách.
  - `shop_voucher` (`shop_voucher_enabled=1` trên production): nút shop dùng sub_id `VOUCHERS`, khách mua ngay trong shop thì đơn không gán được cho khách. Đoạn gọi bridge 9224 (cào Shopee qua CloakBrowser theo PLAN-105) không còn nút nào gọi tới.
  - Tin relay dùng event_type VOUCHER nên tính vào trần 2 tin/ngày của PLAN-107: ngày có relay thì mã AddLiveTag có thể không tới khách.
- Lỗi do WAL tìm thấy khi review: bản backup mang cờ WAL, kiểm tra chỉ đọc để lại `-wal`/`-shm` cạnh file (test_cashback_offsite hỏng). Đã sửa `backup._copy_consistent`: bản sao về `journal_mode = DELETE`.
- Kiểm tra: ruff sạch; toàn bộ `tests/test_cashback_*.py` (chặn TCP ra ngoài) 1088 passed, 2 failed: offsite (đã sửa, chạy lại qua cùng 81 test backup) và `test_b9` có sẵn. DB production đã ở WAL từ lần restart 31/10 02:19Z.
- Chưa commit (ngoài phạm vi cashback): app/, PLAN-106, PLAN-108, test admin/media/facebook, PROJECT.md, ecosystem.config.js, .importlinter.
- **Next:** chủ bot restart để chạy bản backup đã sửa (`systemctl restart cashback-bot cashback-zalo`). Nếu muốn khách không mất hoàn: đổi sub_id nút shop và relay sang sub_id của khách / tách event_type relay khỏi trần (cần chủ bot duyệt).

---

## Phiên 2026-10-31 (ux107) — PLAN-107: báo mã có giờ yên lặng, thẻ link gọn, tiến trình đơn

- Chủ bot gửi bài «5 điểm bất tiện của End-User», duyệt plan «theo em đề xuất». Commit fa30fd7 trên origin/main (nhánh `feat/cashback-ux-107`, worktree `/home/vu/toolsauto-ux107`).
- Đối chiếu dữ liệu thật: bot thấy đơn sau 7,8–34,5 giờ (trung bình 21,6) chứ không phải 15–30 phút; rút tối thiểu 10.000đ, không phải 50k; tối 30/10 có 3 tin mã gửi 17 khách lúc 23:20–00:02 giờ VN.
- **Báo mã (voucher.py):** chế độ «mọi khách» xếp hàng `voucher_posts.sent = -1`, `voucher.tick` (vòng poller) gửi ngoài 22h–8h, gộp mã đến gần nhau (chờ 2 phút, tối đa 10), ≤5 mã/tin, không lặp mã 24 giờ, tối đa 2 tin/ngày/khách. Admin nhận ngay. Chế độ thử giữ nguyên. Màn admin 🎟 ghi luật mới + số mã đang chờ.
- **Thẻ link 17 → 10 dòng:** còn số hoàn (+ «có thể cao hơn»), ⚠️ mua thẳng app, 🛒 món trong giỏ, 🎟 voucher, 💎 món giá cao, ⓘ V1.2, 👉 nút. Popup 🛡️ Lưu ý 193/200 ký tự. Câu ⓘ V1.2 và dòng voucher giữ trên thẻ (công bố + quyết định 27/10).
- **/donhang:** thanh `✅ Đã mua › ⏳ Hoàn thành › ⚪ Sàn duyệt › ⚪ Vào ví`; câu «Đơn mới thường hiện sau khoảng 1 ngày». **/huongdan Telegram:** chia sẻ thẳng sang bot.
- Gộp vào main: tạm stash phần chưa commit của phiên khác trong `messages.py`, `poller.py` → ff → pop sạch, không xung đột; phần đó vẫn chưa commit, giữ nguyên.
- Kiểm tra: ruff sạch; worktree 945 passed + 2 test canh chữ đã sửa (180 passed); còn `test_b9` lỗi có sẵn.
- **Chưa restart.** Production đang chạy cả code chưa commit của phiên shop_voucher (PLAN-105, `shop_voucher_enabled=1`).
- **Next:** chủ bot chạy `systemctl restart cashback-bot cashback-zalo`; sau restart kiểm tra tin mã đầu tiên ngoài 22h–8h. Đo lại 14 ngày (mốc trước: 91 link / 17 khách → 6 link có đơn, ~6,6%). PLAN-107 còn ở active tới khi đo xong.

---

## Phiên 2026-10-30 (buffer-chk2) — Báo cáo Buffer: Maintenance tắt từ 14:53 (chỉ đọc log + DB)

- **WSL tắt 07:53Z (14:53 VN), khởi động lại 07:54Z và 08:00Z.** Bot cashback và store_bot (systemd) tự lên lại. PM2 không có `pm2 startup` nên Maintenance, Web_Dashboard, 9Router_Gateway và DB_Backup **không chạy lại**; không còn xếp lịch Buffer mới. Danh sách tiến trình cũ còn trong `~/.pm2/dump.pm2` (đã chép ra `dump.pm2.before-20261030-reboot`). Lúc 08:50Z một lệnh `pm2 jlist` khi kiểm tra đã bật daemon PM2 rỗng.
- Buffer vẫn giữ bài đã hẹn nên page còn lên bài tới: Sống Nhẹ 01/11 14:30; trnvp89, Hoa Lệ Đây, Uyển Nhi 02/11.
- Job: 29/10 có 14 DONE, 3 FAILED; 30/10 tới 14:53 có 8 DONE, 2 FAILED. Cả 5 lỗi đều «Scheduled posts limit reached 10/10» rơi đúng giờ hẹn (19:00, 19:30, 14:01), cùng kiểu đã báo ở (buffer-chk). 2/5 request của ZVsP trong ngày bị phí vì lỗi này.
- Suất 30 ngày còn: f8pL 1387/2000, RZX2 466/2000, ZVsP 81/1000 (khoảng 5 request/ngày, còn khoảng 16 ngày).
- Sync «đã đăng» vẫn tắt trên cả 3 key (mức giữ 70%): lần xác nhận cuối là 28/10 22:29. Qua giờ hẹn mà chưa xác nhận: Hoa Lệ Đây 25, Sống Nhẹ 16, trnvp89 14, Uyển Nhi 5.
- Kho READY chưa hẹn: Hoa Lệ Đây 179, Sống Nhẹ 21, trnvp89 11, **Uyển Nhi 0** (sau 02/11 15:30 hết bài). Từ 29/10 không có video mới.
- **Đã bật lại (chủ bot duyệt), 09:30Z:** `pm2 start ecosystem.config.js --only Maintenance,9Router_Gateway,Web_Dashboard,DB_Backup` + `pm2 save`. 3 app online, 0 restart; DB_Backup chạy 1 lần (pg_dump 7,1 MB, offsite bỏ qua vì không thấy ổ G:) rồi stopped như cấu hình cron. Dashboard trả 401 (cần đăng nhập, bình thường). Lỗi `9Router provider auth unavailable (404)` có từ trước (272 lần trong log), AI tự chuyển sang Gemini và chạy được. `pm2 startup` bị chặn quyền, **chưa cài** nên WSL khởi động lại thì PM2 vẫn không tự lên.
- Chủ bot đã chạy `pm2 startup`: `pm2-root.service` enabled (ExecStart `pm2 resurrect`), dump.pm2 lưu 09:31Z gồm Maintenance, 9Router_Gateway, Web_Dashboard, DB_Backup. Lần WSL khởi động lại tới PM2 sẽ tự lên. Bật nguồn video cho Uyển Nhi. Sửa lỗi race hàng chờ và sync bị mức giữ 70% chặn thì cần PLAN backend.

---

## Phiên 2026-10-30 (git-clean) — Dọn worktree và nhánh local

- Đã xoá worktree `/home/vu/toolsauto-cashback-notifications` (sạch, a15663f đã có trên origin/main).
- Đã push `cursor/feat-douyin-longvideo-login` (aa3d519, 5 commit 23/09, ~1.700 dòng: cookie Douyin từ Chrome, hoãn cắt video dài, thư mục Drive đánh số + ADR-045 bản Drive, login SPA, key Gemini AQ). **Chưa có trên main**, cần review trước khi merge (tách từ 20/09, đụng viral/đăng bài).
- Xoá 143 nhánh local: 127 đã merge vào origin/main + 16 có nội dung trùng main (theo `git cherry`; phần lệch chỉ là commit khởi tạo lịch sử cũ). Sau đó chủ bot tự chạy `git push origin --delete` 122 nhánh trên origin (đã kiểm tra: đều có trên main, 0 PR mở). origin giờ còn 4 nhánh: `main`, `cursor/feat-douyin-longvideo-login`, `develop`, `rollback/plan079-compat`.
- 4 nhánh đã xoá chỉ có ở local, giữ SHA để khôi phục (`git branch <tên> <sha>`, còn tới khi git gc): `ag/feat-ping-gemini-ui` d3c030a, `backup/local-main-before-sync-20260908-072441` 151e5a6, `backup/main-20260313-024514` 1a91861, `cashback-alt-crosscheck` 4cf6159.
- Còn lại local: `main`, `cursor/feat-douyin-longvideo-login`, `develop` (4 commit tháng 5 chưa có trên main), `rollback/plan079-compat` (nhánh dự phòng). Stash cũ `wip develop before checkout origin/main 20260908-072441` vẫn giữ.

---

## Phiên 2026-10-30 (reup-wm) — Gỡ tự làm mờ watermark khi reup

- Commit 68b06b9 (tự nhận diện + làm mờ watermark/chữ ký tác giả bằng `delogo`, test trên ảnh Allyollyo) đã lên origin/main; working tree có sẵn bản gỡ nhưng để 2 file rỗng 0 byte. Đã gộp thành 0291766 `Revert "feat(reup)…"`: xoá `watermark_blur.py` + test, `reup_config`/`reup_processor` về đúng như trước 68b06b9.
- Lý do: làm mờ chữ ký tác giả trên nội dung người khác để đăng lại là xoá ghi nguồn. Code chưa từng chạy thật (Maintenance chạy từ 25/10, log không có dòng làm mờ nào).
- Kiểm tra: không còn tham chiếu, ruff sạch; test reup/viral 484 qua, 4 hỏng ở `test_notify_jobless.py` (caption/Whisper) hỏng y hệt trên HEAD trước khi gỡ, ngoài phạm vi.
- Mục (buffer-chk) ngày 29/10 (kiểm tra Buffer) không còn trong file — bị ghi đè lúc rebase/commit của phiên khác, chưa ghi lại.
- **Next:** không dựng lại tính năng làm mờ chữ ký tác giả. Hướng nội dung: xin phép tác giả và giữ ghi nguồn, hoặc tự làm hoạt hình mẹo cùng dạng.

---

## Phiên 2026-10-30 (el) — Báo mã: link lưu mã gắn affiliate + chế độ thử chỉ admin

- Chủ bot: «đăng tay thì gắn được mã aff không» → thử 1 lần trên Chrome chủ bot (cầu nối 192.168.112.1:9223): an_redir bọc trang mã mở đúng trang, URL đích có `utm_medium=affiliates`. a15663f: link trang mã shopee.vn trong kênh tự bọc an_redir, sub_id chung `VOUCHERS` (đơn không gắn khách, chủ bot có hoa hồng).
- Chủ bot: «cần test trước cho admin đã» → `bot_state.voucher_audience`: mặc định chế độ thử, chỉ gửi admin (tin có dòng 🧪); /admin → 📣 Nhắc mùa sale → 🎟 Báo mã: 📣 Bật gửi khách / 🧪 Về chế độ thử.
- Shopee: lần 1 Chrome chủ bot bị trang xác thực chống bot → dừng; chủ bot xác minh, chủ bot bảo thử lại 1 lần → đọc được trang Mã giảm giá. 1 request `requests` tới API voucher (chủ bot duyệt) → 403 `90309999`, dừng. Không tự động hoá Shopee thêm.
- Test: toàn bộ 941 qua + 1 hỏng có sẵn (`test_b9…`) trước chế độ thử; sau đó 144 test liên quan qua. Ruff sạch. Main có commit phiên khác (store, reup) → cherry-pick sang nhánh `feat/cashback-voucher-aff2`.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` (nạp a15663f, về chế độ thử); thử bằng tin đăng tay có link mã; ổn thì bấm 📣 Bật gửi khách. Cầu nối: chủ bot chạy `tat-cau-noi-chrome.ps1` (Administrator) khi không cần.

---

## Phiên 2026-10-29 (store-6) — Bot bán hàng: chỉnh tăng giá trong /admin

- Chủ bot muốn tăng giá không phải sửa code, và thấy trước dòng tiền khi chọn. Làm: /admin → 💲 Tăng giá bán (mức chung: +5/10/15/20/30%, +2k/5k/10k, gõ mức khác; giá riêng từng món). Bấm mức → xem trước giá cũ → mới, lãi/món, doanh thu/lãi nếu bán như 30 ngày qua, ví FatCat đủ giao bao nhiêu → ✅ Áp dụng mới đổi giá.
- Code: `store_bot/pricing.py` mới; `Fulfiller.price_for/preview/set_markup`; `db.reprice_upstream`, `db.sales_by_product`; state `markup`, `markup:<upstream_id>`. Chưa đổi giá thật (mức mặc định = giá lẻ FatCat như cũ).
- Proof: 55 test qua, ruff sạch; xem trước trên bản sao DB thật đúng giá.
- **Next:** chủ bot `sudo systemctl restart store-bot store-api` rồi vào 💲 Tăng giá bán.

---

## Phiên 2026-10-29 (buffer-chk) — Kiểm tra Buffer và đăng bài (chỉ đọc log PM2 + DB, không gọi API, không sửa code)

- Tiến trình: Maintenance (đăng Buffer) và Web_Dashboard chạy. FB_Publisher, AI_Generator, Threads_* dừng từ 20/10. Log lỗi không có lỗi mới.
- Job Buffer theo ngày (DONE/FAILED): 25/10 17/0, 26/10 14/2, 27/10 14/1, 28/10 14/5, 29/10 7/0 (tới 14:25). Mỗi kênh có 10 bài hẹn sẵn, xa nhất 31/10 (Sống Nhẹ) và 01/11 (3 kênh còn lại).
- 8 lỗi trong 4 ngày: 7 lỗi «Scheduled posts limit reached 10/10», đều rơi đúng giờ hẹn (08:00, 15:30, 19:00, 19:02, 19:30). DB coi bài hết hàng chờ ngay khi qua `schedule_ts` (`queue_job.py:486-499`), còn Buffer cần vài phút mới đăng xong, nên gửi CreatePost lúc đó bị từ chối và tốn 1 request. Lỗi còn lại: job 1216 (trnvp89) «Video could not be read from its URL».
- Suất 30 ngày còn lại (dòng log cuối): f8pL 1397/2000, RZX2 471/2000, ZVsP 86/1000. Các số «1430/2000…» ở mục (buffer-pol) là suất còn lại, không phải đã dùng. f8pL vừa xuống dưới ngưỡng giữ 1400, nên **cả 3 key đều chặn request nền**, kể cả PostStatuses (sync «đã đăng»). Đăng bài vẫn chạy. ZVsP tụt 90 → 86 từ 28/10, khoảng 4 request mỗi ngày.
- Hệ quả: bot không còn xác nhận được bài đã lên. Đã qua giờ hẹn mà chưa POSTED: Hoa Lệ Đây 22 bài (từ 20/10), trnvp89 11 bài (từ 26/10), Sống Nhẹ 10, Uyển Nhi 1. Bài lỗi phía Buffer cũng không được báo.
- Kho READY chưa hẹn: Hoa Lệ Đây 182, Sống Nhẹ 27, trnvp89 14, **Uyển Nhi 3** (khoảng 1 ngày sau khi hết 10 bài đang hẹn, tức khoảng 02/11). Từ 25/10 không có video mới; nguồn duy nhất đang bật (nunhanthongtue → Sống Nhẹ) đang bỏ quét vì page đủ 15 video.
- Lỗi nhỏ: log «Bo qua N kenh — key dang cooldown…» (`queue_job.py:229-232`) cũng đếm cả kênh đầy hàng chờ. `cluster_router.py:630-633` vẫn tìm chữ `100-in-15min`/`250-in-1day`. `buffer_cooldown.json` còn 2 mục của key cũ (hash không khớp key nào đang dùng), vô hại.
- **Next (chủ bot chọn):** (1) xem tab Sent/Error trên web Buffer hoặc page thật để biết bài Hoa Lệ Đây/trnvp89 có lên không (web không tốn suất API); (2) bật nguồn cho Uyển Nhi trước khoảng 02/11; (3) nếu muốn sửa thì cần PLAN backend: chừa vài phút sau giờ hẹn khi đếm hàng chờ, và cho PostStatuses vượt mức giữ 70% với số request nhỏ.

---

## Phiên 2026-10-28 (buffer-pol) — Buffer đổi giới hạn API (chỉ báo cáo, không sửa code)

- Trang https://developers.buffer.com/guides/api-limits sửa lúc 06:18Z ngày 28/10. Header thật trên cả 3 key đã đổi theo.
- Gói Free: 15 phút 100 → 150; 24 giờ 250 → 600; 30 ngày từ 3000 cố định → **1000 × số kênh mở khoá (tối đa 3000)**. Mọi key/MCP của một tổ chức dùng chung một suất.
- Suất đã dùng giữ nguyên, chỉ trần giảm (log Maintenance): f8pL 1430/2000, RZX2 475/2000, **ZVsP 90/1000** (key 1 kênh = trnvp89). Tổng trần 30 ngày của 3 key: 9000 → 5000.
- Mức giữ 70% tính theo cửa sổ chật nhất (giờ là 30 ngày): RZX2 + ZVsP đã chặn request nền (post_statuses); f8pL còn ~30 request là bị chặn. Đăng bài vẫn chạy tới khi r=0 → key nghỉ theo t (trần 72 giờ).
- Lỗi hiển thị: `cluster_router.py:630-633` tìm đúng chữ `100-in-15min` / `250-in-1day` → trang cluster đọc sai số. `client._note_budget` đọc theo mẫu chung nên vẫn đúng.
- Tốc độ dùng từ lúc Maintenance khởi động lại (25/10 14:17Z, khoảng 2,7 ngày): f8pL +189 (khoảng 70/ngày, phần lớn request nền), RZX2 +11, ZVsP +24 (khoảng 9 CreatePost/ngày). Ước tính: f8pL và RZX2 đủ hơn 30 ngày; **ZVsP hết sau khoảng 10 ngày** nếu suất không hồi. Trong 2,7 ngày suất 30 ngày chưa hồi lần nào, nên chưa biết cửa sổ này cuốn chiếu hay đặt lại cả cửa sổ.
- Không cần quét thêm: mỗi request đã ghi đủ 3 cửa sổ vào log. Ping hoặc mở trang cluster lại tốn suất (nhất là với ZVsP).
- Kho video (DB, 28/10), tính bài đã hẹn + READY chưa hẹn rồi chia số bài/ngày: Uyển Nhi 16 bài, khoảng 5 ngày (nguồn tắt); Sống Nhẹ 41 bài, khoảng 8 ngày (nguồn nunhanthongtue bật, vào khoảng 5 video/ngày); trnvp89 27 bài, khoảng 9 ngày (nguồn tắt); Hoa Lệ Đây 195 bài, khoảng 65 ngày; twot283 0 bài, không có nguồn. Chỉ 1/6 nguồn đang bật. ZVsP: 10 bài tốn 24 CreatePost, trung bình 2,4 request mỗi bài, nên xem lại.
- **Next (chủ bot chọn):** gắn thêm kênh cho tài khoản ZVsP (lên 2000–3000) hoặc giảm tải key đó; muốn sửa mức giữ 70% hoặc regex dashboard thì cần PLAN riêng.

---

## Phiên 2026-10-30 (ek) — Báo mã: thử thật, bỏ giới hạn, gửi mọi khách

- Chủ bot làm xong: bot chuyển tin `zt_noti_voucher_bot`, kênh riêng tư «ZT báo mã» (đã gắn), AddLiveTag theo dõi `METAPARIGDOCT2211` (Instagram giảm 22%, tối đa 300K, đơn từ 50K, hiệu lực tới 2038). Thử mã tay `TEST123` → bot gửi chủ bot sau 1 giây; chủ bot bảo gỡ → backup `cashback-manual-20261030T060926Z.sqlite`, đặt `TEST123` = out.
- Chủ bot: «cứ có mã là báo, không cần giới hạn gì hết» + chọn gửi mọi khách, 0h nhắn ngay. 56e589e: gửi mọi khách đã tạo link (khách tự tắt bằng 🔕 / `/magiam`), bỏ khung 8–22, bỏ cách 12 giờ, bỏ 3 tin / ngày. Toàn bộ test 940 qua, 1 hỏng có sẵn (`test_b9…`).
- Tìm mã Shopee (Chrome WSL, không đăng nhập, chỉ đọc): Voucher Xtra `VCXBL1030` / `VCXBH1030` / `VCXBHH1030` đang hết lượt; 11.11 chỉ có mã SPayLater; còn lại mã người mới.
- Điều khiển Chrome Windows: gọi Windows từ WSL chập chờn (`UtilAcceptVsock accept4 failed 110`). Đã viết `C:\Users\Admin\claude-tools\` (cầu nối portproxy 9223 chỉ trên card WSL + luật tường lửa, file gỡ, file mở Chrome). Lệnh admin bị chặn tự động; chủ bot chạy lần 1 chưa có quyền Administrator → chưa bật.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` (nạp 56e589e). Chủ bot chạy lại script cầu nối bằng Administrator nếu muốn em dùng Chrome Windows; xong việc chạy `tat-cau-noi-chrome.ps1`.

---

## Phiên 2026-10-30 (ej) — PLAN-104: báo mã giảm giá Shopee qua AddLiveTag Theo dõi Voucher

- Chủ bot chọn hướng 2 (báo mã ngay trong bot, «all in one»). Khảo sát qua Chrome của chủ bot (profile `shopee-affiliate-poc`, chủ bot đăng nhập): API `api/portal/voucher-*.php` chỉ có phiên đăng nhập web, không có API key; kho mã dùng chung có 1 mã (đã hết); gói 1 kênh / 3 link. Đã xoá file ghi mạng và mã nguồn tạm.
- Cách A, 7f31b75: AddLiveTag → **bot chuyển tin riêng** → kênh Telegram riêng tư → bot hoàn tiền (quản trị kênh) đọc `channel_post` → gửi khách đã bật (Telegram + Zalo):
  - đọc mẫu tin mặc định AddLiveTag, mẫu có nhãn, tin hết mã; link Shopee trong tin thành nút 🎟 Lưu mã;
  - 8:00–22:00, một mã cách 12 giờ, tối đa 3 tin / khách / ngày; khách tự bật (mặc định tắt);
  - `/magiam` (Zalo `magiam`), nút 🎟 Mã giảm giá ở trang chủ khi đã gắn kênh;
  - admin: 📣 Nhắc mùa sale → 🎟 Báo mã: gắn / gỡ kênh, bật / tắt, số liệu.
- Không dùng token bot hoàn tiền cho AddLiveTag (tranh `getUpdates`, lộ quyền điều khiển, bot không đọc được tin của chính mình).
- Bảng mới `voucher_posts`. Backup trước restart: `cashback-manual-20261030T043250Z.sqlite`. Toàn bộ test 940 qua, 1 hỏng có sẵn (`test_b9…`). Ruff sạch.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo`, rồi làm 5 bước trong PLAN-104 («Chủ bot làm sau khi restart»). Sau «Gửi thử» trên AddLiveTag: kiểm chỉ đọc `voucher_posts` (bot đọc đúng mã, có link hay không).

---

## Phiên 2026-10-29 (ei) — Tin giới thiệu watch-v1

- Chủ bot: «làm thông báo gửi tới mọi người có tính năng mới». Thêm tin `watch-v1` vào 📣 Tin giới thiệu: theo dõi giá, deal gửi liền, ShopeeFood sắp có; nút 🔥 Deal hôm nay / 📋 Món đang theo dõi. Zalo: `/deal` → «gõ deal».
- Không tự gửi: chủ bot xem trước và bấm ✅ Gửi trong /admin → ⚙️ Cài đặt → 📣 Nhắc mùa sale → 📣 Tin giới thiệu. Hiện 17 khách đã tạo link.
- Toàn bộ test 932 qua, 1 hỏng có sẵn (`test_b9…`). Ruff sạch.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` rồi bấm gửi.

---

## Phiên 2026-10-29 (eh) — Kiểm log sau restart + sửa link an_redir dán lại

- Sau restart 08:48Z (code 9291c12): không lỗi; bảng `price_watches` đã có; lượt theo dõi giá 15h chạy (0 món); deal 15h gửi 1 tin; hàng đợi hôm nay 13 tin sent, không kẹt.
- Lỗi trong ngày đã tự hết: Telegram mất kết nối 00:39–01:17Z (HTTPError/502/ReadTimeout); deal hời 07:04Z AddLiveTag ReadTimeout 1 lần.
- Lỗi khách: 08:51Z khách Zalo dán lại link an_redir bot đã gửi (link #81) → bot hỏi AddLiveTag như link rút gọn → `api_status` → khách nhận «Chưa lấy được dữ liệu». Sửa `shopee_url` (lấy `origin_link` bên trong; an_redir Food → luồng Food; an_redir lồng / thiếu gốc thì bỏ). Test mới, toàn bộ 931 qua, 1 hỏng có sẵn (`test_b9…`).
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo`.

---

## Phiên 2026-10-29 (eg) — PLAN-103: theo dõi giá (🔔 trên thẻ link)

- Chủ bot: «cứ có giảm là thông báo»; khách muốn thì điền giờ kiểm, không điền thì kiểm theo lượt chung. 64d6db3:
  - thẻ link Shopee có 🔔 Báo khi giảm giá; theo dõi 30 ngày, tối đa 10 món / khách;
  - mặc định mỗi giờ 7–21 (history.php, thấy rẻ thì đọc product-data xác nhận; một món cách 6 giờ);
  - giờ riêng tối đa 4 giờ trong 6–23, tới giờ đọc product-data; giá thấp hơn lần trước bot thấy là nhắn;
  - `/theodoi` (Zalo `theodoi`); admin bật / tắt ở 📣 Nhắc mùa sale; chế độ báo giảm giá tự động bỏ món đang theo dõi.
- Bảng mới `price_watches` (tự tạo khi khởi động). Backup trước restart: `cashback-manual-20261029T084733Z.sqlite`.
- Toàn bộ test 930 qua, 1 hỏng có sẵn (`test_b9…`). Ruff sạch.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` (gồm (ed), PLAN-102, PLAN-103). Sau restart kiểm chỉ đọc: có bảng `price_watches`, `bot_state.price_watch_list_scan` chạy giờ tròn.

---

## Phiên 2026-10-29 (ef) — PLAN-102: link ShopeeFood chia sub_id riêng

- Chủ bot: «vẫn chia theo subid, lỡ nếu có thì làm căn cứ». 8c19ac9: mỗi lần gửi link Food một sub_id mới ghi `link_requests` (`food_link`, platform `shopeefood`, không lưu link Food). Đơn trùng sub_id Food không gắn khách, không thành tiền hoàn; sub_id vẫn lưu trên đơn để đối chiếu tay.
- Toàn bộ test 919 qua, 1 hỏng có sẵn (`test_b9…`). Ruff sạch.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` (gồm (ed) và PLAN-102).

---

## Phiên 2026-10-29 (ee) — FOODTEST kết quả + PLAN-102 link ShopeeFood

- FOODTEST: app Shopee (ShopeeFood → Hiệu quả tiếp thị 28/10) ghi 1 click, 0 đơn; tab «Đơn chuyển đổi» trống. Link an_redir Food được ghi click, đơn tự đặt chưa được tính (chưa rõ lý do; nghi tự mua). Ghi ở PLAN-098.
- Chủ bot yêu cầu: khách gửi link ShopeeFood thì báo «hoàn tiền Food sắp có» và vẫn gửi link đặt món gắn affiliate. PLAN-102 (34da621): nút «🛵 Đặt trên ShopeeFood», sub_id chung `FOODLINK`, không lưu link; Zalo có tin link riêng ghi «đơn Food chưa được hoàn tiền».
- Toàn bộ test 919 qua, 1 hỏng có sẵn (`test_b9…`). Ruff sạch.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` (gồm cả bản sửa tin kỳ thanh toán (ed)). Muốn biết Food có tính đơn không: nhờ người khác (tài khoản khác) đặt qua link bot; 30/10 khi chủ bot nói «kiểm FOODTEST» thì đọc `source=food` AddLiveTag 1 lần.

---

## Phiên 2026-10-29 (ed) — PLAN-101: tin kỳ thanh toán ghi trạng thái Shopee

- 10:56 bot gửi tin kỳ 17315920094261029 (lượt đồng bộ 03:55Z: 2 kỳ đọc được, không lập trùng kỳ #1). Chủ bot: «phải kiểm tra trạng thái rồi mới báo»: tin chưa ghi trạng thái Shopee mà đã có nút ✅ khi Shopee còn «Đang xử lý».
- Sửa `shopee_payout.py` (09383a5): đọc `payout_status` (2 = Đang xử lý, mã lạ hiện số) và `payment_completed_time`. Tin có dòng «Trạng thái Shopee: …». Chưa chuyển thì chỉ có «🧾 Xem kỳ», dặn bot báo lại. Shopee ghi đã chuyển thì gửi tin thứ hai có ✅ / ⚠️. Màn kỳ vẫn có hai nút.
- Test 7/7 file payout; toàn bộ 917 qua, 1 hỏng có sẵn (`test_b9…`, phụ thuộc ngày thật). Ruff sạch.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo`. Khi Shopee ghi đã chuyển, bot gửi tin «💸 Shopee đã chuyển tiền» kèm «✅ Đã nhận đúng 22.585đ»; chủ bot đối sao kê VCB rồi bấm.

---

## Phiên 2026-10-29 (ec) — PLAN-101: kỳ thanh toán Shopee tự động

- Chủ bot hỏi «lần sau tự động được không», duyệt hai lượt đọc thử trang thanh toán bằng cookie bot và nút xác nhận tiền về.
- Đọc thử: GraphQL Lịch sử thanh toán / Chi tiết kỳ bị 403 (mã bảo mật trình duyệt, không lách). REST `payment/billing_list`, `payment/billing_detail`, `report/validation_detail/v2` đọc được. Thuế và số sau thuế chỉ có ở GraphQL.
- Sửa kỳ #1 theo số thật (chứng từ #2 thay #1, backup `cashback-manual-20261029T020649Z.sqlite`): hoa hồng 25.371, phí 248. Đơn `261023C6GM20NS` Shopee duyệt 1.373 (bot 1.372) → AMOUNT_MISMATCH. Ngày 27/08 4.510 chưa có mã đơn.
- Code (247fbe8, 6 test mới qua, ruff sạch):
  - cuối mỗi lượt đồng bộ Shopee đọc `billing_list`; kỳ mới (khởi tạo ≤ 14 ngày) tự lập và nhập báo cáo Shopee, chưa có thuế;
  - báo admin kèm «✅ Đã nhận đúng X» (X = sau phí − thuế tạm tính 10%), «⚠️ Số khác». Bấm ✅ thì nhập ngân hàng và thay báo cáo có thuế;
  - ví khách vẫn khoá.
- Toàn bộ test: 916 qua, 1 hỏng có sẵn trên main: `test_b9_doi_tai_khoan_cho_7_ngay…` (test cố định ngày, màn ví dùng giờ thật). Không thuộc phạm vi, chưa sửa.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo`. Lượt đồng bộ Shopee kế tiếp gửi admin tin kỳ 17315920094261029 kèm nút «✅ Đã nhận đúng 22.585đ». Tiền về VCB thì chủ bot bấm; kỳ #1 thành «Khớp một phần».

---

## Phiên 2026-10-29 (eb) — Đối soát kỳ thanh toán Shopee 29/10: đã nhập báo cáo Shopee, chờ tiền ngân hàng

- Chủ bot gửi ảnh kỳ 17315920094261029 (khởi tạo 29/10, «Đang xử lý», sau thuế 22.585đ) và bảo nhập ngay. Backup trước: `cashback-manual-20261029T015558Z.sqlite`.
- Đã nhập `settlement_import`: kỳ #1 (2026-10), chứng từ #1 `shopee_payment_report` chép tay từ ảnh. Tổng: hoa hồng 25.326, phí 203 (191 trên hoá đơn 27/10 + 12 suy ra cho đơn 26/10), thuế giữ 2.538 (TNCN 1.269 + VAT 1.269), sau thuế 22.585, số học khớp.
- 3 đơn bot MATCHED: `261023CC4UWJ0N` 17.368, `261027N7MJJKFV` 2.120, `261023C6GM20NS` 1.372 (tổng 20.860). 4.466 «hoàn thành 27/08» không phải đơn bot, chưa có mã đơn → UNALLOCATED.
- Trạng thái kỳ: EVIDENCE_PENDING (NO_BANK). Không đổi ví, settlement_status vẫn NOT_VERIFIED, không tạo payout.
- **Next:** khi VCB nhận khoản Shopee, nhập chứng từ `bank_statement` (received_vnd) vào kỳ #1. Khớp 22.585 thì kỳ thành PARTIALLY_MATCHED (còn 4.466 ngoài bot chưa có mã đơn). Mở ví vẫn do chủ bot quyết. Đĩa sứ `261027PVSFKR94` (hoàn thành 28/10) vào kỳ sau.

---

## Phiên 2026-10-28 (ea) — PLAN-100: deal hời tự động, có món mới là gửi

- Chủ bot: «bot tự update tự gửi, cứ có là gửi, 1 deal cũng gửi». Chọn: quét 60 phút, tối đa 4 tin/khách/ngày, chỉ 8:00–22:00, bỏ lượt 12:08/20:08.
- Đã làm (57f262f, 911 test qua, ruff sạch): quét mỗi giờ 7:00–21:00 (giờ chẵn/lẻ xen kẽ từ khoá, đủ 10 danh mục) → kho deal `bot_state.deals_pool` (24 giờ). Sau mỗi lượt gửi khách món mới hợp danh mục: 1–3 món/tin, cách ≥ 2 giờ, không lặp món 3 ngày, nhường nhắc sale. Không còn duyệt từng lượt; admin còn bật/tắt và ❌ Bỏ món. 🔥 Deal hôm nay đọc kho (12 giờ).
- Chi phí AddLiveTag khoảng 7 lần trước (15 lượt/ngày). Lỗi 429 thì lượt ghi lỗi, giờ sau quét lại. Theo dõi dòng «🔎 Lượt quét gần nhất» ở màn 🔥 Deal hời.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo`. Đang trong 7:00–21:59 thì quét ngay. Khách nhận tin 20:08 hôm nay phải cách 2 giờ nên tin tự động đầu từ 8:00 29/10. Sáng 29/10 xem màn 🔥 Deal hời: số lượt quét, lỗi 429 nếu có, số tin đã gửi.

---

## Phiên 2026-10-28 (dz) — PLAN-099 đổi hướng: 🔥 Deal hôm nay ngay trong bot

- Chủ bot: «dùng chung con bot hiện tại, không cần tạo kênh». Đã gỡ phần kênh Telegram (revert 21fd968), thay bằng mục deal xem ngay trong bot (60d9134, 912 test qua, ruff sạch). Mục (dy) bên dưới không còn đúng.
- Trang chủ có nút «🔥 Deal hôm nay» (cạnh «🛍️ Danh mục deal»), lệnh `/deal`, Zalo gõ `deal`. Hiện lượt gần nhất đã tới giờ gửi (hôm nay hoặc hôm qua, không hiện bản nháp chưa gửi hay lượt admin bỏ): 8 món, mỗi danh mục 2, danh mục khách chọn lên trước, nút lọc theo danh mục, bấm món ra thẻ link.
- Khi deal hời bật, lượt soạn tìm đủ 10 danh mục (trước chỉ tìm danh mục có người chọn), nên soạn lâu hơn vài phút.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` (bật luôn PLAN-098 bước A, B). Sau restart thử «🔥 Deal hôm nay» trên Telegram và Zalo. Menu lệnh Telegram tự có `/deal` sau restart.

---

## Phiên 2026-10-28 (dy) — PLAN-099: kênh Telegram deal hời

- Chủ bot hỏi cách để khách nhớ tới bot lúc mua, gửi ảnh trang AddLiveTag (hạ giá mạnh, deal khung giờ, nhóm Telegram). Chủ bot duyệt làm kênh deal.
- Đã làm (21fd968, 915 test qua, ruff sạch): kênh tắt mặc định. Admin thêm bot làm quản trị kênh rồi chuyển tiếp 1 bài của kênh vào bot → ✅ gắn. Màn 🔥 Deal hời có 📢 Bật/Tắt đăng kênh, 📤 Đăng bài giới thiệu, 🗑 Bỏ kênh.
- Mỗi lượt 12:08 / 20:08 đăng tối đa 8 món (mỗi danh mục 2), soạn đủ 10 danh mục khi kênh bật. Nút món là `t.me/<bot>?start=dl_<shop>_<item>` → bot tạo link riêng cho người bấm. Bài đi qua hàng đợi chung (audience admin, DEALS_CHANNEL).
- Username bot lấy bằng getMe lúc khởi động (`bot_username`). Không đổi schema, không thêm .env.
- Xem trước bằng bản nháp thật tối 28/10 (chỉ đọc): 7 món. Chưa gọi Telegram thật.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` → tạo kênh, thêm bot làm quản trị (quyền đăng bài) → chuyển tiếp 1 bài kênh vào bot → ✅ → 📤 Đăng bài giới thiệu (ghim) → 📢 Bật đăng kênh. Ngoài phạm vi: deal khung giờ (cần xem API AddLiveTag), kênh Zalo.

---

## Phiên 2026-10-28 (dx) — PLAN-098 bước C: thử ShopeeFood

- Khảo sát: 30 ngày 0 đơn Food; chưa có tài liệu gắn sub_id cho Food; AddLiveTag không có giá/hoa hồng món Food.
- Thử (chủ bot duyệt): link an_redir ghép tay sub_id `FOODTEST` tới `spf.shopee.vn/906KKy82bs` mở đúng món; chủ bot tự đặt 1 đơn ~17:15 28/10. AddLiveTag click Food mới nhất là 26/10 (trễ ~2 ngày).
- Tự mua có thể bị Shopee loại (đơn 23/09 FRAUD); vẫn đủ để xem có dòng đơn kèm sub_id. Khuyên không tự đặt thêm, lần sau nhờ người khác.
- **Next:** từ 30/10 chủ bot nhắn «kiểm FOODTEST» → 1–2 lệnh đọc `source=food` (items + clicks), kết luận theo PLAN-098. Chủ bot vẫn cần restart để bật bước A, B.

---

## Phiên 2026-10-28 (dw) — PLAN-098 bước B: nguồn dự phòng AddLiveTag khi cookie Shopee lỗi

- Cookie lỗi / sự cố mở / quá 6 giờ chưa đồng bộ được → mỗi 60 phút đọc AddLiveTag 3 ngày; đơn mới qua link bot (chưa có trong DB, chưa huỷ) → báo admin 🛟 + báo khách «có đơn mới» (cùng điều kiện gửi), ghi bot_state `alt_order:<order_sn>`. Không ghi sổ đơn / ví.
- Cookie chạy lại: đồng bộ chính ghi đơn như cũ, tin khách «có đơn mới» bị giữ lý do `alt_notified` (không báo lần hai).
- Proof: 909 test qua, ruff sạch; chạy thật trên bản sao DB: cookie ổn, 0 đơn thiếu.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo`; em làm bước C (khảo sát ShopeeFood, 1 lệnh đọc source=food).

---

## Phiên 2026-10-28 (dv) — PLAN-098 bước A: đối soát chéo đơn Shopee với AddLiveTag

- Chủ bot chọn API AddLiveTag không chính thống (mục 2) cho: dự phòng, đối soát chéo, chuẩn bị ShopeeFood; duyệt PLAN-098.
- Khảo sát (2 lệnh đọc): AddLiveTag = cùng báo cáo Shopee, không có order_id/is_fraud → không bao giờ ghi sổ đơn; «Chờ trả hoa hồng» = Waiting for payment bot đã có; AddLiveTag chậm hơn bot.
- Bước A xong: 09:00 VN mỗi ngày so 30 ngày theo order_sn, chỉ báo admin khi lệch; dòng 🔁 trên 🔗 Shopee Affiliate. Proof: 905 test, chạy thật trên bản sao DB khớp 4/4.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo`; em làm bước B (dự phòng khi cookie lỗi) rồi C (khảo sát ShopeeFood).

---

## Phiên 2026-10-28 (du) — 🖼 Ảnh đăng bài: ẩn/hiện từng mục

- Bỏ tên sản phẩm khỏi ảnh (e114224); đơn gần đây 1 dòng, nhãn trạng thái thẳng cột.
- Nút 🖼 Ảnh đăng bài mở màn chỉnh (`c:pb:home`): bật/tắt Thành viên · Link · Đơn · Hoàn tiền ghi nhận · Biểu đồ (7/14 ngày) · Đơn gần đây (3/4/6) · Ẩn đơn dưới 1.000đ; lưu bot_state `showcase_options`. 🖼 Tạo ảnh (`c:pb:go`) gửi ảnh + bài viết thành tin mới (service keep), màn chỉnh ở lại. Mục tắt không chừa chỗ; bài viết cũng bỏ mục tắt; ghi chú «Số tạm tính…» luôn có.
- Proof: 898 test qua, ruff sạch; ảnh 14 ngày/ẩn mục dựng từ bản sao DB.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo` rồi bấm thử.

---

## Phiên 2026-10-28 (store-5) — Bot bán hàng AI Pass Store: icon đúng hãng

- Trạng thái store (PLAN-097, commit 3001f25): @aipass_shop_bot + kênh @ai_pass_store chạy systemd `store-bot`, `store-api`; hàng lấy từ FatCat qua API (giá lẻ = giá đại lý ÷ 0,98), đồng bộ 3 phút, báo hàng mới lên kênh + nhắn mọi khách. Mục (store-1…4) cũ bị ghi đè ở bb0ebfd, chi tiết xem `agents/plans/active/PLAN-097-store-bot.md`.
- Chủ bot muốn icon đúng hãng (CapCut → icon CapCut…). Làm: `messages.BRANDS` dò từ khoá trong tên → emoji thường (🎬 CapCut, 🤖 ChatGPT, ✨ Gemini, 🎨 Canva, 💼 Microsoft 365, 🦉 Duolingo, 🧠 Muse AI…) ở danh sách, chi tiết, đơn, tin kênh.
- Logo thật: Telegram chỉ cho bot dùng emoji tuỳ chỉnh khi tài khoản tạo bot có Premium (Bot API 9.4). Admin gắn ở ⚙️ Quản lý shop → 🎨 Logo hãng → gửi emoji logo; lưu state `icon:<hãng>`; nút dùng `icon_custom_emoji_id`, tin dùng `<tg-emoji>`. Kênh và tin gửi hàng loạt luôn emoji thường. Telegram từ chối → `telegram_api` tự gửi lại không logo.
- Proof: `tests/test_store_bot.py` 52 test qua (thêm 3), ruff sạch; 10 món thật đều ra đúng icon.
- **Next:** chủ bot `sudo systemctl restart store-bot store-api`; nếu có Premium thì gắn logo từng hãng trong 🎨 Logo hãng.

---

## Phiên 2026-10-28 (dt) — 🖼 Ảnh đăng bài (số liệu thật để đăng bài uy tín)

- Chủ bot chọn: ảnh + bài viết soạn sẵn; tiền ghi «tạm tính»; có đơn gần đây, tên khách che (chữ đầu***chữ cuối).
- /admin → 🧾 Đơn & hoa hồng → 🗓 Thống kê → 🖼 Ảnh đăng bài (`c:pb:card`): ảnh PNG 1080px (thành viên, link, đơn, hoàn tiền ghi nhận chia chờ sàn/đang giữ/đã duyệt, biểu đồ 7 ngày, 4 đơn gần đây) + bài viết trong <pre> chạm để chép.
- «Đã chi trả» chỉ hiện khi có lượt rút đã trả. Font Be Vietnam Pro (OFL) ở `cashback_bot/assets/fonts`. Code `cashback_bot/showcase.py`.
- Proof: 896 test qua, ruff sạch; ảnh dựng từ bản sao DB trong scratchpad.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo` rồi bấm thử. Chưa có @tên bot trên ảnh (không có trong config).

---

## Phiên 2026-10-28 (ds) — Restart, gửi tin giới thiệu wallet-v1

- Tin xem thử về admin (admin_notifications id 173, gửi 05:12:32Z) → chủ bot duyệt.
- Chủ bot restart cả hai bot lúc 06:04:02Z (code 630ff55); log sau restart không có lỗi.
- Chủ bot bấm gửi 📣 wallet-v1: 17 khách (9 Telegram, 8 Zalo), sent 06:25:50Z–06:26:42Z, 0 failed/unknown.
- **Next:** theo dõi số khách bấm đồng ý V3 (/dieukien); kỳ Shopee đầu có đơn bot → đối soát → mở rút.

---

## Phiên 2026-10-28 (dr) — V3 công bố, ghi payout_terms

- Chủ bot công bố V3 lúc 04:46:56Z (id 3, hash 22c5aaf878b0). Rà nội dung với code: khớp (Hoan tien <mã>, mã giao dịch khi chuyển, 3–7 ngày, đổi tài khoản chờ 7 ngày, thu hồi trừ khoản sau, xử lý yêu cầu khi ví tắt). 0 khách đã đồng ý V3 (công bố không gửi tin).
- Backup `cashback-manual-20261028T044816Z.sqlite` rồi ghi `payout_policy_decisions` id 8: payout_terms APPROVED reference V3. Khoá còn lại duy nhất: `settlement_matched`.
- Ví xem trước hiện thêm dòng hạn mức (V3 dẫn sang 👛 Ví). Proof: 891 test qua.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo`; kỳ Shopee đầu có đơn bot → đối soát → mở rút.

---

## Phiên 2026-10-28 (dq) — Ví xem trước (chưa mở rút)

- Chủ bot yêu cầu bật ví. Không bật được: còn 2 khoá (`settlement_matched`: chưa có kỳ Shopee trả cho đơn qua bot; `decision_payout_terms`: V3 chưa công bố). Các quyết định khác đã APPROVED.
- Chủ bot duyệt "ví xem trước": trang chủ luôn có 👛 Ví của tôi; /vi hiện Có thể rút / Đang chờ sàn / Đang giữ / Đã nhận + đơn gần đây, dòng "⏳ Chưa mở rút tiền…", không nút Rút, không khai ngân hàng. Câu "Ví hoàn tiền chưa mở" → "Chưa mở rút tiền". Khoá mở thì ví tự thành bản có nút Rút.
- Proof: 891 test cashback qua (7 test cũ "ví ẩn khi tắt" sửa theo hành vi mới, vẫn kiểm không có nút u:w:*).
- **Next:**
  - chủ bot restart `systemctl restart cashback-bot cashback-zalo`;
  - chủ bot công bố V3 (/admin → 📋 Điều khoản) → Claude Code backup rồi ghi quyết định `payout_terms` APPROVED reference V3;
  - việc tự xoá dữ liệu hết hạn (V3 hứa) chưa làm: mốc sớm nhất hết hạn 10/2028 (24 tháng, chưa ai chỉnh), cần chủ bot duyệt riêng khi làm;
  - kỳ Shopee đầu tiên có đơn bot về → đối soát → mở rút.

---

## Phiên 2026-10-28 (dp) — Tin admin đơn mới: dòng báo khách + đơn gián tiếp

- Chủ bot hỏi 2 đơn gián tiếp (bấm link món A, mua món B shop khác) hôm nay đã cover chưa / khách đã được báo chưa. Đã cover: đơn gán theo Sub ID, hoa hồng lấy đúng món đã mua, tin khách giải thích "mua món khác món trong link". Cả 2 tin khách đã gửi 10:54–10:55 ICT (••KR94 Telegram, ••SER3 Zalo #4).
- Thêm (456c4f2): tin "Có đơn Shopee mới" có dòng `📨 Báo khách` (⏳ đang chờ → ✅ đã gửi HH:MM / ❌ khách chặn bot / ❔ không rõ / ⏭ bỏ qua + lý do), bot Telegram tự sửa tin khi tin khách xong (cả khách Zalo), sửa lỗi 3 lần thì chỉ ghi DB; dòng `🔀 Mua món khác link: <món>` khi đơn không có món trong link.
- Proof: 891 test cashback qua, ruff sạch.
- **Next:** chủ bot `systemctl restart cashback-bot cashback-zalo` (gồm cả (dm), (dn), (do)).

---

## Phiên 2026-10-28 (do) — Timeout và chống trùng: vá 2 chỗ hở

- Báo cáo `reports/CASHBACK_TIMEOUT_IDEMPOTENCY.md` (timeout, 5 loại lỗi, bảng chống trùng, chọn gửi trùng hay mất, khung cho bot khác).
- bdb9670: việc tạo link TikTok ghi `bot_state.tiktok_job:<sub_id>`, khởi động thì làm tiếp (≤ 30 phút, không gọi RioHub lần hai khi link đã lưu); Zalo khởi động gửi nốt câu trả lời đã lưu hoặc nhắn khách gửi lại (tin ≤ 6 giờ).
- Proof: 887 test qua.

---

## Phiên 2026-10-28 (dn) — Rà soát toàn bot Zalo

- de4aa33: tin chat không ăn suất link; trả lời nhẹ cho tin chữ; gõ nhầm số không xoá danh sách và báo đúng số có; trang chủ liền khối; bỏ nhãn [HOT] trong tên món.

---

## Phiên 2026-10-28 (dm) — Zalo: danh sách deal không hết hạn sau khi chọn 1 món

- 3ebd290: gõ số lấy link món khác vẫn giữ danh sách; tin bot tự gửi giữ danh sách số 24 giờ.

---

## Phiên 2026-10-28 (store-4) — store_bot: báo hàng mới vào chat từng khách (mô hình FatCat)

- "2.639 monthly users" của FatCat là người dùng bot, không phải kênh: FatCat nhắn "HÀNG MỚI VỀ" thẳng vào chat bot từng khách. Làm y vậy:
  - món tăng hàng (≥ 5 hoặc từ 0) → đăng kênh + nhắn mọi khách (chưa tắt, chưa chặn bot), nút 🛒 Mua ngay / 🔕 Tắt báo hàng mới; ~20 tin/giây, xử lý 429, khách chặn bot thì bỏ khỏi danh sách (/start lại thì nhận lại);
  - 👤 Hồ sơ bật/tắt; /admin công tắc "Nhắn khách hàng mới" (mặc định bật theo yêu cầu chủ bot); gửi xong báo admin số khách nhận.
  - /supportadmin + nút 🆘 ở ☎️ Hỗ trợ: báo admin kèm link chat khách, 1 lần/ngày.
- Chưa làm: /api xin khóa bán sỉ (cần tên miền), /language.
- Proof: 49 test qua, ruff sạch, migrate bản sao DB thật OK.
- **Next:** chủ bot restart (`sudo systemctl restart store-bot store-api`). Đã commit + push lên main.

---

## Phiên 2026-10-28 (store-3) — store_bot: dòng tiền, menu cố định, mua thẳng bằng QR

- Đơn FatCat thật đầu tiên chạy đúng 09:51 ICT (Canva 1.000đ, vốn 980đ). Kênh @ai_pass_store đã tạo, bot là admin có quyền đăng (getChatMember: administrator, can_post_messages).
- 📊 Thống kê thành dòng tiền (nạp / doanh thu / vốn FatCat / lãi / hoàn; hôm nay · 7 ngày · từ đầu) + 💸 Giao dịch gần đây; `orders.unit_cost`.
- Gõ thẳng số lượng / số tiền ở màn sản phẩm / nạp tiền.
- Theo mẫu bot đại lý chủ bot gửi: bàn phím menu cố định (🛒 Mua sản phẩm · 👤 Hồ sơ · 📦 Đơn hàng · 🎁 Ví · ☎️ Hỗ trợ), /menu, /support, "Hướng dẫn nhanh"; **mua thẳng**: thiếu tiền → 📱 Thanh toán QR đúng số thiếu (`topups.intent_*`) → admin ✅ / SePay → bot tự mua + giao.
- Proof: 46 test qua, ruff sạch, migrate trên bản sao DB thật 2 lần OK.
- **Next:** chủ bot restart; điền `STORE_SUPPORT_TELEGRAM` / `STORE_SUPPORT_ZALO`; nạp ví FatCat (19.823đ); `STORE_API_PUBLIC_URL` vẫn là địa chỉ FatCat → xoá trống; chưa commit.

---

## Phiên 2026-10-28 (store-2) — store_bot lấy hàng từ FatCat Store

- Chủ bot (@Zusem10) là đại lý FatCat; @aipass_shop_bot đã chạy thật từ 02:14 (bản chưa có FatCat).
- Thêm nguồn FatCat (PLAN-097 bước 2): giá bán = giá lẻ FatCat, bán mọi món khóa được mở, tự đồng bộ 3 phút, tự đăng kênh khi FatCat tăng hàng; đơn FatCat có hoàn tiền khi thiếu / bị từ chối, gọi lại an toàn khi nguồn chậm.
- Proof: 40 test `tests/test_store_bot.py` qua, ruff sạch; chạy thử bản sao DB thật + GET thật FatCat (không mua). Chưa gọi `/api/buy` thật.
- **Lưu ý:** ví FatCat chỉ còn 20.803đ → đơn nào lớn hơn sẽ bị FatCat từ chối (khách được hoàn đủ, admin được báo).
- **Next:**
  - chủ bot `sudo systemctl restart store-bot store-api`;
  - nạp ví FatCat; mua thử 1 món rẻ (Slot Canva 1.000đ) bằng tài khoản của mình để xác nhận đơn thật đầu tiên;
  - chưa commit.

---

## Phiên 2026-10-28 (store-1) — Tool mới: bot bán hàng số (store_bot)

- Chủ bot giao trực tiếp: làm bot kiểu FatCat Store, thư mục ngang `cashback_bot/`. PLAN-097.
- Mới: `store_bot/` (bot Telegram + API đại lý + webhook SePay), `deploy/store/` (2 service systemd + README cài đặt, tài liệu API).
- Không đụng code / DB / `.env` cashback. Dùng chung duy nhất `cashback_bot.vietqr`.
- Proof: `tests/test_store_bot.py` 30 test qua; ruff sạch; chạy thử API với DB tạm trả đúng 200/401.
- **Chưa chạy thật**: chưa có token bot, kênh, tài khoản ngân hàng.
- **Next:**
  - chủ bot tạo bot ở @BotFather + kênh, điền biến `STORE_*` vào `.env` (mẫu ở `deploy/store/README.md`);
  - cài `store-bot`, `store-api`; trỏ tên miền API (Cloudflare Tunnel / nginx);
  - thử: thêm 1 sản phẩm → nhập kho → đăng kênh → mua bằng tài khoản phụ → cấp khóa và gọi `/api/v1/products`.

---

## Phiên 2026-10-28 (dl) — Deal hời thêm lượt trưa 12:08

- Theo yêu cầu chủ bot ("trưa và tối"). Chi tiết `reports/CASHBACK_ADDLIVETAG_EXTRA_INCOME.md` mục 7.
- `deals.SLOTS`: 🍱 trưa (soạn 10:30, gửi 12:08, từ khoá [5:]) và 🌙 tối (soạn 17:30, gửi 20:08, từ khoá [:5]).
- Bản ghi lượt trưa ở `deals:<ngày>:trua`, event key `deals:<ngày>:trua:<khách>`; lượt tối giữ khoá cũ.
- Không lặp món đã gửi khách trong 3 ngày (`recently_shown` đọc nút u:dl của tin DEALS). Hết món mới thì không gửi.
- Công tắc `deals_noon_enabled` (bật mặc định); admin bỏ món / bỏ lượt theo lượt (`c:dl:rm:trua:<id>`, `c:dl:skip:trua`).
- Proof: 882 test cashback qua (test_cashback_deals 16), ruff sạch.
- **Next:**
  - chủ bot restart `systemctl restart cashback-bot cashback-zalo` → lượt trưa đầu tiên 12:08 ngày kế tiếp sau restart (restart trước 10:30 thì có ngay hôm đó);
  - kiểm khách chặn / tắt sau 2–3 ngày có lượt trưa.

## Phiên 2026-10-28 (dk) — Kết quả đêm đầu deal hời + đoán gu

- Production: a17f06f (Telegram + Zalo), chủ bot restart 18:54 ICT 27/10.
- 20:08 ICT 27/10: gửi 11 tin DEALS, 0 lỗi (3 khách tự chọn + 8 khách bot đoán gu); 7 LINK_NUDGE; 0 khách chặn bot.
- Đến 08:18 ICT 28/10:
  - chỉ Zalo chủ bot (-2) bấm deal → tạo 1 link (nước tẩy trang);
  - khách thật chưa bấm, chưa đổi danh mục, chưa ai bấm 🔕 (thêm deal_cats = 0).
- Proof: đọc DB mode=ro (admin_notifications, link_requests, bot_state, telegram_users.notify_blocked_at).
- **Next:**
  - 28/10: bot tự soạn 17:30, gửi 20:08 cho khách tự chọn; khách đoán gu nhận lại sớm nhất 30/10 (cách 3 ngày);
  - sáng 29/10 và 31/10 kiểm lại khách bấm / tắt / chặn.

## Phiên 2026-10-27 (dj) — Deal cho khách chưa chọn danh mục (bot đoán gu)

- Theo yêu cầu chủ bot. Chi tiết `reports/CASHBACK_ADDLIVETAG_EXTRA_INCOME.md` mục 6.
- `deals.guess` / `deals.inferred`; tin có câu "Bot đoán bạn thích…", nút 🛍️ Chọn danh mục / 🔕 Không nhận deal (`u:dc:off`).
- Luật: tối đa 2 tin / tuần, rẻ ≥ 12%, tối đa 3 món; dừng sau 3 tin không tạo link.
- Công tắc `deals_infer_enabled` (bật mặc định) ở 🔥 Deal hời.
- Dữ liệu thật: 12 khách đủ điều kiện.
- Proof: 880 test cashback qua.
- **Next:**
  - chủ bot quyết bật tối nay hay từ mai (restart trước 20:08 thì tối nay gửi);
  - sáng mai kiểm khách bấm / tắt.

---

## Phiên 2026-10-27 (di) — Lối vào deal + nút gửi tin giới thiệu

- Trang chủ có nút 🛍️ Deal hời của tôi (khi đã bật); cuối tin deal có nút ⚙️ Đổi danh mục (Zalo: "gõ số của dòng").
- Lệnh gửi tin hàng loạt từ phía Claude bị auto mode chặn (Real-World Transactions). Thay bằng màn chủ bot tự bấm:
  - `admin_announce.py`: ⚙️ → 📣 Nhắc mùa sale → 📣 Tin giới thiệu;
  - xem trước nội dung, số khách chưa nhận (Telegram / Zalo), bấm ✅ Gửi;
  - khoá `announce:<mã>:<khách>` nên mỗi khách nhận một lần; ghi 📊 Lịch sử.
  - Tin hiện có: `deals-v1`.
- Proof: 876 test cashback qua.
- **Next:**
  - chủ bot restart;
  - vào 📣 Tin giới thiệu → deals-v1 → ✅ Gửi.

---

## Phiên 2026-10-27 (dh) — Zalo: màn bật / tắt dễ nhìn

- Chủ bot chụp màn chọn danh mục trên Zalo iPhone: ô ⬜ hiện thành khối xám to, trông như lỗi.
- `zalo_render.render`, áp cho mọi màn bật / tắt:
  - mục chưa chọn để trơn; mục đã chọn in đậm, ✅ đặt cuối;
  - nút điều hướng tách bằng dòng trống;
  - bỏ danh sách ✅ / ⬜ bị lặp trong nội dung (màn /thongbao).
- Proof: 874 test cashback qua.

---

## Phiên 2026-10-27 (dg) — Thử deal thật + Zalo gõ nhiều số

- Thử thật (đã backup trước khi ghi):
  - soạn deal cho 3 danh mục chủ bot chọn (dep, nha, nu): 8 deal, 69 giây;
  - 1 tin `DEALS` gửi Telegram chủ bot 07:35 UTC;
  - 1 tin giới thiệu gửi Zalo "Thanh Vu" (-2) 07:37 UTC: gửi được.
- Zalo: gõ nhiều số một tin ("1 3 5", "1,3,5") cho màn bật / tắt (danh mục deal, /thongbao). Màn khác báo "gõ từng số".
- Tên món bỏ nhãn khuyến mãi đầu tên; giá lẻ hiện "64,5k".
- Tin giới thiệu: `messages.DEALS_ANNOUNCE` (bản Zalo: "Gõ số 1"). **Chưa gửi cho khách**, chờ chủ bot duyệt.
- Lúc merge gặp file đang sửa dở của phiên reup (thư mục chính): không đụng; ghi mục này sau khi họ commit.
- **Next:**
  - chủ bot restart 2 bot cashback;
  - duyệt tin giới thiệu.

---

## Phiên 2026-10-27 (reup) — Thuyết minh lại video (ADR-060)

- Owner giao trực tiếp: tách giọng (Demucs) → Whisper tự nhận ngôn ngữ → AI dịch từng câu → đọc lại khớp thời gian, trộn lên nền đã tách.
- Mới:
  - `viral_intake/dub_layer.py`;
  - `viral_intake/demucs_separate.py` (chạy tiến trình riêng);
  - 4 setting `reup.dub_*` trong nhóm "Reup — lớp thêm", **mặc định tắt**, 13 ngôn ngữ đích.
- Thứ tự lớp: thuyết minh → phụ đề → âm thanh. Đã thuyết minh thì phụ đề là câu đã dịch.
- Cài vào venv:
  - torch 2.5.1 **CPU**, torchaudio 2.5.1, demucs 4.0.1 (sympy 1.14.0 → 1.13.1);
  - edge-tts 7.2.8 → **7.3.1**, vì 7.2.8 bị Microsoft trả 403, nên voice-over hook ADR-016 cũng đang hỏng nếu bật.
- Proof: video thật 34,6 giây, Việt → Anh.
  - 5/5 câu; Whisper nghe lại file ra thấy `en` 0,99.
  - Demucs CPU 93 giây.
  - Owner nghe bản đầu: "đọc nhanh, cụt cuối câu". Đã sửa: gọt khoảng lặng edge-tts, chừa 0,25 giây nghỉ, tăng tốc tối đa 1,2× (trước 1,5×), câu dài thì lùi câu sau thay vì cắt. Bản mới ở `C:\Users\Admin\Downloads\thuyet_minh_3_tieng_anh_ban_moi.mp4`, chờ Owner nghe.
  - 220 + 218 test qua. Import-linter không thêm vi phạm.
- **Chưa commit.**
- **Next:**
  - Owner commit;
  - restart worker reup để nạp code mới và edge-tts 7.3.1;
  - bật "Thuyết minh lại (dịch + lồng tiếng)" trong /app/settings, chọn ngôn ngữ đích;
  - xem 1–2 video ra trước khi để chạy hàng loạt.

---

## Phiên 2026-10-27 (df) — Deal hời theo danh mục, 20:08 mỗi tối

- `deals.py` + `admin_deals.py` (⚙️ → 📣 → 🔥 Deal hời), mặc định tắt. Chi tiết `reports/CASHBACK_ADDLIVETAG_EXTRA_INCOME.md` mục 5.
- Khách:
  - chọn tối đa 3 danh mục (`bot_state.deal_cats:<id>`) ở /thongbao → 🛍️, hoặc nút mời trên thẻ link đầu tiên (chỉ hiện khi đã bật);
  - bấm món (`u:dl:<shop>:<item>`) thì tạo link như tự dán link, thẻ là tin mới.
- Lịch:
  - 17:30 soạn ở luồng nền (Market Search 30 món / từ khoá + lịch sử giá 30 ngày, giãn 500 món / phút);
  - báo admin `DEALS_READY`;
  - 20:08–21:08 gửi `DEALS` (category `deal`); nhường khi có nhắc sale trong 3 giờ.
- Sửa thêm: `PriceHistoryClient.points/stats` dùng chung cho báo giảm giá và deal.
- Proof:
  - `tests/test_cashback_deals.py` 7 test;
  - chạy thử dữ liệu thật: Làm đẹp 3 deal, Thời trang nữ 3 deal (30 món / từ khoá); gặp 429 khi gọi dồn nên thêm giãn nhịp.
- **Next:**
  - chủ bot restart;
  - bật 🔥 Deal hời;
  - xem bản soạn đầu tiên lúc 17:30 ngày bật.

---

## Phiên 2026-10-27 (de) — Sửa báo giảm giá theo dữ liệu thật

- Gọi thử AddLiveTag `history.php` (12 món, chỉ đọc): `stockAvailable` = 0 ở cả món đang bán bình thường (chỉ là suất flash sale); giá 0 là flash sale ẩn giá; `discountPercent` so với "giá gốc" shop ghi, không đáng tin.
- Sửa `price_watch._point`: chỉ coi là hết hàng khi đang flash sale và suất = 0. Trước đó tối nay sẽ bỏ sót gần hết món giảm giá (không gửi sai).
- Proof: test đọc phản hồi có thêm 3 mẫu dữ liệu thật; test price_drop + sale_reminders qua.
- **Next:** chủ bot restart trước 19:00 tối nay.

---

## Phiên 2026-10-27 (dd) — Báo giảm giá món khách từng xem

- `price_watch.py` (AddLiveTag `price-tracking/history.php`, cùng khoá API), mặc định tắt. Bật ở 📣 Nhắc mùa sale.
- Luật:
  - mỗi tối một lượt 19:00–21:30, chạy ở luồng nền;
  - link Shopee 30 ngày, có hoàn, chưa có đơn; giá giảm từ 15% và còn hàng;
  - mỗi khách 1 món, mỗi link 1 lần;
  - chung ngân sách 1 tin / 7 ngày với nhắc link; nhường tối có nhắc sale; tôn trọng /thongbao.
- Chưa thử với dữ liệu thật: lần bật đầu là lần đầu gọi `history.php`. Lỗi thì báo admin, tối mai thử lại.
- Proof: 864 test cashback qua; `tests/test_cashback_price_drop.py`.
- **Next:**
  - chủ bot restart;
  - bật 🟢 Báo giảm giá;
  - hỏi AddLiveTag chuyện dùng thương mại;
  - gửi 3 thông tin ShopeeFood.

---

## Phiên 2026-10-27 (dc) — Chuẩn bị mở TikTok cho khách

- Chủ bot cho biết RioHub thuộc hệ sinh thái AddLiveTag và **đã đồng ý** (memory `riohub-addlivetag-consent`).
- Rà soát P3 (đã xử lý):
  - tạo link TikTok chạy ở luồng nền (`service.tiktok_runner`, 2 luồng);
  - khách nhận ngay "⏳ Đang tạo link TikTok Shop…", thẻ link / lỗi đi qua hàng đợi chung (`LINK_READY`, category `link_ready`);
  - đẩy đi ngay bằng `service.after_deferred` (Telegram: `flush_pending`, Zalo: `dispatcher.flush`). Vòng nhận tin không còn đứng khi RioHub treo.
- Trang chung theo chế độ TikTok (`messages.TIKTOK_OPEN_PHRASES` / `with_tiktok`):
  - khi 🎵 = "Mở cho khách" và có khoá, trang chủ, hướng dẫn (cả Zalo), cách tính, để được ghi nhận, câu báo link sai, lời chào Zalo nhắc cả Shopee lẫn TikTok Shop;
  - chưa mở thì giữ nguyên.
- Còn lại trước khi mở:
  - điều khoản đang công bố là V2, chỉ nói Shopee (V3 trung tính chưa công bố);
  - mô tả bot Telegram (DESCRIPTION) chưa đổi;
  - đơn `pit` âm chưa quyết.
- Proof: 859 test cashback qua.
- **Next:**
  - chủ bot restart;
  - bật 🎵 TikTok Shop → Mở cho khách khi sẵn sàng.

---

## Phiên 2026-10-27 (db) — Cảnh báo món chạm trần hoa hồng Shopee

- Nghiên cứu: trần phần Shopee trả của tài khoản chủ bot là **40.000đ mỗi lần thanh toán** (`checkout_cap` trong dữ liệu đơn); nguồn công khai ghi 50–70k, tuỳ tài khoản.
- Thẻ link: khi AddLiveTag gắn cờ `isCapped`, khối ⚠️ Để được hoàn có thêm "Món giá cao: … thanh toán riêng món này, mỗi lần 1 cái".
  - Màn gửi lại link cũ (`_render_existing`) chưa có dòng này, vì `LinkRow` chưa có cột `is_capped`.
- Proof: 857 test cashback qua.
- **Next:** chủ bot restart.

---

## Phiên 2026-10-27 (da) — Dòng ➕ "mức thận trọng" sau khi so HOANTIENSP

- Chủ bot thử cùng link ở HOANTIENSP: họ báo khoảng 60% hoa hồng gốc, chưa trừ thuế, tính Shopee Comm 4%. Bot mình chia 62,3% nhưng tính Shopee Comm 2,5%.
  - Ghi ở `reports/CASHBACK_COMPETITORS_2026-10-27.md` mục 5.
- Thẻ link: dòng ➕ đổi thành "Bot báo theo mức **thận trọng**, không phải mức tối đa. Shopee trả cao hơn thì bạn được thêm."
  - Không dùng "chắc chắn" vì voucher vẫn làm giảm số hoàn.
- Proof: 856 test cashback qua.
- **Next:**
  - chủ bot restart;
  - chờ duyệt dòng cảnh báo sản phẩm bị Shopee giới hạn hoa hồng mỗi đơn (`is_capped`).

---

## Phiên 2026-10-27 (cz) — Khách ngủ + nhắc link chưa dùng

- Khách ngủ (link gần nhất cũ hơn 21 ngày): tin nhắc sale có thêm dòng đầu "👋 Lâu rồi hông thấy bạn ghé nè!". Không gửi tin riêng.
- Nhắc link chưa dùng (`engagement.send_nudges`, công tắc `link_nudge_enabled`, **mặc định tắt**), tự gửi theo luật:
  - link mới nhất, có hoàn, 24–72 giờ tuổi, chưa có đơn (không dựa vào click);
  - chỉ 19:00–21:30; mỗi link 1 lần; mỗi khách tối đa 1 tin / 7 ngày;
  - nhường ngày có nhắc sale; tôn trọng /thongbao và chặn bot.
  - Kèm nút 🛒 Mua (Zalo: link thành tin riêng).
- Màn 📣 Nhắc mùa sale có thêm số khách ngủ, công tắc nhắc link, thống kê 7 ngày. Bật / tắt ghi 📊 Lịch sử.
- Proof: 856 test cashback qua.
- **Next:**
  - chủ bot restart;
  - bật 🟢 Nhắc link nếu muốn.

---

## Phiên 2026-10-27 (cy) — Tin nhắc sale giọng Gen Z đậm

- Chủ bot xem 3 mức giọng (Gen Z vui / Gen Z đậm / thân thiện nhẹ nhàng) và chọn **Gen Z đậm**.
- Viết lại cả 12 câu `messages.SALE_REMINDERS` + dòng tắt ("Phiền quá thì gõ /thongbao tắt nhắc nha 🫶").
  - Vẫn giữ: không hứa số tiền, nhắc món trong giỏ, dưới 260 ký tự.
- Proof: 852 test cashback qua.
- **Next:**
  - chủ bot restart `systemctl restart cashback-bot cashback-zalo`;
  - xem lại giọng sau 2–3 tháng (tỷ lệ tắt nhắc).

---

## Phiên 2026-10-27 (cx) — Thử Zalo nhắn chủ động

- Chủ bot xác nhận Zalo "Thanh Vu" (ID nội bộ -2) là của mình. 03:20 UTC 27/10 gửi 1 tin thử chủ động (sendMessage ngoài luồng trả lời): **thành công**.
  - Zalo từ chối text_styles (400), code tự gửi lại chữ thuần như thiết kế.
- Chưa kiểm: nhắn sau **48 giờ** khách im lặng. Lần cuối chủ bot nhắn bot là 02:23 UTC 27/10, tin thử chỉ cách đó khoảng 1 giờ.
- **Next:** từ khoảng 29/10 03:00 UTC, nếu chủ bot không nhắn bot Zalo trong 48 giờ thì gửi tin thử lần 2.
  - Kết quả quyết định khách Zalo có nhận được nhắc 11.11 (10/11) không.

---

## Phiên 2026-10-27 (cw) — Nhắc mùa sale tự lập lịch, duyệt từng lượt

- Nghiên cứu: `reports/CASHBACK_SALE_REMINDERS.md`.
  - 4 cấp: đỉnh 11.11 · 12.12; siêu sale 9.9 · 10.10 · Black Friday; ngày đôi thường; mini 15 · 25.
  - Giờ gửi: 20:30 tối hôm trước; dịp đỉnh thêm 11:30.
  - Dịp nhỏ sát dịp lớn (dưới 5 ngày) thì bỏ.
  - Câu chữ: mốc thời gian, một việc cần làm, nhắc chuyện giỏ hàng, không hứa số tiền.
- Code:
  - `sale_calendar.py`, `engagement.py` (chạy định kỳ trong poller), `admin_engagement.py` (⚙️ Cài đặt → 📣 Nhắc mùa sale);
  - tuỳ chọn khách 🛒 Nhắc mùa sale ở /thongbao: cột mới `customer_notification_prefs.reminders`, migration `_add_column`.
- An toàn:
  - **mặc định tắt**; mỗi lượt phải bấm ✅ Duyệt gửi;
  - báo admin trước giờ gửi 48 giờ;
  - quá 60 phút sau giờ gửi thì bỏ lượt, không gửi muộn;
  - mọi thao tác ghi 📊 Lịch sử.
- Proof: 852 test cashback qua; `tests/test_cashback_sale_reminders.py`.
- **Next:**
  - chủ bot restart (migration thêm cột chạy khi khởi động);
  - bật 📣 Nhắc mùa sale và duyệt lượt 10/11 20:30 (11.11).

---

## Phiên 2026-10-27 (cv) — Giữ chân đợt 1 + tự phản biện thiết kế

- Bản thiết kế có thêm mục 0 "Tự phản biện" và lộ trình rút gọn.
- Tin báo đơn:
  - đơn đầu tiên của khách có dòng "🎉 Đơn đầu tiên của bạn qua bot đó!";
  - cuối tin (trừ đơn huỷ / không đủ điều kiện) có 1 câu mời quay lại, đổi luân phiên theo mã đơn.
  - Không gửi thêm tin nào.
- Bảng 🔁 Giữ chân (Telegram + web) trước đây ghi 0% cho tuần chưa tới. Giờ ghi "chưa tới" / "x% (đang đo)".
- Proof: 846 test cashback qua; `tests/test_cashback_engagement.py`.
- **Next:**
  - chủ bot restart `systemctl restart cashback-bot cashback-zalo` + `pm2 restart Web_Dashboard`;
  - chủ bot xác nhận Zalo "Thanh Vu" (-2) là mình thì gửi 1 tin thử chủ động;
  - 11.11 chủ bot tự nhắn tay.

---

## Phiên 2026-10-27 (cu) — Thiết kế hệ thống giữ chân khách

- Bản thiết kế: `reports/CASHBACK_RETENTION_DESIGN_2026-10-27.md`.
  - 5 tầng: kích hoạt, vòng đời đơn, lịch sale, gọi lại người ngủ, tích luỹ sau khi mở ví;
  - rào chắn chống spam, giọng nói, đo lường, lộ trình 5 đợt.
- Số thật: 13/16 khách chỉ dùng 1 ngày; 9 tin chủ động đã gửi đều qua Telegram, Zalo chưa gửi tin chủ động nào.
- Chưa triển khai gì.
- **Next:** chủ bot duyệt
  - đợt 1 (câu chữ: ghim, mừng đơn đầu, câu mời quay lại);
  - đợt 2 (gửi 1 tin thử Zalo tới chủ bot);
  - PLAN đợt 3, kịp 11.11.

---

## Phiên 2026-10-27 (ct) — Câu chữ theo tâm lý khách (PLAN-096 đợt 3)

- Thẻ link:
  - ➕ không ghi số tiền;
  - thêm dòng 🔒 "Link mở thẳng Shopee… bot không thu tiền gì";
  - voucher thành gạch đầu dòng trong ⚠️ Để được hoàn.
- Tin đơn mới: hoàn thấp hơn hẳn số lúc tạo link thì nói lý do (mua món khác / trả ít hơn giá tham khảo / Shopee tính mức thấp hơn).
- Proof: 843 test cashback qua; test dùng số thật đơn F1 và đơn khung bằng khen.
- **Next:**
  - chủ bot restart `systemctl restart cashback-bot cashback-zalo`;
  - chờ chủ bot chốt câu thời điểm tiền vào ví.

---

## Phiên 2026-10-27 (cs) — Thẻ link làm lại bố cục

- Thứ tự mới: sản phẩm → 💰 hoàn dự kiến (đậm cả dòng) → ➕ có thể được thêm → ⚠️ Để được hoàn (3 ý, có ý "Mua đúng món này") → chữ nhỏ nghiêng → 👉 lời bấm nút ở cuối.
- Áp cho cả Telegram và Zalo; link Shopee lẫn TikTok.
- Proof: 841 test cashback qua; test mới kiểm thứ tự các khối.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo`.

---

## Phiên 2026-10-27 (cr) — Báo hoàn theo Shopee Comm tối đa 2,5% (PLAN-096)

- Kiểm 2 đơn mới, đối chiếu AMS: số trong bot khớp AMS. Lệch nằm ở số AddLiveTag báo lúc tạo link:
  - F1 `261026KTPPNSD1`: link báo Shopee Comm 8%, thực tế 2,5%;
  - Khung bằng khen `261027N7MJJKFV`: khách mua ở shop khác nên mất XTRA 12%.
- Chủ bot chọn cách A: thẻ link chỉ tính Shopee Comm tối đa 2,5%, cộng XTRA. Phần cao hơn ghi "➕ Có thể được thêm tới Xđ nếu Shopee áp mức hoa hồng cao hơn".
- Tin admin khi tạo link ghi rõ số AddLiveTag báo và số bot tính. Link cũ giữ nguyên số đã báo.
- Proof: 841 test cashback qua, ruff sạch.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo` và `pm2 restart Web_Dashboard`. Chờ duyệt 2 việc ở mục "Còn lại" của PLAN-096.

---

## Phiên 2026-10-26 (cq) — Thuật ngữ chung + ticket không mã thô

- Thuật ngữ trên mọi màn admin, tin admin và web: **HH ròng · Phần khách · Dự phòng · Biên** (= HH ròng − phần khách − dự phòng) **· Lãi · Tạm tính / Thực**.
  - Bỏ "Admin còn", "= Admin", "Khách nhận", "HH sau cùng", "Phí+T", "Biên sau dự phòng".
  - Màn `c:menu:glossary` (⚙️ Cài đặt → 📖 Thuật ngữ).
- Ticket:
  - lịch sử ghi "Khách · mở yêu cầu", "Admin · đổi trạng thái 🆕 Mới → 🔎 Đang xử lý";
  - đơn ghi trạng thái, duyệt, đối soát, ví bằng chữ; cách tính "V1.1 · 70%" / "V1.2".
- Proof: test cashback qua hết.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo` và `pm2 restart Web_Dashboard`.

---

## Phiên 2026-10-26 (cp) — Rà soát đợt 4: màn admin

- Trang chủ `/admin`: 📌 Việc cần làm, 📅 Hôm nay, báo giá, ví. Bỏ "Calculator V1.2" và dòng "Đối soát & chi trả: Chưa mở" ghi cứng.
- Menu 13 nút + menu con `c:menu:orders` (🧾 Đơn & hoa hồng) và `c:menu:settings` (⚙️ Cài đặt). Test kiểm mọi màn cũ còn đường vào.
- Thống kê ghi "Tạm tính" và "= Biên". Tin COMMISSION_CHANGED đổi tiêu đề theo nội dung, trạng thái bằng chữ.
- `insights.STATUS_WORDS`, `NOTICE_WORDS`, `SEND_WORDS`; `messages.fit_html`. Giờ VN ở 🔔 Thông báo khách.
- 🎵 TikTok chặn "Mở cho khách" khi chưa có khoá.
- Proof: 838 test cashback qua.
- **Next:**
  - Chủ bot restart `systemctl restart cashback-bot cashback-zalo` và `pm2 restart Web_Dashboard`.
  - Phần còn lại ghi trong `reports/CASHBACK_REVIEW_2026-10-26.md`.

---

## Phiên 2026-10-26 (co) — Rà soát đợt 3: câu chữ cho khách

- Câu nói sai ý:
  - 💰 Cách tính V1.1: "chưa trừ thuế và phí" đổi thành "không trừ thêm thuế hay phí khi chi trả";
  - ví khoá: lý do thật là "Bot chưa chi trả";
  - nút "🛡️ Để được ghi nhận" luôn mở trang mẹo (`u:p:tips`), kèm nút 📋 Điều khoản;
  - mẫu V3 trung tính Shopee / TikTok Shop.
- Zalo:
  - sửa câu lệnh sai ngữ pháp ("hãy dùng gõ hotro"…);
  - thêm PHRASES cho các câu "bấm";
  - "Nút này không còn hiệu lực" thành "Lựa chọn này đã hết hạn. Gõ menu…" (gom về `messages.STALE_BUTTON`);
  - menu số không đánh số hai lần.
- Từ ngữ:
  - "giao dịch" đổi thành "đơn";
  - "Hoàn tạm tính thay đổi";
  - "Mã link" (hỗ trợ chỉ đúng nơi xem);
  - ví và tin đơn ghi "sàn" thay "Shopee";
  - "Nội dung chuyển khoản"; "xoá" / "huỷ".
- Gửi lại link TikTok bị từ chối thì trả đúng lý do. Lời chào Zalo ghi đủ mục đích lưu dữ liệu.
- Proof: 835 test cashback qua.
- Còn lại: xem `reports/CASHBACK_REVIEW_2026-10-26.md`, đợt 3.

---

## Phiên 2026-10-26 (cn) — Rà soát đợt 5, phần nhỏ: an toàn vận hành + sổ ví

- `poller._periodic`: 8 việc định kỳ (ví, đối soát, Zalo, version, digest, bản tin, TikTok, backup) chạy riêng. Một việc lỗi chỉ ghi log và báo admin (mỗi việc 10 phút một lần), không chặn việc sau.
- Trigger `ledger_cashback_cap_insert/update` (phần khách ≤ hoa hồng, trừ dòng đã huỷ) và `ledger_available_frozen` (khoản đã vào ví không đổi số). Production 0 dòng vi phạm (đọc `mode=ro`).
- Backup `REQUIRED_TABLES` thêm `shopee_conversions`, `cashback_entries`, `cashback_payouts`, `payout_events`.
- `migrate()` khoá file `<db>.migrate.lock`. Kết nối admin timeout 15 giây.
- WAL chưa bật (cần thử với đọc `mode=ro`).
- Proof: 831 test cashback qua. Bot tạo trigger khi khởi động; backup tay trước restart.
- **Next:** đợt 3 (câu chữ khách), rồi đợt 4 (màn admin).

---

## Phiên 2026-10-26 (cm) — Rà soát đợt 2: TikTok đúng nền tảng

- Chủ bot: "triển khai theo từng mục".
- Cột `shopee_conversions.platform`:
  - mặc định `shopee`; migrate gán `tiktok` cho mã `tt:`; có index (platform, telegram_user_id);
  - `record_conversion_snapshot(platform=…)`, nguồn TikTok là `riohub_orders`.
- Trigger mới `financial_lock_platform_entry_insert/update`: khoản của đơn không phải Shopee không được `available`.
- Lọc `platform = 'shopee'` ở:
  - đối soát Shopee, khớp báo cáo thanh toán (`settlement.py`);
  - 📈 Thống kê, CSV, đếm ở màn Shopee Affiliate;
  - kiểm "đơn hoàn thành > 45 ngày".
- 🧾 Duyệt hoa hồng: biểu tượng 🎵, lý do TikTok viết thường, nguồn RioHub.
- Tin admin "🎉 Có N đơn TikTok mới"; lỗi đồng bộ viết thường, mỗi loại lỗi một lần mỗi ngày.
- Còn chờ chủ bot quyết: đơn có `pit` âm (hoa hồng giảm, kéo theo "cần kiểm tra" và tin hoàn giảm).
- Proof: 827 test cashback qua. Bot thêm cột và trigger khi khởi động; backup tay trước khi restart.

---

## Phiên 2026-10-26 (cl) — Rà soát câu chữ, UI/UX, kiến trúc + sửa đợt 1

- Chủ bot yêu cầu rà soát toàn bộ (Shopee + TikTok, Telegram + Zalo). Ba lượt rà chỉ đọc, chạy trên DB tạm. Claude Code kiểm lại mọi phát hiện P1.
- Báo cáo: `reports/CASHBACK_REVIEW_2026-10-26.md`, gồm đợt 1–5.
- Đợt 1, đã sửa (bug thật):
  - nút "📦 Xem đơn" của đơn TikTok bị chết;
  - đơn TikTok huỷ làm số hoàn tăng;
  - tin đơn huỷ in dòng tiền, tiêu đề sai;
  - admin bấm màn khác mà vẫn bị chờ gõ (tin kế tiếp bị nuốt);
  - kéo đơn TikTok dừng ở trang đầu khi thiếu `total`; chồng lấn 10 phút đổi thành 24 giờ;
  - 🛠 Vận hành chưa kiểm đồng bộ TikTok;
  - cookie hết hạn thì menu Shopee ẩn công cụ duyệt / đối soát.
- Proof: test cashback qua hết, ruff sạch.
- **Next:**
  - Chủ bot restart `systemctl restart cashback-bot cashback-zalo`.
  - Chủ bot chọn đợt 2–5.

---

## Phiên 2026-10-26 (ck) — PLAN-095: đồng bộ đơn TikTok Shop (giai đoạn B)

- Chủ bot duyệt: kéo mỗi 2 giờ, báo đơn cho khách như Shopee.
- Link TikTok thật đầu tiên (id 56, admin): giá 300.000đ, hoa hồng 5% (15.000đ), hoàn **9.347đ** (V1.2 70%, phí 0,98%, thuế 10%), đã giao.
- Giai đoạn B: `tiktok_sync.py` chạy nền trong bot Telegram, ghi đơn `tt:<order>:<sku>` vào `shopee_conversions`, dùng chung sổ ví, thông báo, dashboard. Không đổi cấu trúc DB, không gán APPROVED / SETTLED, ví khoá.
- Đối soát Shopee bỏ qua đơn TikTok. Tin và màn đơn TikTok ghi "TikTok".
- Proof: 820 test cashback qua.
- **Next:**
  - Chủ bot restart `systemctl restart cashback-bot cashback-zalo`. Lượt đồng bộ đầu chạy ngay sau khi bot lên (kéo 7 ngày).
  - Kiểm 🎵 TikTok Shop sau vài phút.

---

## Phiên 2026-10-26 (cj) — 🧾 Duyệt hoa hồng: đơn đã xem không còn nằm ở "Cần kiểm tra"

- Chủ bot hỏi: đã bấm "đã kiểm tra" mà đơn ••••20NS vẫn hiện ở "Cần kiểm tra". Nguyên nhân: mục này đếm theo trạng thái Shopee (`NEEDS_REVIEW`), không xét admin đã xem.
- Sửa (`admin_validation.py`):
  - "Cần kiểm tra" và danh sách 🚨 chỉ còn đơn admin chưa xem.
  - Thêm dòng và danh sách "✔️ Đã xem, chờ Shopee" (`c:cv:l:seen`).
  - Bảng nới cột lên 19 ký tự.
- Production (đọc `mode=ro`): Cần kiểm tra 0, Đã xem chờ Shopee 1.
- Proof: test cashback qua hết.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo`.

---

## Phiên 2026-10-26 (ci) — PLAN-085 giai đoạn A: link TikTok Shop (chỉ admin thử)

- RioHub đã mở quyền: `orders` đọc được (1 đơn đã chốt, `pit = 0`, tức chưa trừ TNCN); tạo link thử `test085` được. Rio giữ 0%.
- Thuế TikTok: giống Shopee (chủ bot).
- Giai đoạn A đã code: dán link TikTok Shop → thẻ báo giá + nút "Mua trên TikTok Shop" (Telegram + Zalo). Chế độ mặc định **chỉ admin**; `/admin` → 🎵 TikTok Shop để mở cho khách (cần xác nhận). Đơn TikTok chưa đồng bộ (giai đoạn B).
- Đơn Shopee ••••20NS: hoa hồng không đổi (1.372đ). Mã trạng thái Shopee mới `2` (display "Completed") nên bot chuyển "cần kiểm tra", đúng thiết kế. Click Zalo đã về (4/11 link có click).
- Bot sẽ thêm cột `link_requests.platform` khi khởi động. Có backup tay trước khi restart.
- Proof: 815 test cashback qua.
- **Next:**
  - Chủ bot restart `systemctl restart cashback-bot cashback-zalo`.
  - Chủ bot dán thử 1 link TikTok trên Telegram (admin).
  - Giai đoạn B.

---

## Phiên 2026-10-26 (ch) — PLAN-094: backup ngoài máy (Google Drive, rclone crypt)

- Code xong: `offsite.py` + systemd timer 03:30 + dòng "Backup ngoài máy" ở 🛠 Vận hành. Hướng dẫn trong `deploy/cashback/README.md`, mục "Backup ngoài máy".
- 🛠 Vận hành sẽ báo đỏ dòng này cho tới khi chủ bot cài xong. Đây là lời nhắc, không phải lỗi.
- Proof: 808 test cashback qua.
- **Next (chủ bot):**
  - Cài rclone, `rclone config` (gdrive + cashback-crypt), ghi hai mật khẩu ra chỗ khác.
  - Thêm `CASHBACK_OFFSITE_REMOTE=cashback-crypt:` vào `.env`.
  - Chạy thử, rồi cài timer.
  - Restart `systemctl restart cashback-bot cashback-zalo` và `pm2 restart Web_Dashboard` (Vận hành có dòng mới).

---

## Phiên 2026-10-26 (cg) — Test ví Zalo + PLAN-093 thời hạn lưu dữ liệu + mẫu điều khoản V3

- Chủ bot duyệt: "oke em triển khai nhé em, có thể admin cấu hình những con số cho sau này".
- Việc 3 (`19fda4c`): test luồng ví trên Zalo (khai tài khoản → rút → "Hoan tien 000001"; chưa đồng ý điều khoản thì chặn). Không có bug.
- Việc 2: `retention.py` + màn 🗄 (📋 Điều khoản → 🗄 Thời hạn lưu dữ liệu). Mặc định: tài chính 10 năm; tài khoản chưa nhận tiền, link/đơn không ra tiền, ticket: 24 tháng. Admin chỉnh được, có 📊 Lịch sử.
- Việc 1: mẫu V3 vào `terms_content.py` (bản nháp tạo theo mốc lưu đang cài). **Chưa công bố.** Điều kiện công bố: parser báo cáo thanh toán + việc tự xoá dữ liệu hết hạn + bật ví.
- Proof: 804 test cashback qua, ruff sạch.
- **Next:**
  - Chủ bot restart `systemctl restart cashback-bot cashback-zalo`.
  - Việc 4: backup ra Google Drive bằng rclone crypt (chủ bot tự đăng nhập Google và đặt mật khẩu).
  - Sau 10:52 giờ VN: xem click link Zalo.

---

## Phiên 2026-10-26 (cf) — BUG: 🧮 Hoà vốn tính theo cách tính cũ (V1.1) thay vì V1.2 đang chạy

- Phát hiện khi rà điều khoản V3:
  - Từ 24/10 mọi link mới đều tạo theo V1.2 (23 link). Sổ chỉ có 2 đơn của link cũ V1.1.
  - `insights.breakeven` (PLAN-089) đoán cách tính theo đa số dòng trong sổ, nên ra V1.1.
- Ảnh hưởng: chỉ con số hiển thị (màn 🧮 Hoà vốn, thẻ web, gợi ý HH ròng ở 🎯). Không đụng tiền hay chính sách.
  - Trước khi sửa: mức 70% có biên 19%, cần 5,26tr (~562 đơn) mỗi tháng.
  - Đúng là: V1.2 biên 26,7%, cần 3,74tr (~400 đơn) mỗi tháng.
- Sửa: lấy cách tính, % hoàn và dự phòng từ `link_policy_snapshots` của link mới nhất; chưa có snapshot thì suy từ sổ như cũ.
  - Test `test_hoa_von_theo_chinh_sach_link_moi_nhat`: hỏng khi chưa sửa, qua khi đã sửa.
- Proof: 800 test cashback qua.
- **Next:** chủ bot restart `systemctl restart cashback-bot cashback-zalo` và `pm2 restart Web_Dashboard`.

---

## Phiên 2026-10-26 (ce) — PLAN-092: 🌙 bản tin tối cho chủ bot

- Chủ bot chọn "mỗi tối", và dặn "phát hiện bug thì báo anh".
- 21:00 giờ VN mỗi ngày, bot Telegram gửi admin một tin (hàng đợi tin admin, `NIGHTLY_BRIEF`) gồm: giai đoạn, 🎉 mốc G1 mới, số hôm nay, các mục tiêu đã đặt, giới hạn an toàn, top 3 khách 7 ngày. Không gửi khách.
- Proof: 799 test cashback qua, ruff sạch. Xem trước trên production hiển thị đúng.
- Bug trong lúc làm: không có bug production. Test mới của em lúc đầu dựa vào đơn mẫu cố định ngày 21/10, sẽ tự hỏng sau 28/10; đã sửa trước khi merge.
- **Next:**
  - Chủ bot restart `systemctl restart cashback-bot cashback-zalo` (web không đổi).
  - Tối nay 21:00 kiểm tra bản tin đầu tiên.
  - Mục 3 (rà điều khoản V3).

---

## Phiên 2026-10-26 (cd) — PLAN-091: 🔍 Tìm mã cho admin (Telegram + web)

- Chủ bot duyệt ("oke em triển khai plan này đi").
- Telegram: `/tim <mã>` hoặc `/admin` → 🔍 Tìm (`c:in:f`). Màn chi tiết link `c:in:l:<id>`.
- Web: ô tìm trên `/cashback`, trang `/cashback/search?q=` và `/cashback/links/{id}`.
- Bot tự nhận loại mã: mã link (hoặc cả link có sub_id=), mã đơn, #ticket, «Hoan tien N», ID khách, @tên, tên Zalo, tên sản phẩm. Chỉ đọc, không ghi gì.
- Proof: 797 test cashback qua, ruff sạch. Production: `BiE1mRa5` → link của Zalo · Thanh Vu, đã giao, 0 click (báo cáo click chưa về).
- **Next:**
  - Chủ bot restart `systemctl restart cashback-bot cashback-zalo` và `pm2 restart Web_Dashboard`.
  - Sau lần đồng bộ 10:52 giờ VN, tra lại click của các link Zalo.

---

## Phiên 2026-10-26 (cc) — Tin trả link nhắc mua qua link của bot + sửa dòng link 39

- Chủ bot duyệt ("oke em triển khai đi"):
  - Thẻ link (Telegram + Zalo) có thêm 3 dòng: 👉 bấm mua; ⚠️ mua thẳng trong app không được hoàn; món đã có trong giỏ thì xoá rồi mở lại bằng link của bot. Link không có hoàn thì không hiện dòng ⚠️.
  - Dòng dẫn link trên Zalo: "Bấm link này để mua. Mua thẳng trong app Shopee sẽ không được hoàn:".
  - Mục Phễu (Telegram + web) ghi chú click về trễ khoảng 1 ngày. Báo cáo click Shopee về chậm: ví dụ click 24/10 02Z mới vào lần đồng bộ 25/10 03:51Z.
- Production: đã backup `cashback-manual-20261026T020857Z.sqlite`, sửa link id 39 (`priYghQy`) từ `pending` thành `sent`. Hiện còn 0 link kẹt.
- Proof: 793 test cashback qua, ruff sạch.
- **Next:**
  - Chủ bot restart `systemctl restart cashback-bot cashback-zalo` và `pm2 restart Web_Dashboard`.
  - Chủ bot tự bấm thử một link trên Zalo xem có mở đúng sản phẩm trong app Shopee.
  - Sau 10:52 giờ VN 26/10 (lần đồng bộ đầu tiên có click ngày 25/10), xem lại click của link Zalo.

---

## Phiên 2026-10-26 (cb) — Link Zalo `priYghQy` "kẹt": tin đã tới khách, chỉ thiếu cờ đã giao

- Nguyên nhân:
  - Link id 39 (khách Zalo, 24/10 15:28Z) nằm trong tin trả lời Zalo inbox #5. Tin này đã `replied` và có link, tức khách đã nhận.
  - Bản vá ghi `delivery_status` cho luồng Zalo (`f184972`) lên lúc 15:32Z, sau tin đó 4 phút, nên dòng link còn `pending`.
  - Không cần gửi lại cho khách.
- Vá theo dõi: 🛠 Vận hành mục "Link giao tới khách" giờ đếm cả link kẹt quá 1 giờ tính từ đầu, không chỉ trong 24 giờ. 🎯 Mục tiêu thêm mục này vào giới hạn an toàn.
- Dòng 39 trên production vẫn `pending`, nên Vận hành sẽ báo đỏ cho tới khi sửa. Sửa thành `sent` cần chủ bot duyệt và backup trước.

---

## Phiên 2026-10-26 (ca) — PLAN-090: 🎯 Mục tiêu của bot (Telegram + web)

- Chủ bot hỏi góp ý về mục tiêu cho bot. Claude Code đề xuất: chỉ số chính (North Star) là đơn hoàn thành mỗi tháng; giai đoạn G1 (chạy trọn vòng tiền) → G2 (khoảng 100 đơn, 50 khách hoạt động) → G3 (hoà vốn); kèm các giới hạn an toàn. Chủ bot nói "triển khai đi".
- Đã thêm `insights.goals` và màn 🎯 Mục tiêu (Telegram `c:in:t`, nút ✍️ `c:in:t:<mã>`, 📊 Lịch sử action `goal`), cộng thẻ trên web `/cashback`.
  - Bot không tự đặt số. Số gợi ý G2 và mức hoà vốn chỉ hiện ở màn nhập.
- Production (đọc `mode=ro`): G1 đạt 1/4 mốc (có đơn đầu tiên; chưa có đơn hoàn thành). Tháng 10: 2 đơn đặt, 0 hoàn thành, 11 khách mới; % có đơn trong 7 ngày chưa đủ mẫu. Giới hạn an toàn đều xanh.
- Proof: 792 test cashback qua, ruff sạch. Web render được với DB production.
- Chạy production: 26/10 01:35Z, chủ bot restart. Hai bot `code_version` đều là `bbc1da8`, heartbeat còn mới, log không có lỗi mới. Web_Dashboard đang chạy. PLAN-090 đã vào archive.
- **Next:** chủ bot nhập mục tiêu ở `/admin` → 🎯 Mục tiêu (gợi ý G2: 100 đơn hoàn thành, 50 khách hoạt động; ngưỡng huỷ do chủ bot chọn). Phần đăng bài không thuộc phạm vi phiên cashback.

---

## Phiên 2026-10-26 (bz) — Kiểm tra sáng 26/10 (08:15 giờ VN)

- Buffer: 0 lỗi 429 kể từ khi mở lại key. 24h qua đăng 14 bài, cả 4 kênh còn 10/10 bài chờ.
  - Suất 1 ngày còn: f8pL 194, RZX2 205, ZVsP 178 trên 250.
  - Suất 30 ngày còn: RZX2 1484/3000 và ZVsP 2100/3000, đều ở dưới hoặc ngay mức giữ 70%, nên việc nền (quét kênh, `post_statuses`) bị dừng. Đăng bài vẫn chạy.
- Đạo lý: nguồn #5 không còn NEW. Sống Nhẹ có 58 READY. Từ 14:30 26/10, mọi bài hẹn giờ của Sống Nhẹ đều là đạo lý; xếp lịch tới 28/10 07:30.
  - 4 DUPLICATE ở pHash 0–4 là trùng thật.
- 3 job FAILED đều từ 23/10, kênh cũ đã gỡ. Không có lỗi mới.
- Cashback: `cashback-bot` và `cashback-zalo` chạy `c1554bd` (restart 25/10 16:24Z). Web_Dashboard restart cùng giờ. Không có log lỗi trong 12h.
- **Next:** như phiên (bx). Thêm: theo dõi suất 30 ngày của RZX2 và ZVsP.

---

## Phiên 2026-10-25 (by) — 🧮 Hoà vốn (hướng A: chi phí vận hành tính ngoài % khách)

- Chủ bot hỏi có nên trừ chi phí vận hành vào % của khách không. Claude Code đề xuất A: giữ 70%, tính chi phí ngoài, xem hoà vốn rồi mới chọn %. Chủ bot đồng ý.
- Thêm `insights.breakeven` và màn 🧮 Hoà vốn (Telegram `c:in:b` + thẻ web). Chỉ xem, không đổi chính sách.
- Production: chi phí 1tr/tháng (chủ bot đã nhập); mức 70% cần khoảng 5,26tr hoa hồng ròng (khoảng 562 đơn) mỗi tháng; 30 ngày qua đạt 0,4%.
- **Next:** chủ bot chạy `systemctl restart cashback-bot cashback-zalo` và `pm2 restart Web_Dashboard`.

---

## Phiên 2026-10-25 (bx) — PLAN-087: giữ video READY 21 ngày, lấy lại 42 video đạo lý

- `main@28845a4`: file `reup` của material READY được giữ 21 ngày, thay vì 7. Restart Maintenance + Web_Dashboard.
- 42 material nguồn #5 (18 DUPLICATE, 24 FAILED vì bị dọn) về NEW, trỏ Sống Nhẹ Tuổi 40. Backup `data/backups/viral-daoly-rescue-before-20261025T141702Z.json`.
- Đang xử lý: tải lại, lên READY, viết caption, tự hẹn giờ (#1312 hẹn 17:30 26/10). Tổng khoảng 60 video đạo lý, đủ khoảng 12 ngày.
- 9Router auth 404: caption tự chuyển sang Gemini, chưa xử lý.
- **Next:**
  - Kiểm tra NEW nguồn #5 về 0 và không có DUPLICATE mới.
  - Khoảng 01/11: so số liệu Meta, quyết định bật lại nguồn đầm #4.
  - Owner gửi thêm kênh đạo lý. Owner chọn cách xử lý 0 click link.

---

## Phiên 2026-10-25 (bx) — PLAN-089 dashboard khách hàng + dòng tiền (Telegram + web)

- Chủ bot: làm cả hai, đủ chỉ số CEO / COO; chi phí vận hành và hạ tầng chưa tính, nên thêm ô nhập chi phí mỗi tháng.
- `cashback_bot/insights.py` (chỉ đọc) tính:
  - Dòng tiền: GMV → hoa hồng → MCN → phần khách → dự phòng → biên → lãi sau chi phí.
  - Nghĩa vụ với khách, thời gian ra tiền.
  - Tăng trưởng: phễu, mức tập trung, kênh, ngành / shop, giữ chân theo tuần.
  - Vận hành: 11 mục.
  - Từng khách: 6 nhóm, dòng thời gian.
- Telegram /admin có 4 nút mới. Web có `/cashback` (sau đăng nhập dashboard).
- Proof: 800 passed. Chạy thử trên production chỉ đọc: biên 3.563đ / ròng 18.740đ.
- **Đã:** 14:14:59Z hai bot (PID 833260 / 833261) chạy `a193faa`; Web_Dashboard PID 833370.
  - `/cashback` chưa đăng nhập thì chuyển `/login`. Màn Telegram render đúng trên DB thật (chỉ đọc).
  - Claude Code không tự tạo cookie đăng nhập (auto mode chặn), nên trang web cần chủ bot tự mở xem.
- **Lưu ý:** cổng :8000 đang nhận request từ Internet (IP Facebook / AWS lấy `/buffer-media`). `/cashback` có đăng nhập, nhưng nên cân nhắc giới hạn.
- **Next:** chủ bot mở /admin → 💹 và web `/cashback`, nhập chi phí vận hành mỗi tháng.

---

## Phiên 2026-10-25 (bw) — Sống Nhẹ Tuổi 40: ưu tiên video đạo lý

- Meta 27/9–24/10: 14,1K view (99,4% người chưa theo dõi), 0 click link. Video đạo lý 22/10 07:30 (`nunhanthongtue`, material 1275) được 4,8K view; video đầm 300–1,5K.
- Nguồn đạo lý (#5) quét 16/10 được 50 video, chỉ 4 đã đăng. 24 bị dọn sau 7 ngày. 18 bị pHash (khoảng cách 6–8) chặn nhầm là trùng: cùng người, cùng phông, khác nội dung.
- Owner duyệt bước 1, làm qua hàm của app. Backup: `data/backups/viral-settings-before-daoly-20261025T140950Z.json`.
  - `viral.phash_max_distance` từ 8 xuống 5, qua `upsert_setting`, updated_by `claude-code`.
  - Nguồn #5 `max_videos` từ NULL (50) lên 80, qua `SourceService.set_source_limits`.
  - Owner tự bật nguồn #5. Nguồn đầm #4 vẫn tắt.
- Quét tay nguồn #5: found 18, skipped 50. 18 material NEW cho `6adb578c…9cde9a`. Kênh chỉ có khoảng 68 video đạt mức xem, nên đợt này đủ khoảng 3–4 ngày (5 bài/ngày).
- **Next:**
  - Khoảng 28/10, khi READY đạo lý dưới 5: hỏi Owner duyệt bước 2, đưa 42 material cũ (24 FAILED dọn, 18 DUPLICATE) về NEW, backup trước.
  - Sau 1 tuần: so số liệu Meta, quyết định bật lại nguồn đầm.
  - PLAN chia tỉ lệ theo nguồn nếu cần.
  - Còn 0 click link vì gói Free không có bình luận đầu tiên: Owner chưa chọn cách xử lý.

---

## Phiên 2026-10-25 (bw) — PLAN-087 vận hành + PLAN-088 sổ chi trả (chủ bot: "duyệt và vá tất cả")

- **PLAN-087** (`main@4d1f789`):
  - Mất mạng (DNS / không kết nối được) là `offline`: tin trả về hàng đợi, không tính lượt thử, không còn `unknown` hay bị bỏ.
  - Chỉ 403 mới đánh dấu khách chặn bot.
  - Zalo lỗi DB giữa chừng thì báo khách và báo admin. Tin nhiều phần không gửi lặp phần đầu. Mỗi bot gỡ kẹt `sending` của kênh mình.
  - Đồng bộ Shopee không còn quay vòng. Chia phí MCN cho checkout nhiều đơn.
  - Backup tay có tên `cashback-manual-*` và được dọn riêng.
  - `ops_watch`: báo khi hai bot chạy khác commit; bot Zalo canh bot Telegram; tóm tắt tin gửi lỗi lúc 8 giờ.
  - `deploy/cashback/`: unit systemd và logrotate (chưa cài). `test_14` đã sửa.
- **PLAN-088**:
  - B1–B16: không chi khi đơn nguồn đã huỷ; không chuyển tiền 2 lần; quỹ không đếm đôi; thu hồi theo ADR-059 (dòng `:clawback:` số âm, kỳ bị đảo thì về `holding`).
  - Zalo rút được nhiều lần. Nút Rút tự cắt theo hạn mức. Ghi «đã trả» không bị chặn.
  - Trigger DB mới: máy trạng thái và `financial_lock_v2_*`. Chờ 7 ngày khi đổi tài khoản, admin xác minh thì rút ngay.
  - Câu chữ ví, tin chi trả kèm mã giao dịch, màn admin.
  - C3–C7: xoá số tài khoản trong tin đã gửi; cảnh báo chat admin; CSV; tối đa 5 ticket mỗi ngày; `gemini_cookies.json` → 0600.
- Proof: 773 passed; bản sao production chạy `migrate` hai lần không lỗi, 5 trigger mới, ví vẫn khoá (4 lý do), số liệu không đổi.
- **Chưa làm (cần chủ bot):**
  - C2: công cụ xoá dữ liệu và hạn lưu.
  - D3: nơi chép backup ra ngoài máy.
  - Parser báo cáo thanh toán Shopee + migration 007 (cần file thật).
  - Công bố V3 khi ví sắp mở.
- **Đã:** chủ bot cài systemd (cách A) lúc 13:47:46Z.
  - `cashback-bot` PID 828613 và `cashback-zalo` PID 828614, đều `enabled`, `NRestarts=0`.
  - Hai bot chạy `1b957b7`, nhịp sống bình thường, log không lỗi.
  - DB có đủ 5 trigger mới; logrotate đã cài; `gate_b_check` OK.
  - PLAN-087 và PLAN-088 đã chuyển sang archive.
- **Restart từ nay:** `systemctl restart cashback-bot cashback-zalo`.
- **Next:** chờ chủ bot quyết C2 (xoá dữ liệu, hạn lưu) và D3 (nơi chép backup); parser báo cáo thanh toán chờ file Shopee thật.

---

## Phiên 2026-10-25 (bv) — Rà soát 4 góc nhìn

- `reports/CASHBACK_REVIEW_2026-10-25.md`: 4 agent chỉ đọc code (tiền, bảo mật, vận hành, câu chữ); Claude Code kiểm chứng các điểm nặng.
- Ảnh hưởng ngay: bot Zalo chạy code cũ từ 24/10 15:59Z (A1); backup chỉ giữ ~1 ngày vì bản tay chung mẫu tên (A2); tin khách thành `unknown` khi mất mạng (A3); 400 bị coi là chặn bot (A5).
- Trước khi mở ví: 4 lỗi đỏ B1–B4 (chi dù đơn huỷ, chuyển 2 lần, quỹ đếm đôi, thu hồi chưa có), Zalo chỉ rút 1 lần (B5), số dư > hạn mức không rút được (B6).
- **Đã:** chủ bot restart Zalo (PID 812884, 11:36:33Z) và Telegram (PID 813170, 11:38:12Z), cả hai chạy `main` mới; `.env` có `CASHBACK_BACKUP_KEEP=60` (bot đọc được 60). `gate_b_check` OK.
- **Next:** chủ bot chọn gói PLAN làm trước (gợi ý: Vận hành).

---

## Phiên 2026-10-25 (bv) — PLAN-086: kênh kín không hỏi suất; test đang gọi Buffer thật

- `main@e8e3828`: `schedule_reup` đếm hàng chờ trước `_quota_block`. Restart Maintenance 11:11Z: 3 kênh kín, không còn request `Limits`.
- **Rò suất:** 17 test (`test_buffer_cluster.py`, `test_challenger_m1_2_concurrency.py`) gọi `api.buffer.com` bằng key thật. Một lần chạy hồi quy mất 43–58 suất mỗi key. Chi tiết trong PLAN-086.
- Suất lúc 11:11Z (15 phút / ngày / 30 ngày): `f8pL` 43/116/2616, `RZX2` 57/207/1486, `ZVsP` 42/192/2114. Mức giữ 70% đang chặn request nền, đăng bài vẫn được.
- **Next:** Owner duyệt PLAN chặn mạng trong test (autouse fixture trong `tests/conftest.py`). Trước đó KHÔNG chạy 2 file trên nếu không có `-p block_buffer_net`.

---

## Phiên 2026-10-25 (bu) — Hạn mức theo từng khách + V3 nháp

- Chủ bot: hạn mức ngày / tháng theo từng khách, khách tích 5–10tr phải rút được một lần; không thêm câu "tự chịu thuế"; đổi mức không báo trước.
- `main@515b3ee`: `check_limits(conn, user_id, …)` chỉ cộng yêu cầu của chính khách; nút chọn mỗi lần 500k–10tr, ngày 2tr–20tr, tháng 10tr–100tr; màn ghi "Hạn mức rút mỗi khách". Test 47/48 đổi sang theo từng khách. 730 passed, 1 hỏng có từ trước (`test_14`).
- `reports/CASHBACK_TERMS_V3_DRAFT.md`: nháp V3 đã theo câu trả lời, chưa đưa vào bot (công bố khi ví sắp mở).
- Ghi `payout_policy_decisions` id 7 (backup `cashback-20261025T111224Z.sqlite`); reference ghi nhầm `main@e8e3828`, đúng là `515b3ee` (ghi chú ở ADR-059).
- Main có commit PLAN-086 (buffer, `e8e3828`) của luồng khác; đã rebase, không đụng.
- **Đã:** restart PID 808308 (11:14:56Z, không lỗi mới); chủ bot chỉnh hạn mức → id 6: tối thiểu 10k, 1tr/lần, 5tr/ngày, 10tr/tháng mỗi khách. `gate_b_check` OK.

---

## Phiên 2026-10-25 (bu) — Buffer: báo cáo sau khi 3 key mở lại

- Từ khi bật log `[Buffer][req]` (PLAN-072): 0 request lỗi, 0 lần 429 thật. Dòng "post_statuses ... 429" là cooldown nội bộ, không gửi đi.
- Suất ngày còn lại lúc 18:00 25/10: `f8pL` 173/250 (30 ngày 2673/3000), `RZX2` 233/250 (1529/3000), `ZVsP` 172/250 (2172/3000).
- 20 bài đến hạn từ 24/10 07:30: 19 bài có Facebook/Buffer tải video lúc đăng. Bài lỗi duy nhất là material 1300 (job 1118), đã biết, file mất trước PLAN-069. Hàng chờ: Uyển Nhi 10, Hoa Lệ 10, TikTok trnvp89 10, Sống Nhẹ Tuổi 40 3. Page này hết READY sau 26/10 11:30 vì nguồn đang tắt.
- "Bỏ first_comment" chỉ ghi 1 lần mỗi key (job 1135, 1156), đúng PLAN-070.
- **Phát hiện tốn suất:** `queue_job.schedule_reup` gọi `_quota_block` (GetOrganizations + Limits, 2 request) TRƯỚC khi đếm hàng chờ trong DB. Kênh đã 10/10 nên cứ 5 phút lại mất 2 request rồi mới báo "đã kín". `f8pL`: 75 request nền hôm 24/10, chỉ 8 CreatePost. Mức giữ 70% chặn được 429, nhưng phần suất nền bị dùng hết vào việc này, nên `post_statuses` không chạy được (job DONE không có `post_url`).
- **Next:** chờ Owner duyệt PLAN sửa: đếm hàng chờ trước `_quota_block` (1 file + test). Owner cân nhắc bật nguồn cho Sống Nhẹ Tuổi 40 (`/nguon`; PLAN-071 chỉ quét khi < 15 READY).

---

## Phiên 2026-10-25 (bt) — Thuế A1: không khấu trừ khi chi tiền hoàn

- Chủ bot chốt: chi tiền hoàn như chuyển khoản thường, không khấu trừ TNCN; bot lưu chứng từ từng lần chi để kê khai khi cần; thuế của chủ bot lấy từ dự phòng 10%.
- Ghi `payout_policy_decisions` id 6 `tax` APPROVED (backup `cashback-20261025T105632Z.sqlite`); ADR-059 cập nhật.
- Khoá tài chính còn 4 lý do: bằng chứng kỳ Shopee đã trả; "Chưa chốt chính sách thuế" (bảng `payout_tax_policies` thuộc migration nháp 007, chưa có trên production → PLAN backend); điều khoản chi trả (V3); một kỳ đối soát khớp.
- **Next:** Claude Code soạn điều khoản V3 (nháp) cho chủ bot duyệt; PLAN backend: migration 007 + parser báo cáo thanh toán, chờ 7 ngày đổi tài khoản, thu hồi.

---

## Phiên 2026-10-25 (bs) — Admin chỉnh hạn mức rút

- Chủ bot: rút tối thiểu 10k được, hạn mức admin tự chỉnh. Phát hiện lệch: ví 10k nhưng hạn mức 20k (bot lấy số lớn hơn).
- `main@159f9fb`: ⚙️ Cài đặt thêm 3 hàng nút (mỗi lần 200k–2tr, ngày 1tr–10tr, tháng 5tr–50tr); mỗi lần đổi thêm dòng `payout_limit_policies` ACTIVE `admin:<id>`; «Rút tối thiểu» kéo theo `min_vnd`; sai thứ tự thì không ghi; Lịch sử có dòng "hạn mức rút". 730 passed, 1 hỏng có từ trước (`test_14`).
- Ghi `payout_policy_decisions` id 5 `payment_limits` APPROVED (backup `cashback-20261025T105051Z.sqlite`). Giữ tiền đã là 15 ngày (chủ bot tự chọn).
- **Đã:** restart PID 802976 (10:51:33Z, không lỗi); chủ bot bấm 10k → 20k → 10k, hạn mức hiện hành id 4: 10k / 500k / 2tr / 10tr (`admin:`), ví 10k, giữ 15 ngày. `gate_b_check` OK.

---

## Phiên 2026-10-25 (br) — Chính sách chi trả: ADR-059, ghi 4 quyết định + hạn mức

- Chủ bot muốn mở ví → không mở được (khoá tài chính, không có công tắc vượt). Liệt kê 10 điều kiện, chủ bot trả lời bộ câu hỏi + gửi ảnh báo cáo thanh toán Shopee.
- `agents/decisions/ADR-059-cashback-payout-policy.DRAFT.md`: quyết định + phát hiện từ báo cáo thanh toán (07/2026 Shopee không trừ thuế; chi tiết gom theo ngày hoàn thành, không theo đơn; hoá đơn theo ngày, trả thứ Ba / Năm).
- Chủ bot "duyệt" → ghi production (backup `cashback-20261025T103648Z.sqlite`): `payout_policy_decisions` 4 dòng APPROVED (clawback, bank_verification, payment_limits, manual_payment), `payout_limit_policies` id 1 ACTIVE 20k/500k/2tr/10tr. Không bật ví, không tạo payout. `gate_b_check` OK.
- Khoá tài chính còn 5 lý do: bằng chứng kỳ Shopee đã trả (2 dòng), thuế (2 dòng), điều khoản chi trả.
- **Next:**
  1. chủ bot: hỏi kế toán A1; vào /admin → 👛 Ví khách → ⚙️ Cài đặt chọn giữ 15 ngày, rút tối thiểu 20k (hiện 30 ngày / 10k);
  2. Claude Code: soạn điều khoản V3 sau A1;
  3. cần PLAN backend: parser báo cáo thanh toán Shopee (ghép theo ngày hoàn thành), chờ 7 ngày khi đổi tài khoản, thu hồi trừ tiền sau + khoá rút (sửa ADR-052 mục 7).

---

## Phiên 2026-10-25 (bq) — Thống kê: tên khách Zalo + số click theo link

- **Hỏi:** click Zalo trong Báo cáo click Shopee không có sub_id. Kết luận: 4 click 22:03–22:05 24/10 xảy ra trước khi bot Zalo chạy lần đầu (22:26), không phải link bot; link bot luôn có sub_id.
- **Chủ bot duyệt cả 2 (a)+(b):** `main@b7cbcc4` (backup `cashback-20261025T100632Z.sqlite`).
  - `admin_stats.py`: `TopUser` (tên Telegram / tên Zalo, link, click), `RecentLink` (5 link gần nhất kèm click); click = `shopee_clicks` khớp `sub_id`.
  - `admin_ui.py`: "Gửi nhiều nhất" hiện `Zalo · tên` (chưa có tên: `Zalo #N`) thay cho −1, thêm "· N click"; mục mới "🖱️ Link gần nhất" ở màn Chi tiết.
  - `admin_support.py`: dòng link trong ticket thêm "· N click".
- **Test:** 729 passed, 1 hỏng có từ trước (`test_14`); ruff sạch. Dựng thử trên bản sao DB (đã shred): 1.762 ký tự.
- **Đã restart:** bot Telegram PID 798434 (10:16:46Z, `main@0bc045c`); `gate_b_check` OK (2 pending 13.117đ, ví khoá, trigger 6/6). Bot Zalo không đổi.
- **Next:** sau restart mở /admin → 📈 Thống kê → 🔎 Chi tiết để kiểm tra; link `priYghQy` (22:28 24/10) vẫn `delivery_status=pending`, chưa xem nguyên nhân.

---

## Phiên 2026-10-25 (bp) — Thử RioHub lần 1: creator chưa vào RioMCN

- Chủ bot thêm `RIOHUB_API_KEY` + `RIOHUB_CREATOR_USERNAME=twot283` (xác nhận đúng tài khoản); duyệt thử đọc đơn + 1 link.
- `orders --days 7` → `403 mcn_membership_required` ("chưa là thành viên RioMCN (chưa được duyệt)"). Khoá hợp lệ.
- Sửa client đọc lỗi `{"error": {"code", "message"}}`, CLI in 1 dòng; 25 test RioHub đạt, ruff sạch.
- **Chưa tạo link thử** (chờ RioMCN). Không ghi DB, bot không đổi.
- **Next:**
  1. chủ bot đăng ký / chờ duyệt RioMCN, hỏi tỷ lệ chia MCN + phí thành viên;
  2. duyệt xong: thử lại `orders`, rồi `link <link sản phẩm> test085`.

---

## Phiên 2026-10-25 (bo) — PLAN-085 A2: client RioHub lên main (chưa nối bot)

Chủ bot dán spec đủ 8 phần, chọn "Viết client, chưa nối bot".

- **Code:** `main@0d613ea`.
  - `cashback_bot/riohub_client.py`: tạo link / link + sản phẩm, tra sản phẩm, kéo đơn, phân loại lỗi, CLI thử tay;
  - `config.py`: `RIOHUB_API_KEY`, `RIOHUB_CREATOR_USERNAME`;
  - `.env.example`;
  - 24 test giả lập.
- **Không gọi RioHub.** Không nối vào luồng khách. Bot đang chạy không cần restart (không file nào đang chạy dùng tới).
- **Test:** 726 passed, 1 failed có từ trước: `test_cashback_auto_sync.py::test_14_bam_tay_khi_tu_dong_dang_chay`. Test đặt giờ giả 2026-10-25 02:00Z nhưng màn admin dùng giờ thật, nên test hỏng từ 02:00Z hôm nay. Chưa sửa vì ngoài phạm vi; cần chủ bot cho sửa test.
- **System State:** Telegram PID 747966, Zalo PID 690595; ví khoá.
- **Next:**
  1. chủ bot hỏi RioHub, thêm khoá vào `.env`;
  2. thử tay `python -m cashback_bot.riohub_client products <id>` (cần duyệt);
  3. sửa test_14 nếu chủ bot đồng ý.

---

## Phiên 2026-10-25 (bn) — Spec tích hợp RioHub: bổ sung nghiên cứu, PLAN-085 nháp

Chủ bot dán spec "RioHub × TikTok Shop Affiliate API" (09/10/2026, phần yêu cầu viết code).

- Báo cáo `reports/CASHBACK_TIKTOK_RIOHUB_RESEARCH.md` thêm phần spec: `actual_commission` đã trừ TNCN 10% + chia MCN (dấu âm), báo giá dùng `observed_commission`, `/product-links` cho link + giá 1 lượt, `sub_id` không được chứa `-`, khoá đơn (`order_id`, `sku_id`).
- **Rủi ro:** áp nguyên chính sách V1.2 → trừ thuế hai lần cho TikTok.
- `agents/plans/active/PLAN-085-cashback-tiktok-riohub.md`: **nháp**, 3 giai đoạn.
- **Chưa viết code:** vướng điều kiện mục 0 (tài khoản TikTok, RioHub cho phép cashback, khoá trong `.env`, hồ sơ thuế); phần client / đơn là backend.
- **Next:** chủ bot trả lời mục 0 của PLAN-085.

---

## Phiên 2026-10-25 (bm) — Nghiên cứu TikTok Shop qua RioHub API (chỉ đọc)

Chủ bot gửi bài RioHub, đồng ý nghiên cứu. Báo cáo `reports/CASHBACK_TIKTOK_RIOHUB_RESEARCH.md`.

- Mẹo "1 link gốc" trong bài: Shopee đã làm sẵn (bot tự ghép `an_redir` + `sub_id`). Với TikTok qua RioHub thì dùng được (`/general-links` + `event_id`).
- RioHub có tạo link, tra giá + hoa hồng, kéo đơn (status 1/2/3, `est_commission` / `actual_commission`). Webhook cần HTTPS công khai nên sẽ dùng `GET /orders`.
- **Vướng:** điều khoản RioHub cấm "tự mua qua link của mình" và cấm bot ngoài phạm vi; không nói tới cashback; tiền về Ví RioHub, chưa rõ tỷ lệ RioHub giữ; công thức `actual_commission` trong tài liệu mâu thuẫn.
- **Không làm:** không đăng ký, không gọi API RioHub, không viết code.
- **Next:**
  1. chủ bot xác nhận có tài khoản TikTok Affiliate (≥ 1.000 follow);
  2. chủ bot hỏi `hotro@riohub.vn` 4 câu trong mục 7 của báo cáo;
  3. sau đó mới viết PLAN (phần client / đơn là việc backend).

---

## Phiên 2026-10-25 (bl) — PLAN-084 ĐANG CHẠY, đã archive

- **Restart:** chủ bot restart Telegram lúc 01:44:06Z, PID 747966 (`main@6f91065`), log khởi động sạch, `shopee auto sync enabled=True interval_min=240`.
- **System State:**
  - Zalo PID 690595 không đổi, heartbeat bình thường;
  - hàng thông báo: 57 `sent`, 1 `suppressed`, không còn tin chờ; chưa có `net_down_since`;
  - `gate_b_check` OK (2 pending 12.157đ / 960đ, ví khoá, trigger 6/6).
- PLAN-084 chuyển vào `agents/plans/archive/`.
- **Next:**
  1. lần rớt mạng tới: kiểm tra chỉ 1 tin "📡 Bot đã kết nối lại" (≥ 60 giây) hoặc không có tin (< 60 giây);
  2. khoảng 2026-10-26: xin duyệt rồi thử tin chủ động Zalo.

---

## Phiên 2026-10-25 (bk) — PLAN-084 gộp tin lỗi mạng: lên main (chờ restart Telegram)

Chủ bot: "anh duyệt nhé sáng nay bot báo lỗi nữa em".

- **Lỗi sáng nay:** 01:11:45–01:12:26Z (08:11 VN), Telegram trả 502 rồi quá giờ khoảng 1 phút. Bot Zalo không lỗi, bot tự hồi → 1 tin "Lỗi bot" (id 59, `sent`). Hôm qua cũng lỗi khung giờ này.
- **Backup:** `cashback-20261025T013601Z.sqlite`.
- **Code:** `main@6f91065`, 703 passed, ruff sạch.
  - Lỗi mạng khi nhận tin Telegram không báo ngay. Mất ≥ 60 giây → 1 tin "📡 Bot đã kết nối lại"; > 5 phút → thêm 1 tin "đang mất kết nối".
  - "Lỗi bot" bỏ khối `Update -` / `User -` khi trống.
- **System State:** Telegram PID 692497 vẫn chạy bản cũ; Zalo PID 690595 không cần restart.
- **Next:**
  1. chủ bot restart Telegram, rồi kiểm tra log khởi động + `gate_b_check`;
  2. archive PLAN-084 sau khi chạy ổn;
  3. khoảng 2026-10-26: xin duyệt rồi thử tin chủ động Zalo.

---

## Phiên 2026-10-24 (bj) — Điều khoản V2 đã công bố; rớt mạng 17:22Z tự hồi; PLAN-084 chờ duyệt

- **V2:** chủ bot công bố lúc 17:28:14Z. DB: V1 `SUPERSEDED`, V2 `PUBLISHED` (hash `cfe2f6af…`).
  - Nội dung khớp `DRAFT_SECTIONS`; khác V1 đúng 2 câu "Telegram hoặc Zalo".
  - Dựng thử Zalo `dieukien` trên bản sao 0600 (đã shred): "Phiên bản V2 · hiệu lực từ 25/10/2026", mục 4 ghi "Mã tài khoản Telegram hoặc Zalo".
  - `CASHBACK_TERMS_REQUIRED` tắt nên khách chưa đồng ý V2 vẫn tạo link bình thường.
- **Sự cố mạng:** 17:22–17:27Z máy mất mạng. Cả hai bot `ConnectionError` rồi tự chạy lại, không restart. Admin nhận 3 tin "Lỗi bot `telegram_poll_failed`" (đều `sent`). Không có tin Zalo kẹt; heartbeat Zalo 17:28:22Z.
- **PLAN-084** `agents/plans/active/PLAN-084-cashback-net-outage-alert.md`: gộp lỗi mạng thành 1 tin khi kết nối lại; bỏ khối `Update -` / `User -`. Chờ chủ bot duyệt.
- **System State:**
  - Telegram PID 692497 (`main@e34fb0f`), Zalo PID 690595 (`21e1532`);
  - `gate_b_check` OK (2 pending 12.157đ / 960đ, ví khoá, trigger 6/6).
- **Next:**
  1. chủ bot duyệt PLAN-084 → làm trên nhánh, test, merge, chủ bot restart Telegram;
  2. khoảng 2026-10-26: xin duyệt rồi thử tin chủ động Zalo.

---

## Phiên 2026-10-24 (bi) — PLAN-083 phần B: mẫu điều khoản V2 (Telegram hoặc Zalo); rút gọn link không làm

Chủ bot: "anh quyết theo đề xuất của em nhé triển khai luôn".

- **Backup:** `cashback-20261024T160753Z.sqlite`.
- **Code:** `main@e34fb0f`, 698 passed.
  - `terms_content.py` lên V2: chỉ đổi 2 câu "tài khoản Telegram hoặc Zalo". Mẫu cũ trùng hash V1 đang công bố.
- **B2 rút gọn link:** không làm. AddLiveTag short link là Shopee Open API, cần App ID; qua cookie thì rủi ro phiên đồng bộ đơn.
- **System State:** vẫn chạy bản cũ (Telegram PID 686054, Zalo PID 687608).
- **Next:**
  1. chủ bot restart Telegram rồi Zalo (gồm PLAN-083 + mẫu V2);
  2. /admin → 📋 Điều khoản → tạo nháp V2 từ mẫu → công bố;
  3. nhắn thử Zalo `hd`, link, `don`;
  4. khoảng 2026-10-26 thử tin chủ động Zalo.

---

## Phiên 2026-10-24 (bh) — PLAN-083 hoàn thiện bot Zalo: lên main (chờ restart)

Chủ bot: "chỉnh cho chỉnh chu hoàn thiện, rà lại rồi làm 1 plan". Báo cáo `reports/CASHBACK_PLAN083_ZALO_POLISH.md`, PLAN `agents/plans/active/PLAN-083-cashback-zalo-polish.md`.

- **Backup:** `cashback-20261024T155318Z.sqlite`.
- **Code:** `main@21e1532`, 697 passed, ruff sạch.
  - Câu chữ Zalo (lệnh gõ tắt, Cách dùng riêng, link mua tin riêng, bỏ mũi tên);
  - admin thấy `Zalo #N` / `Tin Zalo #N`;
  - báo lỗi xử lý; báo bot Zalo dừng > 10 phút (bot Telegram canh); cảnh báo khách thứ 40 / 50;
  - nguồn đồng ý điều khoản `zalo_choice`; toast lên đầu tin.
- **Diễn tập** 20 bước trên bản sao (đã xoá): đạt.
- **System State:** chạy bản cũ (Telegram PID 686054, Zalo PID 687608 bản `f184972`).
- **Next:**
  - chủ bot restart Telegram rồi Zalo; nhắn thử `hd`, link, `don`;
  - phần B chờ quyết: điều khoản V2 ghi "Telegram hoặc Zalo", rút gọn link, thử tin chủ động ~26/10, ảnh / mô tả bot, gói Pro.

---

## Phiên 2026-10-24 (bg) — PLAN-082 kênh Zalo ĐANG CHẠY

Báo cáo `reports/CASHBACK_PLAN082_ZALO.md` (mục "Đã triển khai").

- **System State:**
  - bot Telegram PID 686054 (`main@6fa5a38`);
  - bot Zalo PID 686122 (`python -m cashback_bot.zalo_bot`, log `logs/cashback_zalo.log`);
  - 1 khách Zalo (chủ bot), 1 link Zalo 17.011đ;
  - `gate_b_check` OK; ví khoá.
- **Done:**
  - chủ bot nhắn thử đủ luồng (menu, gõ số, thẻ xem trước, link, đơn);
  - admin nhận "Zalo #1";
  - `text_styles` hiển thị đúng trên Zalo thật.
- **Sửa sau triển khai:** `main@f184972` (link Zalo ghi đã giao), 689 passed. Chờ chủ bot khởi động lại riêng tiến trình Zalo.
- **Unfinished:**
  - thử bot tự nhắn trước sau 1–2 ngày (thông báo đơn);
  - gói BASIC 50 người;
  - trang hướng dẫn chung còn chữ "nút".
- **Next:** chủ bot restart Zalo (`kill -TERM 686122` + lệnh khởi động); ~2026-10-26 xin thử tin chủ động.

---

## Phiên 2026-10-24 (bf) — PLAN-082 kênh Zalo: code + test + diễn tập, đã lên main (chờ chủ bot khởi động)

Chủ bot: "triển khai em viết em làm toàn như các báo cáo vừa làm hôm nay". Báo cáo `reports/CASHBACK_PLAN082_ZALO.md`, PLAN `agents/plans/active/PLAN-082-cashback-zalo-channel.md`.

- **Backup:** `cashback-20261024T152104Z.sqlite` (45 bảng, 38 link).
- **Code:** `main@6fa5a38`, 689 passed, ruff sạch.
  - Tiến trình riêng `cashback_bot.zalo_bot`, ID nội bộ âm (`channel_identities`), hộp thư `zalo_inbox`.
  - Nút Telegram → gõ số; URL trần; style UTF-16.
  - `Dispatcher(channel=)`: bot Telegram không lấy tin của khách Zalo.
- **Diễn tập** trên bản sao DB (đã xoá): 6 tin Zalo `replied`; +1 link (ID −1); ví / đơn / lệnh chi +0; hàng tin Telegram không đổi; `gate_b_check` OK.
- **System State:** production vẫn chạy PID 675442 bản cũ; chưa có tiến trình Zalo.
- **Next:**
  1. chủ bot restart bot Telegram **trước**;
  2. khởi động `cashback_bot.zalo_bot` (log `logs/cashback_zalo.log`);
  3. chủ bot nhắn `menu`, link (bấm ✕), `don`;
  4. kiểm tra log + `gate_b_check`;
  5. sau 1–2 ngày thử bot tự nhắn trước.

---

## Phiên 2026-10-24 (be) — Nghiên cứu bot Zalo + thử thật với token (chỉ thử, chưa code)

Chủ bot muốn chạy bot song song trên Zalo. Báo cáo `reports/CASHBACK_ZALO_BOT_RESEARCH.md`.

- **System State:** production không đổi (`main`, PID 675442). Chủ bot đã thêm `ZALO_BOT_TOKEN` vào `.env` (bot "Bot Săn Hoàn Tiền", gói BASIC: 50 người / bot, 3.000 tin / tháng). Chưa có tiến trình Zalo nào chạy.
- **Done:**
  - so sánh Zalo Bot Platform / OA / zca-js → chọn Bot Platform;
  - thử thật: `getMe` OK; Zalo không giữ tin khi không ai nhận; link dán thẳng thành thẻ xem trước → bot nhận `unsupported` không có link; bấm ✕ hoặc bỏ `https://` thì nhận được;
  - gửi 1 tin thử cho chủ bot: `<b>`, `<u>`, URL trần OK; `<a href>` mất link; không có nút.
- **Đề xuất thiết kế** (trao đổi trong phiên, chưa ghi vào báo cáo): ID nội bộ âm cho khách Zalo qua bảng `channel_identities`; tiến trình riêng `cashback_bot.zalo_bot`; `zalo_render.py` chuyển `BotReply`; lệnh gõ `don` / `vi` / `hd`; hàng đợi thông báo bỏ qua ID âm; bật WAL. Ví / rút tiền Zalo làm cùng đợt mở ví.
- **Unfinished:** chưa thử bot tự nhắn trước sau 1–2 ngày; chủ bot chưa chốt tỷ lệ hoàn bên Zalo; chưa có PLAN.
- **Next:** chủ bot duyệt hướng → Anti viết PLAN (Codex làm backend, Claude Code làm render + câu chữ Zalo).

---

## Phiên 2026-10-24 (bd) — PLAN-081 B + A và sửa link ShopeeFood đã triển khai

Chủ bot restart ("reset r em"). Báo cáo `reports/CASHBACK_DEPLOY_2026-10-24_PLAN081.md`.

- **System State:**
  - production `main@8de3bd3`, PID 675442;
  - tự đồng bộ 240 phút, lượt kế 14:39:33Z;
  - Phương án A tắt (`reconcile_lookup=False`);
  - 2 khoản pending 12.157đ / 960đ; ví khoá; `gate_b_check` OK.
- **Done:**
  - log khởi động sạch;
  - bảng theo dõi + 2 trigger sự kiện đã có;
  - đánh giá đầu đưa 2 đơn qua bot (…0309, …0025) vào `OBSERVED_RECENTLY`, 2 sự kiện, 0 tin admin, 0 tin khách.
- **Unfinished:**
  - chủ bot thử lại link `spf.shopee.vn`;
  - sau lượt 14:39Z, kiểm tra màn 🧾 hết "(suy ra)".
- **ShopeeFood (chủ bot hỏi):** AddLiveTag `product-data` với `url=spf.shopee.vn/...` trả `status=error` "item_id or valid Shopee URL is required" (1 lần gọi, chủ bot yêu cầu). Shopee Affiliate có hoa hồng ShopeeFood (app ghi tới 9%; Sapo: trần ~10.000đ/đơn, 1 đơn/khách/7 ngày). Chưa hỗ trợ; muốn làm cần thử nguồn link + báo cáo đơn và chính sách % hoa hồng thực nhận, chủ bot quyết.
- **Next:**
  - 2026-11-12: kiểm tra 2 đơn chuyển 🟡 và tin tổng hợp admin;
  - trước 2026-11-22: chủ bot quyết định bật `SHOPEE_RECONCILE_LOOKUP_ENABLED=1`.

---

## Phiên 2026-10-24 (bc) — PLAN-081: Phương án B lên main; thử nguồn thành công; Phương án A lên main (cờ tắt)

Chủ bot: "triển khai pa B đi em, có em cho phép thực thi phương án A luôn".

- **Backup:** `cashback-20261024T112613Z.sqlite` (verify ok: 43 bảng, 37 link). Phương án B merge `ea1359c`, 666 passed.
- **Thử nguồn:** 1 yêu cầu `report/list`, giờ mua ± 60 giây của đơn …7156 (30,91 ngày) → `code=0`, 1 dòng khớp. Không ghi DB, không in cookie.
- **Phương án A:**
  - tra khung hẹp trong lượt `SyncCoordinator`, tối đa 10 đơn / lượt, 1 lần / đơn / ngày, tuổi 30–180 ngày;
  - cờ `SHOPEE_RECONCILE_LOOKUP_ENABLED` mặc định tắt;
  - 676 passed.
- **System State:** chờ chủ bot restart (đang chạy PID 656347 bản cũ).
- **Next:**
  - chủ bot (tuỳ chọn) thêm `SHOPEE_RECONCILE_LOOKUP_ENABLED=1`, rồi restart;
  - kiểm tra log (`reconcile_lookup=...`), màn 🧾 (2 đơn "Đang theo dõi"), `gate_b_check`;
  - sau lượt tự đồng bộ kế tiếp, "lần cuối thấy" hết nhãn "(suy ra)".

---

## Phiên 2026-10-24 (bb) — PLAN-081 Gate B Phương án B: theo dõi đơn quá 30 ngày (CODE READY, chưa triển khai)

Claude Code, chủ bot duyệt Gate A ("anh duyệt"). Báo cáo `reports/CASHBACK_PLAN081_GATE_B.md`; ADR-058 Accepted cho Phương án B.

- **System State:** production không đổi (`main@4a52f82`, PID 656347, tự đồng bộ 240 phút).
- **Done** (nhánh `cursor/cashback-plan081-reconciliation`, 666 passed):
  - `last_seen_*`; bảng theo dõi + sự kiện chỉ thêm;
  - nhãn 20 / 30 / 45 ngày và vắng 2 lượt;
  - đánh giá sau mỗi lượt và mỗi giờ; tin admin chống trùng; màn 🧾 Đơn cần đối soát;
  - diễn tập trên bản sao đạt.
- **Unfinished:** chờ duyệt triển khai; Phương án A (thử nguồn > 30 ngày) chờ xác nhận riêng.
- **Next:**
  1. Chủ bot duyệt → backup, merge, test, push → restart → kiểm tra màn 🧾 và `gate_b_check`.
  2. Hạn: trước 2026-11-12.

---

## Phiên 2026-10-24 (ba) — PLAN-081 Gate A: audit đơn Shopee quá 30 ngày (chỉ đọc)

Claude Code. Báo cáo `reports/CASHBACK_PLAN081_GATE_A_AUDIT.md`, ADR-058 (DRAFT), PLAN `agents/plans/active/PLAN-081-cashback-reconciliation-beyond-30-days.md`.

- **System State:**
  - production không đổi: `main@4f4a701`, PID 656347;
  - tự đồng bộ 240 phút, lượt kế 14:39Z;
  - 2 khoản pending 12.157đ / 960đ; ví khoá.
- **Done (chỉ đọc):**
  - khung quét là 30 ngày theo `purchase_time`, cố định trong code;
  - đơn …7156 (không qua bot, FRAUD) đã vắng từ lượt #4, chứng minh đơn ra khung không được đọc lại;
  - không có `last_seen_at` riêng (`updated_at` / `evidence_ref` gần nghĩa);
  - 2 đơn qua bot ra khung ngày 2026-11-22;
  - website endpoint > 30 ngày UNVERIFIED; Open API không có quyền.
- **Đề xuất:** Phương án B (theo dõi + cảnh báo + chứng từ PLAN-075) trước 2026-11-12; A (khung hẹp theo giờ mua) chỉ sau một lần thử nguồn được duyệt.
- **Unfinished / Blockers:** chờ chủ bot duyệt mục 21 của báo cáo. Gate B NOT AUTHORIZED.
- **Next:** chủ bot chọn phương án và ngưỡng → viết Gate B (code + test matrix 31 case) → diễn tập → triển khai trước 2026-11-12.

---

## Phiên 2026-10-24 (az) — PLAN-080 Gate B: tự đồng bộ Shopee ĐÃ BẬT (mỗi 240 phút)

Chủ bot thêm `SHOPEE_AUTO_SYNC_ENABLED=1`, `SHOPEE_AUTO_SYNC_INTERVAL_MINUTES=240` và restart. Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN080.md` (mục Gate B).

- **System State:**
  - `main@879b24c` (code `5232840`), PID 654209, khởi động 10:34:28 UTC;
  - tự đồng bộ bật, chu kỳ 240 phút, lượt kế 14:39:33Z; thông báo đơn bật;
  - ví khoá, 2 khoản pending 12.157đ / 960đ.
- **Done:** lượt tự động #11 (10:39:32Z): success, 2 trang, 0 mới / 0 đổi, 0 tin khách, 0 sự cố; `gate_b_check` OK; log sạch.
- **Ghi nhận:**
  - lần sửa `.env` đầu gõ sai tên biến (bot bỏ qua);
  - một lần khởi động khi bot cũ chưa dừng bị khoá tiến trình chặn đúng thiết kế.
- **Next:**
  - theo dõi 24–48 giờ (màn ⏱, `gate_b_check`, log `database is locked`) rồi chốt chu kỳ;
  - quyết định khung quét > 30 ngày;
  - Gate B ví (PLAN-078) vẫn chờ.

---

## Phiên 2026-10-24 (ay) — Đã triển khai PLAN-080 Gate A (tự đồng bộ Shopee: code lên, cờ TẮT)

Claude Code, chủ bot duyệt ("oke anh duyệt nhé"). Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN080.md`.

- **System State:**
  - `main@5232840`, PID 652982, khởi động 10:26:34 UTC, 2 luồng (poll + đồng bộ);
  - `.env` không có `SHOPEE_AUTO_SYNC_*`, nên tự đồng bộ tắt; thông báo đơn vẫn bật;
  - 2 khoản pending 12.157đ / 960đ; ví khoá; trigger 6/6.
- **Done:**
  - backup `cashback-20261024T102126Z.sqlite`; merge 648 passed; push;
  - log 0 lỗi, 0 locked, 0 token;
  - lượt 🔄 #10: thành công, 2 trang, 0 mới / 0 đổi / 2 không đổi, 0 tin khách, khoá đã nhả;
  - màn ⏱ đúng (ảnh chủ bot).
- **Unfinished:** Gate B chờ duyệt riêng; quyết định khung quét > 30 ngày.
- **Next:** Gate B = bấm 🔄 kiểm tra nguồn → thêm `SHOPEE_AUTO_SYNC_ENABLED=1` → restart → theo dõi 24–48 giờ (mục 19 báo cáo PLAN-080).

---

## Phiên 2026-10-24 (ax) — PLAN-080 Automatic Shopee Sync (CODE READY, CHƯA triển khai)

Claude Code, chủ bot giao PLAN-080. Báo cáo `reports/CASHBACK_PLAN080_AUTO_SYNC.md`, ADR-057, PLAN `agents/plans/active/PLAN-080-cashback-auto-shopee-sync.md`.

- **System State:** production không đổi.
  - `main@4712c9a` + `e3f31e7` (giao diện `/donhang`), PID 646983;
  - thông báo đơn bật; tự đồng bộ tắt (không có `SHOPEE_AUTO_SYNC_*`, không có `bot_state.shopee_auto_sync`);
  - 2 khoản pending 12.157đ / 960đ; ví khoá.
- **Done** (nhánh `cursor/cashback-plan080-auto-sync`, 648 passed, ruff sạch):
  - đồng bộ chạy ở luồng nền, khoá một lượt trong DB (lease, heartbeat, thu hồi);
  - lịch bền UTC, giãn cách khi lỗi, chạy bù một lượt;
  - 9 loại lỗi; NEEDS_AUTH; trang bất thường → PARTIAL;
  - sự cố báo admin một lần, nhắc lại sau 24 giờ, báo khi phục hồi;
  - màn ⏱ Tự động đồng bộ; nút Telegram chỉ còn tạm dừng / tiếp tục khi cờ bật.
- **Diễn tập:** trên bản sao DB production đạt (mục 16 báo cáo). Code cũ chạy được trên schema mới.
- **Unfinished / Blockers:**
  - chờ chủ bot duyệt Gate A (deploy, cờ tắt);
  - Gate B cần duyệt riêng;
  - quyết định khung quét > 30 ngày cho đơn còn chờ xác minh.
- **Next:**
  1. Chủ bot duyệt Gate A → backup, merge, test, push → chủ bot restart → kiểm tra theo mục 19 báo cáo.
  2. Gate B: bấm 🔄 kiểm tra nguồn → thêm `SHOPEE_AUTO_SYNC_ENABLED=1` → restart → theo dõi 24–48 giờ.

---

## Phiên 2026-10-24 (aw) — Gửi tin giới thiệu thông báo đơn cho 2 khách có đơn

Chủ bot duyệt nội dung ("gửi").

- Hai tin `orders_intro:<user>` (loại `order_update`, `source_ref='orders_intro'`) xếp vào hàng đợi chung; mỗi tin có khoá chống trùng, có audit `customer_notify_intro`.
- Bot đã gửi: khách …966 lúc 09:42:09Z, khách …420 lúc 09:42:10Z, cả hai `sent`, có mã tin Telegram.
- Sau khi gửi: `gate_b_check` OK, 12.157đ / 960đ giữ nguyên, ví khoá, log 0 lỗi.

---

## Phiên 2026-10-24 (av) — Màn «Đơn hàng của tôi» dễ đọc hơn (đã triển khai)

Claude Code, chủ bot duyệt mẫu ("oke anh duyệt").

- **System State:**
  - `main@e3f31e7`, PID 646983, khởi động 09:37:48 UTC;
  - thông báo đơn vẫn `on`, mốc 09:21:19Z không đổi;
  - log 0 lỗi, 0 token; `gate_b_check` OK: 12.157đ / 960đ, ví khoá, trigger 6/6.
- **Done:**
  - `/donhang` hiện tên sản phẩm của link, ngày mua, nhãn ngắn; chỉ hiện số khác 0; đánh số qua các trang;
  - chi tiết đơn có tiến trình từng bước, chỉ đánh ✅ khi Shopee đã có dữ liệu;
  - bỏ chữ «V1.1»; trang trống có nút 📖 Cách lấy link;
  - backup `cashback-20261024T093324Z.sqlite`; 607 passed; dựng thử trên bản sao (đã xoá) đúng với 2 khách và trang trống.
- **Next:** như mục (au): theo dõi 🔔 sau mỗi lần 🔄; PLAN tự đồng bộ Shopee nếu cần.

---

## Phiên 2026-10-24 (au) — Đã triển khai PLAN-079 Gate A.1 + Gate B (thông báo đơn BẬT cho mọi khách)

Claude Code + chủ bot ("oke thực hiện 3 mục cho anh đi em"). Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN079_GATE_B.md`.

- **System State:**
  - `main@792397d`, PID 644839, khởi động 09:21:18 UTC;
  - `.env`: `CUSTOMER_NOTIFICATIONS_ENABLED=1`, không có `CUSTOMER_NOTIFICATIONS_TEST_IDS`;
  - chế độ `on`, mốc kích hoạt 09:21:19Z; lịch sử `off` (08:52) → `test` (08:55) → `on` (09:21);
  - ví khoá: 2 khoản pending 12.157đ / 960đ, 0 available, 0 payout, 6 trigger; `gate_b_check` OK.
- **Done:**
  - backup `cashback-20261024T084807Z.sqlite`; merge 606 passed, đã push;
  - chế độ test với tài khoản admin: tin thử gửi đúng; xử lý lại không thành tin thứ hai; tắt "Đơn mới" thì bỏ qua; bật lại thì gửi; 0 tin đơn tới khách thật;
  - log 0 lỗi, 0 token qua 3 lần restart.
- **Không thử thật** (đã có test tự động): khách chặn bot (chưa có tài khoản phụ); 🔄 trong chế độ test.
- **Unfinished:** không.
- **Next:**
  - sau mỗi lần 🔄 chạy `.venv/bin/python -m cashback_bot.gate_b_check` và xem /admin → 🔔; 2 khách thật có thể nhận tin "cập nhật" lần đầu;
  - tắt nhanh: xoá dòng `CUSTOMER_NOTIFICATIONS_ENABLED=1`, rồi restart;
  - PLAN riêng nếu muốn tự đồng bộ Shopee (tin gần thời gian thực);
  - Gate B ví (PLAN-078) vẫn chờ chứng từ và quyết định.

---

## Phiên 2026-10-24 (at) — PLAN-079 Gate B pre-activation review (CONDITIONAL GO, chưa triển khai)

Claude Code, chủ bot giao audit Gate B. Báo cáo `reports/CASHBACK_PLAN079_GATE_B_REVIEW.md`; ADR-056 có mục sửa đổi.

- **System State:** production không đổi. `main@e36281c` (code `0deb060`), PID 636239, thông báo đơn tắt. Không merge, không restart, không đổi `.env`, không gửi Telegram thật. DB production chỉ đọc (`gate_b_check`: OK; 2 khoản pending 12.157đ / 960đ; ví 0, available 0, payout 0; trigger 6/6).
- **Done (nhánh `cursor/cashback-plan079-gate-b`, worktree `/home/vu/toolsauto-cashback-notifications`, 606 passed, ruff sạch):**
  - mốc kích hoạt theo chế độ `off` / `test` / `on` (bật → tắt → bật không gửi dồn), lịch sử chỉ thêm;
  - tin khách không kẹt sau tin admin; 429 dừng vòng gửi; lý do `no_purchase_time`;
  - tin đơn huỷ ngay lần đầu không hiện số hoàn;
  - chế độ `CUSTOMER_NOTIFICATIONS_TEST_IDS`, 🧪 tin thử ở màn 🔔, `python -m cashback_bot.gate_b_check` (chỉ đọc).
- **Rollback:** nhánh `rollback/plan079-compat` (worktree `/home/vu/toolsauto-cashback-rollback`, `f3ab6ec`, 558 passed): code `c4b9b1a` + bộ lọc, không cần `UPDATE … SET status='sent'`. Diễn tập trên bản sao: `c4b9b1a` nguyên bản gửi lại 6 dòng lạ, bản tương thích gửi 0 dòng lạ.
- **Unfinished / Blockers:** chờ chủ bot duyệt ngưỡng OR 500đ / 10% và 3 điểm nghiệp vụ ở mục 3 của báo cáo.
- **Next:**
  1. Chủ bot duyệt triển khai nhánh sửa (cờ vẫn tắt).
  2. Chạy kịch bản thử 8 bước với 2 tài khoản test (mục 5).
  3. Bật cho mọi khách theo mục 10.

---

## Phiên 2026-10-24 (as) — Đã triển khai PLAN-079 Gate A (đơn hàng của tôi, thông báo đơn TẮT)

Claude Code, chủ bot duyệt. Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN079.md`.

- Backup trước triển khai: `data/backups/cashback-20261024T080656Z.sqlite` (verify ok).
- `main` fast-forward `1b0d145` → `0deb060`, 588 passed, đã push. Chủ bot restart 08:10:45 UTC, PID 636239.
- Sau triển khai: log 0 lỗi, 0 token; cột hàng đợi mới, bảng tuỳ chọn, cột chặn bot có; hàng đợi 42 dòng cũ (admin, sent), 0 tin mới; cờ `CUSTOMER_NOTIFICATIONS_ENABLED` tắt, mốc kích hoạt chưa đặt; 2 khoản pending giữ 12.157đ / 960đ; ví khoá, 6 trigger. Trên bản sao: menu có `/donhang`, `/thongbao`; `/donhang` của 2 khách đúng số. PLAN-079 đã chuyển sang `agents/plans/archive/`.

Next:
- Gate B: chủ bot duyệt câu chữ và ngưỡng, thử tài khoản test, bật `CUSTOMER_NOTIFICATIONS_ENABLED=1`.
- PLAN riêng cho tự đồng bộ Shopee nếu muốn tin gần thời gian thực. Gate B của ví (PLAN-078) vẫn chờ chứng từ và quyết định.

---

## Phiên 2026-10-24 (ar) — PLAN-079 Customer Order Tracking & Notifications (CODE READY, CHƯA triển khai)

Claude Code, chủ bot giao PLAN-079. Worktree `/home/vu/toolsauto-cashback-notifications`, nhánh `cursor/cashback-plan079-notifications`. Báo cáo `reports/CASHBACK_PLAN079_CUSTOMER_NOTIFICATIONS.md`, ADR-056.

- Audit: tin khách (ví, chi trả, hỗ trợ) đi chung `admin_notifications` với tin admin; chỉ xả khi thông báo admin bật; không giãn cách khi thử lại, không đọc retry_after, không biết khách chặn bot, không lưu message_id. Chưa có thông báo đơn và chưa có trang xem đơn.
- Đã làm: `/donhang` (tổng quan, phân trang, chi tiết, chỉ đơn của chính khách); `/thongbao` (4 loại, riêng từng khách); sự kiện đơn sinh trong transaction ghi đơn (`conversion_hooks` + SAVEPOINT); khoá chống trùng theo sự kiện, gom một tin mỗi đơn mỗi lần đồng bộ, ngưỡng 500đ/10%, tiền theo snapshot; một bộ gửi chung `notify_dispatch` (429 theo retry_after, 5xx giãn cách, 4xx → failed + đánh dấu chặn bot, không rõ kết quả → unknown không tự gửi lại, dừng giữa lúc gửi → unknown); cờ `CUSTOMER_NOTIFICATIONS_ENABLED` mặc định tắt (sự kiện khi tắt → suppressed, không gửi dồn); mốc kích hoạt chống báo đơn lịch sử; màn admin 🔔 Thông báo khách; số tin khách trong tin kết quả đồng bộ.
- Proof: **588 passed** (+33). Diễn tập trên bản sao DB production: ghi lại y hệt 2 đơn → 0 tin; `/donhang` đúng số; ví khoá; integrity ok.
- KHÔNG merge, KHÔNG restart. Gate B (bật thông báo đơn) NOT AUTHORIZED.

Next:
- Chủ bot duyệt Gate A. Gate B: thử với tài khoản test, duyệt ngưỡng và câu chữ, rồi bật cờ.
- Đề xuất PLAN riêng cho tự đồng bộ Shopee nếu muốn tin gần thời gian thực.

---

## Phiên 2026-10-24 (aq) — Sửa chữ hai điều kiện hạn mức (màn Sẵn sàng chi trả)

- Chủ bot duyệt. `main` `c4b9b1a`, backup trước `data/backups/cashback-20261024T073103Z.sqlite`. Chủ bot restart 07:36:31 UTC, PID 631959.
- «Hạn mức rút» → «Quyết định chính sách hạn mức rút»; «Hạn mức rút đang hiệu lực (có người duyệt)» → «Bảng số hạn mức đã duyệt, đang dùng». Chỉ đổi chữ; thêm test chống trùng chữ. 555 passed.
- Sau restart: log 0 lỗi, 0 token; 2 khoản pending giữ 12.157đ / 960đ; ví 0, 0 available, 0 payout; 6 trigger khoá; bất biến ổn; quick_check ok.

Next: như mục (ap), Gate B chưa được phép.

---

## Phiên 2026-10-24 (ap) — Đã triển khai PLAN-078 Gate A (code, ví vẫn khoá)

Claude Code, chủ bot duyệt "có phát hành". Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN078.md`.

- Backup trước triển khai: `data/backups/cashback-20261024T071547Z.sqlite` (verify ok).
- `main` fast-forward `88ebf63` → `e50afeb`, 554 passed, đã push. Chủ bot restart 07:18:41 UTC, PID 629793.
- Sau triển khai: log 0 lỗi, 0 token, 0 số tài khoản; 6 bảng mới (chỉ `bank_account_history` có 1 dòng, 4 số cuối); thêm cột và index của `cashback_payouts`; trigger khoá cũ còn đủ, thêm `financial_lock_payout_progress` và `payout_paid_needs_evidence`; 2 khoản pending giữ 12.157đ / 960đ; ví 0, 0 available, 0 payout; bất biến ổn; không gửi tin. Trên bản sao: bật ví bị chặn, tạo yêu cầu rút trả `locked`, `/vi` hiện câu ví đóng mới. PLAN-078 đã chuyển sang `agents/plans/archive/`.

Next (Gate B, chưa được phép):
- Kỳ Shopee MATCHED thật và bằng chứng APPROVED; quyết định thuế (kế toán), thu hồi, điều khoản chi trả, hạn mức, xác minh tài khoản, quy trình chuyển khoản; bước phát hành riêng để ghi quyết định và mở khoá cũ; đợt thử nhỏ.

---

## Phiên 2026-10-24 (ao) — PLAN-078 Wallet & Payout Readiness (CODE READY, CHƯA triển khai)

Claude Code, chủ bot giao PLAN-078. Worktree `/home/vu/toolsauto-cashback-payout`, nhánh `cursor/cashback-plan078-payout`. Báo cáo `reports/CASHBACK_PLAN078_WALLET_PAYOUT.md`, ADR-055.

- Audit: ví PLAN-066 tính số dư gộp, yêu cầu rút đi thẳng requested → paid không cần chứng từ, tài khoản bị ghi đè không có lịch sử. Lỗ tìm thấy: `payout_headroom` của quỹ cũ chỉ trừ yêu cầu ở trạng thái 'requested' và 'paid'.
- Đã làm (mở rộng, không dựng ví mới): máy trạng thái 11 bước (`payout_events` chỉ thêm, phiên bản, khoá chống gửi lặp); `payout_allocations` truy từng đồng về đơn; unique index một yêu cầu mở mỗi khách; trigger `financial_lock_payout_progress` và `payout_paid_needs_evidence`; khoản vào ví cần SETTLED và không điều chỉnh OPEN; quỹ có chứng từ từ kỳ MATCHED (trừ toàn bộ phí và thuế kỳ); `payout_readiness` (6 quyết định, hạn mức ACTIVE, kỳ MATCHED, backup ≤ 48 giờ, điều khoản chi trả, tài khoản đã xác minh); lịch sử và xác minh tài khoản (4 số cuối + sha); hạn mức mặc định không có; màn chi trả theo bước, ẩn bước chi tiền khi khoá; ví đóng hiện câu mới.
- Proof: **554 passed** (+33 mới, 17 test cũ viết lại theo máy trạng thái; có test hai thread rút cùng lúc). Diễn tập trên bản sao DB production đạt: thêm 6 bảng, 3 cột, 2 index, ghi 1 dòng lịch sử tài khoản; 2 khoản pending giữ số; khoá còn; integrity ok.
- KHÔNG merge, KHÔNG restart. Gate B (mở ví, chi tiền) NOT AUTHORIZED.

Next:
- Chủ bot duyệt Gate A (phát hành code ở trạng thái khoá).
- Gate B cần: kỳ Shopee MATCHED thật và bằng chứng APPROVED; quyết định thuế, thu hồi, điều khoản chi trả, hạn mức, cách xác minh tài khoản, quy trình chuyển khoản; một bước phát hành riêng để ghi quyết định.

---

## Phiên 2026-10-24 (an) — Chủ bot công bố điều khoản V1

- Chủ bot tạo bản nháp V1 lúc 06:09:28 UTC và công bố lúc 06:16:03 UTC (audit `terms_draft`, `terms_publish`; hash `63c0d16dab0c`). `customer_terms_versions` #1 PUBLISHED; 0 chấp thuận; cờ `CASHBACK_TERMS_REQUIRED` vẫn tắt; không gửi tin cho khách. Log 0 lỗi, 0 update lỗi.
- Chủ bot thấy `/dieukien` lúc 13:06 VN ra trang chủ: không phải lỗi. Bot sửa đè tin cũ khi bấm nút (giữ giờ gửi ban đầu, Telegram không hiện «đã sửa» với tin bot có nút). Đã dựng lại trên bản sao: `/dieukien` trả đúng trang (trước công bố: trang cũ; sau: V1).

Next: như mục (am).

---

## Phiên 2026-10-24 (am) — Đã triển khai PLAN-077 Terms, Support & Payout Readiness

Claude Code, chủ bot duyệt phát hành. Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN077.md`.

- Backup trước triển khai: `data/backups/cashback-20261024T060320Z.sqlite` (verify ok).
- `main` fast-forward `cca8f8c` → `5a14fc1`, 521 passed, đã push. Chủ bot restart 06:05:53 UTC, PID 620902.
- Sau triển khai: log 0 lỗi, 0 token; 5 bảng mới trống, trigger đóng băng / chỉ-thêm đủ; 33 link chứng minh được chính sách; 2 khoản pending giữ 12.157đ / 960đ; ví 0, 0 available, 0 payout; không gửi tin cho khách. Khách thấy 📩 Hỗ trợ và `/hotro`; `/dieukien` vẫn là trang cũ (V1 chưa công bố); `terms_required` tắt. PLAN-077 đã chuyển sang `agents/plans/archive/`.

Next:
- Chủ bot: duyệt và tự công bố điều khoản V1; quyết định cờ bắt buộc, SLA, thời gian lưu và xoay vòng log; hỏi kế toán 14 câu thuế; chính sách thu hồi; chứng từ Shopee thật.

---

## Phiên 2026-10-24 (al) — PLAN-077 Terms, Support & Payout Readiness (code + test xong, CHƯA triển khai)

Claude Code, chủ bot giao PLAN-077. Worktree `/home/vu/toolsauto-cashback-terms`, nhánh `cursor/cashback-plan077-terms`. Báo cáo `reports/CASHBACK_PLAN077_TERMS_POLICY.md`, ADR-054.

- Audit quyền lợi: đơn gắn theo Sub ID cho người tạo link (chia link không chuyển quyền), giữ lần gắn đầu; APPROVED, thanh toán và rút tiền chưa hoạt động. Phát hiện: tin không phải link bị lưu nguyên văn (≤500 ký tự); màn admin xem khách hiện đủ số tài khoản; cổng ví chưa chặn link `unresolved`.
- Đã làm: điều khoản theo phiên bản (`customer_terms_versions`, trigger đóng băng; `customer_terms_acceptances` chỉ thêm; `link_terms_context`); dự thảo V1 (DRAFT); `/dieukien` hiện bản công bố, chưa công bố thì giữ trang cũ; cờ `CASHBACK_TERMS_REQUIRED` mặc định tắt; `/hotro` và ticket (7 trạng thái, lịch sử chỉ thêm, chặn trùng, che token/số thẻ); màn admin 📩 Hỗ trợ, 📋 Điều khoản, ⚖️ Sẵn sàng chi trả (chỉ đọc); `payout_gate.proven_policy` chặn link `unresolved`; tin không phải link chỉ lưu độ dài; che số tài khoản ở màn admin xem khách; DDL nháp sổ quyết định thuế (không chạy).
- Tra cứu pháp luật (subagent): Luật TNCN 109/2025, NĐ 252/253/141/2026, CV 7403/CT-TMĐT, Luật BVDLCN 91/2025 + NĐ 356/2025; phần lớn mới xác nhận qua nguồn thứ cấp, nên ghi PENDING_REVIEW kèm 14 câu hỏi cho kế toán. Theo nguồn thứ cấp, Shopee khấu trừ 5% GTGT + 5% TNCN affiliate từ 01/10/2026.
- Proof: **521 passed**. Diễn tập trên bản sao DB production đạt. KHÔNG merge, KHÔNG restart.

Next:
- Chủ bot release review; đọc và duyệt nội dung điều khoản V1 rồi tự công bố trong /admin.
- Quyết định: bật bắt buộc đồng ý, SLA, thời gian lưu dữ liệu và xoay vòng log, thuế (hỏi kế toán), chính sách thu hồi, xem lại dự phòng 10%.

---

## Phiên 2026-10-24 (ak) — Tin báo admin khi gửi link có bảng chia tiền

Claude Code, chủ bot yêu cầu. `main` `13eb3f5`, backup trước `data/backups/cashback-20261024T051459Z.sqlite`. Chủ bot restart 05:17:26 UTC, PID 615042.

- Tin "🔗 Đã gửi link" thêm bảng: HH ước tính (shop / Shopee Xtra), dự phòng phí, dự phòng thuế, quỹ chia (V1.2), khách nhận, Admin còn. Tính bằng `cashback_for` trên snapshot của link; không khớp số đã báo thì không hiện bảng. 493 passed. Báo cáo: mục 22 của `reports/CASHBACK_PLAN076_PRICING.md`.
- Kiểm tra sau restart: log 0 lỗi, 0 token. Link mới #34 (`6zD5kifo`) có snapshot `captured`, báo 15.842đ (HH 25.425 × V1.2); tin admin đã gửi kèm bảng đúng số. Snapshot 31 backfilled + 2 captured, 0 lệch, 0 thiếu. 2 khoản pending giữ 12.157đ / 960đ; ví 0, 0 available, 0 payout; 4 trigger khoá + trigger chỉ-thêm của bảng chính sách đã có.

Next: như mục (aj): chứng từ Shopee thật, thuế người nhận, chính sách thu hồi.

---

## Phiên 2026-10-24 (aj) — Đã triển khai PLAN-076 Pricing & Policy Consistency

Claude Code, chủ bot duyệt phát hành kèm mục 2 («Admin còn») và mục 3 (nhập số tự do ở Mô phỏng, huỷ lịch hẹn). Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN076.md`.

- Bổ sung trước khi phát hành (`810acc5`): «Admin còn» = HH − khách − dự phòng phí − dự phòng thuế trên mọi màn; ✏️ Nhập số khác ở Mô phỏng (RAM, 10 phút, không ghi DB); huỷ chính sách đã hẹn giờ chỉ trước mốc (`policy_cancellations` chỉ thêm, CHECK `cancelled_at < effective_at`, audit). 490 passed.
- Backup trước triển khai: `data/backups/cashback-20261024T045217Z.sqlite` (verify ok, 32 link).
- `main` fast-forward `a9ff267` → `810acc5`, 490 passed, đã push. Chủ bot restart 04:56:23 UTC, PID 612405.
- Sau triển khai: `backfilled=31 unresolved=0`, 0 lệch quote ↔ snapshot; 2 khoản pending giữ 12.157đ / 960đ; conversion không đổi; khoá tài chính còn nguyên (ví 0, 0 available, 0 payout); log 0 lỗi, 0 token. Trigger chỉ-thêm của `share_policies`/`reserve_policies` tạo ở lần mở kết nối admin đầu tiên (đã xác nhận trên bản sao). PLAN-076 đã chuyển sang `agents/plans/archive/`.

Next:
- Chủ bot gửi mẫu chứng từ thật (Thanh toán, sao kê, Xác thực) cho parser + APPROVED có chứng từ.
- Quyết định thuế người nhận, chính sách thu hồi; sau đó nối đối soát vào khoá, mở ví có điều kiện.

---

## Phiên 2026-10-24 (ai) — PLAN-076 Pricing & Policy Consistency (code + test xong, CHƯA triển khai)

Claude Code, chủ bot giao PLAN-076. Worktree `/home/vu/toolsauto-cashback-pricing`, nhánh `cursor/cashback-plan076-pricing`. Báo cáo: `reports/CASHBACK_PLAN076_PRICING.md`, ADR-053.

- Preflight: production `main@a9ff267`, PID 604968, `.env` v1.2 / 70%, `reserve_policies` #1 (0,98% / 10%), `share_policies` trống; 27 link V1.1 + 4 link V1.2 `+r1`; 2 khoản pending trên link V1.1 (12.157đ, 960đ). Baseline 412 passed.
- Lỗi tìm thấy: sổ ví tính lại pending theo chính sách tra theo giờ + `.env` hiện tại (không theo nhãn r/s); quote và giờ ghi link có thể lệch chính sách ở mốc chuyển; mốc đã qua lúc Áp dụng vẫn được ghi (hồi tố); 🧮 Mô phỏng và 🎖️ Hạng tính tỷ lệ × quỹ, không theo V1.2.
- Đã làm: `pricing.cashback_for` + `PolicyResolution` là một cửa tính tiền; `admin_reserve.resolve_policy` (một transaction đọc); bảng chỉ thêm `link_policy_snapshots` ghi cùng transaction với link; backfill link cũ chỉ khi tính ra đúng số đã báo, không thì `unresolved`; sổ ví tính theo snapshot; `effective_from` chặn hồi tố; trigger chỉ-thêm cho `share_policies`/`reserve_policies`; màn Mô phỏng mới (so sánh V1.1/V1.2, lịch hẹn, hạng bản nháp, chọn 10k–500k); 📊 Lịch sử có phiên bản chính sách; `/cachtinh` và trang chủ sửa chữ. Không đổi công thức, không đổi 70% / 0,98% / 10%.
- Proof: **456 passed** (412 + 44 `tests/test_cashback_pricing_policy.py`), ruff sạch phần thay đổi. Diễn tập trên bản sao DB production (0600, đã xoá): 31/31 backfilled, 0 unresolved, 0 lệch quote ↔ snapshot, 2 khoản pending giữ số, bảng cũ không đổi (hash), khoá tài chính còn, integrity ok.
- KHÔNG merge, KHÔNG restart, KHÔNG sửa production.

Next:
- Chủ bot duyệt phát hành PLAN-076 (quy trình ở mục 16 của báo cáo) và nghĩa mới của «còn lại» (phần dư sau dự phòng).
- Sau đó: mẫu chứng từ thật cho parser + APPROVED có chứng từ; thuế người nhận; chính sách thu hồi.

---

## Phiên 2026-10-24 (ah) — Đã triển khai PLAN-075 Settlement & Fund Reconciliation

Claude Code. Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN075.md`.

- Backup trước triển khai: `data/backups/cashback-20261024T035456Z.sqlite` (verify ok, 32 link).
- `main` fast-forward `5bf2796` → `6dc2dd1`, 412 passed, đã push. Chủ bot restart 03:57:20 UTC, PID 604968.
- Migration: 5 bảng `settlement_*` (trống) và 3 trigger chỉ-thêm. Khoá tài chính còn nguyên: 4 trigger, không có bảng mở khoá, ví 0, 0 available, 0 payout. Dữ liệu cũ không đổi. Log: 0 lỗi, 0 token.
- Màn 🧾 Đối soát thanh toán hiện "Chưa xác minh" (chưa có chứng từ thật). PLAN-075 đã chuyển sang `agents/plans/archive/`.

Next:
- Chủ bot gửi mẫu báo cáo Thanh toán + sao kê + báo cáo Xác thực của một kỳ có tiền, rồi làm PLAN-076/077 (parser + APPROVED có chứng từ).
- Quyết định thuế người nhận và chính sách thu hồi. PLAN-078: nối đối soát vào khoá, mở ví có điều kiện.

---

## Phiên 2026-10-24 (ag) — PLAN-075 Settlement & Fund Reconciliation (code + test xong)

Claude Code, chủ bot giao PLAN-075 (cho phép triển khai phần an toàn; chủ bot restart). Worktree `/home/vu/toolsauto-cashback-settlement`, nhánh `cursor/cashback-plan075-settlement`.

- Không có mẫu báo cáo Xác thực/Thanh toán Shopee hay sao kê trên máy: Evidence Discovery CONDITIONAL, APPROVED BLOCKED.
- 5 bảng `settlement_*` (tên khác bảng mở khoá của payout_gate, ADR-052) và trigger chỉ-thêm cho audit/chứng cứ.
- `settlement.py`:
  - nhập định dạng chuẩn `cashback_settlement_v1` (chống trùng sha256/mã, thay chứng từ có lịch sử, lưu 0600);
  - đối soát 3 nguồn (báo cáo ↔ số học ↔ ngân hàng);
  - phân bổ bot / ngoài bot / không rõ / chưa phân bổ;
  - điều chỉnh sau kỳ: 1 sự kiện = 1 dòng.
- Công cụ nhập trên máy chủ `python -m cashback_bot.settlement_import`. Màn /admin → 🔗 → 🧾 Đối soát thanh toán ("Chưa xác minh" khi thiếu chứng từ).
- Test: 412 passed. Diễn tập migrate trên bản sao DB thật: chỉ thêm 5 bảng, dữ liệu cũ không đổi, ví khoá.

Next:
- Triển khai: backup → merge ff → chủ bot restart → kiểm tra.
- Chủ bot gửi mẫu báo cáo Thanh toán + sao kê + báo cáo Xác thực của một kỳ có tiền để làm parser (PLAN-076/077).

---

## Phiên 2026-10-24 (af) — Đã triển khai PLAN-074 Shopee Validation & Commission

Claude Code, chủ bot duyệt "duyệt 074". Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_PLAN074.md`.

- Backup trước triển khai: `data/backups/cashback-20261024T032835Z.sqlite` (verify ok, 31 link).
- `main` fast-forward `539e3d9` → `cef3467`, 368 passed, đã push. Chủ bot restart 03:30:51 UTC, PID 601747.
- Migration: đủ 13 cột, có bảng `shopee_conversion_changes`. Backfill: 2 đơn bot PENDING, đơn 23/09 FRAUD, 0 APPROVED, settlement NOT_VERIFIED.
- Khoá tài chính còn nguyên (4 trigger, ví 0, 0 payout). Màn 🧾 dựng trên bản sao: 2 chờ xác minh, 0 đã duyệt. Log: 0 lỗi, 0 token.
- PLAN-074 đã chuyển sang `agents/plans/archive/`.

Next:
- Để mở APPROVED: sau khi Shopee duyệt kỳ tháng 10, chủ bot bấm 🔄 (hoặc xuất CSV Xác thực/Thanh toán).
- PLAN-075: chủ bot chọn nguồn bằng chứng Shopee đã trả (trang Thanh toán hay sao kê).

---

## Phiên 2026-10-24 (ae) — PLAN-074 Shopee Validation & Commission (nhánh, chưa triển khai)

Claude Code, chủ bot giao PLAN-074. Worktree `/home/vu/toolsauto-cashback-validation`, nhánh `cursor/cashback-plan074-validation`. Production không đổi (main@539e3d9, PID 597550).

- Khảo sát field từ 3 response đã lưu (không gọi Shopee):
  - **không có field chứng minh "đã duyệt"**: APPROVED BLOCKED;
  - gian lận có bằng chứng (`is_fraud=1` + `fraud_reason`, 1 mẫu).
- Thêm `validation_status` / `settlement_status` (NOT_VERIFIED), 13 cột, bảng `shopee_conversion_changes`, backfill từ raw.
- `record_conversion_snapshot`: 1 transaction/đơn; không để thiếu field ghi đè; giữ Sub ID đầu; dữ liệu cũ đến muộn → NEEDS_REVIEW; 1 cảnh báo admin/lần đồng bộ.
- Màn /admin → 🔗 → 🧾 Duyệt hoa hồng (chỉ xem; "đã kiểm tra" có audit).
- Khoá tài chính giữ nguyên + điều kiện APPROVED; FRAUD/REJECTED → sổ `cancelled`.
- Test: 368 passed. Diễn tập migrate trên bản sao DB thật: 2 đơn bot PENDING, đơn 23/09 FRAUD.

Next:
- Chủ bot duyệt triển khai (mục 14 của `reports/CASHBACK_PLAN074_VALIDATION.md`).
- Để mở APPROVED: sau khi Shopee duyệt kỳ tháng 10, chủ bot bấm 🔄 một lần, hoặc xuất CSV Xác thực/Thanh toán.
- PLAN-075: settlement và đối chiếu quỹ.

---

## Phiên 2026-10-24 (ad) — Đã triển khai PLAN-073 Safety Hardening V1

Claude Code, chủ bot duyệt "oke em triển khai tiếp đi". Báo cáo: `reports/CASHBACK_DEPLOY_2026-10-24_SAFETY_V1.md`.

- Backup trước triển khai: `data/backups/cashback-20261024T025715Z.sqlite` (verify ok, 29 link).
- `main` fast-forward `eca64fd` → `a9bb42a`, 334 passed, đã push. Chủ bot restart lúc 02:58:43 UTC, PID 597550; có `chmod 600` log và backup cũ.
- Migration: thêm `failed_updates` và 4 trigger `financial_lock_*`. Dữ liệu cũ nguyên vẹn (29 link, 6 user, 2 pending).
- Backup tự động lần đầu chạy ok lúc 02:59:19 (`cashback-20261024T025919Z.sqlite`, 0600).
- Khoá tài chính đã kiểm trên bản sao backup: ví khoá với 2 lý do, nút cũ, gọi hàm và SQL trực tiếp đều bị chặn.
- Log: 0 chuỗi token/cookie; không có ERROR từ sau restart.
- PLAN-073 đã chuyển sang `agents/plans/archive/`.

Next:
- Chủ bot chọn nơi lưu backup ngoài máy (mã hoá); quyết định bot công khai hay không.
- PLAN đối soát: luồng nhập bằng chứng kỳ Shopee đã trả; điều chỉnh âm khi hoa hồng giảm sau khi vào ví; quyết định thuế người nhận.

---

## Phiên 2026-10-24 (ac) — PLAN-073 Production Safety Hardening V1 (nhánh, chưa triển khai)

Claude Code, user giao task "CASHBACK BOT: PRODUCTION SAFETY HARDENING V1". Làm trong worktree `/home/vu/toolsauto-cashback-safety`, nhánh `cursor/cashback-safety-hardening`. Production không đổi (main@eca64fd, PID 590993 không restart).

- P0-4: mỗi update được cô lập. Lỗi tạm thì thử lại tối đa 5 lần, lỗi vĩnh viễn thì ghi `failed_updates` rồi mới tiến offset. Admin được báo; 📊 hiện "Update cách ly".
- P1-8: thêm `redact.py` và `RedactingFormatter` cho mọi handler; sửa 11 chỗ log lỗi thô (token có thể nằm trong URL của requests).
- P1-9: bot tự backup mỗi 24 giờ (Backup API, `.partial`, verify, 0600/0700, dọn đúng mẫu tên, sàn 3 bản), lỗi thì báo admin. `OFFSITE_BACKUP = NOT CONFIGURED`.
- Khoá tài chính (ADR-050): cần bảng bằng chứng Shopee đã trả và thuế đã duyệt (chưa có, DDL nháp 007), nên mặc định KHOÁ.
  - Chặn: bật ví, yêu cầu rút, xác nhận đã chuyển, chuyển khoản sang `available`.
  - Có thêm 4 trigger SQLite chặn SQL trực tiếp.
- Test: 334 passed. Đã diễn tập migrate trên bản sao DB production (0600, đã xoá).

Next:
- Chủ bot duyệt và triển khai theo `reports/CASHBACK_SAFETY_HARDENING_V1.md` mục F (backup → merge ff → restart với umask 077 → xác minh).
- `chmod 600` log và backup cũ (lệnh ở mục F).
- PLAN đối soát: luồng nhập bằng chứng kỳ Shopee đã trả; điều chỉnh âm khi hoa hồng giảm sau khi vào ví.

---

## Phiên 2026-10-24 (ab) — Audit toàn hệ thống Cashback Bot (chỉ đọc)

Claude Code. Task "CASHBACK BOT FULL SYSTEM AUDIT", audit only: không sửa code, không restart, không ghi DB, không gọi Shopee/AddLiveTag.

- Báo cáo: `reports/CASHBACK_FULL_AUDIT.md`. Worktree `toolsauto-cashback-arch` không còn; 6 nhánh cashback đều đã vào main.
- Production: PID 590993 chạy HEAD `6de6f82` (xác định qua mtime), bot **công khai** (`CUSTOMER_ACCESS_ENABLED=true`).
  - 5 người dùng, 28 link, 7 click có Sub ID.
  - 2 đơn thật khớp đúng người (đang chờ duyệt). Ví tắt, 0 lần chi.
- P0:
  - (1) Mốc "có thể rút" = COMPLETED + 15 ngày, không đọc cờ gian lận hay trạng thái duyệt. Đơn đã vào ví thì bỏ qua thay đổi hoa hồng.
  - (2) Không đối chiếu tiền Shopee trả, không có trần quỹ.
  - (3) Chưa quyết định thuế.
  - (4) Update Telegram lỗi lặp lại làm cả bot im lặng (`poller.py:228-296`).
- P1:
  - Token có thể vào log (`telegram_api.py:165, 214`; chưa xảy ra).
  - Backup chạy tay.
  - Chữ /admin gây hiểu nhầm.
  - Snapshot V1.2 chưa đọc.
  - Ước tính lệch −17% đến −43%.
- Hạng thành viên và tax_profile chỉ là code + test, không nối vào báo giá hay ví.

Next:
- Chủ bot đọc báo cáo, quyết 7 mục ở phần 12.
- Anti lập PLAN cho P0-4, P1-8, P1-9 (sửa nhanh) và P0-1, P0-2 (trước khi chi tiền).

---

## Phiên 2026-10-24 (aa) — Cashback: sửa câu chữ số tiền hoàn cho khách

Claude Code, user yêu cầu "chỉnh sửa lại câu từ cho người dùng về số tiền được hoàn về".

- Lý do: link DOPI báo khách hoàn 21.357đ theo giá tham khảo 339.000. Khách trả 231.570 nên thực tế chỉ 12.157đ.
- Thẻ link:
  - Đổi thành "Hoàn dự kiến: khoảng X".
  - Ghi chú nói rõ số này tính theo giá tham khảo. Shopee tính trên số tiền thực trả: dùng voucher, xu hoặc mua lúc giảm giá thì tiền hoàn giảm theo.
  - Giữ câu "Chỉ được hoàn khi Shopee xác nhận đơn hợp lệ. Chưa phải tiền có thể rút."
- /cachtinh: thêm một gạch đầu dòng về giá tham khảo và tiền thực trả. Vẫn không hiện ký tự %.
- Tin "Có đơn mới" (khi ví bật):
  - "Hoàn tạm tính".
  - Nếu thấp hơn số đã báo lúc tạo link thì giải thích: "Lúc tạo link bot báo khoảng X… nên còn Y".
  - `Transition.estimated_vnd` lấy từ `link_requests.estimated_cashback`.
- Test: 291 passed (thêm 4), ruff sạch.

Next:
- User restart bot, gửi thử một link và đọc thẻ.

---

## Phiên 2026-10-24 (z) — Cashback: gọn màn 📊 Thống kê admin

Claude Code, user báo "phần thống kê trong admin bị rối quá".

- Trước: một màn 60 dòng. Tiền thật Shopee nằm cuối, số dự kiến lẫn với số thật, có 2 bảng 7 ngày, top khách và top món chen giữa.
- Sau: 2 màn.
  - **Tổng quan** (`c:st:<kỳ>`, khoảng 24 dòng):
    - 💰 Tiền thật: bảng Doanh số / HH / − Khách / − Phí+T / = Admin, kèm số đơn chờ, xong, huỷ.
    - 🔗 Phễu: Người dùng → Link → Click → Đơn, kèm CR.
    - 📅 Một bảng 7 ngày gộp Link, Click, Đơn, HH; bỏ ngày trống.
    - 🩺 chỉ hiện khi có lỗi.
  - **🔎 Chi tiết** (`c:st:<kỳ>:more`): Link và lỗi, số dự kiến, đối soát Shopee (HH gốc, MCN, qua bot, huỷ), ngành hàng/shop, top khách, top món. Đổi kỳ ở đây thì vẫn ở màn chi tiết.
- Bỏ `shopee_stats_lines`, thay bằng `_money_lines`, `_funnel_lines`, `_week_lines` và `stats_detail_text`.
- Test: 287 passed, ruff sạch. Đã dựng thử từ DB thật (chỉ đọc).

Next:
- User restart bot và xem 📊 trên điện thoại.

---

## Phiên 2026-10-24 (y) — Cashback: tin 🔄 hiển thị dạng bảng

Claude Code, user yêu cầu "hiển thị dạng table cho dễ quan sát".

- Telegram không có bảng HTML, nên dùng `<pre>` chữ đều. Cột: `# Trả HH Khách Phí+T Admin TT`, có dòng Σ (không tính đơn huỷ).
- Độ rộng cột tính theo số dài nhất. Với 2 đơn hiện tại, bảng rộng khoảng 38 ký tự.
- Tên món đánh số bên dưới bảng, kèm trạng thái và 🆕. Chưa có dòng sổ ví thì cột chia tiền để "-".
- Test: 287 passed, ruff sạch.

Next:
- User restart bot, bấm 🔄 và xem bảng trên điện thoại. Nếu bị xuống dòng thì bỏ cột Trả.

---

## Phiên 2026-10-24 (x) — Cashback: hiện phần admin còn sau mọi chi phí

Claude Code, user yêu cầu: "admin chưa thấy được phần admin nhận về sau khi trừ hết các chi phí".

- `cashback_entries` thêm `fee_vnd`, `tax_vnd` (migrate tự thêm cột). `wallet.Split` thay cho tuple trả từ `_real_cashback`.
  - Phí và dự phòng thuế lấy theo mức /admin áp dụng lúc tạo link.
  - V1.1 hoàn 70% trên HH gốc nên admin chịu cả hai khoản. V1.2 trừ hai khoản trước khi chia.
- 📊 Thống kê thêm dòng `💼 Qua bot: HH − khách − phí − dự phòng thuế → Admin còn` (không tính đơn huỷ).
- Tin 🔄: dưới mỗi đơn có dòng `↳ khách · phí + dự phòng thuế · admin còn`. Poller cập nhật sổ trước rồi mới gửi tin.
- Sửa thêm: "Chờ duyệt" trên màn thống kê đếm cả PAID (trước chỉ đếm UNPAID/PENDING/WAIT), khớp `wallet.order_state`.
- Bản sao DB thật:
  - DOPI: HH 17.368, khách 12.157, phí 171, thuế 1.737, admin còn 3.303.
  - Cọ: HH 1.372, khách 960, admin còn 260.
  - Tổng admin còn 3.563 / HH 18.740 (khoảng 19%, vì 2 link này tạo theo V1.1).
- Test: 287 passed, ruff sạch.

Next:
- User restart bot, bấm 🔄, kiểm tra 📊 Thống kê.

---

## Phiên 2026-10-24 (w) — Cashback: tin 🔄 liệt kê hoa hồng từng đơn, gửi ngay

Claude Code, user đồng ý ("oke em anh đồng ý") sau khi báo "anh bấm rồi mà nó không thông báo gì hết".

- Nguyên nhân: tin có gửi (08:49:09) nhưng chậm khoảng 30 giây vì đợi vòng long-poll. Tin chỉ ghi "0 đơn mới qua bot" nên nhìn như không có gì. Ví đang tắt (user tắt 19:34 ngày 23/10) nên khách không được báo.
- Sửa:
  - `SyncResult.bot_orders` (`BotOrder`): tin 🔄 liệt kê từng đơn qua bot dạng `tên · trả … · HH … · trạng thái`. Đơn mới (🆕) lên đầu, tối đa 10 dòng, đếm "mới / cập nhật".
  - Thêm nhãn UNPAID = Chờ thanh toán, PAID = Chờ duyệt.
  - Poller `flush_pending` ngay sau khi bấm 🔄.
- Test: 284 passed, ruff sạch. Đã dựng thử từ 2 đơn thật: DOPI 17.368đ, Cọ 1.372đ.

Next:
- User restart bot, bấm 🔄, xem tin.
- Chờ user quyết câu chữ "ước tính theo giá niêm yết" ở tin trả link.

---

## Phiên 2026-10-24 (v) — Cashback: hoa hồng thật khác ước tính, sửa HH gốc

Claude Code, user báo "đã có chuyển đổi nhưng hoa hồng lại khác".

- User bấm 🔄 lúc 08:44. Về 2 đơn qua bot, cả hai đang chờ duyệt.
  - DOPI kem nền: ước tính 30.510 đ (9% × giá niêm yết 339.000). Thật 17.368 đ = (5% shop + 2,5% Shopee) × 231.570 thực trả.
  - Cọ mắt: ước tính 1.663 đ, thật 1.372 đ (2,5% × 54.900 thực trả).
  - Lệch do giá thực trả thấp hơn giá niêm yết, và phần Shopee chỉ 2,5% chứ không phải 4% như API sản phẩm báo. Đây không phải lỗi đồng bộ.
- Sửa `shopee_sync`:
  - "HH gốc" lấy `estimated_total_commission` (Shopee + shop), không lấy `gross_commission` (chỉ phần Shopee). Trước đây admin thấy HH gốc 5.789 < HH sau cùng 17.368.
  - Checkout nhiều đơn có cộng thêm `capped_brand_commission`. Trước đây thiếu phần shop, nên tiền hoàn của khách bị tính thiếu.
- Test: 281 passed, ruff sạch. Các dòng đã lưu sẽ được sửa ở lần 🔄 kế tiếp (upsert).

Next:
- User restart bot và bấm 🔄 lại.
- Cân nhắc nói rõ với khách: số hoàn khi tạo link là ước tính theo giá niêm yết. Khách 8628718420 được báo 21.357 đ, thực tế 12.157 đ.

---

## Phiên 2026-10-23 (u) — PLAN-072: log từng request Buffer, bỏ quét lại kênh vô ích

Claude Code, Owner duyệt "oke em làm đi em".

- Mỗi request Buffer (qua `execute` và ping trên dashboard) ghi một dòng INFO `[Buffer][req] <key che> #<thứ tự trong ngày> <thao tác> purpose=<…> HTTP <mã> | <cửa sổ còn lại>`.
- Còn key chưa có bảng kênh (key 2, 3 đang khóa) thì kênh lạ không làm key 1 quét lại organizations/channels nữa.
- Test: 695 Buffer passed, 12 test đọc DB thật fail như cũ.
- Restart xong, cả 3 key cooldown nên chưa có dòng `[req]` thật.

Next:
- Từ khoảng 15:20 24/10 (key 2, 3) và 20:00 24/10 (key 1), đếm `[Buffer][req]` theo key và đối chiếu với `250-in-1day r=` để tìm chỗ tiêu suất.
- Nếu `r` tụt nhanh hơn số dòng `[req]` thì có nơi khác đang dùng key.

---

## Phiên 2026-10-23 (t) — Tắt quét nguồn, PLAN-070 bỏ bình luận đầu tiên, PLAN-071 quét theo nhu cầu

Claude Code, Owner duyệt "oke thực hiện đi em":

- PLAN-069 đã commit `4f92452` và push.
- 21:37 tắt cả 6 nguồn tự động bằng `SourceService.set_enabled`. Backup ở `data/backups/viral-sources-before-pause-20261023T143732Z.json`. Muốn bật lại: `/nguon`.
- Nguồn 3, 4, 5 trỏ mã kênh cũ (sót lúc đổi kênh ở PLAN-067) → đổi sang `6adb578c…9cde9b` / `…9cde9a`. Material 1709 cũng đổi.
- PLAN-070: key gói Free bị từ chối bình luận đầu tiên thì 7 ngày không thử lại (khóa `first_comment:<key>` trong `buffer_cooldown.json`). Mỗi bài còn 1 request, không gọi AI.
- PLAN-071: setting `viral.source_skip_ready_per_page` (mặc định 15, `/caidat dutru`). Nguồn tự bỏ quét khi mọi page đích đã đủ video READY.
- **Key 1 `f8pL...Y1DI` hết suất ngày, 429 lúc khoảng 22:00, nghỉ 79296s (mở lại khoảng 20:00 24/10).**
  - Suất: 59/250 lúc 21:05, 50/250 lúc 21:33, 0 lúc khoảng 22:00. Trong 21:33–22:00 tool chỉ đăng 2 bài (4–6 request).
  - Chưa giải thích được phần tiêu còn lại. Máy này không có process nào khác dùng key.
  - Cần hỏi Owner key có dán ở nơi khác không, và nên log đếm request theo key.
- Phát hiện thêm: khi key 2, 3 khóa (chưa có bảng kênh), kênh của chúng làm `get_client_for_channel` quét lại bảng kênh key 1 mỗi 30 phút (2 request mỗi lần nếu chưa chạm mức giữ). Chưa sửa, đề xuất cho Owner.

Next:
- 24/10 khoảng 15:20 key 2, 3 mở lại; khoảng 20:00 key 1 mở lại.
- Kiểm "Bo first_comment" chỉ còn một lần mỗi key.
- Kiểm suất ngày sau mỗi bài.

---

## Phiên 2026-10-23 (s) — PLAN-069: dọn ổ đĩa không xóa video bài đang hẹn Buffer

Claude Code, Owner duyệt "Vá code + gia hạn file". Bài Sống Nhẹ 20:30 23/10 (job 1113, material 1280) hỏng: Buffer tải `/buffer-media/1280/…` nhận 404. Nguyên nhân: `StorageCleanupService.prune_media` (Maintenance chạy 6 giờ/lần và ngay khi khởi động) xóa file `reup` quá 7 ngày. Job Buffer DONE ngay khi hẹn, không có `media_path`, nên không được che. Vòng 20:10 (sau restart 20:07) xóa file 1280 và 1300 (job 1118, 14:30 24/10), đặt hai material FAILED.

- 21:28 ICT: `touch -m` 10 file reup của bài đang hẹn (1326, 1330, 1332–1334, 1380–1383, 1388), gia hạn 7 ngày.
- Code: `_get_buffer_scheduled_material_ids()` (job `buffer` có `external_post_id`, không FAILED/CANCELLED, `schedule_ts` trong 2 ngày qua trở đi). `prune_media` bỏ qua `viral_<id>_…` thuộc tập đó. 4 test mới; 145 passed (storage_cleanup, adversarial, hardware).
- 21:33 restart Maintenance + Web_Dashboard: vòng dọn đầu không đụng bài đang hẹn, 18 bài từ 24/10 còn đủ file (trừ 1118).
- **Chưa commit.** Deploy `git reset --hard` sẽ mất bản vá. Commit + push khi Owner đồng ý.
- Job 1118 (14:30 24/10) sẽ fail trên Buffer vì file mất. Không khôi phục được.
- Suất ngày key mới `f8pL...Y1DI`: 59/250 lúc 21:05, 50/250 lúc 21:33. Mức giữ chặn hỏi trạng thái bài ⇒ job đã đăng chưa được đánh dấu tới khi cửa sổ ngày hồi trên 175. Mỗi bài hiện tốn 2–3 request (first_comment bị từ chối + gửi lại).

Next: commit/push PLAN-069; theo dõi vòng dọn 03:33 và 09:33 24/10; key 2, 3 mở lại khoảng 15:20 24/10.

---

## Phiên 2026-10-23 (r) — PLAN-067 đã push, PLAN-068 suất 24 giờ

Claude Code: PLAN-067 commit `3d3d383` + `7890c0c`, push `main`. PLAN-068: `client._note_budget` đọc header `RateLimit` (3 cửa sổ 15 phút / 1 ngày / 30 ngày), mức giữ 70% theo cửa sổ chật nhất; response 200 mà một cửa sổ `r=0` thì key nghỉ `t` giây luôn. `sync_posted.INTERVAL_SEC` 15 → 60 phút. PM2 đã restart 20:07, không 429. Key mới: 6 bài hẹn (Uyển Nhi 2, Sống Nhẹ 4). 12 test cluster/concurrency fail vì đọc `BUFFER_CHANNELS` thật trong DB (fail giống hệt trên code cũ). Next: theo dõi bài 20:30 Sống Nhẹ lên; key 2, 3 mở lại khoảng 15:20 ngày 24/10; cân nhắc bỏ thử first_comment (mỗi bài tốn thêm 1 request bị từ chối trên gói Free); sửa test đọc DB thật.

---

## Phiên 2026-10-23 (q) — PLAN-067 chạy thật, key 1 thay key mới

Claude Code: PLAN-067 (bảng kênh lưu `storage/db/config/buffer_channels.json`, `post_statuses` gom theo key, kênh lạ không đổ về key chính khi còn key chưa có bảng) đã chạy trên PM2, chưa commit. Lúc 19:29–19:49 cả 3 key cũ dính 429 cạn suất 24 giờ (key 2, 3 mở lại khoảng 15:20 ngày 24/10; key 1 cũ 15:17 ngày 24/10). Theo tài liệu Buffer: Free = 250 request/24 giờ mỗi key, 429 không kéo dài khóa. Owner tạo key mới cho tài khoản #1 (`.env` `BUFFER_API_KEY`, vị trí 1 = `f8pL...Y1DI`), Uyển Nhi + Sống Nhẹ có mã kênh mới. Owner duyệt: đổi `BUFFER_CHANNELS`, 48 material READY/NEW, job 1110/1111 → FAILED; backup `data/backups/buffer-channel-move-20261023T125358Z.json`. 19:56 job 1113 hẹn Sống Nhẹ 20:30 qua key mới. Next: xem bài 20:30 có lên; Uyển Nhi được xếp ở vòng sau; Owner quyết sửa tiếp đọc cửa sổ 24 giờ + giãn sync 60 phút; commit PLAN-067.

---

## Phiên 2026-10-23 (p) — VietQR tự tạo, chọn ngân hàng bằng nút

Bot tự tạo mã VietQR (EMVCo/NAPAS, CRC16) và gửi ảnh vào chat khi admin mở yêu cầu rút; bỏ `img.vietqr.io`. Khách chọn ngân hàng bằng nút (30 ngân hàng), gõ STK + tên. 59 test ngoại lệ mới, 279 passed. `qrcode==8.0` đã cài `.venv` và thêm requirements. Chưa quét bằng app ngân hàng thật. Next: user restart (PID 464286), quét thử QR theo checklist trong tin trả lời.

---
## Phiên 2026-10-23 (p) — Bật lại Buffer: chạy được, chưa 429

Claude Code bật theo lời user: `pm2 start Web_Dashboard` (:8000, funnel `/health/json` 200) rồi `pm2 start Maintenance` khoảng 19:17 ICT, chạy code `main` có PLAN-061. Vòng đầu: không 429, chưa có file `buffer_cooldown.json`; job 1110 qua key 1 → "Đã hẹn Sống Nhẹ Tuổi 40 lúc 20:30 23/10" (key 1 hết khóa); 4 video tự đánh dấu đã đăng; 9 bài lỗi trên Buffer (job 1041, 1101–1108) bị tự xóa để nhả slot. Phát hiện chưa sửa: key 2 còn 1617/3000 < ngưỡng giữ 2100 nên không quét kênh key 2 → kênh của key 2 đổ về key 1; `manager.post_statuses` gom nhóm theo object client mà `get_clients()` tạo mới mỗi lần → mỗi bài 1 request, 7 bài "Account is not allowed" + 5 "Post not found" mỗi 15 phút, đều tốn suất key 1. Next: user quyết có sửa không (PLAN mới, số kế tiếp sau PLAN-065); trong lúc chờ, theo dõi `grep -E "Key vào cooldown|HTTP 429"`.

---

## Phiên 2026-10-23 (o) — Tắt tự đồng bộ Shopee mặc định, công tắc trong /admin

User: không chạy đồng bộ tự động, khi cần thì bấm. Thêm công tắc ở 🔗 Shopee Affiliate (`bot_state.shopee_auto_sync`, mặc định tắt, bật/tắt ghi 📊 Lịch sử). Nút 🔄 vẫn chạy ngay. Sổ ví tự cập nhật mỗi giờ chỉ từ DB (không gọi Shopee) để đơn đủ ngày giữ vẫn vào ví đúng hạn. Claude Code không tự gọi Shopee nữa (đã ghi memory). 221 passed. Next: user restart.

---
## Phiên 2026-10-23 (n) — 📊 Lịch sử ghi cả cài đặt ví và cookie Shopee

User báo đổi giữ tiền 15 ngày mà Lịch sử không thấy. Nguyên nhân: Lịch sử đọc `admin_change_audit`, cài đặt ví và kết nối cookie (PLAN-065/066) đổi thẳng `bot_state` không ghi audit. Sửa: `AdminPanel._log_setting` ghi bật/tắt ví, giữ tiền, rút tối thiểu (bỏ qua khi bấm lại cùng mức), kết nối cookie (chỉ tên tài khoản, không ghi cookie). 219 passed; 2 test mới fail trên code cũ. Production (PID 462329, `5efe310` từ 12:06): ví ĐÃ BẬT, giữ 15 ngày — hai thay đổi này trước bản sửa nên không có trong Lịch sử, không chèn bù. Next: user restart để có bản sửa và menu /vi.

---
## Phiên 2026-10-23 (m) — PLAN-066 ví hoàn tiền trên Telegram (Claude Code, user giao trực tiếp)

Production: bot chạy `000240b` từ 11:43 (PID 458675), cookie dán lại 11:45, đồng bộ thật ok: tài khoản `ID 17315920094`, 10 click (7 qua bot), 1 đơn không qua bot. PLAN-066 + ADR-049 code xong (chưa chạy trên bot): đối soát đủ ô như Addlivetag (doanh số, số lượng, HH gốc → phí MCN → HH sau cùng, huỷ, bảng 7 ngày, CSV), 🔄 chạy nền; sổ `cashback_entries` pending→holding→available, ví khách (/vi, 👛), khai ngân hàng, rút tiền, admin 👛 Ví khách xem STK + VietQR, ✅ đã chuyển / ✖️ từ chối có xác nhận. **Ví mặc định TẮT**: khách không thấy gì khác cho tới khi admin bật. Mặc định giữ 30 ngày sau khi đơn hoàn thành, rút tối thiểu 10.000 đ (đổi trong /admin). 217 passed, ruff sạch; bản sao DB thật khớp số click Addlivetag. Next: user restart bot (có bảng/cột mới, đã backup); thử /admin → 👛 Ví khách, 📈 Thống kê, 🔗 → 📤 CSV; khi sẵn sàng chi trả thì bấm 🟢 Bật ví rồi restart lần nữa để menu có /vi.

---
## Phiên 2026-10-23 (l) — PLAN-065 chạy thật: sửa tham số Shopee, sự cố test đè cookie

Bot chạy `ea17b44` từ 11:33:42 (PID 457087). Cookie qua `user/status` nhưng click/đơn HTTP 400 (sai tên tham số). Claude Code đọc lỗi, thử tay khoảng 8 request, sửa theo response thật: `page_num` + `click_time_s/e` / `purchase_time_s/e` + `version=1`, `page_size=100`, tiền luôn ÷100.000, giờ unix → ISO, thống kê theo giờ click/đặt hàng, Sub ID lấy phần trước `-`, không cộng trùng hoa hồng checkout nhiều đơn, endpoint lỗi thì báo `partial`. 30 ngày: 10 click (7/7 gần nhất khớp Sub ID bot), 1 đơn không qua bot. Sự cố: pytest lúc 11:40:02 ghi cookie giả đè cookie thật (test cũ gọi `save_cookies` mặc định) → đã chặn bằng `tests/conftest.py`, có proof mtime. 199 passed. Next: user restart bot, dán lại cookie, bấm 🔄; kỳ vọng khoảng 10 click, 1 đơn, 0 đơn qua bot.

---
## Phiên 2026-10-23 (k) — PLAN-065: review + sửa lỗi Shopee Cookie Sync (Claude Code, user giao trực tiếp)

Review `0ad0b10` của Antigravity, rồi sửa theo yêu cầu user (chưa commit, 9 file `cashback_bot/` + test). Đã sửa: TypeError trong nhánh lỗi sync (từng làm callback lặp gọi Shopee mỗi 5 giây); đồng bộ tay giờ báo đơn mới; lỗi mạng không còn bị ghi là cookie hết hạn; nút Hủy thoát chế độ chờ cookie; JSON cookie bị Telegram tách được ghép lại và phần nào cũng bị xoá; phân trang có trần; thống kê "khớp bot" đối chiếu Sub ID thật; giờ VN, chữ tiếng Việt. pytest `tests/test_cashback_*.py`: 196 passed, ruff sạch; 9 test chạy trên code cũ đều fail. Chưa sửa (cần response Shopee thật): đơn vị tiền, mốc thời gian thống kê, tham số endpoint. Chưa gọi Shopee thật lần nào. Next: user commit; restart bot; vào /admin → 🔗 Shopee Affiliate dán cookie; bấm 🔄 một lần rồi gửi Claude Code/Anti một dòng `raw_json` (che cookie) trong `shopee_conversions` để chốt đơn vị tiền và định dạng thời gian.

---
## Phiên 2026-10-23 — cashback_bot: trạng thái bàn giao (Claude Code)

Đã chạy trên production: PLAN-060 (UI/UX Telegram), V1.2, PLAN-062 + ADR-047 (admin áp dụng phí/thuế dự phòng), ADR-048 (tỷ lệ chia trong /admin), /cachtinh không lộ số nội bộ, PLAN-063 (📈 Thống kê). Code PLAN-064 (lưu ngành hàng, shop, tách hoa hồng) đã merge `main`, cần user restart bot. pytest `tests/test_cashback_*.py`: 171 passed.

Đã xác nhận: phí Shopee thật 0,98%; tới kỳ 08/2026 chưa có khấu trừ thuế; click qua link bot mang đúng Sub ID.

Còn mở: user xác nhận nút phía khách để archive PLAN-060; số `base_rate`/`cap` tài khoản để kiểm tra lệch hoa hồng; phần đồng bộ số liệu đơn/hoa hồng thật từ Shopee — user giao cho Antigravity, Claude Code không làm. Phương án Claude Code làm được: nhập file báo cáo Shopee xuất ra qua /admin.

---
## Phiên 2026-10-23 (d) — PLAN-061 code xong: cooldown Buffer ghi ra file

Claude Code (Owner giao trực tiếp): mốc 429 ghi ra `storage/db/config/buffer_cooldown.json` (`app/features/buffer/cooldown_store.py`, chỉ sha256 rút gọn của key). Guard trong `client.py` đọc file mỗi lần xem cooldown, nên Maintenance, Web và lần restart sau đều thấy cùng mốc. Trần 18 giờ → 72 giờ. `ping-key` đang khóa thì không gửi request; nhận 429 thì ghi vào guard chung. pytest Buffer: toàn bộ test mới + hồi quy pass; 7 test fail có sẵn trên code gốc (đã so bằng `git stash`). Thử 2 process riêng: B không gửi request khi A đã ghi khóa. Proof chi tiết trong PLAN-061. Chưa commit. PM2 vẫn tắt, chưa chạy thật với Buffer. Next: user bật Web_Dashboard rồi Maintenance sau 18:00 ICT 23/10, theo dõi `grep -E "Key vào cooldown|HTTP 429"` 24 giờ; nếu không có 429 lặp lại thì archive PLAN-061.

---

## Phiên 2026-10-23 (c) — Kiểm tra Buffer trước khi bật lại (chỉ đọc)

Claude Code: chỉ đọc code + log PM2, không gọi Buffer, không bật process. PM2: chỉ 9Router online; Maintenance và Web_Dashboard tắt từ khoảng 08:20 ICT 22/10 (mtime log), từ đó không có request Buffer. Log không có timestamp, giờ ước theo nhịp tick 5 phút (sai số khoảng ±1 giờ). Lần 429 cuối từng key: key 1 `AnD9...ABTm` khoảng 23:30 21/10, job 1109, kênh `6ad724e7...` không có trong bảng quét nên đi key 1, Retry-After 142824s → Buffer mở khoảng 15:10–16:10 ICT 23/10. Key 3 `ZVsP...1QO5` khoảng 19:00 21/10, Retry-After 80717s → mở khoảng 17:30 22/10. Key 2 `RZX2...PVmg` không dính 429; số 1796/3000 là đọc lúc 17:57 21/10, chưa phải số mới. Phát hiện thêm: `POST /api/buffer/ping-key` (`cluster_router.py:550`) gọi thẳng `requests.post`, không qua guard cooldown; trang `/buffer-cluster` poll `cluster-status` mỗi 30 giây; Web và Maintenance mỗi process có guard RAM riêng. Next: bật Maintenance sau 18:00 ICT 23/10, không mở `/buffer-cluster` và không bấm Ping key 1 trước đó; nếu muốn chạy 24/7 thì Anti tạo PLAN ghi cooldown ra `storage/db/config/` và thêm ping-key vào scope.

---

## Phiên 2026-10-23 (j) — AddLiveTag: rủi ro phi thương mại + PLAN-064, chờ restart

AddLiveTag tự ghi `nonCommercialOnly=True`, `apiUnofficial=True`; không có endpoint đơn/click/thống kê tài khoản. User không đăng ký được Shopee Open API → tiếp tục AddLiveTag, tìm nguồn dự phòng sau. PLAN-064: lưu ngành hàng, shop, tách hoa hồng, Xtra, chạm trần lúc tạo link (7 cột NULL được, tự thêm khi khởi động) và hiện ở 📈 Thống kê. 171 passed. Chờ user: restart; số `base_rate`/`cap` của tài khoản để kiểm tra lệch hoa hồng.

---

## Phiên 2026-10-23 (i) — PLAN-063 thống kê /admin, chờ restart

`/admin` → 📈 Thống kê (Hôm nay / 7 ngày / 30 ngày / Tất cả): người dùng, link, lỗi theo lý do, số dự kiến (ghi rõ chưa phải doanh thu), xu hướng 7 ngày, top người gửi và món, sức khoẻ gửi tin. Chỉ đọc. 165 passed. Gộp restart với bản sửa /cachtinh. Chưa có số đơn/doanh thu vì chưa có Conversion Sync.

---

## Phiên 2026-10-23 (h) — /cachtinh bỏ số nội bộ, chờ restart

User không muốn khách thấy phí/thuế/tỷ lệ chia. `/cachtinh` giờ chỉ giải thích, không có %. Test chặn `%` ở mọi trang khách. 158 passed. Gộp chung lần restart với ADR-048.

---

## Phiên 2026-10-23 (g) — ADR-048 tỷ lệ chia trong /admin, chờ restart

Bot chạy PLAN-062 từ 09:41 UTC (PID 441796); user đã áp dụng mức dự phòng #1 (Cá nhân 0,98%/10%). Mới: `/admin` → Chính sách → Đổi tỷ lệ chia (bảng `share_policies`, migration 006 tự tạo khi dùng lần đầu). Thử trên bản sao DB ok. 157 passed. Cần user restart; số khách không đổi cho tới khi admin áp dụng tỷ lệ mới.

---

## Phiên 2026-10-23 (f) — PLAN-062 admin áp dụng phí/thuế dự phòng, chờ restart

Bot đang chạy V1.2 từ 09:26 UTC (PID 439579). PLAN-062 + ADR-047: `/admin` → Thuế & phí → Đổi mức áp dụng (loại hình, phí, thuế 0–50%, ngày hiệu lực, xem trước). Bảng mới `reserve_policies`/`reserve_drafts` tự tạo khi bot dùng lần đầu (CREATE IF NOT EXISTS, không đụng bảng cũ). Thử trên bản sao DB ok. 151 passed. Cần user restart; chưa có mức nào được áp dụng nên số khách không đổi cho tới khi admin bấm Áp dụng. Phần 2 (hồ sơ thuế cho đối soát) chưa làm.

---

## Phiên 2026-10-23 (e) — Bật V1.2 cashback: chuẩn bị xong, chờ user dừng bot + migrate + start

`.env` đã có `CASHBACK_ESTIMATE_POLICY=v1.2`. Backup `data/backups/cashback-20261023T092506Z.sqlite`. Migration `001` thử trên bản sao ok. Khách sẽ thấy số hoàn còn ~89% so với V1.1; link cũ giữ số cũ. Code admin/khách khớp V1.2, 141 passed. Nếu user muốn quay lại V1.1: xoá dòng `CASHBACK_ESTIMATE_POLICY` trong `.env` rồi restart (cột mới để lại không hại).

---

## Phiên 2026-10-23 (d) — PLAN-060 admin gõ phần trăm, chờ restart

Bot chạy bản thông báo mới từ 09:17 UTC (PID 437856); user xác nhận blockquote hiển thị đúng; 11/11 tin khách lưu `reply_markup_json` và gửi được. Mới: admin gõ `10` / `0,98` thay vì phần vạn (`b554a6d`, 139 passed). Cần user restart. Còn chờ user xác nhận nút phía khách để archive PLAN-060.

---

## Phiên 2026-10-23 (c) — PLAN-060 thông báo admin dễ đọc, chờ restart

Bot đã chạy bản P0–P4 từ 08:29 UTC (PID 428535, migration `reply_markup_json` ok trên DB thật). `getMyCommands`: khách 5 lệnh, `/admin` chỉ trong scope chat admin. User phản hồi thông báo "Đã gửi link" khó nhìn → làm lại bố cục, mã kỹ thuật vào `<blockquote expandable>`. 138 passed. Cần user restart lần nữa.

---

## Phiên 2026-10-23 (b) — PLAN-060 P0–P4 xong, chờ restart

Claude Code làm hết P1–P4 (user trực tiếp giao cả P1 backend). Khách: trang chủ có nút, đổi trang bằng edit, thẻ kết quả có nút Lưu ý → popup, "đang gõ", gửi lại giữ đủ nút (cột mới `outbound_messages.reply_markup_json`, migration tự chạy lúc khởi động, đã thử trên bản sao backup: ok). Admin: breadcrumb, nút Hủy khi nhập số, quay về màn vừa sửa, Thuế & phí đọc số thật, lịch sử tiếng Việt. Thông báo admin im lặng trừ lỗi; sửa lỗi `flush_pending` không bắt `TelegramDeliveryError`. pytest `tests/test_cashback_*.py`: 137 passed. Next: user restart bot (auto mode chặn Claude `kill`), bấm thử 6 màn ở mục 6 PLAN-060, rồi archive plan.

---

## Phiên 2026-10-23 — PLAN-060 UI/UX Telegram cashback_bot: duyệt + P0 + P2 chữ xong

Claude Code: user duyệt `agents/plans/active/PLAN-060-cashback-telegram-ux-rewrite.md` (giữ "bạn/mình", ẩn `/hang`, không reply keyboard). P0 xong: admin không còn biến dấu phẩy thành dấu chấm (`0,98%`, "Đồng, Bạc, Vàng"); Tổng quan hết lặp dòng; nút hết hạn giữ nút điều hướng. Sửa `cashback_bot/admin_ui.py`, `cashback_bot/admin_policy.py`, thêm 3 test (đỏ trên code cũ). P2 phần chữ khách xong (`messages.py`: trang chủ, thẻ kết quả chung V1.1/V1.2, khuôn lỗi, bỏ `/hang` khỏi menu). User đã duyệt chữ mới, gồm cả câu hiển thị V1.2 (ADR-045); duyệt chữ chưa bật V1.2. pytest `tests/test_cashback_*.py`: 123 passed. Đã merge fast-forward vào `main` (`da98387`) và push. Backup `data/backups/cashback-20261023T081443Z.sqlite`. User tự restart bot (auto mode chặn Claude `kill`): PID mới 426449, log 08:16:40 `setMyCommands ok` + `start ... public=True`, chạy code `main` `da98387`. Chưa bấm thử trên chat thật. Chưa restart bot — user chưa chốt giờ restart. Next: Anti tạo TASK P1 cho Codex (lưu `reply_markup` trong `outbound_messages`, routing callback `u:`/`c:`, `answer_callback` toast/alert, `sendChatAction`, description, scope `/admin`); sau P1 Claude Code gắn nút P2 rồi làm P3 admin.

---

## Phiên 2026-10-22 (b) — Dừng đăng bài

Cursor: `pm2 stop` FB_Publisher_1, AI_Generator_1, Threads_AutoReply, Threads_NewsWorker, Threads_Publisher. Cùng Maintenance và Web đã tắt trước đó. Còn 9Router online. Không gọi Buffer.

---

## Phiên 2026-10-22 — Dừng gọi Buffer cho hết phạt

Cursor: `pm2 stop Maintenance Web_Dashboard`. Hai process đã chết, không còn vòng quét gọi Buffer. Facebook, Threads, AI, 9router vẫn chạy. Không gọi Buffer. Bật lại trước khoảng 15:12 ngày 23 sẽ quên khóa trong bộ nhớ và gọi ngay.

---

## Phiên 2026-10-21 (b) — Vòng quét bỏ key đang khóa

Cursor: cooldown nội bộ không còn tính là 429 và không dừng cả vòng. Kênh không có trong bảng thì không đổ về key chính đang cooldown. Vòng quét chỉ mở khi còn key gọi được. pytest buffer queue, rate-limit, manager, slots, api: 49 passed. Không restart maintenance — process đang giữ khóa trong bộ nhớ tới 23:27 và 13:32 ngày mai. Không gọi Buffer. Không commit.

---

## Phiên 2026-10-21 — Buffer 429 giữ Retry-After, dừng vòng quét, job FAILED

Cursor: trần cooldown 2 giờ lên 18 giờ (`MAX_429_COOLDOWN_SEC = 64800`). Một 429 dừng cả `sweep_unscheduled_ready`. Job Buffer chưa nhận bài ghi `FAILED`, giữ `schedule_ts`. Bốn job 1081, 1090, 1093, 1096 (không mã bài) chuyển `FAILED`. pytest buffer queue + rate-limit + slots + api: 40 passed. PM2 `Maintenance` đã restart. Log 17:57 ICT: `retry_after=19805`, cap `64800` (khóa tới khoảng 23:27). Web dashboard chưa restart. Không commit.

---

## Phiên 2026-09-29 — Preset giờ hẹn theo kênh mạnh

Cursor: nút Hẹn giờ Telegram đổi thành 08:00 (Uyển Nhi), 12:00 (Sống Nhẹ), 15:30 (Uyển Nhi), 20:00 (Mê Câu Cá). Giờ hôm nay đã qua thì tự lấy ngày mai. pytest `tests/test_telegram_schedule.py` 16 passed. Worker maintenance khởi động lại. Không commit.

---

## Phiên 2026-09-27 — Buffer 429 khi tự đánh dấu đã đăng

Cursor: vòng tự đánh dấu hỏi từng bài một nên Buffer trả HTTP 429, kéo theo xếp hàng job 876 và 877 cũng bị từ chối. Giờ một vòng gộp tối đa 25 bài trong một request; gặp 429 thì dừng và đợi thêm 15 phút. pytest `tests/test_buffer_sync_posted.py` + `tests/test_buffer_api.py`: 25 passed. Worker maintenance đã khởi động lại. Không commit.

---

## Phiên 2026-09-24 — Hẹn giờ đăng từ Telegram

Cursor: spec `004-telegram-schedule-post`. Nút Hẹn giờ và lệnh `/hen` chọn giờ Việt Nam (10 phút–30 ngày). Tạo lịch hoặc sửa đúng bài đang chờ. Hủy lịch không đụng bài đã đăng. Xếp hàng không giờ và đăng ngay giữ nguyên. pytest `tests/test_telegram_schedule.py` + `tests/test_buffer_queue.py` và hồi quy Telegram liên quan: 107 passed. Chưa bấm trên chat thật. Không commit.

---

## Phiên 2026-09-23 (c) — Nút Telegram xếp hàng Buffer

Cursor: tin video sẵn sàng có nút 5 page. Bấm gọi `queue_reup` → job `platform=buffer` + caption AI + `viral_material_id`, mode hàng chờ. Không ghi `media_path` (tránh cleanup xóa file). Funnel `https://laptop-t2hf25cd.tail67527a.ts.net` đã tải đúng file #1063. pytest buffer + nút 34 passed. Poller Telegram bật riêng vì web-only không chạy maintenance.

---

## Phiên 2026-09-23 (b) — URL https cho video reup → Buffer

Cursor: route công khai `/buffer-media/{id}/{chữ ký}.mp4` (không login, không hết hạn). Setting `BUFFER_MEDIA_BASE_URL` phải là https công khai. Job có `viral_material_id` thì `public_media_url` trả link đó thay vì file local. pytest `tests/test_buffer_media.py` + `tests/test_buffer_api.py` 14 passed. Chưa có base https thật nên Buffer chưa tải được video. Chưa gắn nút Telegram.

---

## Phiên 2026-09-23 — Buffer GraphQL

Cursor: nhánh `cursor/feat-buffer-api`. Client `app/features/buffer/client.py`, adapter platform `buffer`, `manage.py buffer channels|post`. Media phải là URL https công khai. pytest `tests/test_buffer_api.py` 8 passed. Chưa commit, chưa push. Cần `BUFFER_API_KEY`.

---

## Phiên 2026-09-20 (h) — Affiliate comment sau Reel + hiện Jobs/cockpit
Cursor: `cursor/feat-affiliate-on-post`. Path comment đã có; thêm posted/comment_ok/affiliate_url; COMMENT max_tries=1. pytest 24. Không push.

---

## Phiên 2026-09-20 (g) — P0-4 default Playwright headed
Cursor: `cursor/fix-fb-headed-default`. Default `FACEBOOK_PLAYWRIGHT_HEADLESS=false` (headed). Env true/false vẫn override. pytest 6 passed. A=`7789db7` merge=`ba0523b`. Không push.

---

## Phiên 2026-09-20 (f) — P0-3 clamp cooldown 1800 / concurrent 2
Cursor: `cursor/fix-fb-antiban-floors`. Floor: cooldown≥1800, max_concurrent 1–2, delay_min≥30, delay_max≥min. Claim GREATEST. pytest 12 passed. A=`86e7d80` merge=`f7d935a`. Không push. P0-4 headless default — chưa làm.

---

## Phiên 2026-09-20 (e) — P0 checkpoint harden (detect/stop, không bypass)
Cursor: branch `cursor/fix-fb-checkpoint-harden`. `JobStatus.CHECKPOINT`; markers gom 1 dict `CHECKPOINT` trong `selectors.py`. Adapter abort ngay, không `_safe_goto("/")` sau checkpoint; screenshot `logs/screenshots/`; Telegram chữ CHECKPOINT; acc INVALID. pytest 66 passed (`test_fb_checkpoint_harden` 19 + admin overview + idle/publisher/media_gate). Chưa commit/push. Còn P0-3 cooldown/concurrent clamp, P0-4 headless default — không làm.

---

## Phiên 2026-09-20 (d) — Cockpit Tổng quan + hashed assets
Cursor: hashed Vite `index-DQrcaxcu.js`. Cockpit worker/disk/gemini/checkpoint/FAILED. Commits `25afd3d` + `9d6e433` branch `cursor/feat-admin-cockpit`. URL `/app`.
Stack http://127.0.0.1:8002 — Ctrl+Shift+R Tổng quan. Không push.

---

# Current Status

## Phiên 2026-09-20 (c) — Restart :8002 + commit SPA

Cursor: stack `http://127.0.0.1:8002` PID supervisor `529779` (uvicorn web `529780`), `/health/json` ok, login `dev/dev` cookie OK. Verify live: curl authenticated `/app`+`/app/go/jobs` 200 SPA shell; bundle có `Tạo job thủ công`; không `Admin·React`; HTML không badge REACT. Browser MCP không mở được tab — chưa hard-reload visual. Commit `fc695fb` (114 files) branch `cursor/feat-native-spa-crud`. Leftover Classic chưa làm. Không push.

---

## Phiên 2026-09-20 (b) — SPA native CRUD (dừng, chưa verify live)

Cursor: gỡ badge REACT; Jobs/Viral/Accounts/Affiliates/Sources/Compliance/AI Studio/FB tasks/Threads/Syspanel/DB/Insights có thao tác JSON `/api/admin/*`. `pytest tests/test_admin_api_lists.py` 12 passed, `npm run build` OK. Stack :8002 **đã tắt** lúc chốt — không hard-reload Jobs. Còn Classic: cookie login, PM2/Gemini cookie, selector platform-config, heatmap/boost, allowlist/CSV, sandbox AI, kho kênh cũ. Chưa commit.

---

## Phiên 2026-09-20 — Khởi động stack local WSL

Cursor: stack Windows :8002 đã chết. Postgres `127.0.0.1:5432/toolsauto_db` sống, alembic `s6a3b4c5d6e7` = head.
Đã `manage.py stack --host 0.0.0.0 --port 8002 --no-reload-web`. `/health/json` → `status=ok`.
Worker: web + maintenance + fb_publisher + ai_generator = ok. Drive G: mounted.
9Router `localhost:20128` không chạy → AI fallback Gemini. Không có PLAN mới từ Anti.

---

## Phiên 2026-09-19 (h) — Roadmap native: hết sidebar

Cursor: Threads / Logs / Control plane / AI Studio / Platform config / Syspanel / Database
sang React list. API mới: `GET /api/admin/{threads,logs,ai-studio,syspanel,database}`.
Platform config dùng `/platform-config/{platforms,workflows}` sẵn có. Control plane không API.
CRUD / PM2 / SQL / lưu prompt vẫn Classic. Test admin lists + threads/ai-studio/logs.
`npm run build` OK. Chưa commit.

---

## Phiên 2026-09-19 (g) — Roadmap native: Compliance

Cursor: SPA `/app/go/compliance` gọi `/compliance/{analytics,keywords,categories,violations}`.
Native: 4 StatCard + tab Từ khóa / Lịch sử. Tester, CRUD, allowlist, chart vẫn Classic.
Không API admin mới. `npm run build` OK. Chưa commit.

---

## Phiên 2026-09-19 (f) — Roadmap native: Nhiệm vụ FB

Cursor: `GET /api/admin/fb-pro-tasks` bọc `build_dashboard`. SPA `/app/go/fb-pro-tasks`:
scope picker + tiến độ tuần + 3 thẻ nhiệm vụ + queue hints. Form lưu / reset tuần vẫn Classic.
Test `test_admin_fb_pro_tasks_lists_scope`. `npm run build` OK. Chưa commit.

---

## Phiên 2026-09-19 (e) — Roadmap native: Insights

Cursor: SPA `/app/go/insights` gọi `/insights/api/{growth,top-posts,secondary-metrics,page-analysis}`.
Native: filter platform/days + StatCard + top posts + page analysis. Heatmap / AI / boost vẫn Classic.
Không API admin mới. `npm run build` OK. Chưa commit.

---

## Phiên 2026-09-19 (d) — Roadmap native: Affiliates / Nguồn video / Kho kênh cũ

Cursor: `GET /api/admin/affiliates|viral-sources|tiktok-links` (bọc service sẵn có).
FE native list + Classic link; CRUD vẫn Jinja. Test `test_admin_api_lists.py` 3 passed.
`npm run build` OK. Chưa commit.

---

## Phiên 2026-09-19 (c) — Mọi module admin vào `features/` + iframe Jinja

Cursor: mỗi mục sidebar có thư mục `frontend/src/features/<tên>/`.
Native: Overview / Jobs / Jobs-Threads / Accounts / Viral / Settings.
Còn lại: iframe Jinja `?embed=1` (ẩn sidebar classic) trong AppShell.
Layout: `app/templates/layouts/app.html`. `npm run build` OK. Chưa commit.

---

## Phiên 2026-09-19 — Frontend: tách internals theo feature (phase 2)

Cursor: Overview / Jobs / Accounts / Viral giờ cùng pattern Settings:
`api` · `types` · `hooks` · `components` · `pages`. Shared UI:
`PageHeader`, `Pagination`, `Panel`, `SearchField`, `QueryBody`.
Xóa `shared/api/adminApi.ts`. Behavior giữ nguyên. `cd frontend && npm run build` OK.
Chưa commit (chờ Owner).

---

## Phiên 2026-09-15 (b) — Tái cấu trúc frontend feature-based

Cursor: `frontend/src` → `app/` (routes+nav) · `layouts/` · `shared/` · `features/{overview,jobs,accounts,viral,settings,classic}`. Behavior giữ nguyên; `npm run build:admin` OK.

---

## Phiên 2026-09-15 — React admin roadmap (Overview / Jobs / Accounts / Viral)

Cursor: tiếp roadmap SPA sau Settings.
- Backend: `GET /api/admin/{overview,jobs,accounts,viral}` (`app/platform/admin_api/`).
- FE native: Overview wire API; Jobs/Accounts/Viral thay ClassicBridge tại `/app/go/*`.
- Jinja `/app/jobs|accounts|viral` giữ nguyên (link Classic trên từng page).
- Build: `npm run build:admin` → `app/static/admin/`. Chưa commit (chờ Owner).

---

## Phiên 2026-09-12 — ADR-046 hướng A: video dài giữ full lần đầu

Owner chọn hướng A. Video nguồn > `viral.long_video_sec` (mặc định 180) và chưa có
`clip_length_sec` → lần Xử lý đầu **không cắt** theo «Độ dài tối đa». Tin READY thêm nút
**🧩 Chia phần** + **✂️ Cắt ngắn** (`cat90` → gắn độ dài từ ô Thiết lập, mặc định 90 nếu ô=0,
giữ mốc bắt đầu, `process_one`). ADR: `agents/decisions/ADR-046-long-video-defer-cut.md`.
Đã sync sang Windows scratch. **Cần restart** `.\start.ps1 -Lan -Stack` để bot nhận callback.
Test mới ADR-046: 7 passed. (1 fail sẵn có `test_da_dang_doi_trang_thai…` path Drive ADR-045
≠ assertion cũ — ngoài scope.)

---

## Phiên 2026-09-11 (j) — menu "/" Telegram sinh từ code, không cài tay

Owner: *"menu đang lỗi không được đẹp"*. Menu do BotFather cài tay từ lâu: quảng cáo /done,
/failed (không tồn tại), thiếu /sansang /moi /nguon /dadang /tai /caidat. Nay `MENU` trong
`command_handler` là nguồn sự thật (lệnh hằng ngày lên đầu, luồng Job xuống cuối), poller gọi
`setMyCommands` lúc khởi động (hỏng mạng chỉ ghi log). Test canh hai chiều menu ↔ handler_map.
Owner khởi động lại bot là menu đổi; nếu Telegram còn cache thì đóng mở lại app Telegram.

---

## Phiên 2026-09-11 (i) — đường TẢI TikTok cũng phải giả Chrome; hướng dẫn Tailscale

Ảnh Owner 17:00: `/moi` ra #1001–#1006 với views thật ⇒ **quét kênh đã sống trên laptop** (có
curl_cffi). Bấm Xử lý #1001 ⇒ FAILED "Unexpected response" — cờ giả Chrome mới nối vào quét
và `/tai`, chưa nối vào `processor.py` (preflight + tải); TikWM dự phòng lần này cũng hỏng.
Vá: `_platform_args` trong processor, dùng chung `impersonate_args`; lỗi tải TikTok dịch bằng
`humanize_scan_error` (bỏ id, nói "trang kiểm tra bot", tự khai bản yt-dlp + gợi ý curl_cffi).
Test đọc argv thật processor dựng. **1061 passed.**

Tailscale (cho link 📱 ngoài nhà): cài trên laptop + iPhone cùng tài khoản, lấy IP 100.x.y.z
của laptop trong app, `/caidat diachi http://100.x.y.z:8002`, web chạy `-Lan`.

---

## Phiên 2026-09-11 (h) — test đã bắn tin GIẢ vào Telegram thật của Owner; chặn ở gốc

Owner gửi ảnh: hàng loạt "Video sẵn sàng đăng tay · Material #1 · facebook · 1,234 lượt xem ·
viral_1_src_reup.mp4 · 4 KB" kèm nút ✅ Đã đăng, lúc 16:49 và 16:58 — đúng hai lần chạy toàn bộ
test ở máy dev. Nguyên nhân: test import `app.main` ⇒ đăng ký kênh Telegram THẬT từ `.env` ⇒
mọi `notify_*` sau đó (file giả 4096 byte) bay thẳng vào chat Owner. Cùng họ với lỗi log sáng.

Chặn hai tầng trong `tests/conftest.py`: token rỗng TRƯỚC khi `app.config` đọc `.env`
(`load_dotenv(override=False)`), và autouse fixture xoá `NotifierService._channels` + chặn
`httpx` trong `telegram_client`. `tests/test_conftest_walls.py` khoá cả hai tường. **1058 passed.**

**Owner: các tin "Material #1 · 1,234 lượt xem" trong chat là giả — xoá đi, ĐỪNG bấm ✅ Đã đăng
trên chúng** (nút trỏ tới material #1 trong DB laptop, có thể là video thật).

---

## Phiên 2026-09-11 (g) — ADR-044: link "📱 Mở trên điện thoại" trong tin video

Owner đăng từ điện thoại bằng Chia sẻ vào app. Video > 50 MB không về Telegram, tin chỉ có
đường dẫn Drive không bấm được. Nay: ô Thiết lập **"Địa chỉ mở tool từ điện thoại"**
(`PUBLIC_BASE_URL`, `/caidat diachi http://…`) → tin video có dòng bấm-là-tải file về Files
(route `/viral/{id}/phone`, attachment, tên theo tiêu đề) → Chia sẻ vào Facebook/TikTok/Threads.
`start.ps1 -Lan` cho web nghe trên mạng nhà và in địa chỉ LAN. Chưa đặt ô ⇒ không in link giả.
Route sau màn đăng nhập. **1055 passed.** Không migration.

### Next Action (Owner, laptop)

1. `git pull` → `pip install -r requirements.txt` → `alembic upgrade head` (vẫn nợ).
2. Chạy `.\start.ps1 -Lan` (thêm `-Stack` như thường) — dòng xanh in `Web (LAN): http://192.168.x.x:8002`.
3. Telegram: `/caidat diachi http://192.168.x.x:8002`.
4. `/sansang` → 📤 Gửi lại #984 → tin có dòng 📱 → bấm trên điện thoại (cùng Wi‑Fi; Safari hỏi
   đăng nhập một lần) → file vào Files → Chia sẻ → Facebook. Ngoài nhà: Tailscale, dùng IP đó.

---

## Phiên 2026-09-11 (f) — `/caidat`: đổi cài đặt luồng video ngay trong Telegram

Owner: *"mấy setting này setting ở tele được không"* — sau khi video bị cắt 1:30 mà phải mở
web mới tìm ra ô "Độ dài tối đa". `/caidat` xem 7 ô hay chỉnh (tên ngắn: `dodai`, `giugoc`,
`caption`, `nguong`, `sovideo`, `quet`, `trung`; nhận cả key đầy đủ); `/caidat dodai 0` đổi.
Ghi bằng chính `upsert_setting` của web (validate min/max, audit, bust cache), rồi ĐỌC LẠI giá
trị hiệu lực để trả lời. Bool nhận bật/tắt tiếng Việt. Chỉ chat của Owner mới ra lệnh được
(poller đã lọc chat_id). Tin video cắt theo số chung nay chỉ đường tới ô đó (commit ecbd710).

**1048 passed.** Không migration.

---

## Phiên 2026-09-11 (e) — gộp nhánh Cursor `--impersonate chrome`, sửa cho không hỏng máy thiếu gói

Owner gửi ảnh laptop: Cursor (WSL) tạo nhánh `cursor/fix-tiktok-scan-impersonate` (dd66ede)
— quét TikTok thêm `--impersonate chrome`, nâng `curl_cffi` 0.14 → 0.16.3. Owner: *"kiểm tra
để đồng bộ git main"*.

Kiểm thật trước khi gộp: máy dev **chưa cài curl_cffi** ⇒ cờ đó làm yt-dlp **dừng ngay**
(`Impersonate target "chrome" is not available`) — merge nguyên là quét chết ở mọi máy chưa
`pip install`. Cài gói vào thì có/không cờ đều ra 3 video. Kết luận: cờ đúng cho IP bị chặn
(laptop), nhưng phải **có điều kiện**.

Đã gộp vào `main` (không xung đột) rồi sửa: `impersonate_args()` ở `app/core/yt_dlp_path.py`
trả cờ CHỈ khi import được `curl_cffi`; `sources`, `tiktok_scraper`, `fetch` (ADR-043, TikTok)
dùng chung. Tin lỗi "trang không phải dữ liệu" nói thêm *"máy này chưa có curl_cffi"* + lệnh cài.
Test khoá cả hai nhánh có/không gói; YouTube không giả Chrome.

Ảnh còn lộ: **`.env` với TELEGRAM_BOT_TOKEN và GOOGLE_API_KEY hiện rõ** — đã nhắc Owner xoay
khoá. Và `where.exe yt-dlp` ở laptop trỏ tới `Python312\Scripts\yt-dlp.exe` toàn cục — tool
không dùng nó (ADR-029 ưu tiên venv), nhưng là bằng chứng laptop có hai bản.

**1032 passed.** `main` = merge + sửa; nhánh Cursor có thể xoá sau khi laptop pull.

### Next Action

Laptop: `git checkout main && git pull` → `venv\Scripts\python.exe -m pip install -r
requirements.txt` (lấy curl_cffi 0.16.3) → `alembic upgrade head` → khởi động lại → `/nguon` →
🔍 Quét ngay. Xoay Telegram bot token + Google API key vì đã lộ trong ảnh.

---

## Phiên 2026-09-11 (d) — ADR-043: `/tai <link>` tải bản gốc về máy, không reup

Owner: *"xem video FB thấy hay muốn tải về máy chứ không reup, video nào cũng được"*. Đội mũ
trong ADR; ranh giới quan trọng nhất: **không đi qua luồng viral** (không material, không chống
trùng, không cắt, không caption, không đụng `REUP_DIR`) — kho lưu, không phải kho sản xuất.

- Telegram `/tai <link>` (web: ô "Tải về máy" trên trang Viral). Mọi link http(s); link kênh /
  danh sách bị chặn **trước** khi gọi yt-dlp.
- Lưu `storage/media/tai-ve/<tháng>/<tiêu đề>.mp4`; chép Drive `videos/Tải về/<tháng>/` nếu bật.
- Cookie: lượt đầu KHÔNG (video công khai; Chrome mở profile là cookie hỏng); Facebook/Instagram
  đòi đăng nhập ⇒ thử lại bằng tài khoản ACTIVE.
- ≤ 50 MB gửi file qua Telegram; hơn thì báo đường dẫn. `--max-filesize 500M`.
- Lỗi dịch như `/nguon`, kèm bản yt-dlp đang chạy.

Đo thật: TikTok công khai 148,5 MB / 15,9 s. **1030 passed.** Không migration.

### Next Action

Owner: `git pull` (laptop còn nợ migration ADR-041/042: `alembic upgrade head`) → khởi động lại
→ `/tai <link Facebook đang xem>`. Nếu Facebook đòi đăng nhập mà chưa có tài khoản FB ACTIVE
trong tool, tin sẽ nói thẳng — đó là lúc cân nhắc đăng nhập một tài khoản.

---

## Phiên 2026-09-11 (c) — /nguon phải nói thật: lỗi quét đọc được, biết quét lúc nào

**Bổ sung (c2):** Owner chụp lại sau khi pull — "Quét lúc 06:24" trong khi ảnh chụp 13:53:
**laptop chạy bot theo UTC**, lượt quét thật là 13:24 (code mới, vẫn hỏng). Hai vá thêm:
- Telegram in giờ theo `config.TIMEZONE` (`ZoneInfo`), như trang web — không theo đồng hồ tiến trình.
- Tin lỗi **tự khai bản yt-dlp đang chạy** so với bản ghim (dùng `_ytdlp_version_status` của
  ADR-029): cũ ⇒ in lệnh `pip install -r requirements.txt`; đúng bản ⇒ kết luận TikTok chặn tạm.
  Owner không phải đi mở trang Sức khỏe nữa. `last_error` nới 200 → 300 ký tự để chứa đủ.
**1005 passed.** Chờ Owner pull lần nữa và bấm 🔍 Quét ngay — tin trả lời sẽ tự nói yt-dlp bản nào.

Owner gửi ảnh `/nguon`: `❌ ERROR: MS4wLjABAAAAMgUb…: Failed to parse JSON (caused by JSO` và
*"tìm được lần cuối: 0"*. Kiểm thật: chạy **đúng lệnh tool chạy** trên đúng nguồn ở máy dev,
yt-dlp 2026.08.19 ⇒ **21 video, 3/3 lần**. Kênh không hỏng — **máy chạy bot (laptop) mới là
chỗ cần nhìn**: yt-dlp cũ hoặc TikTok trả trang kiểm tra bot cho IP đó.

Ba chỗ vá (thuộc ADR-033, không cần ADR mới):
- `humanize_scan_error`: lỗi quét được dịch như bên tải video; bỏ sec_uid 60 ký tự chiếm chỗ;
  "Failed to parse JSON" → chỉ Owner tới trang Sức khỏe xem bản yt-dlp.
- `/nguon` ghi **"Quét lúc 11/09 08:12: ✅ 3 video mới / ⚪ không có video mới / ❌ hỏng — lý do"**.
  Trước đây "0" không phân biệt được "không có gì mới" với "quét hỏng", và không biết lúc nào.
- `tests/conftest.py` trỏ `LOG_DIR` ra thư mục tạm: test từng ghi `@a: ERROR: boom` vào
  `logs/app.log` thật. Đo: chạy cả suite, `app.log` không đổi một byte.

### System State

**1000 passed, 16 skipped, 0 failed**. `ruff` sạch · `lint-imports` giữ. Không migration mới.

### Next Action

1. **Owner (laptop chạy bot): `git pull` → `alembic upgrade head` (ADR-041/042 còn nợ) → khởi
   động lại.** Mở trang Sức khỏe xem dòng yt-dlp: bản nào, đường dẫn nào. Rồi `/nguon` → 🔍 Quét
   ngay — tin trả lời giờ nói rõ lúc nào và vì sao.
2. Nếu vẫn "trang không phải dữ liệu" với đúng bản 2026.08.19 ⇒ TikTok chặn IP laptop; giãn
   lịch quét kênh đó.

---

## Phiên 2026-09-11 (b) — ADR-042: "Đã đăng" là một trạng thái, không phải một thư mục

Owner hỏi *"đã đăng rồi thì bấm trên tele để nó dời thư mục khác không"*. Lật lại: dời file mà
không ghi trạng thái thì `/sansang` vẫn hiện, DB vẫn READY — thêm một nhãn nói dối. Nên:
**trạng thái trước, file là hệ quả**.

- `ViralStatus.POSTED` + `posted_at`. Nút **✅ Đã đăng** ngay dưới tin video và trong
  `/sansang`; nút **↩️ Chưa đăng** lùi lại; lệnh **`/dadang`** liệt kê 10 video đăng gần nhất.
- Bấm Đã đăng: `_reup` cục bộ → `<platform>/da-dang/`; bản Drive → `videos/<tháng>/Đã đăng/`
  (cùng tháng, không gom chung). File GỐC không đụng. Drive hỏng vẫn ghi POSTED, tin nói rõ.
- **Chống trùng (ADR-024) nay soi cả POSTED** — lý do quan trọng nhất: thứ đã đăng không được
  lọt vào lại. Có test chứng minh.
- Web: badge 📌, nút Đã đăng / Chưa đăng, bộ lọc POSTED. Hàng POSTED ẩn Reup lại / Chọn đoạn /
  Chia phần.

### System State

**985 passed, 16 skipped, 0 failed** (trước 961). `ruff` sạch · `lint-imports` giữ ·
`alembic heads` = `s6a3b4c5d6e7`. **Migration mới — Owner phải `alembic upgrade head`.**

### Unfinished + Blockers

- Chưa gắn link bài Facebook vào material (`posted_url`) — cố ý để sau; có link mới đo được
  lượt xem thật. Cách rẻ nhất: trả lời tin bằng link ⇒ tool tự gắn.
- `da-dang/` chưa có cơ chế dọn — mở rộng giữ-N-ngày khi thấy số thật.
- ADR-041 vẫn chưa có proof cắt thật N phần trên Telegram (cần DB dev bật).
- Nợ cũ như phiên (e)/(a).

### Next Action

1. **Owner: `git pull` → `alembic upgrade head` → khởi động lại.** Đăng một video, bấm ✅ Đã đăng
   dưới tin, kiểm: `/sansang` không còn nó, `/dadang` có nó, Drive có thư mục `Đã đăng/` trong
   tháng, file máy nằm ở `da-dang/`.
2. Bấm ↩️ Chưa đăng một lần cho biết nó lùi được.

---

## Phiên 2026-09-11 (a) — ADR-041: chia video dài thành nhiều phần, cắt ở chỗ "đang gay cấn"

Owner: *"xây luôn tính năng, và dùng thuật toán tối ưu nhất, tính toán đoạn hay nhất, xong cắt
ra để đăng phần tiếp theo"*. Hỏi lại một câu, Owner chốt **giữ cả video, chỉ chọn chỗ cắt**.

### Cách làm

Phần con = một material bình thường có cha, đi **nguyên đường xử lý cũ** với mốc riêng. Ba chỗ
đường cũ biết "đây là con": không tải lại (file gốc nối cứng sang tên của con lúc chia), không
chống trùng với anh em, caption biết mình là phần mấy.

Chọn chỗ cắt ba tầng, tầng nào cũng **nói rõ mình là tầng nào**: (1) Whisper lời thoại kèm mốc
→ AI chọn câu kết mỗi phần; (2) chia đều rồi kéo về cuối câu / khoảng lặng / đổi cảnh; (3) chia
đều, ghi "CHƯA tính". Tool **đề nghị**, Owner bấm ✅ mới cắt.

Luồng Telegram: `/sansang` → 🧩 Chia phần → 2/3/4 → (nền) ảnh lưới + kế hoạch → ✅ Cắt → mỗi
phần một tin "🧩 Phần i/N của #cha". Web: cùng hai bước trên dòng video.

### Đo thật (video 1:15 có nhạc nền)

`silencedetect` **0 khoảng lặng** — nhạc nền lấp; Whisper **28 câu**, mất **65.7 s ≈ 0.9×
thời lượng**. Hệ quả: cuối câu Whisper đưa thẳng vào tầng 2 (không thì video có nhạc nền không
bao giờ có ranh giới); tin nhắn sửa "vài chục giây" → "khoảng bằng độ dài video".

Guard chống trùng chứng minh được là cần: bỏ nó, phần con bị đánh `DUPLICATE (sha256 giống
hệt)` ngay lượt đầu.

### System State

**961 passed, 16 skipped, 0 failed** (trước: 914). `ruff` sạch · `lint-imports` 2 hợp đồng giữ
· `alembic heads` = `r5f2a3b4c5d6`. **Migration mới — Owner phải `alembic upgrade head`.**

### Unfinished + Blockers

- **Chưa có proof cắt thật N phần rồi nhận đủ N tin Telegram** — cần DB dev (port 5434) bật.
  Test end-to-end chạy nguyên `process_material` trên SQLite với ffmpeg giả.
- AI tầng 1 chưa chạy được ở shell kiểm thử (key trong DB) — chuỗi dự phòng đã hạ đúng tầng.
- Video **không có lời** chỉ có tầng 2/3 — đường "Gemini xem video" để sau.
- Nợ cũ: `publish` 765 dòng chưa test; chữ không dấu ở `overview_warnings_api`; link rút gọn
  `vt.tiktok.com` bị hiểu thành handle; `test_threads_world_news.py` vẫn `--ignore`.

### Next Action

1. **Owner: `git pull` → `alembic upgrade head` → khởi động lại.** Chọn một video dài đã READY,
   `/sansang` → 🧩 Chia phần → 3 → đợi khoảng bằng độ dài video → xem kế hoạch → ✅ Cắt.
   Báo lại: các phần có cắt giữa câu không, caption có ghi "Phần i/N" không.
2. Nếu tin kế hoạch ghi "chia đều, CHƯA tính" nghĩa là không nghe được lời — báo em, đó là
   lúc cần đường Gemini xem video.

---

## Phiên 2026-09-10 (e) — ADR-040: tách hàm 770 dòng, test cho hai file lớn nhất

Owner: *"triển khai cho xong đi em"*. ADR-039 để lại đúng hai việc, làm nốt cả hai.

### Tách `_process_viral_materials`: 770 → 660 dòng

Vòng `for mat in materials:` dài 570 dòng chứa **12 lệnh `continue`** — đó là lý do không tách
hết được: khối nào điều khiển vòng lặp thì cắt ra là đổi hành vi. Chỉ tách **ba khối có
`continue` = 0**: `_finish_ready_material`, `_caption_metadata_for`, `_resolve_target_page`.

Suýt hỏng khi tách: hai regex `BOOST_CONTEXT` **không phải một** — bản để đọc có nhóm bắt, bản
để xoá ăn luôn khoảng trắng hai bên. Gộp làm một là tiêu đề còn hai dấu cách dính nhau.

### Hai lỗi thật do việc viết test lôi ra

`delete_page_config` và `update_page_config` đều dùng `set()` cho danh sách Page, mà setter
`target_pages_list` lấy **phần tử đầu làm Page chính**.

```
4 Page: [mecauca, tet, phu, x]  →  xoá "tet"
cũ:  ['x', 'phu', 'mecauca']    ← Page chính hoá ra "x"
mới: ['mecauca', 'phu', 'x']
```

Nguy ở chỗ `_resolve_target_page` khoá video generic về Page đầu danh sách: **Page chính đổi =
video sang Page khác niche, không lỗi nào báo**. Chỉ cần lưu niche của một Page phụ là đủ xáo.

Test 3 Page viết lần đầu **qua được do may** — `set` chuỗi đổi thứ tự theo từng lần chạy. Phải
chọn đúng bộ bốn URL tái hiện được rồi mới vá.

### System State

| | Trước | Sau |
|---|---|---|
| Hàm dài nhất luồng viral | 770 dòng | **660** |
| `app/core/account.py` (936 dòng) | 0 test | **52** |
| `app/core/config_service.py` (1041 dòng) | 0 test | **28** |
| Toàn suite | 816 | **914 passed, 16 skipped, 0 failed** |

`ruff check .` sạch · `lint-imports` 2 hợp đồng giữ.

### Unfinished + Blockers

- **`publish` 765 dòng** trong `facebook/adapter.py` nay là hàm dài nhất repo — đụng Playwright
  thật, **không test nào phủ**, tách mù là liều.
- Ghi lại chưa vá: `vt.tiktok.com/ZS8Kx` bị hiểu thành handle `@ZS8Kx` (link rút gọn — vá đúng
  phải gọi mạng). Đã khoá bằng test ghi rõ "hành vi hiện tại — sai, đã biết".
- Chữ trong `overview_warnings_api` **không dấu** ("Khong co preset active") — trái quy ước chữ
  trên web phải có dấu. Test bám cấu trúc chứ không bám câu chữ nên sửa lúc nào cũng được;
  **chờ Owner chốt** vì đây là chữ Owner nhìn thấy.
- Nợ cũ chưa động: `tests/test_threads_world_news.py` vẫn bị `--ignore` ở CI (hỏng 4 tháng);
  gộp hai hàm làm sạch tiêu đề; bỏ `import ViralService as _VS` thừa.
- **12 video đang có vẫn là bản cắt sai** (sinh ra khi lỗi ADR-038 #1 còn đó) — phải cắt lại.

### Next Action

1. **Owner: `git pull` + khởi động lại.** Nếu tài khoản có nhiều Page: kiểm lại **Page chính**
   có đúng không — trước bản này nó có thể đã bị đổi lặng lẽ ở lần lưu cấu hình gần nhất.
2. Đặt lại mốc cắt cho 12 video cũ.
3. Quyết số phận `tests/test_threads_world_news.py`: viết lại 8 test hay xoá file.
4. Đăng bài đầu tiên lên Page "Mê Câu Cá".

---

## Phiên 2026-09-10 (d) — ADR-039: bật ruff, chỉ luật bắt lỗi thật

Owner hỏi *"code hiện tại có scale được không, có main tain không, có clean không, có theo quy
chuẩn nào không"* rồi giao *"triển khai vá đi em"*.

Đo trước: **198 file · 48.813 dòng**, 52 hàm > 100 dòng, 70/198 file không test nào nhắc tới,
và **không có linter / formatter / type-checker nào**. Có ADR, có `RULES.md`, có import-linter
ở CI — luật kiến trúc có người canh, **luật viết code thì không**.

Bật `ruff` chỉ với `F` + `E9` (vi phạm = chạy sai). **Cố ý không bật luật định dạng**: bật lên
là diff gần toàn bộ 48.813 dòng, không đổi hành vi dòng nào mà xoá sạch `git blame`.

### Bảy lỗi thật bắt được ngay lượt chạy đầu

Năm `NameError` nằm im vì bị `except` nuốt — trong đó `facebook/adapter.py` **chưa bao giờ tải
được account**, và hàm chuyển Page bằng aria-label **luôn trả `False`**.

Hai khai báo `global` thiếu tên trong `ai_generator.py`, nặng hơn cả: `GEMINI_CIRCUIT_RESET_TIME`
gán vào biến cục bộ ⇒ **ngắt mạch vừa mở đã đóng lại**, và bộ đếm lỗi không bao giờ reset. Tức
tin Telegram *"tạm ngưng 30 phút"* **chưa bao giờ đúng** — worker vẫn nện Gemini sau khi cookie
hỏng. Lại đúng họ "nhãn nói dối".

Diff: 52 file, +62/−97. Proof: 816 test xanh, 26 bảng model vẫn đăng ký đủ sau khi xoá 97 import.

---

## Phiên 2026-09-10 (c) — ADR-038: bảy lỗi do code-review bắt

Owner: *"kiểm tra code đi"*. Chạy `/code-review` mức cao trên `e8b6c4b..HEAD` (17 commit,
57 file, +6.450 dòng). **Bảy lỗi**, trong đó một cái vô hiệu hoá hẳn tính năng chính.

### Lỗi #1 — mốc cắt KHÔNG hề có tác dụng ở đường chạy thật

`ReupProcessor.process` có chốt `skip_existing`: thấy `_reup.mp4` cũ là trả lại và **báo thành
công**. `reprocess_reup` truyền `force=True`, **đường chính thì quên**. Mà xử lý lại để đổi mốc
thì file cũ luôn còn đó, nên ADR-031/036 **không làm gì cả** suốt từ hôm qua.

Chứng minh bằng video đồng hồ: đặt mốc 120 ra `mode=skip_existing`, khung giây 2 hiện **2**.
Sau khi vá hiện **122**.

**Vì sao mọi lượt chạy thật trước không bắt được:** chúng đều tự gọi `process(force=True)`.
Chạy thật vẫn sai nếu **không chạy đúng đường production đi**.

### Sáu lỗi còn lại (đã vá, có test)

| # | Lỗi |
|---|---|
| 2 | Bỏ qua kết quả `process_material` — Owner nhận lời hứa rồi **im lặng vĩnh viễn** |
| 3 | `media_info` lấy **chiều cao** làm thời lượng khi ffprobe trả N/A, clip 90s báo "Dài 17:04" |
| 4 | Bấm khung hình **xoá mất độ dài** đã đặt (chuỗi rỗng và None bị gộp) |
| 5 | File tạm `…_reup.tmp.mp4` **thắng ở bước sort**, "bản gốc" hoá ra là bản đã cắt |
| 6 | Nút Gửi lại tải video **trên luồng poller**, callback hết hạn, bot đứng im |
| 7 | Chốt tách tin chỉ bật khi có caption; tiêu đề dài (**đo thật 1.369 ký tự**) làm Telegram trả 400, **mất cả tin lẫn video** |

**Tự làm hỏng khi vá, test bắt lại:** gom `scan` và `gui` vào một nhánh rồi cho cả hai im lặng
khi thành công — nhưng quét xong mà im thì Owner không biết có gì không. Nay `scan` báo kết
quả, `gui` im vì chính video đã là câu trả lời.

### System State

16 test mới khoá cả bảy; 3 test cũ sửa theo ngữ nghĩa mới.
**816 passed, 16 skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ.

### Unfinished + Blockers

- **12 video đang có vẫn là bản cắt sai** — chúng tạo ra khi lỗi #1 còn đó. Phải cắt lại.
- Nợ cũ: file test Threads chết 4 tháng (`ai_runtime` đã bị xoá hẳn, phải viết lại hoặc xoá);
  gộp hai hàm làm sạch tiêu đề; bỏ `import ViralService as _VS` thừa.

### Next Action

1. **Owner: `git pull` + khởi động lại.** Đặt lại mốc cho một video rồi kiểm — **từ giờ nó mới
   thật sự cắt**. Trước bản vá này mọi lần đặt mốc đều vô tác dụng.
2. Quyết số phận `tests/test_threads_world_news.py`: viết lại 8 test hay xoá file.
3. Đăng bài đầu tiên lên Page "Mê Câu Cá".

---

## Phiên 2026-09-10 (b) — ADR-037: lệnh Telegram nối vào luồng video

Owner hỏi *"mấy cái command đó nó có nối với nguồn video đồ không"*. Soi thật: **không**.
Ba trên chín lệnh (`/jobs` `/drafts` `/retry`) chỉ chạm `Job` — cần tài khoản Facebook mà Owner
có 0 ⇒ luôn rỗng. `/discovery` quét theo tài khoản ⇒ cũng rỗng. `/viral` ghi ngưỡng **chung**,
mà nguồn của Owner có ngưỡng **riêng** nên lệnh đó **không đổi được gì cho nguồn đang chạy**.
Toàn bộ ADR-025→036 chỉ chạm Telegram ở hai chỗ: dán link vào, nhận video ra.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| **`/nguon`** — liệt kê nguồn, nút **Quét ngay** / **Bật-Tắt** | 4 test |
| **`/moi`** — video `NEW`, nút **Xử lý** | 2 test |
| **`/sansang`** — video `READY`, nút **Gửi lại** + **Chọn đoạn** | 3 test |
| **Chọn mốc cắt trong chat**: ảnh lưới 4×3 + 12 nút ghi phút | dựng thật **800×1068, 103 KB**; 5 test |
| Bấm mốc ⇒ đặt `clip_start` rồi cắt lại | `test_bam_moc_thi_dat_clip_va_xu_ly_lai` |
| Quét / Xử lý **trả lời ngay rồi chạy nền** | 2 test |
| `/jobs` `/drafts` rỗng ⇒ nói rõ "chưa nối tài khoản, xem /sansang" | sửa nội dung |
| `/viral` nói rõ **không đụng nguồn có ngưỡng riêng** | sửa nội dung |
| `telegram_bot` vẫn không import `viral_intake` (7 hook mới ở `bootstrap_hooks`) | `lint-imports` 2 hợp đồng giữ |
| Toàn suite | **799 passed, 16 skipped, 0 failed** |

**Cái canh của ADR-033 tự bắt lỗi của ADR-037**: `test_help_khong_quang_cao_lenh_khong_ton_tai`
đỏ vì danh sách lệnh trong test **chép tay** nên lệch khi thêm lệnh mới. Không vá bằng cách
thêm ba chữ, mà tách `handler_map()` ra để test đọc **bảng thật** — từ nay không thể lệch.

### System State

Owner điều khiển được cả luồng video trong Telegram: xem nguồn, quét, bật/tắt, xem video mới,
xử lý, xem video chờ đăng, gửi lại file, và **chọn đoạn cắt bằng cách bấm khung hình**. Bảng
100 video và trang Thiết lập vẫn ở web, cố ý.

### Unfinished + Blockers

- **Chưa thử các lệnh mới trên bot thật** — máy dev không nối được DB thật nên chỉ gửi `/help`
  vào chat. Owner gõ `/nguon`, `/sansang` trên máy chạy tool là biết ngay.
- Video > 50 MB vẫn không gửi kèm file được (giới hạn Bot API).
- Nợ cũ: gộp hai hàm làm sạch tiêu đề trùng nhau; bỏ `import ViralService as _VS` thừa.

### Next Action

1. **Owner: `git pull` + khởi động lại `start.ps1 -Stack`**, gõ `/nguon` và `/sansang`.
2. Ở `/sansang` bấm **✂️ Chọn đoạn** → nhìn ảnh lưới → bấm mốc có cá → nhận video mới.
3. Đăng bài đầu tiên lên Page "Mê Câu Cá".

---

## Phiên 2026-09-10 (a) — ADR-036: chọn cả hai đầu đoạn cắt, và cho phép không cắt

Owner: *"sao lại cắt em nhỉ, người xem xem không hiểu đầu đuôi như nào"*.

**Kiểm lại giả định cũ**: `MAX_REELS_DURATION = 90` đặt theo giới hạn Facebook Reels, nhưng
**6/2025 Meta đã bỏ giới hạn đó**. Câu "phải cắt vì Reels chỉ cho 90 giây" không còn đúng —
ADR-031 giữ con số này mà không kiểm lại.

**Nhưng bỏ cắt cũng không phải lời giải**: Facebook xếp hạng theo **tỷ lệ xem hết**, vlog 9,5
phút thì tỷ lệ đó gần 0 và bị dìm. Vấn đề thật là **cắt ẩu**: bắt đầu ở chỗ vô nghĩa, kết thúc
giữa chừng. Muốn một đoạn trọn vẹn phải chọn được **cả hai đầu**.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| Cột `clip_length_sec` + migration `q4e1f2a3b4c5` | `alembic heads` = 1 head |
| Độ dài riêng từng video, thắng cả preset lẫn ô chung | **chạy ffmpeg thật**: từ giây 60, dài 50 ⇒ **50.0s** |
| Ô `reup.max_duration_sec = 0` ⇒ **không cắt** | **chạy thật**: ⇒ **300.0s** = nguyên bản, `success=True` |
| 0 **không** truyền xuống mà đổi thành `NO_CUT_DURATION` — vì `max_duration` còn là **cổng kiểm chất lượng**, số 0 ở đó loại sạch mọi bản xuất | 5 test |
| Độ dài sai (chữ/âm/dưới 5 giây) ⇒ từ chối, không đổi status | 3 ca |
| UI: ô "dài" ngay cạnh ô "từ giây" | render thật |
| Toàn suite | **774 passed, 16 skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ |

**Lỗi thật chỉ lộ khi chạy thật — lần thứ ba trong hai ngày:** `_fast_trim_fallback` có chốt
`duration <= max_duration ⇒ "không cần dự phòng"`. Chốt đó đúng khi mọi video dài đều bị cắt,
nhưng ở chế độ **không cắt** thì `duration` không bao giờ vượt ngưỡng ⇒ lượt mã hoá chính hỏng
là **hỏng hẳn**: material bị `FAILED`, file tải về bị xoá. Chính tính năng mới mở ra đường đi
**không có lưới**. Đã sửa: dự phòng chạy cả hai chế độ, và **cả bốn** nhánh hỏng đều thử dự
phòng thay vì hai.

**Lỗi phụ tự tạo tự bắt:** `_fast_trim_fallback() or ReupResult(...)` — `ReupResult` luôn
truthy nên nhánh sau không bao giờ chạy và **lỗi gốc bị nuốt**. Đổi sang xét `.success`.

### System State

Mỗi video chọn được **từ giây mấy** và **dài bao nhiêu**. Bỏ trống ⇒ y như trước (90 giây).
Ô chung đặt 0 ⇒ không cắt. Không đổi mặc định — đổi mặc định là đổi hành vi mọi video cũ.

### Unfinished + Blockers

- **Chưa làm nút chọn mốc trong Telegram** (dải khung hình + nút) — việc tiếp theo.
- Postgres máy dev vẫn tắt (`port 5434`), nên mọi kiểm chứng dùng SQLite tạm / chạy ffmpeg rời.
- Nợ cũ: gộp hai hàm làm sạch tiêu đề trùng nhau; bỏ `import ViralService as _VS` thừa.

### Next Action

1. **Owner: `git pull` + `alembic upgrade head`** (có migration mới) + khởi động lại.
2. Với một video: mở **"✂️ Chọn đoạn cắt"**, đặt **từ giây** và **dài** để được một đoạn trọn
   vẹn (mở → cao trào → kết). Khoảng 15-60 giây thường ăn nhất trên Facebook.
3. Muốn thử không cắt: `/app/settings` → "Độ dài tối đa video sau xử lý" = **0**. Em vẫn khuyên
   đừng, vì tỷ lệ xem hết quyết định phân phối.
4. Đăng bài đầu tiên lên Page "Mê Câu Cá".

---

## Phiên 2026-09-09 (k) — ADR-035: tin Telegram nói rõ dài bao nhiêu, cắt từ đâu

Owner chạy thật luồng ADR-034 (dán link vào chat ⇒ nhận video + caption) và phản hồi:
*"anh nhìn như này không biết video bao nhiêu phút hay như nào hết"*.

### Done This Session (có proof)

| Việc | Proof |
|---|---|
| Dòng `⏱ Dài 1:30 · cắt từ 5:32 (gốc 9:33)` trong tin | `test_k1` |
| Không có mốc ⇒ "cắt từ đầu"; không biết gốc ⇒ **bỏ ngoặc**, không đoán bừa | `test_k2`, `test_k3` |
| Đo hỏng ⇒ bỏ dòng đó, tin vẫn gửi | `test_k4`, `test_k7` |
| `sendVideo` mang `duration`/`width`/`height` ⇒ Telegram hết hiện `0:00` trên khung video | `media_info` đo thật: `{duration 90.0, width 576, height 1024}` |
| `media_info` đặt ở `core/media` — notifier lẫn processor đều dùng; `ViralService.probe_duration` **gọi lại nó** thay vì giữ bản riêng | `test_khong_suy_duong_dan_ffprobe_bang_replace` (đã cập nhật) |
| Toàn suite | **758 passed, 16 skipped, 0 failed**; `lint-imports` 2 hợp đồng giữ |

Bối cảnh kỹ thuật: `send_video` không truyền `duration` nên Telegram không biết độ dài mà
hiển thị. Sửa ở **tầng client** nên mọi chỗ gửi video đều được, không riêng tin này.

### Unfinished + Blockers

- **Chưa làm nút chọn mốc cắt trong Telegram** (dải khung hình + 12 nút) — việc tiếp theo,
  và giờ càng đáng làm vì Owner đã thấy được "cắt từ đâu, còn bao nhiêu chưa lấy".
- Video > 50 MB vẫn không gửi kèm file được (giới hạn Bot API).
- Nợ cũ: gộp hai hàm làm sạch tiêu đề trùng nhau; bỏ `import ViralService as _VS` thừa.

### Next Action

1. **Owner: `git pull` + khởi động lại**, dán lại một link ⇒ tin mới phải có dòng `⏱`.
2. Thấy "cắt từ đầu (gốc 9:33)" mà đoạn đầu nhạt ⇒ báo em làm nút chọn mốc trong Telegram.
3. Đăng bài đầu tiên lên Page "Mê Câu Cá".

---

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
