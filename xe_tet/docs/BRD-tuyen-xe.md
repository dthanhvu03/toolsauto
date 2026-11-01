# BRD — Tuyến xe thật: bến đi, hướng xe, km thật, đường quanh co

Ngày 31/10/2026 · Người viết: Claude Code · Trạng thái: **anh đã quyết mục 8 (31/10) — đã làm, xem PLAN-122 + mục 9**

## 1. Vấn đề

Luật chơi hiện tại (PLAN-120) dùng mô hình đơn giản, lộ ra 3 chỗ sai so với thực tế:

| # | Hiện tại | Vì sao sai |
|---|---|---|
| 1 | Một xe chở mọi hướng; điểm dừng xếp theo vĩ độ Nam → Bắc từ «Bến xe Thành Phố» trừu tượng | Xe ở **Bến xe Liên tỉnh Đà Lạt** đang đi hướng Bắc mà có người comment **Cà Mau** → xe phải vòng xuống Cà Mau rồi mới ra Bắc. Không nhà xe nào chạy như vậy |
| 2 | Km giả: mỗi chặng 80 km | Đà Lạt → Cà Mau thật **592 km**, Đà Lạt → Hà Nội **1.401 km** (OSRM). Người xem quê ở đâu đều biết đường về nhà dài bao xa — số giả làm mất cảm giác thật |
| 3 | Đường thẳng, phẳng suốt | Thiếu đèo dốc (Prenn, Bảo Lộc, Hải Vân…), khúc quanh co, đồng bằng thẳng tắp — đúng thứ người đi xe Tết nhớ nhất |

## 2. Khái niệm

| Thuật ngữ | Nghĩa |
|---|---|
| **Bến đi** | Bến xe nơi phòng live «đặt» xe — admin chọn (mặc định đề xuất ở mục 8). Ví dụ Bến xe Liên tỉnh Đà Lạt |
| **Hướng (tuyến)** | Nhóm điểm đến cùng một ngả đường từ bến đi: từ Đà Lạt có **hướng Bắc** (ra Nha Trang theo QL1A ra Hà Nội) và **hướng Nam** (xuống Bảo Lộc, TP.HCM, miền Tây) |
| **Chuyến** | Một xe 24 giường chạy một hướng, dừng các tỉnh có khách theo thứ tự km tăng dần |
| **Bến đến** | Bến xe chính của tỉnh khách về (tên thật nếu đã xác minh, không thì «Bến xe {tỉnh}») |
| **Km thật** | Quãng đường bộ từ bến đi tới bến đến (OSRM), tính sẵn một lần |
| **Tỉnh trùng bến đi** | Khách comment đúng tỉnh của bến đi (ở Đà Lạt comment «Lâm Đồng») |

## 3. Câu hỏi của anh: xe ở Đà Lạt đang hướng Bắc, có người comment Cà Mau

**Trả lời đề xuất:** khách đó **không lên xe đang đón** (xe hướng Bắc), mà **giữ chỗ cho chuyến hướng Nam kế tiếp**,
và thấy ngay điều đó trên màn hình:

- Thẻ lớn: «🎫 Út Ráng giữ chỗ xe số 3 · Đà Lạt → Cà Mau (592 km) · khoảng 12 phút nữa».
- Bến có **2 làn**: làn «⬆ MIỀN BẮC» (xe đang đón) và làn «⬇ MIỀN NAM» với bảng đếm «7/24 đã giữ chỗ». Người hướng Nam
  thấy hàng của mình đang dài ra → có lý do ở lại chờ và rủ người cùng quê.
- Hết chuyến hướng Bắc thì chuyến kế tiếp chạy **hướng của người chờ lâu nhất** (luật BR-4, sửa 01/11), nên người Cà Mau
  không bị bỏ quên; tên + thứ tự của họ luôn hiện ở bảng «⏳ Chờ xe sau», lời kêu gọi báo «Xe kế tiếp: ⬇ … · ~N phút».

## 4. Các phương án

