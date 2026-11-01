# Rà soát Xe Tết Sum Vầy — BRD · BA · thuật toán · SA (31/10/2026)

Phạm vi: code P1 trong `xe_tet/` (luật chơi, server, overlay, bảng điều khiển). Mỗi phát hiện đều đã kiểm chứng
bằng code chạy thật (script đo, fuzz, Playwright), không chỉ đọc. Trạng thái: **Đã sửa** (kèm test chặn tái phát),
**Cần anh quyết**, hoặc **P2/P3** (đã có trong kế hoạch).

## 1. BRD — yêu cầu nghiệp vụ (as-built)

**Mục tiêu kinh doanh:** phòng live 9:16 mùa Tết (15/12 → mùng 10), giữ người xem lâu, kéo comment / tim / quà / follow
bằng cảm xúc «về quê» và **được gọi tên**. Đo bằng: phút xem trung bình, tỉ lệ người xem có comment, quà / giờ, follow / giờ.

| Mã | Yêu cầu | Trạng thái |
|---|---|---|
| FR-1 | Comment tên tỉnh (63 tên cũ, không dấu, viết tắt, đầu biển số) → vé + giường trên xe 24 chỗ | Có |
| FR-2 | Xe đầy → người sau giữ chỗ xe kế tiếp | Có (năng lực chở xem BA-1) |
| FR-3 | «Không về» → phòng trọ + câu an ủi riêng | Có |
| FR-4 | Tim làm xe nhanh hơn, mốc tim, phụ xe danh dự | Có |
| FR-5 | Trạm dừng chân: gọi món, WC, mua quà, bao cả xe | Có |
| FR-6 | Thả khách: **gọi tên từng người** + lời chúc riêng | Có (đã sửa BA-2) |
| FR-7 | Quà 4 bậc, phần thưởng cố định, không ngẫu nhiên | Có (đã sửa BA-3, BA-4) |
| FR-8 | Admin điều khiển mọi thứ: camera, thời gian, hiển thị, câu lơ xe, băng rôn | Có |
| FR-9 | Đọc sự kiện TikTok thật | **Có** (TikTokLive 7, tự nối lại; thử thật 31/10: vào phòng ~350 người xem, 145 sự kiện / 40 s, 0 lỗi) |
| FR-10 | Lưu vé khứ hồi / số chuyến qua nhiều ngày | P2 (đang trong RAM) |
| NFR-1 | Chữ quan trọng không nằm dưới vùng TikTok che | Có (ước lượng vùng, cần thử máy thật) |
| NFR-2 | Không nội dung bậy / link / số điện thoại lên sóng | Có (đã sửa BA-6) |
| NFR-3 | Không tương tác giả khi live thật | Có cảnh báo trên `/control`; P2 tự khoá khi nối TikTok |
| NFR-4 | 30 khung hình / giây trên GTX 1650 khi đang phát | **Chưa đo trên GPU thật** |
| NFR-5 | Server không dừng vì 1 màn hình / 1 sự kiện lỗi | Có (đã sửa SA-1, SA-2) |
| KPI | Ghi số liệu (comment → vé, quà / chuyến, thời gian chờ) | **Thiếu** — đề xuất P2 |

## 2. BA — phát hiện nghiệp vụ

