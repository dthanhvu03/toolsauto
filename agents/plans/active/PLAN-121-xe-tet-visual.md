# PLAN-121 — Xe Tết Sum Vầy: làm đẹp hình 3D

- Status: V1–V4 xong — chờ anh duyệt ảnh, đo khung hình trên GPU thật
- Executor: Claude Code (anh duyệt 31/10: «Anh duyệt em triển khai nhé»)
- Liên quan: PLAN-120 (MVP), `xe_tet/README.md`

## Mục tiêu

Người lướt TikTok quyết định ở lại trong vài giây đầu → cảnh phải đẹp, đọc được trên màn điện thoại.
Hướng: low-poly bo tròn, ấm áp, «quê nhà ngày Tết» (đỏ / vàng / hồng đào, nắng chiều).
Đồ đặc trưng Việt Nam tự dựng bằng code; không mua mô hình; nền xa tạm bằng code, chừa chỗ gắn tranh AI.

## Các bước

- **V1 — 3 giây đầu:** ánh sáng (tone mapping, bóng đổ quanh xe, trời chuyển màu, vệt tối dưới chân), xe khách mới
  (bo tròn, kính viền + rèm, mâm bánh, gương, đèn, bảng LED «VỀ QUÊ ĂN TẾT», biển số, cành đào, câu đối),
  người chibi (đầu to, tay chân, đi vung tay, nón lá / mũ len / ba lô / vali), cánh hoa đào – mai bay, đồng hồ FPS `?fps=1`.
- **V2 — 3 bối cảnh:** bến xe, trạm dừng chân (ghế nhựa đỏ xanh, trà đá, nồi phở), đầu ngõ (cổng làng, mái ngói, bánh chưng).
- **V3 — đường 4 vùng:** lớp nền xa (code → tranh AI khi anh có), đồ ven đường theo vùng, thời tiết, ban đêm, trong xe.
- **V4 — hiệu ứng + tối ưu:** pháo hoa có vệt, bụi đường, khói; «Chất lượng hình thấp / cao» trên `/control`.

## Ràng buộc

- ≥ 30 khung / giây ở 1080×1920 trên GTX 1650 khi LIVE Studio phát (anh đo bằng `?fps=1`, máy em không có GPU).
- Giữ bố cục đã kiểm (xe trên khung comment TikTok, chữ không bị che); chạy lại e2e sau mỗi bước.
- Không đổi luật chơi / server.

## Proof

### V1 (31/10)

- `xe_tet/overlay/src/art.ts` (mới): vật liệu mịn / phẳng, texture chữ canvas, vệt tối dưới chân, vòm trời chuyển màu,
  xe khách mới, người chibi + dáng đi, cánh hoa. `scene.ts` dùng lại, bỏ code hình cũ.
- Ánh sáng: ACES tone mapping, bóng đổ mềm 1024² chỉ quanh khu xe (±24), trời đỉnh → chân trời theo giờ, sương = màu chân trời.
- Xe: thân bo tròn đỏ / kem, chỉ vàng, kính 2 tầng + khung (instanced) + rèm kem xen kẽ, kính lái, bảng LED «VỀ QUÊ ĂN TẾT»,
  biển số, đèn pha (sáng ban đêm), đèn hậu, gương, câu đối PHÚC / LỘC, chữ «XE TẾT SUM VẦY» sơn 2 bên, cành đào, mâm bánh
  có nan (thấy quay), vòm bánh, máy lạnh trên mui, cửa kính sáng đèn ban đêm.
- Người: đầu to, mắt, má hồng, tóc; nón lá / mũ len; ba lô; tay chân vung khi đi, đứng thả lỏng, gia đình vẫy tay.
- Mặt đất / đường: vân cỏ, nhựa đường có vân, lề đường; cây có bóng + vệt tối gốc; 220 cánh hoa (đào hồng miền Bắc, mai vàng nơi khác).
- `?fps=1` đồng hồ khung hình + lần vẽ; `?res=0.5` vẽ nửa độ phân giải. Sửa lỗi canvas không giãn theo khung khi độ phân giải ≠ 1.
- Số liệu mỗi khung (cảnh bến): **384 lần vẽ, 59k tam giác** — nhẹ với GTX 1650. Máy em (SwiftShader, CPU) chỉ 1–3 khung/s
  nên **chưa đo được khung hình thật** → anh mở `http://127.0.0.1:8810/?fps=1` trên Chrome Windows.
- e2e chạy ở `res=0.5` + chờ 120 s (máy không GPU); điều khiển 26/26. Ảnh: scratchpad `v1-before-after.png`, `v1-phone.png`.

