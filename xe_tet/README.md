# Xe Tết Sum Vầy — live tương tác TikTok

Phòng live 9:16: người xem comment tên tỉnh để lên **xe khách 24 chỗ** về quê ăn Tết, thả tim cho xe chạy,
giữa đường ghé **trạm dừng chân** ăn uống, đi vệ sinh, mua quà; tới đầu ngõ thì thả khách, đọc tên.
Mùa chạy: 15/12/2026 → mùng 10 Tết (Tết Đinh Mùi 6/2/2027).

## 0. Chạy

```bash
cd /home/vu/toolsauto
python3 -m venv /home/vu/venv-xetet && /home/vu/venv-xetet/bin/pip install -r xe_tet/requirements.txt  # lần đầu
cd xe_tet/overlay && npm install && npm run build && cd ../..   # chỉ cần khi sửa overlay
/home/vu/venv-xetet/bin/python -m xe_tet.server                  # cổng 8810 (XE_TET_PORT để đổi)
```

- Venv riêng vì `TikTokLive` kéo `websockets` 17 (venv chung toolsauto đang 16). Chạy bằng `venv/bin/python` của toolsauto
  vẫn được, chỉ không nối TikTok (bảng điều khiển báo lỗi khi bấm Kết nối).
- **Nối TikTok:** `/control` → «📡 Kết nối TikTok LIVE» → gõ `@username` hoặc dán link live → Kết nối. Nối trước khi lên live
  cũng được (tự chờ, tự vào khi live bắt đầu); rớt mạng tự nối lại 5 → 60 s; live kết thúc thì dừng. Đang nối thì khoá giả lập.
  Khoá Euler (tuỳ chọn, khi gói miễn phí bị giới hạn): `SIGN_API_KEY=…` trước lệnh chạy.
- **Mật khẩu (tuỳ chọn):** `XE_TET_TOKEN=…` → mở `/control?token=…`. Màn hình live (`/`) vẫn mở để LIVE Studio quay.
  Muốn điều khiển từ điện thoại trong mạng: thêm IP máy vào `XE_TET_ALLOWED_HOSTS` **và** đặt `XE_TET_TOKEN`.

- Màn hình live: http://127.0.0.1:8810/ (khung 1080×1920, tự co theo cửa sổ). Khi thử có thể thêm `?view=inside|outside`
  hoặc `?cam=x,y,z,lx,ly,lz` trên URL để ghi đè lựa chọn của admin; `?fps=1` hiện khung hình / số lần vẽ (đo trên GPU thật);
  `?res=0.5` vẽ nửa độ phân giải (máy yếu, máy không GPU); `?hour=10` ép giờ trong ngày (chụp ảnh ngày / đêm khi thử).
- Bảng điều khiển: http://127.0.0.1:8810/control — admin điều khiển mọi thứ, **không có gì tự đổi góc**:
  - Thanh ghim đáy màn hình (điện thoại): ⏸ Dừng · ⏭ Qua pha · 📺 Xe chính · 🎥 Góc kế · 🚌 Các xe. Bị từ chối (đổi bến
    khi còn khách, gọi xe cho làn trống…) thì lời báo hiện ngay đầu màn hình.
  - Camera: ngoài xe / trong xe (24 giường), 4 góc máy (toàn cảnh, từ trên cao, ngang xe, cận xe), gần / xa;
    **chất lượng hình Cao / Thấp** (thấp: ~60 % độ phân giải, tắt bóng đổ, bớt hạt — khi máy nóng / LIVE Studio giật).
  - Chuyến xe: tạm dừng / chạy tiếp, ±30 giây, qua pha tiếp, làm lại; thời gian đón khách / nghỉ trạm.
  - Màn hình: bật / tắt bảng tuyến, lơ xe, thông báo, bảng tỉnh; bật / tắt lơ xe tự nói.
  - Lơ xe nói câu admin gõ; băng rôn tuỳ ý (tiêu đề + dòng phụ + số giây).
  - Gửi sự kiện thử, giả lập phòng đông.
  - **Bến đi** (Miền Đông mới / Giáp Bát / Liên tỉnh Đà Lạt / Đà Nẵng / Cần Thơ) — chỉ đổi được khi bến trống.
  - **Nhạc & âm thanh (PLAN-127):** mỗi xe một bài (⏭ Bài / 🔇 ở «Các chuyến xe»), tiếng theo xe đang chiếu; âm lượng
    nhạc / hiệu ứng (còi, pháo hoa, tiếng máy, «ting» khi có vé; vào hầm nhạc bị «bịt»). Nhạc có sẵn do máy tự sáng tác
    (ngũ cung, đàn tranh / sáo / trống / mõ) — không vướng bản quyền. Nhạc của anh: chép mp3 / ogg / m4a / wav vào
    `storage/media/xe_tet/music/`. Trình duyệt chặn tự phát tiếng: bấm vào màn hình live một lần (🔇 sẽ mất), hoặc mở cửa
    sổ live bằng Chrome với cờ `--autoplay-policy=no-user-gesture-required`.
  - **Các chuyến xe:** xe chính + xe tăng cường đang chạy — «📺 Chiếu» cho màn hình live theo xe đó (góc máy ở phần Camera),
    «⏭ Tới điểm kế», gọi thêm xe tăng cường cho làn có người chờ, công tắc tự gọi khi làn đủ 24 người.
  - Thiết lập lưu ở `storage/db/config/xe_tet.json` (giữ qua restart / deploy), mọi màn hình live đổi theo ngay.
