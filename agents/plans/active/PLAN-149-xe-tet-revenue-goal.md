# PLAN-149 — Xe Tết: mục tiêu 100k / giờ — thanh mục tiêu buổi live, bảng doanh thu, tự bù lỗ 60 giây

- Status: Code + test xong (03/11), chưa nạp 8810
- Executor: Claude Code (anh 03/11: «mục tiêu 1h phải kiếm được 100k … tâm lý học hành vi user … tự bù lỗ 60s, anh tự bật
  setting cấu hình thời gian và bật tắt được»)

## Bài toán
- 100.000 đ / giờ ≈ 1.000 xu / giờ (người live nhận ~100 đ / xu; người xem nạp ~200 đ / xu) ≈ 17 xu / phút.
- Buổi thật 02/11: 20 phút, TB 46 người xem, 411 lượt vào phòng, 6 quà = 6 xu → ~18 xu / giờ ≈ 1.800 đ. Cần gấp ~55 lần.
- Doanh thu = lượt người xem × tỉ lệ người tặng × xu mỗi người. Game nâng được tỉ lệ tặng + cỡ quà; lượt người xem do TikTok
  đề xuất (bình luận, share, follow, thời gian xem) + giờ live + mùa Tết.

## Tâm lý học hành vi đã dùng (có nguồn) — và cái KHÔNG dùng
- Dùng: mục tiêu tập thể có thanh tiến độ + nói rõ còn thiếu bao nhiêu (goal gradient); cảm ơn tên ngay + bảng Chủ nhà xe
  (ghi nhận công khai — nghiên cứu Notre Dame: người tặng nhiều quan tâm địa vị); quà nhỏ 1 xu cũng thấy tác dụng ngay
  (lên đầu hàng, xe x2); mỗi mốc mở cảnh vui cho cả phòng (người không tặng cũng được vui → ở lại xem lâu).
- Không dùng: quà đổi lấy may rủi (giống cờ bạc), đếm ngược giả, quà / người xem giả, ép người không tặng (xe luôn đi nhờ tự
  bù lỗ). TikTok (theo tóm tắt bên thứ 3, cần anh xem bản gốc trong app: Live Center > Rules and Guidance > Inauthentic Gift
  Requests) hạn chế game chấm điểm chỉ bằng quà, game tự chạy không người dẫn, xin quà liên tục — vi phạm có thể bị khoá nhận quà.

## Đổi
- Tự bù lỗ: công tắc `cover_on` (mặc định bật) + `cover_seconds` (mặc định 60, 10–600) trên /control.
- Thanh «🎯 Mục tiêu buổi live N/1000 xu · tới X xu: …» trong khung kêu gọi; mốc 10 % mưa lì xì, 30 % đèn lồng, 60 % pháo hoa
  lớn, 100 % cả xe chúc Tết rồi vòng mới; lơ xe đọc mốc + cảm ơn người tặng (câu `goal_step`, 3 kiểu nói).
- /control «💰 Doanh thu»: tiền 1 giờ gần nhất, ước cả giờ (chia ít nhất 10 phút), 10 phút gần nhất, người tặng / lượt, thanh %
  mục tiêu tiền / giờ, top 5 người tặng; chỉnh mục tiêu tiền, đ / xu, mục tiêu xu của thanh.

## Proof (03/11)
- pytest 172 (`test_session_goal_steps_unlock_fun_for_everyone_and_money_panel`); fuzz 20 × 30 phút 0 lỗi.
- 8811: thanh mục tiêu 125/1000 «tới 300 xu: 🏮 thả đèn lồng»; /control bảng doanh thu + mục trạm thu phí có công tắc tự bù lỗ;
  0 lỗi JS.

## Đề xuất kế tiếp (chưa làm, chờ anh chọn)
- Đua tỉnh: bình luận + tim + quà cộng điểm cho tỉnh quê, tỉnh dẫn đầu được ưu tiên chuyến sau (bản sắc nhóm — kiểu PK) — trộn
  hành động miễn phí để không thành «chấm điểm chỉ bằng quà».
- Mốc quà khớp giá quà TikTok thật (5, 30, 99, 199, 299 xu) — mỗi món một cảnh riêng thấy rõ.
- Khách quen: điểm danh ngày thứ N, huy hiệu theo số chuyến (giữ người quay lại).
- Lịch live cố định khung 20–23 giờ; cao điểm 23–28 Chạp.