### V2 (31/10, anh: «v2 đi em, đừng code lộn xộn và chắp vá»)

- Cấu trúc overlay sau V2 (mỗi file một việc):
  - `art.ts`: vật liệu, texture chữ, trời, người chibi, xe khách, cánh hoa (V1) + `slab` / `post`.
  - `props.ts` (mới): đồ dùng lại — hoa văn canvas (gạch, ngói, bạt sọc), `SignBoard`, mái ngói, cây (chuyển từ scene),
    cây đào / mai, chậu quất, `LanternString`, ghế nhựa (instanced), bàn nhựa, ly trà đá (instanced), vali, ghế chờ, `Steam`.
  - `sets.ts` (mới): `BenSet`, `RestSet`, `HomeSet` — dựng hình + **điểm mốc** (`waiting`, `seats`, `counterSpot()`,
    `shop`, `wcQueue()`, `gate`, `door`, `family`, `fireworksAt`) + `update(dt, t)` (hơi nồi, đèn lồng, lửa bếp).
  - `scene.ts`: chỉ điều phối; bỏ 3 hàm dựng cũ, `wcSpot`, `homeTree`, `restSign` và mọi toạ độ cứng của bối cảnh.
- `tsconfig`: bật `noUnusedLocals` / `noUnusedParameters` (đã dọn 1 hằng thừa từ V1).
- Bến xe: sân lát gạch, nhà chờ tường + kính, cột, mái đỏ nẹp vàng, biển «BẾN XE THÀNH PHỐ», quầy «BÁN VÉ», ghế chờ,
  dây đèn lồng đung đưa, đống vali / thùng quà, chậu quất, người chờ có vali.
- Trạm dừng chân: quán mái ngói + bạt sọc đỏ trắng, quầy phở có nồi bốc hơi + chồng bát, 4 bàn nhựa xanh + 16 ghế nhựa
  đỏ / xanh + ly trà đá, sạp đặc sản (biển ghi đặc sản theo vùng), nhà vệ sinh, đèn lồng, chậu quất; người gọi món đi tới quầy
  rồi ngồi đúng một ghế nhựa.
- Đầu ngõ: cổng làng mái ngói, biển «CHÀO MỪNG VỀ <TỈNH>» đổi theo nơi thả khách, câu đối AN KHANG / THỊNH VƯỢNG,
  hàng rào tre, lối gạch đỏ, nhà vàng mái ngói có hiên cột, cửa gỗ, câu đối PHÚC / LỘC, đèn lồng hiên, mâm ngũ quả,
  nồi bánh chưng trên bếp củi (lửa lập loè + hơi), cây đào (Bắc) / mai, chậu quất, gia đình đứng trước cổng vẫy tay.
- Chỉnh sau ảnh đầu: biển bến / trạm hạ xuống mép mái (cao hơn bị khung lời kêu gọi che), biển cổng to hơn, gia đình ra
  trước cổng (trong sân bị mái cổng che), gộp bảng đặc sản vào biển sạp.
- Số liệu mỗi khung (cảnh bến): 512 lần vẽ, 116k tam giác (V1: 384 / 59k).
- Chỉnh tiếp: biển bến / trạm lệch phải (giữa cảnh nằm sau bong bóng lơ xe bên trái màn hình).
- Lỗi thật ở `/control` tìm ra khi chạy e2e: vòng làm mới 1 s đè giá trị cũ lên công tắc admin vừa bấm (công tắc «tự bật lại»)
  → công tắc vừa bấm không bị làm mới trong 3 s.
- e2e `control_panel.py`: chờ theo điều kiện thay vì chờ cố định (overlay 3D trên máy không GPU cập nhật chậm → chập chờn),
  đặt đón khách 15 phút khi chạy, **luôn trả thiết lập mặc định trong `finally`** (lần chạy hỏng trước để lại thiết lập bẩn,
  đã trả lại). Kết quả: e2e 11 tình huống sạch, điều khiển 26/26.

### V3 (31/10, anh: «duyệt v3, đi đường gồ ghề, ổ gà ổ voi, trụ điện…»)

