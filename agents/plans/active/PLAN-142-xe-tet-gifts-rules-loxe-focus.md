# PLAN-142 — Xe Tết: lơ xe theo xe đang chiếu + cách chơi + mỗi món quà một hiệu ứng

- Status: Code + test xong (02/11), chưa nạp 8810
- Executor: Claude Code (anh 02/11: «làm tặng quà cho game», «chiếu xe khác rồi mà Anh Tư vẫn đọc chỗ khác», «user chưa hiểu
  luật game»; anh chọn: mỗi món quà một hiệu ứng + bảng quà; thẻ «Cách chơi» luôn có + màn hướng dẫn đầu chuyến)

## A. Lỗi: lơ xe nói về xe chính khi màn hình chiếu xe tăng cường
- Nguyên nhân: mọi câu vị trí (qua tỉnh, tới trạm, xuất bến, về bến, bóp còi, thùng quà, đón dọc đường…) lấy theo xe chính;
  xe tăng cường chạy qua tỉnh thì im. 8810 đang để tự chiếu «xoay vòng» nên lộ rõ.
- Sửa: câu của xe chính khi xe chính không lên màn hình → câu nhỏ (qua tỉnh, bóp còi) bỏ; câu quan trọng thêm «Xe số N.» ở đầu.
  Xe tăng cường đang chiếu: qua tỉnh thì lơ xe gọi bà con tỉnh đó, thả khách có bong bóng; chuyển xe thì lơ xe giới thiệu xe
  đang chiếu (số xe, hướng, số khách, điểm kế).

## B. Cách chơi
- Thẻ CTA thêm dòng cố định 3 bước: «Gõ tên tỉnh = lên xe · Thả tim = xe chạy nhanh · Tặng quà = hiệu ứng».
- Màn hướng dẫn lớn 10 giây mỗi khi xe chính vào bến đón khách (và lúc mở trang).
- Lơ xe đọc luật: mỗi ~3 phút, hoặc sớm hơn (≥ 60 giây) khi có ≥ 3 người mới vào phòng.

## C. Mỗi món quà một hiệu ứng (giữ nguyên các mốc xu cũ)
- Server gắn `fx` cho sự kiện quà theo tên món (tiếng Anh / Việt) hoặc giá một món: hoa hồng → hoa mai / đào rơi; TikTok →
  xe bóp còi; tim → tim bay; 10–29 xu → pháo nhỏ; 30–99 xu → lì xì bay; ≥ 100 xu → đèn lồng thả trời (+ băng rôn như cũ).
- Overlay: thêm hiệu ứng lì xì, đèn lồng (gom sẵn, không tạo mới giữa trận); bảng «Quà → hiệu ứng» xoay vòng trong thẻ CTA,
  ghi chú 18+.

## Proof (02/11)
- pytest 150: `test_loxe_follows_the_bus_on_screen` (chiếu xe tăng cường: không «via» / «honk» của xe chính, câu xe chính có
  «Xe số N.», về xe chính có câu báo), `test_loxe_introduces_featured_relief`, `test_rules_reminder_every_three_minutes_or_after_
  newcomers`, `test_each_gift_has_its_own_effect` (Rose → hoa, TikTok → còi, Finger Heart → tim, Doughnut 30 xu → lì xì, Hand
  Hearts 100 xu → đèn lồng, «Ultimate» không khớp nhầm «tim»).
- 8811 ảnh: màn «Cách chơi» lúc mở trang, dòng 3 bước trong thẻ CTA, lì xì bay, đèn lồng thả trời, «Em bóp còi xe!», bảng quà
  xoay vòng; chiếu xe tăng cường số 2 → thẻ tuyến «Tới Bạc Liêu», lơ xe «Qua xe số 2 nè bà con, xe đi Cà Mau chở 2 người, còn
  254 ki lô mét tới Bạc Liêu» → thả khách «Bạc Liêu, Bạc Liêu…» → về xe chính «Trở về xe số 1 hướng Hà Nội». 0 lỗi JS.
- e2e control_panel 28/28; ux_scenarios: 10 cảnh đạt, bước cuối (mở thêm cửa sổ 16:9) hết giờ chụp ảnh khi máy tải nặng —
  chạy riêng bước đó chụp xong 11,4 giây, 0 lỗi JS.
