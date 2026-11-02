# PLAN-140 — Xe Tết: chi tiết đường VN + phông núi theo vùng + giữ mượt / ổn định

- Status: Code + đo xong (02/11), chưa nạp 8810
- Executor: Claude Code (anh 02/11: «oke em triển khai đi», theo thứ tự em đề xuất: biển chào tỉnh + biển chỉ đường → phông núi
  theo vùng (vẽ bằng code) → xe máy chở mai đào, quán ven đường, cọc tiêu; «tham khảo các nguồn, học hỏi người đi trước làm
  sao game mượt ổn định»)

## 1. Biển chào tỉnh + biển chỉ đường (`road.ts`, `scene.ts`)
- Biển địa giới nền xanh dương «TỈNH NGHỆ AN / THÀNH PHỐ ĐÀ NẴNG / TP. HỒ CHÍ MINH · Kính chào quý khách»: hiện phía trước
  (ngoài khung) đúng lúc `place` của xe đang chiếu đổi khi đang chạy; hai tấm luân phiên.
- Biển chỉ đường xanh dương: 3 dòng «tên tỉnh · km» — điểm trả + tỉnh đi qua sắp tới (bỏ trạm dừng) lấy từ bảng chặng thật.
  Vẽ lại ngay trước khi lọt khung hình (x < 30); km tính tại CHỖ BIỂN ĐỨNG (đo km / đơn vị đường từ odo thật) — chuyến bị nén
  nên vẽ lúc quay vòng thì lệch ~70 km.
## 2. Phông núi vẽ bằng canvas theo vùng (`landscape.ts`)
- Lớp xa: thay 26–36 khối nón (mỗi khối một lượt vẽ) bằng 1–3 tấm đứng có ảnh canvas lặp liền mạch, trôi bằng dời ảnh: núi
  đá vôi miền Bắc, dãy núi sau biển miền Trung, cao nguyên + núi lửa tắt Tây Nguyên, hàng dừa + đồi thấp miền Tây.
- Lưu ý: góc máy toàn cảnh / từ trên cao không thấy chân trời; thấy rõ ở góc ngang / cận (thẻ HUD phía trên che một phần).
## 3. Đồ ven đường (`road.ts`, `landscape.ts`)
- Cọc tiêu trắng đầu đỏ (cả hàng 1 lượt vẽ), biển hạn chế tốc độ 60, xe máy ngược chiều chở chậu mai / đào (theo vùng; người
  lái nằm trong đám đông vẽ lặp), quán cóc mái bạt (TRÀ ĐÁ, CƠM PHỞ, BƠM VÁ XE, NƯỚC MÍA, BÁNH MÌ — ghế nhựa vẽ lặp), thêm biển
  nhà ven đường (NHÀ NGHỈ, RỬA XE, BƠM VÁ XE). Không vẽ logo thương hiệu thật.
## 4. Mượt / ổn định (nguồn: agent nghiên cứu — three.js docs, Chromium, web.dev, utsubo 100 tips)
- Mất ngữ cảnh WebGL: dựng lại → biên dịch lại shader (`warmUp`); 10 giây không trả → tải lại trang; tạo WebGL lỗi → 30 giây
  tải lại (Chromium chặn WebGL 2 phút sau nhiều lần mất liên tiếp).
- Nhịp 30 khung: nới ngưỡng từ 2 ms lên 8 ms (máy chủ gọi đúng 30 nhịp hơi sớm thì không bỏ khung → không lặp khung trên live).
- CSS2DRenderer `sortObjects = false` (bỏ duyệt cả cây + ghi zIndex mỗi khung); bỏ tạo vector mới mỗi người mỗi khung.

## Proof (8811, SwiftShader)
- Ảnh: biển «TỈNH PHÚ YÊN · Kính chào quý khách» hiện khi xe qua ranh Phú Yên; biển chỉ đường «Khánh Hòa 49 km / Phú Yên 154 km /
  Bình Định 256 km»; phông núi đá vôi (Ninh Bình), núi sau biển (miền Trung), cao nguyên + núi lửa (Đắk Nông), hàng dừa (Cà Mau);
  quán cóc «NƯỚC MÍA», cọc tiêu, biển 60; xe máy chở chậu mai (chụp bằng bản tạm đặt xe máy giữa khung, đã trả lại code).
- Lượt vẽ trên đường ~125–200 (trước ~160–220): lớp núi xa bớt 26–36 lượt, đồ mới thêm ~10–15 khi lọt khung.
- Mất ngữ cảnh: mất + trả lại → vẽ tiếp, không tải lại trang; mất hẳn → tự tải lại sau 12 giây, vẽ bình thường; 0 lỗi JS.
- `npm run build` (tsc) sạch; e2e control_panel 28/28, ux_scenarios 0 lỗi (cả sau bước 1–2 và bản đủ).
- Chưa làm từ nghiên cứu (để sau): overlay gửi sức khoẻ (khung/s, khung giật, GPU, phiên bản Chromium của LIVE Studio) về server;
  HUD chuyển `left/width` sang `transform`; hẹn giờ pháo hoa theo đồng hồ khung hình.