- File mới, mỗi file một việc; `scene.ts` bỏ hết code đường / cảnh cũ (băng cuộn, cây ven đường, núi, cột đèn, đất):
  - `road.ts`: `Conveyor` (băng chuyền quay vòng dùng chung), `Roadway` — nhựa + vạch kẻ **vẽ chung một texture trôi bằng
    offset** (bỏ 32 khối vạch), lề đất sỏi, vá nhựa, vết nứt, **ổ gà** (mép vỡ răng cưa, nửa số nằm đúng vệt bánh; mưa thì
    đọng nước), **trụ điện bê tông** xà + sứ + đèn đường, **3 dây điện võng + 2 bó cáp viễn thông võng thấp + cuộn dây thừa**
    gộp 1 khối / trụ, cột cây số đỏ trắng ghi điểm tới + km còn lại (vẽ lại lúc cột quay vòng ra sau).
    Đường không biết gì về xe: nhận vị trí bánh, trả về «bánh nào vừa sập ổ gà, bên nào, sâu bao nhiêu».
  - `landscape.ts`: đất theo vùng (trôi bằng offset), dải sát đường xen kẽ khoảnh đặc trưng vùng (ruộng bậc thang / đồi cà
    phê đất đỏ / ruộng nước / bãi cát + phi lao + thuyền thúng) và cụm **nhà ống có bồn nước inox**, biển TẠP HOÁ / CƠM BÌNH DÂN…,
    nhà sàn miền Tây; hàng cây xa + tiền cảnh phía camera; nền xa núi nhiều tầng (mỗi đỉnh tự quay vòng) / biển + thuyền.
  - `weather.ts`: mưa phùn miền Bắc (vệt mưa xiên).
  - `art.ts` `Bus`: **giảm xóc** lò xo + giảm chấn (nảy / chúi / lắc), `bump()` theo ổ gà (bánh trước chúi, bánh sau ngóc,
    bên nào nghiêng bên đó), rung nhẹ theo tốc độ.
- Trời: bảng `LOOKS` (bình minh / ngày / hoàng hôn / đêm) thay chuỗi if; đêm ánh trăng xanh lạnh, phơi sáng 0,8.
- Chỉnh sau ảnh đầu: camera rộng chỉ thấy dải sát đường (xa hơn nằm sau khung chữ) → đặc trưng vùng dời vào dải đó;
  thuyền thúng chìm dưới đất → đáy đặt đúng y = 0; đêm quá sáng → ánh trăng + phơi sáng thấp.
- Số liệu mỗi khung khi chạy: 209–284 lần vẽ, 35–45k tam giác (nhẹ hơn cảnh bến).
- Hoàng hôn / bình minh hơi tối ngả nâu (ảnh chụp lúc 17h UTC) → tăng ánh trời + phơi sáng.

### V4 (31/10, anh: «v4 đi em»)

- `effects.ts` (mới): `Fireworks` — quả pháo bay lên có vệt sáng rồi nổ thành chùm tia có đuôi (mỗi tia là một nét kéo
  theo vận tốc, không nhớ lịch sử), phát sáng cộng màu, lấp lánh khi tàn; trần 10 quả (thấp: 4), 80 tia / quả (thấp: 36).
  `Puffs` — làn bụi / khói nở to rồi tan (bể sprite dùng lại, trần 72; thấp: 1/3). Bỏ `Burst` cũ khỏi `scene.ts`.
- Bụi bốc sau bánh sau + khói ống xả khi xe chạy (càng nhanh càng dày); sập ổ gà → bụi tung ở đúng bánh vừa sập.
- **Chất lượng hình Cao / Thấp** (`/control` → Camera; lưu `quality` ở server): thấp = ~60 % độ phân giải, tắt bóng đổ
  (bằng `castShadow`, three tự dựng lại shader — không tải lại trang), 35 % cánh hoa, 40 % mưa, ít hạt pháo hoa / bụi.
  Overlay ghi `data-quality` lên khung `#stage` (e2e kiểm). Test server + e2e thêm kiểm chất lượng.
- **Lỗi trải nghiệm tìm ra khi chụp V4 (có từ trước):** pháo hoa nổ cao (y 9–12) → nằm dưới băng rôn / bảng chữ ở đầu
  màn hình, người xem gần như không thấy (góc cận: y màn hình 138–335; đầu ngõ: 442 ngay dưới băng rôn thả khách).
  Tính toạ độ màn hình theo 4 góc máy → gom về một hằng `SHOW_SKY` (0, 5, -6): y màn hình 921 / 846 / 627 / 1019 (toàn cảnh /
  ngang / cận / trên cao) — đều trong khoảng trống giữa màn. Pháo hoa đầu ngõ hạ xuống (1.5, 5.5, trước cổng).
- Đo chất lượng (cảnh đang chạy, SwiftShader): Cao 223 lần vẽ / 21k tam giác → Thấp 107 / 13k.
- Tim bay chạm mép khung 3 px → thu vùng xuất hiện.
- e2e điều khiển có 1 lần trượt «trong xe giữ nguyên» chưa rõ nguyên nhân; chạy lại 2 lần liền đều 28/28. Đã gắn chẩn đoán
  (in góc nhìn server đang ghi) để lần sau nếu lặp lại thì biết ngay.