- Sửa overlay có hot reload: `cd xe_tet/overlay && npm run dev` → http://127.0.0.1:5173 (server Python vẫn phải chạy).
- Test: `/home/vu/venv-xetet/bin/python -m pytest xe_tet/tests -q` (không gọi mạng, TikTok dùng client giả). Test trên trình duyệt thật (server phải đang chạy, sẽ reset game):
  `xe_tet/e2e/ux_scenarios.py` (11 tình huống + vùng TikTok che), `control_panel.py` (bảng điều khiển → overlay),
  `flicker.py` (đếm màn đen / đổi cảnh).
- Rà soát BA / BRD / thuật toán / SA: `xe_tet/REVIEW.md`.
- **Tuyến xe thật** (`docs/BRD-tuyen-xe.md`): km, làn theo hướng, độ quanh co, đèo đọc từ `server/game/data/routes.json`
  (game không gọi mạng). Dựng lại (có mạng, OSRM ≤ 1 lượt / giây): `venv/bin/python -m xe_tet.tools.build_routes`; phản hồi
  OSRM lưu ở `tools/osrm_cache.json.gz` (không commit) nên chỉnh thuật toán làn / độ quanh co rồi chạy lại là chạy offline.
  Tuyến OSRM vòng qua Lào / Campuchia (79 / 310 tuyến Nam ↔ Bắc) tự dẫn lại qua QL1; đèo có hầm mà đường thẳng → «Hầm …».

## 1. Công nghệ

```
TikTok LIVE ──(TikTokLive, Python)──► server/ ──WebSocket──► overlay/ (Three.js, 1080×1920)
                                         │                        ▲
                                         ├─ SQLite (vé, chuyến)   │ TikTok LIVE Studio
                                         ├─ VieNeu TTS :8790      │ quay cửa sổ overlay
                                         └─ /control (bảng điều khiển, sự kiện thử)
```

| Phần | Chọn | Vì sao |
|---|---|---|
| Đọc sự kiện live | `TikTokLive` 7.x (Python, không chính thức) | TikTok không có API đọc comment live. Cần khoá sign server (Euler Stream, có gói miễn phí giới hạn lượt). |
| Server | Python 3.12 + FastAPI + uvicorn | Cùng ngôn ngữ toolsauto; gọi thẳng server VieNeu đang có. |
| Luật chơi | Máy trạng thái thuần Python (`game/`) | Test được không cần TikTok, không cần trình duyệt. |
| Lưu dữ liệu | SQLite trong `storage/` của thư mục này | Vé khứ hồi, số chuyến, bảng tỉnh qua nhiều ngày. |
| Màn hình live | Vite 5 + TypeScript + **Three.js 0.187** | Cảnh 3D low-poly: xe chạy trên đường, cắt vào trong xe, trạm dừng chân. |
| Chữ trong cảnh 3D | `CSS2DRenderer` của Three.js + font Be Vietnam Pro | Tên khách trên giường, biển trạm: chữ HTML nên dấu tiếng Việt sắc nét, không cần nạp font vào WebGL. |
| Chữ giao diện | HTML/CSS đè lên canvas | Vé mới, bảng tỉnh, đếm ngược: sắc nét, dễ sửa. |
| Mô hình 3D | Tự dựng bằng code (hình khối low-poly) + gói CC0 (Kenney, Quaternius) | Không vướng bản quyền; nhẹ cho GTX 1650 vừa render vừa phát live. |
| Giọng loa | VieNeu TTS (`127.0.0.1:8790`), tắt thì im lặng | Lơ xe gọi khách, báo trạm, đọc tên xuống xe. |
| Lên sóng | TikTok LIVE Studio → nguồn cửa sổ / trình duyệt | Không cần OBS. |