| Mã | Vấn đề | Bằng chứng | Mức | Trạng thái |
|---|---|---|---|---|
| BA-1 | **Năng lực chở thấp so với phòng đông.** 1 xe / vòng, khách về nhiều tỉnh thì vòng dài | Đo: 24 khách / 24 tỉnh = 15 phút / vòng (≈ 96 khách / giờ); 6 tỉnh ≈ 130; có 40 tim/s ≈ 150–210. Phòng 300 người hăng hái → người xếp hàng chờ hàng giờ, không thấy mình ở đâu | Cao | **Đã làm (anh duyệt 31/10)**: giờ cao điểm tự rút ngắn + giờ chờ trên vé |
| BA-2 | Thả khách chỉ đọc tên 8 người, còn lại «và N người» — trái lời hứa cốt lõi «được gọi tên» | 20 người xuống Nghệ An → 8 tên | Cao | **Đã sửa**: đọc tên tất cả, lật trang 6 người / 4 s |
| BA-3 | Quà băng rôn (≥ 100 xu) tặng lúc hết chuyến bị **mất** (xe mới không có băng rôn) | Thử: tặng 199 xu lúc FINISH → xe sau `banner=None` | Cao | **Đã sửa**: dán cho xe sau |
| BA-4 | Quà 1000 xu lúc đón khách / ở trạm phải chờ tới 3 phút mới có cảnh chúc Tết | Chỉ chen được lúc đang chạy | Vừa | **Đã sửa**: chen ngay ở đón khách / chạy / trạm, xong quay lại đúng pha + thời gian còn lại; vẫn lên xe được trong lúc chúc |
| BA-5 | Thông báo quyền lợi quà hứa sai: «giường VIP hàng đầu» (không đổi chỗ), «pháo hoa khi về quê» cho người **chưa có vé** | Đọc luật + thử | Vừa | **Đã sửa**: lời hứa theo việc có vé hay chưa («VIP khi lên xe — comment tên tỉnh nha») |
| BA-6 | Tên TikTok + bong bóng chat hiện thẳng lên live: chửi thề, link, số điện thoại | Không có lọc | Cao | **Đã sửa**: tên che từ bậy, chat có bậy / link / SĐT thì không hiện; lọc trên chữ có dấu nên «đi», «các», «lớn» không bị nhầm |
| BA-7 | Tán gẫu bị hiểu thành lệnh: «Hà Nội lạnh quá», «chị Huệ ơi» → đặt vé; «mẹ chưa về à», «ai ở lại không» → **huỷ vé người đang ngồi xe** | Thử parser | Cao | **Đã sửa**: chỉ nhận khi phần còn lại toàn từ đệm («về», «thôi», «nha»…); 22 câu mẫu đúng |
| BA-8 | Giả lập phòng đông bật khi live thật = tương tác giả, rủi ro bị TikTok phạt | Nút nằm cạnh nút thật | Vừa | Đã thêm cảnh báo; P2: tự khoá khi đang nối TikTok |
| BA-9 | Quà nhỏ không cộng dồn: 10 hoa hồng (10 xu) vẫn chỉ bậc 1 | Bậc tính theo từng lần tặng | Thấp | **Đã làm (anh duyệt 31/10)**: cộng dồn trong chuyến + gợi ý «thêm X xu → bậc sau» |
| BA-10 | Người «không về» không còn việc gì để làm trong phiên | Chỉ có câu an ủi | Thấp | P3: «nhắn một câu về nhà» hiện ở ga quê |
| BA-11 | Đếm ngược Tết theo giờ máy chủ (UTC) → lệch ngày từ 0h–7h sáng | `date` máy chủ = UTC | Thấp | **Đã sửa**: theo giờ Việt Nam |

## 3. Thuật toán & logic

| Thuật toán | Cách làm | Nhận xét |
|---|---|---|
| Hiểu comment | Bỏ dấu → so cụm tên tỉnh dài nhất trước; mã ngắn / biển số chỉ khớp cả câu; mới thêm luật «phần còn lại toàn từ đệm» | Đúng 22/22 câu mẫu. Còn rủi ro: tên người trùng tên tỉnh nói **một mình** («Huệ», «Hà Giang») vẫn thành đặt vé — chấp nhận được, hậu quả nhẹ (đổi được 1 lần) |
| Tuyến | ~~Xếp theo vĩ độ Nam → Bắc~~ → từ PLAN-122/123: tuyến thật OSRM, ghé theo đường (`Network.plan`), xem `docs/BRD-tuyen-xe.md` BR-3 | Mô hình vĩ độ đã bỏ |
| Thời gian chặng | ~~480 s chia đều~~ → tỉ lệ km thật, cả chuyến chạy đường ≤ ~4 phút (BR-7) | Gốc BA-1 đã hết |
| Tốc độ / tim | Tăng tốc = 0,01 / tim, tối đa ×3, giảm nửa sau 6 s | Ổn. Phòng rất đông thì luôn ở ×3 → tim mất cảm giác «có tác dụng»; P3 có thể hiện thanh «nhiên liệu» |
| Hàng chờ | Danh sách FIFO, số xe = vị trí / 24 | Đã sửa số xe báo sai khi người trong hàng đổi tỉnh |
| Quà | Bậc theo giá trị một lần tặng; cảnh chúc Tết xếp hàng | Đã sửa BA-3/4/5. P2: TikTok gửi quà theo combo → chỉ tính khi hết combo, nhân số lần |
| Bất biến | Không ai vừa ngồi xe vừa trong hàng chờ; ≤ 24 người / xe; không trùng ghế | Fuzz 30 × 20.000 bước (có tạm dừng, ±30 s, qua pha): không vi phạm |
| Chọn làn (01/11) | Ai chờ trước đi trước (BRD BR-4) — so 5 luật bằng mô phỏng 4 giờ trên dữ liệu thật | Thắng cả tỉ lệ được lên xe lẫn làn thiệt nhất |

## 4. SA — kiến trúc

```
TikTok (P2) ─┐
/control ────┼─► FastAPI (1 tiến trình) ─ Engine (RAM) ─► WebSocket 5 lần/s ─► overlay Three.js ─► LIVE Studio
giả lập ─────┘        └─ storage/db/config/xe_tet.json (thiết lập admin)
```

