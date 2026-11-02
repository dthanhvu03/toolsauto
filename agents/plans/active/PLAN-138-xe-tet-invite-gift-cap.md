# PLAN-138 — Xe Tết: mời người xem lặng lẽ + bỏ vòng gợi ý quà không đáy

- Status: Code + test xong (02/11), chưa nạp 8810
- Executor: Claude Code (anh 02/11: «em làm mấy cần thiết và quan trọng giúp anh», sau khi em báo còn thiếu: người chỉ thả tim
  chưa comment, trần cho người tặng nhiều)

## Luật
- **Mời lên xe:** một người thả ≥ 15 tim trong chuyến mà chưa có vé (chưa gõ tỉnh, chưa chọn «không về», buổi này chưa về quê)
  → lơ xe gọi tên mời gõ tên tỉnh. Mỗi người một lần mỗi buổi, cả phòng tối đa một lần / 45 giây. Biết quê từ buổi trước
  (SQLite) thì mời đúng tỉnh («năm nay về Nghệ An nữa hông, gõ Nghệ An là có giường»). Câu 3 kiểu, không «!» / «nha».
- **Gợi ý «🎯 thêm N xu → …»:** đã tới bậc cao nhất (1000 xu trong chuyến) thì thôi gợi ý — trước đây hiện mãi
  «thêm N xu → cả xe chúc Tết thêm lần nữa» cho người đã tặng nhiều. Gợi ý dưới 1000 xu giữ nguyên (anh vẫn đang cân nhắc).

## Proof (02/11)
- pytest 144 (`test_silent_liker_is_invited_once`, `test_no_gift_hint_past_top_tier`).
- 8811 (bản overlay build lại): e2e control_panel 28/28, ux_scenarios 0 lỗi; fuzz 395 chuyến × 5 bến OK. 8811 đã tắt.