Mục tiêu hiệu năng: 30 khung hình/giây ở 1080×1920 trên i5-10300H + GTX 1650 trong lúc LIVE Studio đang phát.

Overlay chia file theo việc: `art.ts` (vật liệu, trời, người, xe + giảm xóc), `props.ts` (đồ vật dùng lại), `sets.ts`
(bến / trạm / đầu ngõ + điểm mốc), `road.ts` (mặt đường, ổ gà, trụ điện, cột cây số), `landscape.ts` (cảnh 4 vùng),
`weather.ts` (mưa), `effects.ts` (pháo hoa, bụi, khói), `scene.ts` (điều phối cảnh, camera, người đi lại, chất lượng),
`hud.ts` (lớp chữ), `main.ts` (kết nối, vòng vẽ).

Server chỉ gửi **trạng thái + sự kiện đã chuẩn hoá** cho overlay; overlay không tự quyết luật chơi.
Nhờ vậy bảng điều khiển gửi sự kiện thử đi đúng đường như sự kiện TikTok thật.

## 2. Một chuyến xe (12–18 phút; giờ cao điểm 6–9 phút)

**Giờ cao điểm** (hàng chờ ≥ 1 xe): chặng còn 10–20 s, 1 trạm dừng 45 s — tính lại mỗi chặng nên hàng chờ dài lên giữa
chuyến thì xe chạy nhanh lên ngay; màn hình có thẻ «⚡ Cao điểm». Vé xếp hàng ghi «khoảng N phút nữa» (ước theo phần còn
lại của chuyến đang chạy + trung bình trượt độ dài các chuyến trước).

```
BẾN XE ─► CHẠY ─► TRẠM DỪNG CHÂN (90 s) ─► CHẠY ─► THẢ KHÁCH ─► CHẠY ─► … ─► HẾT CHUYẾN
  ▲  đón 24 khách                                       đầu ngõ, người nhà chờ        │
  └─────────────────────────────── xe sau đã đón khách sẵn ở bến ◄────────────────────┘
```

- **Bến xe:** xe 24 giường (limousine 2 tầng × 12 phòng). Xuất bến khi **đủ 24 khách** hoặc hết 3 phút
  (ít nhất 1 khách). Đông hơn 24 thì xếp vào **xe sau** đang đón ở bến (khung nhỏ góc màn hình).
- **Tuyến:** chỉ ghé tỉnh có khách, xếp theo vĩ độ Nam → Bắc. Bến xuất phát: «Bến xe Thành Phố».
- **Chạy:** tốc độ nền luôn có (không có tim xe vẫn chạy), tim cộng thêm. Ngày / đêm, mưa phùn miền Bắc,
  nắng miền Nam theo đoạn đường. Chuyến dài quá 18 phút thì tự tăng tốc nền.
- **Trạm dừng chân:** 1 trạm mỗi chuyến (chuyến dài > 5 tỉnh thì 2 trạm). Xem mục 4.
- **Thả khách:** cảnh đầu ngõ có mái nhà, cành đào/mai, người nhà đứng chờ. Loa «Tới Nghệ An rồi bà con ơi»,
  đọc tối đa 8 tên, còn lại «và 9 người con Nghệ An khác», mỗi người một câu chúc Tết riêng trên màn hình.
- **Hết chuyến:** bảng «Tỉnh về đông nhất», người thả tim nhiều nhất chuyến, rồi chuyển camera về bến.

Camera do admin chọn trên `/control`: ngoài xe (4 góc máy) hoặc **trong xe** (24 giường có tên khách — lúc mỗi người
thấy tên mình nằm trên giường). Không tự đổi góc.

