# PLAN-126 — Xe Tết Sum Vầy: MVP live tương tác (P1)

> Đổi số 01/11: tạo ngày 31/10 với số 120 trùng PLAN-120 ngắt dòng phụ đề (Studio) — số không được dùng lại nên chuyển sang 126.

- Status: Done — anh duyệt 01/11, commit `b3d0636` (nhánh `feat/xe-tet-sum-vay`)
- Executor: Claude Code (anh giao trực tiếp 31/10: «triển khai luôn cho nóng đi em, mvp trước»)
- Thiết kế: `xe_tet/README.md`

## Scope (P1 — chạy thử không cần TikTok)

- `xe_tet/server/`: FastAPI + WebSocket, luật chơi thuần Python (bến → chạy → trạm dừng chân → thả khách → hết chuyến),
  nhận diện 63 tỉnh (tên, không dấu, viết tắt, đầu biển số), `KHÔNG VỀ`, lệnh ở trạm (món ăn / WC / mua quà),
  tim, quà 4 bậc cố định, follow, chia sẻ, vào phòng; giả lập phòng đông.
- `xe_tet/server/control.html`: bảng bấm gửi sự kiện thử.
- `xe_tet/overlay/`: Vite 5 + TypeScript + Three.js, khung 1080×1920, cảnh low-poly hình khối.
- Test pytest cho nhận diện tỉnh + luật chơi.

## Ngoài scope

TikTokLive thật, SQLite, giọng VieNeu, lọc từ (P2); mô hình đẹp, kẹt xe, gửi hàng, chế độ chúc Tết (P3).
Không đụng code toolsauto khác.

## Proof (31/10)

- `venv/bin/python -m pytest xe_tet/tests -q` → 16 passed (nhận diện 63 tỉnh / biển số / viết tắt, cả vòng chuyến,
  xe đầy → xe sau, KHÔNG VỀ, đổi tỉnh 1 lần, tim tăng tốc + giảm dần, quà 4 bậc, quà lớn chen cảnh SPECIAL, trạm dừng, bong bóng chat).
- Fuzz 30 seed × 20.000 bước luật chơi + giả lập: không lỗi.
- `ruff check xe_tet` sạch; `npm run build` (tsc strict + vite) sạch.
- Chụp Chromium thật (SwiftShader, không GPU) đủ 5 cảnh: bến xe, trong xe 24 giường, đang chạy, trạm dừng chân, thả khách.
  FPS trên SwiftShader ~3 (CPU) — chưa đo trên GPU thật.
- Lỗi tìm ra khi chạy thật và đã sửa: vòng lặp server chết khi màn hình ngắt giữa lúc gửi (set đổi kích thước khi đang lặp)
  → lặp trên bản sao + vòng tự chạy lại có ghi log; nhãn CSS2D đọng lại khi xoá cả nhóm → gỡ tay;
  nhãn 3D đè HUD → z-index; camera quá gần → lùi; giường quá sát → giãn.

### Test UI/UX (31/10, anh: «em test giúp anh ui ux luôn»)

Script Playwright (Chromium thật) chạy 11 tình huống: màn trống, tên dài / emoji / tên chứa HTML, 15 sự kiện/giây,
xe đầy 24 người (trong xe), đang chạy, quà 1000 xu, trạm dừng 14 người, thả 10 người cùng tỉnh, hết chuyến,
5 người KHÔNG VỀ, cửa sổ 16:9; bảng điều khiển ở 390 px + 1280 px (bấm nút → kiểm state thật). Đo tự động phần tử HUD
nằm trong vùng TikTok che (ước lượng: thanh trên 150 px, khung comment trái 720×520 từ y=1240, thanh dưới 140 px) + chữ tràn.

Đã sửa:
- **Lỗi thật:** sự kiện ở trạm (`rest_action`) có trường `kind` ghi đè `kind: "event"` của khung tin → overlay bỏ qua,
  trạm dừng không có ai đi lại. Đổi thành `action`, server bọc `{**event, "kind": "event"}`; thêm test chặn tái phát.
- Sự kiện trạm / thả khách tới trước khi cảnh kịp đổi bị bỏ → giữ lại, phát khi cảnh đổi xong.
- Xe + người nằm dưới khung comment TikTok → góc máy dốc hơn, bến / trạm / nhà lùi sau, mái nhỏ (không che người).
- Bảng tỉnh lấn khung comment + thanh dưới → hẹp lại, đặt góc phải y=1300.
- Băng rôn che nhà khi thả khách → hiện ở chỗ bảng tuyến, tạm ẩn bảng tuyến + lơ xe.
- Tiêu đề / bảng tuyến gọn hơn; dòng trạng thái bị cắt vì ô số ghế dài → `🚌 24/24 · chờ 25`; tối đa 3 thông báo.
- Bảng điều khiển: ô trạng thái không xuống dòng, nút giả lập đang bật được tô sáng.