| | Phương án | Ưu | Nhược | Kết luận |
|---|---|---|---|---|
| A | Giữ một xe chở mọi hướng (hiện tại) | Đơn giản | Sai thực tế (mục 1); km vô nghĩa | Loại |
| **B** | **Bến có nhiều làn theo hướng; mỗi lần chỉ một xe xuất bến; hướng xuất bến chọn theo nhu cầu** | Đúng thực tế, giải thích được với người xem, km thật có nghĩa, tạo «hàng chờ» kéo tương tác | Mỗi xe đầy chậm hơn (chia 2 hướng) → cần giờ cao điểm theo từng hướng | **Đề xuất** |
| C | Hướng xe chọn theo số đông lúc xuất bến, ai lệch hướng xuống xe sau | Ít thay đổi giao diện | Người đã có ghế bị «đẩy» xuống lúc xuất bến → ức chế; khó giải thích | Không chọn |

## 5. Luật nghiệp vụ (phương án B)

- **BR-1 Phân hướng:** mỗi tỉnh thuộc đúng một hướng tính từ bến đi, dựa trên ngả đường thật (đoạn đầu lộ trình OSRM từ bến
  đi tới tỉnh đó), không dựa vĩ độ. Ví dụ từ Đà Lạt: Ninh Thuận / Khánh Hòa thuộc hướng Bắc (ra QL1A), Bình Thuận / Đồng Nai
  thuộc hướng Nam.
- **BR-2 Lên xe:** comment tỉnh cùng hướng xe đang đón + còn ghế → lên xe ngay. Khác hướng → giữ chỗ chuyến kế tiếp của
  hướng đó (vé ghi số xe, hướng, km, ước giờ chờ). Cùng hướng nhưng xe đầy → chuyến kế tiếp cùng hướng.
- **BR-3 Thứ tự dừng (sửa 01/11):** xe luôn ghé tỉnh gần vị trí xe nhất theo đường thật; tỉnh rẽ nhánh khỏi trục thì
  xe chạy về chỗ rẽ rồi vào nhánh, km xe chạy tính đủ (`Network.plan`, km chung đường từng cặp tỉnh trong `routes.json`).
  Vé / thả khách vẫn ghi km tuyến của khách (bến đi → tỉnh). Trạm nghỉ đặt ở tỉnh xe đang đi qua, bán đặc sản tỉnh đó;
  chuyến < 150 km không ghé trạm; > 900 km nghỉ 2 trạm chỉ khi không ai chờ xe sau.
- **BR-4 Chọn hướng xuất bến kế tiếp (sửa 01/11):** **ai chờ trước đi trước** — xe chạy làn của vé chờ cũ nhất. Mô phỏng
  4 giờ (TP.HCM, 1 comment / 20 s): 82 % người được lên xe trong 30 phút, làn thiệt nhất 78 % (luật cũ «đếm vé + 8 × bỏ
  qua» chỉ 67 %, làn nhỏ có lúc 24 %). Hết giờ đón mà xe trống → đổi sang làn có người chờ.
- **BR-5 Tỉnh trùng bến đi:** không lên xe; trả lời vui «Ở ngay Lâm Đồng rồi, đi bộ về nha!» và tính như đã về quê (có tên trên
  bảng tỉnh). Không mất lượt đổi tỉnh.
- **BR-6 Km hiển thị:** vé («Đà Lạt → Cà Mau · 592 km»), bảng tuyến («Tới Cần Thơ · còn 41 km»), cột cây số
  («CÀ MAU 592»), băng rôn thả khách («Đã đi 592 km về tới Cà Mau!»), tổng km nhà xe đã chở trong phiên.
- **BR-7 Nén thời gian (sửa 01/11):** phần chạy đường của một chuyến tối đa ~4 phút (cao điểm 2,5 phút), tối thiểu 3 km / giây;
  km hiển thị vẫn thật, thả khách ghi «~26 giờ xe» cho chân thật. Giờ đón tỉ lệ số giường còn trống (xe đã kín người chờ lên
  sẵn thì không bắt đợi đủ 3 phút). Lý do: một xe 24 giường chở ~110 khách / giờ, người xem TikTok ở lại vài phút.
- **BR-8 Đổi bến đi:** admin chọn trên `/control`; chỉ đổi được khi không có chuyến đang chạy và không ai đang giữ chỗ
  (tránh vé sai hướng).
- **BR-9 Giờ cao điểm, cộng dồn quà, vé hết hạn:** giữ nguyên, tính **theo từng hướng** (cao điểm = làn của xe còn ≥ 24
  người chờ). Vé ma (rời phòng > 30 phút) bị bỏ trước khi chọn làn / tính cao điểm / đếm số chờ.