## 3. Tương tác trên đường

| Sự kiện TikTok | Điều kiện | Trên màn hình |
|---|---|---|
| Vào phòng | — | Avatar ra **sân bến chờ**; dòng nhỏ «Minh Anh vừa ra bến» (gộp khi đông). |
| Comment tên tỉnh | Nhận tên cũ (63), tên mới (34), không dấu, viết tắt (`NA`, `sg`, `hcm`, `huế`), **đầu biển số** (`37`, `29`, `51`) | Vé «Minh Anh → Nghệ An · giường 7 tầng trên». Xe hiện tại đầy hoặc đã chạy → giữ chỗ xe sau. Đổi tỉnh: 1 lần / chuyến. |
| Comment `KHÔNG VỀ` (`ko ve`, `k về`, `o ve`…) | — | Avatar ở lại **phòng trọ** góc bến, câu an ủi riêng («Năm nay chưa về được thì gọi về nhà một cuộc nhé, Minh Anh»). |
| Comment khác | Đã có chỗ, qua lọc từ | Bong bóng chat trên giường / đầu avatar 5 s, cắt 40 ký tự. |
| Thả tim | — | Xe nhanh hơn, thanh «km tới điểm tiếp theo». Mốc 1.000 / 5.000 tim: «Cả xe tiếp lửa, bác tài nhấn ga!». Người nhiều tim nhất chuyến = **phụ xe danh dự**. |
| Chia sẻ | — | «Minh Anh vừa gọi người Nghệ An về» + ô «còn N chỗ» của xe nhấp nháy. |
| Follow | — | **Vé khứ hồi**: huy hiệu + đếm số chuyến đã đi (lưu qua nhiều ngày). |
| Tặng quà | **Cộng dồn trong chuyến** (10 hoa hồng = 10 xu); combo TikTok cộng từng lần bấm | Theo bậc, **luôn cố định, không quay ngẫu nhiên**; thông báo kèm «🎯 thêm X xu → bậc sau»; mỗi mốc 1.000 xu = thêm một lần cả xe chúc Tết: |
| | 1–9 xu (hoa hồng…) | Giường VIP hàng đầu, tên viền vàng. |
| | 10–99 xu | Pháo hoa khi xe thả khách ở quê người tặng. |
| | 100–999 xu | Xe dán băng rôn «Xe Tết của [tên]» + treo cành đào suốt chuyến. |
| | ≥ 1.000 xu | Cảnh riêng 20 s: xe dừng bên đồng lúa, cả xe chúc Tết đích danh người tặng. |

## 4. Trạm dừng chân (90 giây)

Lơ xe hô «Xe nghỉ 15 phút, bà con xuống ăn uống, vệ sinh nha!». Mọi người trong phòng (cả người chưa có vé)
đều comment được ở trạm.

| Comment | Trên màn hình |
|---|---|
| Món ăn: `PHỞ` `BÁNH MÌ` `CƠM` `BÚN` `MÌ` `TRÀ ĐÁ` `CÀ PHÊ` | Avatar ra quầy, bong bóng hình món; bảng «Món được gọi nhiều nhất trạm này». |
| `WC` / `ĐI VỆ SINH` | Avatar xếp **hàng nhà vệ sinh**, hàng càng dài càng vui; đồng hồ trên cửa. |
| `MUA QUÀ` | Xách túi đặc sản lên xe; khi thả khách: «Minh Anh mang quà về cho mẹ». |
| Tặng quà ở trạm | «Minh Anh **bao cả xe** trà đá!» — 24 cốc bay lên các giường. |
| 15 s cuối | Còi «Bíp bíp! Lên xe bà con ơi!»; ai còn trong hàng WC chạy hớt hải lên xe (chỉ hoạt hình vui, không gọi tên chê). |

## 5. Lịch mùa

| Thời gian | Chế độ |
|---|---|
| 15/12 → 30 Tết | Xe về quê, đếm ngược tới Tết |
| Mùng 1 → mùng 5 | Chúc Tết theo tỉnh: comment tỉnh nhận lời chúc năm mới, cảnh sân nhà ngày Tết |
| Mùng 6 → mùng 10 | Xe trở lại thành phố: chạy Bắc → Nam, cùng code |