Kết quả lần chạy cuối: 0 lỗi JS, 0 phần tử HUD bị vùng TikTok che > 15 %, 0 chữ tràn, không cuộn ngang ở 390 px.
Chưa làm: vùng che của TikTok là ước lượng — cần anh xem trên điện thoại thật khi live thử.

### Admin điều khiển mọi thứ (31/10, anh: «cho admin đổi góc camera… tự đổi không auto nữa, mọi thứ được control»)

- Bỏ chu kỳ tự đổi ngoài / trong xe. Thiết lập admin ở server (`xe_tet/server/settings.py`), lưu
  `storage/db/config/xe_tet.json`, gửi kèm state → mọi overlay đổi ngay, giữ qua tải lại / restart.
- `/control` thêm: Camera (ngoài / trong xe, 4 góc máy, gần / xa — camera trượt mượt), Chuyến xe (tạm dừng / chạy tiếp,
  ±30 s, qua pha, làm lại, thời gian đón khách / nghỉ trạm), Màn hình (bật / tắt 4 phần + lơ xe tự nói),
  Lơ xe nói câu tuỳ ý, băng rôn tuỳ ý.
- Engine: `paused`, `skip()`, `extend()`, `board_seconds` / `rest_seconds` theo thiết lập.
- Proof: 23 test qua (thêm 7 test admin: tạm dừng, ±giờ, kẹp giá trị, lưu file, câu / băng rôn tới overlay qua WebSocket,
  tắt lơ xe tự nói). Test bấm thật bằng Playwright: 26/26 kiểm tra qua (bảng điều khiển → overlay đổi đúng), 0 lỗi JS,
  không cuộn ngang ở 390 px. Thiết lập đã trả về mặc định sau test.

### Nhấp nháy màn hình (31/10, anh: «nó hay bị nhấp nháy màn hình»)

- Đo (Playwright, 120 s, giả lập 6 sự kiện/giây): màn đen 0,3 s **14 lần / 2 phút** — mỗi lần đổi cảnh bến ↔ đường ↔ trạm ↔ nhà
  (một chuyến thả khách là 2 lần). Gắn log tạm: không có vòng bật tắt lỗi, chỉ là hiệu ứng mờ đen cố ý → nhìn như nhấp nháy.
- Sửa: mặc định **cắt cảnh thẳng**; thêm công tắc «Hiệu ứng chuyển cảnh (mờ nhẹ)» trên `/control` (mặc định tắt, bật thì mờ 45 %
  thay vì đen hẳn). HUD chỉ ghi DOM khi nội dung đổi (trước đó ghi lại 5 lần / giây).
- Sau sửa: 13 lần đổi cảnh → **0 lần màn đen**; 10 s đứng yên → 0 lần ghi DOM; bật công tắc → mờ 0,45 đúng.
  23 test, test điều khiển 26/26, test UI/UX 11 tình huống không lỗi.

### Rà soát BA / BRD / thuật toán / SA (31/10, anh yêu cầu) — chi tiết `xe_tet/REVIEW.md`

- Đã sửa (có test): đọc tên tất cả người xuống xe (lật trang); quà băng rôn lúc hết chuyến không mất; quà 1000 xu chen ngay
  ở đón khách / chạy / trạm rồi quay lại đúng chỗ; lời hứa quà đúng theo có vé hay chưa; lọc tên + chat (bậy / link / SĐT);
  tán gẫu không còn thành đặt vé / huỷ vé; giờ Việt Nam cho đếm ngược; ép kiểu an toàn (400 thay 500); gửi WebSocket có
  giới hạn 1 s; tối đa 14 chùm pháo hoa; cảnh báo giả lập; test trình duyệt đưa vào `xe_tet/e2e/`.
- Proof: 33 test, fuzz 30 × 20.000 bước có kiểm bất biến, e2e 11 tình huống + 26/26 điều khiển, ruff + tsc sạch.
- Cần anh quyết: năng lực chở (đề xuất tự rút ngắn khi hàng chờ dài + báo giờ chờ), cộng dồn quà trong chuyến, mật khẩu `/control`.

### Học từ 2 repo cùng ngách (31/10, anh gửi link) — chi tiết README mục 5b

- Đọc `zane-tv/tiktok-live-temple-rpc`, `kentjuno/chanh-dien-online` (chỉ đọc, không chạy). Cả hai: `tiktok-live-connector` 2.x.
- Áp dụng ngay: kiểm Host (chặn DNS rebinding — trước đó Host lạ trả 200, giờ 400) + test; overlay vẽ tối đa 30 khung / giây.
- Ghi vào thiết kế P2: `processInitialData=false`, khoá = userId, quà combo cộng phần tăng theo groupId, SOCIAL fallback,
  ROOM_USER, ảnh đại diện, **tự nối lại** (cả hai repo đều thiếu), hàng đợi giọng có trần.
- Proof: 34 test, e2e điều khiển 26/26, Host lạ → 400, 127.0.0.1 / localhost → 200.

