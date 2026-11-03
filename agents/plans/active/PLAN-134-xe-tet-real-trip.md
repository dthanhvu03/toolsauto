# PLAN-134 — Xe Tết: tuyến đường thật, người xem biết mình ở xe nào, mùa Tết thật, đọc vị từng người xem

- Status: A, B, C (trừ chiều ra), D xong + đã nạp 8810 (01/11). Chiều ra (C3) làm bước riêng trước 9/2/2027.
- Executor: Claude Code (anh yêu cầu 01/11: «không đi qua tỉnh không có người nhưng vẫn đi qua địa phận», «user không biết
  ở xe nào, chuyến nào bắt đầu / kết thúc / chuẩn bị / đang chạy», «tìm hiểu quy trình về quê, mua vé, giành vé», «học lại
  các tỉnh thành», «thuật toán kích thích user, đọc vị tâm lí từng user»)

## Phát hiện (đo trên dữ liệu thật, 01/11)
- Tuyến zig-zag (ảnh anh: xe số 2, 16 tỉnh, 4.441 km, Hải Dương → Cao Bằng → Hòa Bình … → Lào Cai → Vĩnh Phúc) là do
  **mô hình cây**: mỗi tỉnh là một nhánh tách từ trục, đổi nhánh phải quay về chỗ rẽ. Hòa Bình / Tuyên Quang / Yên Bái /
  Lào Cai / Vĩnh Phúc tách ở km 1.436 (trước Hà Nội), Hà Nội / Hải Dương / Cao Bằng ở nhánh khác. Phân tích cũ (tham lam
  +3,1 % so tối ưu) đo trên chính mô hình cây nên không thấy lỗi này.
- Thử nghiệm: ghép 310 chuỗi tỉnh đã có (5 bến × 62 tuyến OSRM, `places` mỗi 10 km) thành đồ thị 63 tỉnh / 88 cạnh,
  Floyd–Warshall ra km + đường đi mọi cặp tỉnh (không gọi mạng). Cùng 16 tỉnh: **4.441 → 1.960 km**, thứ tự Hà Nội → Hưng Yên
  → Hải Dương → Vĩnh Phúc → Tuyên Quang → Yên Bái → Lào Cai → Cao Bằng; 16 tỉnh «đi qua» không ai xuống.
- Người xem: thẻ lên xe ghi giường, không ghi số xe; giữ chỗ / chuyển xe tăng cường xong không có cách tra lại.
- RAM: server 6 giờ giả lập 15.000 người xem → 8,7 MB (~300 B / người xem), state 16–19 KB; overlay 12 phút / 8 chuyến:
  hình 208 → 367 rồi đứng (dựng vùng một lần), ảnh 59, heap 26 MB. 8810 sau 36 phút 84 MB, log 0 lỗi. Không rò.
- Nghiên cứu (agent, có nguồn): Tết 2027 không có 30 Tết (giao thừa 29 Chạp = 5/2/2027); cao điểm chiều về 24–28 Chạp
  (≈ 31/1–4/2/2027), chiều ra mùng 6–7; vé hết sau vài giờ mở bán, giá tăng 40–60 %, cò vé ×2–3, xe dù; tài xế ≤ 4 giờ liên
  tục; gửi hàng qua xe tăng 3–5 lần; 34 tỉnh từ 1/7/2025 (cả 34 tên đều là tên cũ, 23 tên gộp thêm tỉnh khác).

## Đợt đề xuất
- **A. Tuyến đường thật:** đồ thị tỉnh + Floyd–Warshall thay mô hình cây; thứ tự ghé tham lam + 2-opt theo tổng giờ chờ
  của khách; mỗi đoạn mang theo nguồn (tuyến + km) để địa hình / đèo / hầm / cảnh vùng vẫn đúng; bảng chặng + /control hiện
  tỉnh «đi qua» (mờ). Proof: chuyến xe số 2 ≤ ~2.000 km, fuzz 0 vi phạm, test dữ liệu thật.
- **B. Người xem biết mình ở đâu:** thẻ vé ghi số xe; comment «xe» / «vé» / «tôi đâu» → thẻ riêng «An: xe số 3 · giường 5 ·
  còn 2 điểm tới Huế ~3 phút»; bảng đội xe trên live: mỗi xe một trạng thái (Đang đón m:ss / Đang chạy → tỉnh kế / Trạm dừng /
  Thả khách / Về bến) + «chuyến sau»; báo riêng khi được chuyển sang xe tăng cường.
- **C. Mùa Tết thật:** lịch 2027 (giao thừa 29 Chạp, cao điểm, chiều ra mùng 4–10 cho vé khứ hồi); mở bán vé theo đợt, chỉ
  khan hiếm thật; đổi tài sau mỗi ~4 giờ xe chạy (gắn trạm dừng); «gửi quà Tết lên gầm xe» (quà thành thùng hàng mang tên);
  hiểu tên 34 tỉnh mới (gõ «Gia Lai» → hỏi lại «hay Bình Định?»).