## 5b. P2 — nối TikTok: học từ 2 repo cùng ngách (đọc 31/10)

`zane-tv/tiktok-live-temple-rpc` (Bun) và `kentjuno/chanh-dien-online` (Node) đều dùng `tiktok-live-connector` 2.x
(Node, không chính thức, ký qua Euler Stream gói miễn phí, không cookie / mật khẩu). Áp dụng cho P2:

| Việc | Cách làm | Nguồn |
|---|---|---|
| Kết nối | Ô «@username hoặc link live» trên `/control`, tự cắt `tiktok.com/@…`; trạng thái đang nối / đã nối / lỗi / mất kết nối + nhật ký | cả hai |
| Không phát lại tin cũ | `processInitialData = false` — nếu không, nối lại sẽ đặt vé trùng | kentjuno (zane để true: lỗi) |
| Định danh | Khoá người xem = `userId` (số, cố định); `uniqueId` đổi được nên chỉ để hiện; tên = `nickname` | cải tiến so với cả hai (cả hai dùng uniqueId) |
| Quà combo | Quà loại 1 gửi liên tục khi đang combo: theo dõi `groupId`, chỉ cộng phần tăng `repeatCount − lần trước` → phản hồi ngay từng lần bấm, không đếm trùng; dọn bộ nhớ > 500 nhóm | zane (kentjuno chờ `repeatEnd`: chậm hơn) |
| Giá trị quà | `diamondCount × số lần`, `enableExtendedGiftInfo` để có tên quà | cả hai |
| Follow / chia sẻ | Nghe cả `FOLLOW`, `SHARE` và `SOCIAL` (action 1 = follow, 3 = share) | zane |
| Số người xem thật | `ROOM_USER` → hiện + dùng cho nhịp chuyến (BA-1) | zane |
| Ảnh đại diện | `profilePicture.url[0]` → hiện trên giường / vé (rất mạnh cho cảm giác «được thấy») | cả hai |
| Mất kết nối | **Cả hai đều không tự nối lại** → mình phải làm: thử lại 5 s, 10 s, 20 s… tối đa 60 s; hết live thì dừng | bài học |
| Giọng đọc | Hàng đợi có trần (15 câu), bỏ câu trùng đang đọc, có timeout, xoá file cũ | cả hai |
| Bảo mật | Chỉ nghe 127.0.0.1 + kiểm Host (**đã làm 31/10**), overlay chỉ nghe không gửi lệnh | kentjuno |
| Hiệu năng | Vẽ tối đa 30 khung / giây (**đã làm 31/10**), tạm dừng khi tab ẩn | zane |

Không làm theo: zane mở server mọi địa chỉ + CORS mở (trang lạ điều khiển được) và **đưa tên 1.605 người xem thật lên repo
công khai** (`data/merit-state.json`); bật «giả lập đông người xem» khi live = tương tác giả.

Python hay Node cho P2: giữ server Python, nối TikTok bằng `TikTokLive` (Python, cùng hệ ký Euler); nếu thư viện Python
trục trặc thì chạy `tiktok-live-connector` 2.5.0 làm tiến trình phụ đẩy sự kiện vào `POST /api/event` — luật chơi không đổi.

## 6. Các bước làm

1. **P1 — chạy thử không cần TikTok:** luật chơi + cảnh Three.js hình khối (đường, xe, trạm, đầu ngõ)
   + `/control` gửi sự kiện thử.
2. **P2 — nối thật:** TikTokLive, SQLite, giọng VieNeu, lọc từ.
3. **P3 — làm đẹp:** mô hình xe / trạm / cảnh vùng miền, đầu ngõ theo vùng, chế độ chúc Tết / xe trở lại.

## 7. Cần anh chuẩn bị (từ P2)

- Tên tài khoản TikTok sẽ live, và tài khoản đã mở được TikTok LIVE Studio chưa.
- Khoá Euler Stream (đăng ký miễn phí) cho TikTokLive.

## 8. Lưu ý

- Không dùng tên / logo nhà xe thật; xe mang tên kênh.
- Sự cố trên đường chỉ là kẹt xe, mưa, đèo — **không có cảnh tai nạn** (mùa Tết nhạy cảm về an toàn giao thông).