- **BR-11 Xe tăng cường (thêm 01/11, PLAN-125):** làn đủ 24 người chờ → xe tăng cường tự chạy (tối đa 4 xe cùng lúc,
  admin tắt được); người đang chờ tặng đạt 100 xu (bậc băng rôn) → xe tăng cường chạy ngay làn của họ, họ lên trước, tên
  trên xe (tối đa 6 xe kể cả xe do quà / admin gọi). Xe chạy ngầm theo tuyến thật, tới nơi đọc tên (gom ~6 giây một băng rôn);
  admin chọn xe nào lên màn hình. Lý do: một xe 24 giường chở ~110–220 khách / giờ; có xe tăng cường, phòng 1 comment / 6 s
  lên xe trong 30 phút 40 % → 98 %.
- **BR-10 Đèo hay hầm (thêm 01/11):** đo độ quanh co ±2 km quanh đỉnh đèo trên lộ trình thật: hầm / đường tránh 0–34 °/km,
  đường đèo 61–240. Thẳng + đèo có hầm (Hải Vân, Đèo Cả, Cổ Mã, Cù Mông, Tam Điệp) → «🚇 Hầm …», đường thẳng phẳng; quanh co
  → «⛰ Đèo …» có dốc. Riêng Đèo Ngang: có hầm (2018) nhưng dữ liệu bản đồ dẫn xe qua đỉnh → giữ là đèo theo dữ liệu.

## 6. Dữ liệu

| Dữ liệu | Nguồn | Cách làm | Rủi ro |
|---|---|---|---|
| Km đường bộ bến đi → 63 tỉnh | OSRM (dữ liệu OpenStreetMap). Đã thử: Đà Lạt → Cà Mau 592 km, → Hà Nội 1.401 km | Tính **một lần** cho các bến đi cho phép (≈ 6 bến × 63 tỉnh ≈ 380 lượt, 1 lượt / giây), lưu JSON trong repo; game không gọi mạng | Giờ chạy OSRM lạc quan (18,8 giờ so với ~26 giờ xe khách thật) → chỉ dùng km, giờ tự tính theo tốc độ xe khách |
| Hướng của từng tỉnh | Hình học lộ trình OSRM (đoạn 100–150 km đầu) | Gom cụm theo ngả rẽ đầu tiên | Vài tỉnh giáp ranh cần chỉnh tay (bảng ghi đè) |
| Tên bến xe 63 tỉnh | Bến lớn tra tay (Giáp Bát, Miền Đông mới, Liên tỉnh Đà Lạt, Trung tâm Đà Nẵng, Bắc Vinh, Phía Bắc Huế, Trung tâm Cần Thơ, Cà Mau…); còn lại «Bến xe {tỉnh}» | Bảng tay trong repo, cột «đã xác minh» | Sáp nhập tỉnh 2025 đổi tên đơn vị hành chính, tên bến thường giữ theo thành phố |
| Đoạn quanh co / đèo / đồng bằng | Hình học lộ trình OSRM (độ cong thật) + danh sách đèo nổi tiếng (Prenn, Bảo Lộc, Ngoạn Mục, Cả, Cù Mông, Hải Vân, Ngang…) | Mỗi chặng lưu «hồ sơ địa hình»: thẳng / uốn nhẹ / quanh co / đèo dốc theo km | Không có độ cao trong OSRM → dốc theo danh sách đèo + vùng (Tây Nguyên, Tây Bắc), không đo thật |

## 7. Hình: đường quanh co, đèo dốc, đồng bằng

- Kỹ thuật **«thế giới uốn cong»**: xe vẫn đứng yên giữa màn hình, đoạn đường phía trước được uốn sang trái / phải và lên /
  xuống ngay trong shader (mọi vật ven đường uốn theo) → thấy đường lượn vào khúc cua, leo dốc, đổ đèo mà không phải dựng
  đường cong thật.
- Hồ sơ địa hình theo km điều khiển độ uốn: **đồng bằng** (miền Tây, đồng bằng Bắc Bộ) thẳng tắp + ruộng hai bên;
  **ven biển** uốn nhẹ; **đèo** (Hải Vân, Prenn…) cua gắt liên tục + dốc + biển báo «ĐÈO HẢI VÂN», xe nghiêng theo cua,
  chúi khi đổ dốc; **cao nguyên** đồi lượn sóng.