- **D. Đọc vị từng người xem:** hồ sơ người xem (lần đầu / quay lại / hay comment / hay thả tim / tặng quà) → câu lơ xe +
  thẻ riêng theo loại; «nợ gọi tên»: hàng ưu tiên (heap) người lâu chưa được gọi tên lên trước, ai cũng được gọi; gọi người
  cùng quê. Rào chắn: không đếm ngược / «còn N chỗ» giả, không xin quà, nhắc tặng quà chỉ từ 18 tuổi, trần cho người tặng lớn.

## Đợt A — đã làm (01/11)
- `network.py`: `RoadGraph` — đồ thị 63 tỉnh ghép từ 310 chuỗi tỉnh OSRM sẵn có (không gọi mạng); tỉnh đặt ở giữa địa phận
  trên mỗi tuyến (đặt ở chỗ «bắt đầu vào địa phận» phụ thuộc chiều đi → ghép ra TP.HCM – Hà Nội 650 km); mỗi cạnh lấy lần đo
  gần trung vị; cận dưới chim bay × 1,2 (miền Bắc tỉnh dày đo hụt: Hà Nội – Hòa Bình 20 → 69 km); Floyd–Warshall 0,1 s.
- `Network.plan`: chặng đầu đúng tuyến OSRM của bến (khớp km trên vé); giữa hai tỉnh lấy đường ngắn hơn của «quay về chỗ
  rẽ» (đúng km OSRM, thắng ở miền Tây — đồ thị một mình ra Sóc Trăng → Cà Mau 265 km) và «đi tắt trên đồ thị» (thắng ở miền
  Bắc). Thứ tự: tham lam + 2-opt theo tổng km khách chờ. `Trip.via`: tỉnh đi qua mà không ai xuống. Khúc đồ thị mang hồ sơ
  «bến:tỉnh» → đèo / hầm / cảnh vùng đúng đường đang đi (`Network.profile`), km tuyến giãn theo tỉ lệ khi áp cận dưới.
- Hiển thị: state `route.via` + `fleet[].via`; HUD huy hiệu «🛣 Qua <tỉnh>» + chấm nhỏ trên thanh chặng; /control chip nét
  đứt «qua <tỉnh>» chen giữa điểm dừng theo km.
- Proof: xe số 2 (ảnh anh) 4.441 → 2.999 km, Vĩnh Phúc trước Lào Cai; 1.440 chuyến ngẫu nhiên × 5 bến so mô hình cũ: km
  trung vị −16 % (p10 −39 %, tệ nhất +3 %), km chờ trung vị −9 % (không chuyến nào chờ lâu hơn); fuzz 2 giờ × 5 bến 292
  chuyến 0 vi phạm (đoạn nối liền, «đi qua» không trùng điểm dừng, khúc nào cũng trên tuyến thật); pytest 117 (test hồi quy
  xe số 2 thay test mô hình cây); ảnh HUD «Qua Đồng Nai» + /control chip «qua …».
- Lộ ra (chờ anh quyết): khách «Huế» phải chờ xe «Hướng Đà Nẵng» trong khi xe «Hướng Hà Nội» chạy ngang Huế (luật làn
  PLAN-122). Còn lệch: Lào Cai → Cao Bằng 606 km (thật ~400, dữ liệu không có tuyến qua Hà Giang); miền Tây đôi khi để
  Sóc Trăng cuối (tối ưu tổng chờ).

## Đợt B — đã làm (01/11)
- Thẻ vé ghi số xe: «lên xe số N về …», «giữ chỗ xe số N ⬆ Hướng …».
- Tra vé: comment «xe nào», «xe số mấy», «tới đâu rồi», «còn bao lâu», «bao giờ tới …», «tra vé», «vé» (chữ «vé» có dấu
  — «ve» trơn trùng «về Huế») → `Engine.ticket_of`: đang ngồi (xe số, giường, đang đón + xuất bến sau m:ss / còn N điểm tới
  quê ~m:ss / đang thả khách), xe tăng cường, giữ chỗ (thứ mấy, xe số mấy, ~phút), đã về quê, chưa có vé. 15 giây / người.
- Bảng «Xe khác» trên live: 🟢 đang đón / → điểm kế / ☕ nghỉ trạm / 📍 thả khách / 🏁 về bến.
- Nối A ↔ D: xe chính vào địa phận tỉnh không ai xuống → lơ xe gọi bà con tỉnh đó (3 kiểu nói) + thông báo «🛣 Xe số N đang
  qua …», tối đa 40 giây / lần (chuyến nén ~4 phút qua cả chục tỉnh).
- Proof: pytest 120 (parser «vé» vs «về», 5 trạng thái vé + giới hạn 15 giây, gọi tỉnh đi qua cách ≥ 40 giây); ws 8811 nhận
  sự kiện `where` đúng; DOM thẻ: «🎫 Lan Anh · xe số 1 · giường 1 — Đang đón khách · xuất bến sau 0:28 · về Hà Nội»; ảnh lơ
  xe «Tới địa phận Đồng Nai rồi…» + thông báo «Xe số 1 đang qua Đồng Nai»; 0 lỗi trang.

