# PLAN-143 — Xe Tết: báo cáo sau mỗi buổi live (học khán giả từ số liệu thật)

- Status: Code + test xong (02/11), chưa nạp 8810
- Executor: Claude Code (anh 02/11: «báo cáo sau mỗi buổi live … quà và bình luận theo từng phút và từng cảnh, bao nhiêu người
  lên xe, bao nhiêu người quay lại … em áp dụng vào game đi»)

## Ghi
- Một buổi = từ lúc cầu nối TikTok «connected» tới khi rời trạng thái đó. Chỉ đếm sự kiện từ TikTok (không đếm giả lập /
  bấm thử trên /control).
- Mỗi phút: bình luận, người bình luận khác nhau, tim, quà (lượt + xu), vào phòng, follow, share, lên xe (có giường), giữ chỗ
  chuyến sau, bắt xe dọc đường, về tới quê (người), khách quen quay lại, số người xem (TikTok báo), cảnh chiếm nhiều nhất
  trong phút (bến / đường / trạm / thả khách / về bến / chúc Tết).
- Lưu SQLite `storage/db/xe_tet.db` (bảng mới `live_sessions`, `live_minutes`; CREATE IF NOT EXISTS, không xoá / sửa dữ liệu
  cũ), ghi theo lô ở luồng riêng như hồ sơ khách.

## Xem
- `/report` (cùng mã bảo vệ như /control): danh sách buổi live; mỗi buổi: thẻ tổng, biểu đồ theo phút (xu + bình luận, nền
  màu theo cảnh), bảng theo cảnh (xu / bình luận / tim / lên xe mỗi phút), 5 phút nhiều quà nhất, chuyển đổi (người bình
  luận → lên xe → về quê, khách quay lại), vài nhận xét tự động. /control có nút mở báo cáo.

## Proof (02/11)
- Đổi so với kế hoạch: bảng «theo cảnh» đếm sự kiện vào ĐÚNG cảnh lúc xảy ra + số giây thật của cảnh (bảng `live_phases`) —
  gán theo phút thì cảnh thả khách (vài giây) bị phút «xe chạy» nuốt mất. Cột «khách quen» tên `regulars` (`returning` trùng
  từ khoá SQLite).
- pytest 159 (`tests/test_live_report.py`: đếm theo phút + cảnh, ghi lại cùng buổi, rớt mạng ngắn vẫn một buổi / quá
  SESSION_GAP thì hết buổi, quà lúc thả khách tính đúng cảnh, trang render, Hub chỉ đếm sự kiện TikTok khi đã kết nối).
- Buổi mô phỏng 60 phút chạy bằng engine thật → trang báo cáo: thẻ tổng, nhận xét («Quà nhiều nhất lúc Thả khách…»),
  biểu đồ theo phút, bảng theo cảnh, 5 phút nhiều quà, danh sách buổi.
- 8811: `/report` 200 (DB trống báo «Chưa có buổi live…»), /control có nút «📊 Báo cáo buổi live», 0 lỗi log.
