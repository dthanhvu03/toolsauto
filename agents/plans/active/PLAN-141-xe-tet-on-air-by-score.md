# PLAN-141 — Xe Tết: xe tăng cường lên sóng theo điểm quà / bình luận / tim

- Status: Code + test xong (02/11), chưa nạp 8810
- Executor: Claude Code (anh 02/11: «ai tặng quà nhiều thấy xe họ lâu hơn, hoặc bình luận»; anh chọn: tính quà + bình luận +
  tim, tối đa 60 giây / lượt)

## Vấn đề
Xe tăng cường (xe người tặng ≥ 100 xu gọi, xe chạy thêm khi đông) chạy ngầm, chỉ lên màn hình ~25 giây trước khi thả khách —
người tặng quà gọi xe hầu như không thấy xe mình chạy.

## Luật
- Điểm lên sóng trong buổi của mỗi người: 1 xu = 3, 1 bình luận = 1 (tối đa 30 / người — spam không leo), 50 tim = 1. Điểm một
  xe = tổng điểm khách trên xe.
- Chế độ tự chiếu «theo chuyện hay»: xe chính chỉ đang chạy đường trơn (không xuất bến / trạm / thả khách / chúc Tết) và đã lên
  ≥ 20 giây → chiếu xe tăng cường nhiều điểm nhất trong các xe chưa lên sóng 90 giây qua: 15 giây + 1 giây mỗi 5 điểm, tối đa
  60 giây; hết lượt về xe chính (≥ 20 giây) rồi xe khác (kể cả xe 0 điểm) tới lượt. Xe sắp thả khách vẫn ưu tiên như cũ; cảnh
  xe chính luôn là xe chính; admin bấm tay vẫn hơn.
- Thông báo «📺 Xe số 5 (của người gọi xe) đang lên sóng · Cảm ơn Lan, Bình · Hướng Cà Mau» (tối đa 3 tên, người gọi xe trước).
- AI Gemini biết luật này.

## Proof (02/11)
- pytest 146 (`test_on_air_by_stage_score_gifter_bus_shown_longer_and_others_get_turns`: xe có quà lên trước 60 giây, xe 0 điểm
  vẫn có lượt ≤ 15 giây, giữa hai lượt xe chính ≥ 20 giây, cảnh xe chính không bị cướp; `test_stage_score_caps_comment_spam`).
- 8811: khách xe tăng cường tặng 100 xu → xe số 2 lên sóng, thông báo «📺 Xe số 2 đang lên sóng · Cảm ơn Út Lan · Hướng Cà Mau»,
  0 lỗi JS.
- e2e control_panel 28/28; ux_scenarios 0 lỗi (lần đầu hết giờ chụp ảnh SwiftShader, chạy riêng đạt; ghi chú «nút 200 tim không
  tính» = đọc trip_likes 0,4 giây sau bấm lúc máy bận / xe vừa đổi chuyến — luồng tim chỉ thêm cộng điểm, không đổi).