## Anh chốt cho C + D (01/11)
1. **Luật làn:** xe nhận khách dọc đường — tỉnh nằm trên đường tới điểm cuối của làn lên được xe làn đó (Huế lên xe Hà Nội
   khi còn giường); hàng chờ làn của mình vẫn giữ.
2. **Chiều ra:** có — từ mùng 4 (9/2/2027) xe chạy ngược quê → bến đi; người đã về quê mùa này (vé khứ hồi) ưu tiên giường.
3. **Quà Tết lên gầm xe:** làm — mỗi lần tặng quà thành thùng hàng ghi tên dưới gầm xe, tới quê thì bốc xuống giao tận cổng
   (hình + gọi tên, không đổi quyền lợi quà hiện có).
4. **Nhớ khách:** lưu SQLite riêng của Xe Tết trong `storage/db/` (tên, tỉnh quê, số chuyến, tim, lần cuối gặp) để lơ xe
   chào người quay lại.

## Đợt C — đã làm (01/11)
- **C1 luật làn** (`Network.serves`): xe làn L chở được tỉnh p nếu p thuộc L hoặc chi phí chèn (km bến → p + km p → điểm cuối
  − km bến → điểm cuối) ≤ 50 km. TP.HCM: xe Hà Nội nhận thêm Huế / Đà Nẵng / Kon Tum; Giáp Bát: xe Quảng Ninh nhận Bắc Ninh /
  Hải Dương. Lên xe ngay khi còn giường; xe đang đón lấy người chờ làn mình trước rồi người chờ làn khác mà xe đi ngang quê
  (ai chờ lâu trước). Vé ghi làn của xe đang ngồi.
- **C2 lịch mùa** (`season.py`): mùng 1 = 6/2/2027, tháng Chạp thiếu (giao thừa 29 Chạp = 5/2); cao điểm 23–28 Chạp; chiều
  ra mùng 4–10. HUD «25 Chạp · còn 5 ngày nữa là Tết» / «Giao thừa» / «Mùng 2 Tết»; lơ xe mời lên xe theo mùa (3 kiểu nói).
- **C4 quà Tết lên gầm xe:** tặng quà lúc có vé (ngồi / giữ chỗ / xe tăng cường) → +1 thùng mang tên (tối đa 3 / người /
  chuyến), thông báo «📦 Thùng quà Tết lên gầm xe», huy hiệu «📦 N» trên thẻ tuyến; tới quê người đó ôm thùng đỏ nơ vàng đi
  vào cổng + lơ xe «Bốc thùng quà của … giao tận cổng». Quyền lợi quà cũ giữ nguyên.
- **C3 chiều ra:** chưa làm — xe chạy ngược (đón ở quê, trả ở bến), cảnh 3D đón thay thả, lơ xe / HUD riêng; chỉ dùng từ
  9/2/2027 → làm bước riêng sau khi mùa chiều về chạy ổn (không đụng vòng chơi chính trước 15/12).

## Đợt D — đã làm (01/11)
- `server/store.py`: SQLite riêng `storage/db/xe_tet.db` (WAL) — tên, tỉnh đã về, số chuyến, tim, xu, comment, ngày đầu / cuối,
  số ngày ghé. Engine đọc một dòng khi gặp khách lần đầu trong buổi (`recall`), đánh dấu người đổi (`dirty`); Hub ghi theo lô
  mỗi 30 giây ở luồng riêng, ghi nốt khi reset / tắt server. Test dùng DB tạm (`XE_TET_DB`).
- Khách buổi trước quay lại (tương tác thật, không tính vào phòng): lơ xe chào «đã về Hà Nội 1 chuyến» / «ghé lại bến» +
  thông báo «🎉 … quay lại»; 20 giây / lần cả phòng.
- Gọi người cùng quê: lên xe gặp người cùng tỉnh → lơ xe ghép đôi (30 giây / lần).
- Gọi tên công bằng: thẻ dồn nhiều vé hiện 3 tên lâu chưa được gọi nhất (nhớ 500 người gần nhất).
- Rào chắn: gợi ý tặng quà ghi «chỉ dành cho người từ 18 tuổi». Không thêm khan hiếm giả / đếm ngược giả / xin quà.
- Cần anh cân nhắc (chưa đổi): gợi ý «🎯 thêm N xu → …» sau mỗi lần tặng là cơ chế «suýt được» gắn với tiền mà nghiên cứu
  khuyên tránh — giữ hay bỏ là quyết định của anh.
- Proof C + D: pytest 125 (lịch 2027, làn dọc đường bằng dữ liệu thật, thùng quà, hồ sơ SQLite + chào lại, ghép cùng quê,
  câu lơ xe đủ chỗ điền / không «!» / không «nha»).
