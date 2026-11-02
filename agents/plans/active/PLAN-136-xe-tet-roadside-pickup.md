# PLAN-136 — Xe Tết: bắt xe dọc đường

- Status: Code + test xong (02/11), chưa nạp 8810 (anh đang live)
- Executor: Claude Code (anh yêu cầu 02/11: «có dịch vụ bắt xe dọc đường nữa, em học cái đó… qua địa phận của họ rồi mà họ
  bình luận thì báo xe sau, chưa qua thì ra chỗ đón lên xe bắt dọc đường»)

## Tìm hiểu (02/11)
- Xe tuyến cố định đón / trả khách ở bến hoặc **điểm dừng đón trả khách** đã công bố dọc tuyến (Thông tư 36/2024/TT-BGTVT,
  hiệu lực 01/01/2025); đón trả sai chỗ bị phạt (1–2 triệu, tước bằng 1–3 tháng — theo tin báo); có nơi giới hạn dừng ≤ 3 phút
  (Vĩnh Phúc). Người đi hẹn nhà xe, ra điểm đón chờ (ví dụ điểm đón QL1 đoạn Linh Trung, Thủ Đức).
  Nguồn: lsvn.vn/tag/xe-khach.html, plo.vn (bến xe vs điểm đón QL1), daibieunhandan.vn (xe khách đón trả sai QL1),
  tuoitre.vn (xe khách dừng giữa đường đón khách, 02/10/2025).
- Trong game: «ra **điểm đón** ở tỉnh X chờ» — không vẽ cảnh xe dừng giữa quốc lộ (game tránh cảnh mất an toàn mùa Tết).

## Luật (xe chính đang trên đường: chạy / nghỉ trạm / thả khách)
- Quê P còn ở phía trước (điểm trả chưa tới hoặc tỉnh xe sẽ đi qua) + còn giường → đặt giường ngay, P thành điểm trả (chèn
  đúng km, tách chặng nếu cần, giữ vị trí xe), hẹn điểm đón cách xe ~20 giây thật (chuyến bị nén); xe tới → «tấp vô đón».
  Xe đang nghỉ trạm / thả khách → lên luôn tại chỗ.
- Xe đã qua P hoặc tới P dưới ~30 giây → giữ chỗ xe sau, thẻ ghi «Xe vừa qua P rồi», lơ xe báo (8 giây / câu).
- Hết giường / P ngoài đường → giữ chỗ xe sau như cũ.

## Proof
- pytest 134: đón tỉnh phía trước (vé có điểm đón, điểm trả chèn đúng, «xe nào» báo điểm đón, xe đón rồi trả đúng tỉnh), tỉnh
  đã qua → xe sau + lơ xe báo, nghỉ trạm → lên tại chỗ; câu lơ xe 3 kiểu đủ chỗ điền, không «nha».
- Fuzz 2 giờ × 5 bến: ai trên xe cũng có điểm trả phía trước, chặng tăng dần theo km.

## Thêm từ live 02/11 (anh gửi ảnh comment)
- **Địa chỉ chi tiết:** «qua hải phòng ngõ 174 phường Lê Thanh Nghị» gõ nhiều lần không lên xe (bị coi là tán gẫu). Giờ tên tỉnh
  + chữ địa chỉ (ngõ, ngách, hẻm, kiệt, phường, xã, thôn, xóm, ấp, huyện, quận, thị trấn, khu phố, số nhà, tỉnh, thành phố)
  hoặc «qua / ở / tại / đến» → đặt vé về tỉnh đó; không tính «đường» («đường về Hà Nội xa quá» vẫn là tán gẫu). Thẻ vé chỉ ghi
  tên tỉnh, không hiện lại địa chỉ. Còn hạn chế: phường Lê Thanh Nghị thuộc Hải Dương cũ (nay trong TP Hải Phòng) — game hiểu
  «hải phòng» là Hải Phòng cũ; hiểu tới cấp phường cần bộ dữ liệu phường / xã → tỉnh cũ.
- **Vừa về quê lại ra bến (anh chọn: cho đi, lơ xe trêu):** vẫn đặt vé; lơ xe trêu một lần «mới về Nghệ An đã quay ra bến,
  quên đồ hả» (10 giây / câu); thẻ vé ghi «chuyến thứ N».
- **Cho xe ra bến khác (anh chọn: tự đổi theo người xem):** «từ Hà Nội», «bến Giáp Bát», «ra bến Đà Nẵng», «từ Sài Gòn»… =
  phiếu gọi bến (15 phút); «từ Hà Nội về Nghệ An» = gọi bến + đặt vé. Bến đủ 3 phiếu → lần tới bến hiện tại trống (luật đổi bến
  cũ) xe ra bến đó, lơ xe báo, thiết lập «bến đi» tự cập nhật. HUD: thông báo gọi bến «2/3», chữ lớn khi đổi, gợi ý «Muốn xe
  ra bến khác? Gõ «từ Hà Nội»»; /control mục Bến đi hiện số phiếu. Câu hỏi «ra bến khác / đổi bến» lơ xe trả lời sẵn cách gọi.
- Proof: pytest 137 (địa chỉ, gọi bến đủ / thiếu / hết hạn / bến còn khách, gọi bến + đặt vé, trêu một lần + chuyến thứ 2).

## Thêm từ live 02/11 (lượt 2, anh dặn)
- **«Đây là chuyến đi …, ai chuyến khác đợi chuyến sau»:** người khác hướng giữ chỗ (không tính người «xe đã qua») → lơ xe gom
  tối đa 3 tỉnh, nói một câu mỗi 20 giây («Đây là chuyến đi Hà Nội, ai đi Cà Mau, Đồng Tháp, Bến Tre đợi chuyến sau»); HUD
  lúc đón khách thêm dòng «🚌 Chuyến này đi Hướng … · hướng khác đợi chuyến sau».
- **«10s lên xe thì không cho ai xuống»:** BOARD_LOCK = 10 giây cuối giờ đón (xe đầy là đếm ngược 10 giây) — người đã ngồi
  không đổi tỉnh / «không về» được, lơ xe nhắc. Test cũ «đổi hướng nhường giường lúc xe đầy» viết lại theo luật mới.
- **Nhận đủ 63 tỉnh:** thử 118 cách gõ (tên, viết tắt, biển số, không dấu, tên mới) → sót 7 (Vinh, Đồng Hới, Đông Hà, Tam Kỳ,
  Phủ Lý, BMT, TT Huế); thêm `CITY_ALIASES` tên thành phố tỉnh lỵ / nơi quen gọi cho 59 tỉnh (4 thành phố trung ương tên trùng).
  «anh Vinh ơi đẹp quá» vẫn là tán gẫu.
- Proof: pytest 139; fuzz 422 chuyến × 5 bến 0 vi phạm (~900 lượt đón dọc đường); e2e control_panel 28/28.