### Làm theo đề xuất + nối TikTok (31/10, anh: «làm theo đề xuất theo các chuyên gia đi em, và kết nối thư viện»)

- Giờ cao điểm (hàng chờ ≥ 24): chặng 10–20 s, 1 trạm 45 s, tính lại mỗi chặng; vé xếp hàng có `eta_min`; thẻ «⚡ Cao điểm».
- Quà cộng dồn trong chuyến; mỗi mốc 1.000 xu = 1 lần chúc Tết; gợi ý `next_tier` «thêm X xu → …».
- `XE_TET_TOKEN` tuỳ chọn cho `/control` + `/api/*` (overlay, /ws vẫn mở); cảnh báo khi mở Host ra mạng mà thiếu mã.
- `xe_tet/server/tiktok.py`: TikTokLive 7.0.1 trong venv riêng `/home/vu/venv-xetet` (websockets 17 ≠ 16 của venv chung);
  nạp lười; userId làm khoá; combo cộng phần tăng; `process_connect_events=False`; tự nối lại 5→60 s, chưa live chờ 30 s,
  hết live dừng, không tìm thấy / giới hạn tuổi dừng có lỗi; đang nối khoá giả lập (409). `/control` có mục kết nối + nhật ký.
- Proof: 48 test (9 test cầu nối với client giả: combo, nối lại, chưa live, hết live, sai tài khoản, khoá giả lập, mã);
  chạy được cả 2 venv. **Thử thật** vào `@lavie3398` (phòng anh gửi): nối lần đầu 6 s, ~350 người xem, 145 sự kiện / 40 s,
  0 lỗi trong log; đã ngắt, làm lại game, xoá tài khoản thử khỏi ô gợi ý. e2e 11 tình huống + 26/26 điều khiển.
- Server giờ chạy: `/home/vu/venv-xetet/bin/python -m xe_tet.server` (nền, chưa PM2).

### Rà soát BA / SA lần 2 (31/10, anh yêu cầu) — chi tiết `xe_tet/REVIEW.md` phần «Rà soát lần 2»

- Đã sửa: combo quà spam (gộp thẻ, pháo hoa chỉ khi lên bậc, «bao cả xe» 1 lần / trạm); follow 1 lần, chia sẻ 1 lần / phút;
  vé ma (im lặng 30 phút trong hàng chờ → bỏ); nối lại vào-rớt có bậc chờ tăng dần (chỉ reset khi giữ ≥ 60 s); live tắt 10 phút
  → dừng; server khởi động lại tự nối TikTok (`tiktok_auto`); tắt log truy cập + xoá mã khỏi URL; e2e từ chối chạy khi đang live.
- Đo: cao điểm 178 khách / giờ (thường 97). 55 test, fuzz sạch, e2e 11 tình huống + 26/26.
- Cần anh quyết: thêm `XeTet` vào PM2.

### Trải nghiệm người xem trước (31/10, anh: «tập trung vào trải nghiệm end user trước»)

- Đo ở cỡ điện thoại (khung 1080 → 390 px, ×0,36): chữ 20–27 px còn 7–10 px — đa số không đọc được; nhân vật ~10 px.
- Làm lại HUD theo quy ước chữ chính ≥ 38 px, phụ ≥ 30 px; bớt chữ (bỏ dãy chip điểm dừng → «Tiếp: 📍 A → ☕ Trạm → 📍 B»).
- Lời kêu gọi to dưới bảng tuyến: «💬 Gõ TÊN TỈNH để lên xe» + gợi ý xoay 4 s (ví dụ / KHÔNG VỀ / thả tim / cao điểm);
  ở trạm đổi sang PHỞ · TRÀ ĐÁ · WC · MUA QUÀ.
- Thẻ lớn giữa màn cho từng vé («🎫 Bé Na lên xe về Nghệ An! · Giường 2»), đông quá 3 người thì gộp tên.
- Tim: server gom 0,5 s → overlay cho tim bay từ góc nút tim lên thanh tốc độ; trạng thái hiện «⚡x1.8» khi tim đẩy xe.
- Bảng góc phải luân phiên 8 s: «🏆 Tỉnh dẫn đầu» ↔ «🚌 Trên xe số N» (tên khách) — thấy tên mình cả khi camera ngoài xe.
- Thả khách 4 tên / trang (tên to + lời chúc dòng riêng); nhãn 3D 30 px; nhân vật ngoài trời ×1,35; vào phòng không chen thông báo.
- Proof: 56 test; e2e 11 tình huống (thêm kiểm khung kêu gọi + thẻ lên xe) 0 lỗi, 0 vùng bị TikTok che; 26/26 điều khiển;
  0 chữ bị cắt ở tiêu đề / kêu gọi / bảng. Ảnh cỡ điện thoại: scratchpad phone2a.png, phone2b.png.
- Còn: tên trên giường (cảnh trong xe) vẫn nhỏ do giường sát nhau — bảng «Trên xe» bù lại.