| Mã | Phát hiện | Trạng thái |
|---|---|---|
| SA-1 | Vòng game chết khi màn hình ngắt giữa lúc gửi | Đã sửa trước (lặp trên bản sao, vòng tự chạy lại có log) |
| SA-2 | Một màn hình nhận chậm làm **cả vòng game đứng** (gửi tuần tự, không giới hạn thời gian) | **Đã sửa**: mỗi lần gửi tối đa 1 s, chậm hơn thì bỏ màn đó |
| SA-3 | Dữ liệu bẩn (`count: "abc"`) → lỗi 500 | **Đã sửa**: ép kiểu an toàn, sai thì 400 |
| SA-4 | Trường `kind` của sự kiện ghi đè khung tin → overlay bỏ sự kiện trạm dừng | Đã sửa trước + test |
| SA-5 | Không có xác thực cho `/control`, `/api/*` | **Đã làm (anh duyệt 31/10)**: `XE_TET_TOKEN` tuỳ chọn; mở Host ra mạng mà thiếu mã thì log cảnh báo. Kiểm Host chống DNS rebinding |
| SA-6 | Trạng thái game chỉ trong RAM: restart giữa live mất vé, hàng chờ | P2 (SQLite) |
| SA-7 | Chưa chạy dưới PM2: sập là dừng | P2 (thêm `XeTet` vào ecosystem) |
| SA-8 | `overlay/dist` không nằm trong git → sau deploy phải `npm run build` | Đã ghi trong README |
| SA-9 | Pháo hoa không giới hạn khi quà dồn dập | **Đã sửa**: tối đa 14 chùm cùng lúc |
| SA-10 | Thư viện TikTok không chính thức (P2): có thể đổi / chặn bất kỳ lúc nào | Rủi ro chấp nhận; cần phương án dự phòng (vẫn live được bằng `/control`) |
| SA-11 | Test trình duyệt nằm ngoài repo | **Đã sửa**: `xe_tet/e2e/` |

## 5. Cần anh quyết — **anh đã duyệt cả 3 theo đề xuất (31/10), đã làm**

1. **BA-1 — tăng năng lực chở.** Em đề xuất **(b)** trước, rẻ và không đổi màn hình:
   - (a) Đoàn 2–3 xe chạy song song: gấp 2–3 lần, nhưng màn hình rối hơn, camera phải theo nhiều xe.
   - **(b) Tự rút ngắn khi hàng chờ dài**: hàng chờ > 24 thì chặng 10 s, 1 trạm 45 s, đón khách 60 s → ước gấp ~2 lần;
     kèm báo «Xe số 5 · khoảng 25 phút nữa» trên vé để người chờ biết.
   - (c) Giữ nguyên.
2. **BA-9 — cộng dồn quà trong một chuyến** để tính bậc (10 hoa hồng = bậc 2)? Em đề xuất **có**: phổ biến ở game live, khuyến khích tặng tiếp.
3. **SA-5 — mật khẩu cho `/control`** khi cần mở ra mạng ngoài: thêm khoá trong `.env`, bảng điều khiển gửi kèm.

## 6. Bằng chứng

- `pytest xe_tet/tests`: 33 test (thêm 10 test cho các lỗi trong rà soát này).
- Fuzz luật chơi 30 × 20.000 bước kèm kiểm bất biến: sạch.
- `xe_tet/e2e/ux_scenarios.py`: 11 tình huống, 0 lỗi JS, 0 phần tử bị vùng TikTok che; `control_panel.py`: 26/26.

---

# Rà soát lần 2 (31/10/2026, sau khi nối TikTok thật)

Trọng tâm: phần mới (cầu nối TikTok, giờ cao điểm, giờ chờ, cộng dồn quà, mã điều khiển) và hành vi khi gặp **dữ liệu live
thật** (combo quà, spam follow / share, người rời phòng, mạng chập chờn, server khởi động lại). Mỗi điểm đều dựng lại tình
huống bằng code trước khi sửa.

## BA