- Khi tới bến / trạm / đầu ngõ thì đường duỗi thẳng (bối cảnh không bị uốn).

## 8. Cần anh quyết

1. **Bến đi mặc định:** Bến xe Liên tỉnh Đà Lạt (như ảnh anh dùng) hay bến lớn nơi người đi làm xa về quê nhiều nhất
   (Miền Đông mới TP.HCM / Giáp Bát Hà Nội)? Em đề xuất **cho admin chọn, mặc định TP.HCM (Miền Đông mới)**: phần lớn người
   xem «về quê ăn Tết» đi từ TP.HCM / Bình Dương / Đồng Nai; Đà Lạt chỉ hợp nếu kênh của anh gắn với Đà Lạt.
2. **Phương án B** (bến nhiều làn theo hướng, xe xen kẽ theo nhu cầu) — đồng ý?
3. **Cho em gọi OSRM** (dịch vụ công khai, ≈ 380 lượt, 1 lượt / giây, một lần) để dựng bảng km + hướng + độ quanh co thật
   lưu vào repo?
4. Thứ tự làm: (R1) dữ liệu km / hướng / bến → (R2) luật chơi theo hướng + km thật → (R3) bến 2 làn + km trên màn hình →
   (R4) đường quanh co / đèo / đồng bằng.

## 9. Kết quả dựng dữ liệu (31/10)

- Anh chốt: mặc định **Miền Đông mới**, **phương án B**, **cho gọi OSRM**.
- OSRM chỉ tìm đường nhanh nhất, không biết xe khách không qua biên giới: **79 / 310 tuyến** Nam ↔ Bắc vòng qua
  Campuchia – Lào (Cần Thơ → Điện Biên qua cả Thái Lan; TP.HCM → Hà Nội chỉ còn 1.493 km, mất đèo Hải Vân / Ngang).
  Cách nhận: điểm nào trên lộ trình xa mọi tỉnh lỵ > 130 km là ở nước ngoài (đường trong nước xa nhất ~90 km — đường Hồ
  Chí Minh qua Quảng Nam). Tuyến đó dẫn lại qua các điểm QL1 nằm giữa hai đầu; sau dựng lại còn 0 tuyến ra nước ngoài.
  TP.HCM → Hà Nội **1.676 km**, qua Cổ Mã, Cả, Cù Mông, Hải Vân, Ngang, Tam Điệp.
- Làn: tỉnh nào chung đường với một trục ≥ 70 % quãng (tối thiểu 150 km) thì chung làn; làn < 3 tỉnh gộp vào làn chung
  đường dài nhất; tên làn ưu tiên Hà Nội / TP.HCM / Đà Nẵng. Miền Đông mới: ⬆ Hà Nội (38 tỉnh) · ⬇ Cà Mau (11) ·
  ⬆ Đà Nẵng qua Tây Nguyên (9) · ⬅ Kiên Giang (4). Đà Lạt: ⬆ Hà Nội · ⬇ TP.HCM (Cà Mau thuộc làn này) · ⬅ Kiên Giang · ⬆ Kon Tum.
- Độ quanh co đo trên lộ trình lấy mẫu 200 m, trung vị 3 đoạn 10 km (bỏ nhiễu rẽ phố): đồng bằng 10–16 °/km,
  trung vị 24, đèo Bảo Lộc ~60, Pha Đin / Khau Phạ 130–220.
- Bảng tay tên bến xe đến cho 63 tỉnh chưa làm (ngoài scope PLAN-122) — màn hình ghi tên tỉnh.

## Nguồn

- Bến xe liên tỉnh Đà Lạt (tuyến miền Tây, Đông Nam Bộ; Phương Trang, Vũ Linh): https://mia.vn/cam-nang-du-lich/ben-xe-lien-tinh-da-lat-18057
- Thời gian xe Đà Lạt – miền Bắc / Hà Nội ~26 giờ: https://www.vietnamtourism.com/vi/di-chuyen-en-a-lat-may-bay-xe-khach-va-cac-tuyen-xe-giuong-n
- Bến xe Cà Mau (tuyến đi miền Tây, các thành phố lớn): https://mia.vn/cam-nang-du-lich/thong-tin-ben-xe-ca-mau-18007
- Km đường bộ: OSRM (router.project-osrm.org, dữ liệu OpenStreetMap) — thử 31/10/2026.