| Mã | Vấn đề | Bằng chứng | Mức | Trạng thái |
|---|---|---|---|---|
| BA2-1 | **Combo quà spam màn hình**: TikTok gửi một sự kiện cho mỗi lần bấm combo | Combo 30 hoa hồng ở trạm → 30 thông báo, 30 «bao cả xe», 30 câu lơ xe, 21 lần pháo hoa | Cao | **Đã sửa**: thông báo quà của một người gộp thành một thẻ tự cập nhật; pháo hoa chỉ khi **lên bậc**; «bao cả xe» một lần / người / trạm. Đo lại: 1 «bao cả xe», 1 câu lơ xe, 2 lần pháo hoa |
| BA2-2 | Spam follow / chia sẻ để được hiện tên | 5 follow → 5 thông báo; 10 chia sẻ → 10 | Vừa | **Đã sửa**: cảm ơn follow một lần / người; chia sẻ tối đa 1 lần / phút / người |
| BA2-3 | **Vé ma**: TikTok không báo ai rời phòng → người đã đi vẫn giữ chỗ trong hàng chờ, giờ cao điểm càng phí | Đọc luật + thư viện (không có sự kiện rời phòng) | Vừa | **Đã sửa**: trong hàng chờ mà im lặng (không comment / tim / quà) quá 30 phút thì bỏ vé lúc tới lượt, nhường người đang xem. Vào phòng không tính là tương tác |
| BA2-4 | Năng lực chở sau khi có giờ cao điểm | Đo: 24 khách / 24 tỉnh — thường 14,8 phút / vòng (97 khách / giờ), cao điểm 8,1 phút (178 khách / giờ) | — | Đạt mục tiêu ~×2. Phòng > 200 người tích cực vẫn phải chờ — nếu cần thêm thì làm đoàn 2 xe (P3) |
| BA2-5 | Ảnh đại diện đã lấy về nhưng chưa hiện | `avatar` nằm trong dữ liệu người xem | Thấp | P3 (hiện trên giường / vé) |
| BA2-6 | Chưa ghi số liệu để đánh giá kinh doanh (comment → vé, quà / chuyến, thời gian chờ) | Không có bảng lưu | Vừa | P2 cùng SQLite |

## SA

| Mã | Vấn đề | Bằng chứng | Mức | Trạng thái |
|---|---|---|---|---|
| SA2-1 | **Kết nối vào-rớt liên tục → thử lại mỗi 5 s mãi**, đốt lượt ký Euler (gói miễn phí giới hạn) | Client giả vào rồi rớt ngay: chờ 5, 5, 5, 5… | Cao | **Đã sửa**: chỉ về bậc chờ đầu khi kết nối giữ được ≥ 60 s → 5, 10, 20, 40, 60 s |
| SA2-2 | Lỡ mất tín hiệu «live kết thúc» → hỏi TikTok mỗi 30 s mãi | Đọc vòng nối lại | Thấp | **Đã sửa**: đã từng vào live mà «chưa live» suốt 10 phút → coi như kết thúc, dừng |
| SA2-3 | **Server khởi động lại giữa live mất kết nối TikTok** (PM2 bật lại nhưng phải có người bấm nối) | Kết nối chỉ nằm trong RAM | Cao | **Đã sửa**: đang nối thì lưu `tiktok_auto`; server bật lên tự nối lại; live hết / sai tài khoản / admin bấm ngắt thì thôi |
| SA2-4 | Mã điều khiển lọt vào log (`?token=…` trong dòng log truy cập) và lịch sử trình duyệt | Mặc định uvicorn ghi đường dẫn kèm query | Vừa | **Đã sửa**: tắt log truy cập (lỗi vẫn ghi); trang điều khiển đọc mã rồi xoá khỏi thanh địa chỉ, giữ trong phiên tab; API chỉ gửi mã qua header |
| SA2-5 | Script e2e reset game + bật giả lập → lỡ chạy lúc live là xoá vé khán giả | Đọc script | Vừa | **Đã sửa**: đang nối TikTok thì script từ chối chạy |
| SA2-6 | Thư viện TikTokLive cần `websockets` 17 ≠ 16 của venv chung | `pip` | — | Đã xử lý: venv riêng `/home/vu/venv-xetet` + `xe_tet/requirements.txt` |
| SA2-7 | **Chưa chạy dưới PM2** — sập là dừng, log nằm thư mục tạm | Đang chạy nền bằng tay | Cao | **Cần anh quyết**: thêm app vào ecosystem PM2 chung của toolsauto |
| SA2-8 | Trạng thái game chỉ trong RAM — khởi động lại giữa live mất vé / hàng chờ (kết nối thì đã tự nối lại) | — | Vừa | P2 (SQLite) |
| SA2-9 | Hạn mức Euler gói miễn phí chưa rõ con số | Thư viện chỉ báo lỗi khi chạm trần | Vừa | Theo dõi khi live thật; trạng thái «Euler giới hạn lượt ký» đã hiện trên `/control`; có `SIGN_API_KEY` khi cần |

## Bằng chứng

- 55 test (thêm 7: combo không spam, follow / chia sẻ, vé ma, vào-rớt / ổn định, live tắt lâu, tự nối lại khi khởi động,
  cờ tự nối theo kết nối / ngắt); chạy được cả venv chung và venv riêng.
- Fuzz 20 × 20.000 bước có kiểm bất biến: sạch. e2e: 11 tình huống, 26/26 điều khiển; 20 lần tặng liên tiếp → 1 thẻ thông báo.
