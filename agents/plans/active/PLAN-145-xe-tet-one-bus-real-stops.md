# PLAN-145 — Xe Tết: một xe, dừng đón thật bên đường, xếp hàng lên xe, chọn tuyến cho đầy xe

- Status: Code + test xong (03/11), chưa nạp 8810
- Executor: Claude Code (anh 03/11: «chỉ dùng 1 xe … ai muốn đi thì mua vé xếp hàng đợi, hết chuyến quay lại đón … đang đi Đồng
  Nai gần tới Bình Định thì tấp vào, dừng xe bên đường, user Bình Định đứng chờ sẵn, xe tới dừng là lên nếu còn giường … không
  còn trống thì báo xếp hàng … lên xe là phải xếp hàng lên từ từ, đọc tên là lên xe»)

## Luật
- Một xe: không xe tăng cường (PLAN-144 đã tắt); /control ẩn nút xe tăng cường / tự chiếu xe, ghi rõ luật một xe.
- Chọn tuyến chuyến mới: tuyến chở được nhiều người đang chờ nhất (tính cả người làn khác mà xe đi ngang quê, tối đa 24);
  ai chờ quá 10 phút (LANE_MAX_WAIT) thì tuyến của người chờ lâu nhất đi trước.
- Đón dọc đường (giữ luật PLAN-136: quê còn phía trước + còn giường → giữ giường, hẹn điểm đón ~20 giây trước mặt xe; hết
  giường / quê đã qua → xếp hàng chuyến sau): người hẹn sau đứng chung điểm đón sắp tới (còn ≥ 40 % thời gian hẹn) — xe dừng một
  lần cho cả nhóm. Tới điểm đón: xe DỪNG HẲN (3,5 giây + 1,3 giây mỗi người), người chờ đứng bên lề có tên + biển «🚏 ĐIỂM ĐÓN ·
  tỉnh», lên từng người, lơ xe đọc tên; xong chạy tiếp. Đang ở trạm / đầu ngõ: lên luôn (xe vốn đứng).
- Bến: người có vé xếp hàng ở cửa xe (gập dòng 8 người), mỗi giây một người bước lên; giọng đọc gom tên đọc «… lên xe».

## Proof (03/11)
- pytest 165: `test_new_trip_takes_the_fullest_route_unless_someone_waited_too_long`, `test_oldest_ticket_goes_first` (chờ quá
  10 phút thì tuyến đó đi trước), `test_roadside_pickup_for_province_still_ahead` (xe dừng — snapshot có «halt», tốc độ 0 —
  đón rồi trả đúng tỉnh), `test_pickup_at_rest_stop_boards_right_there`.
- 8811 ảnh: bến 12 người xếp hàng sau cửa xe; dừng đón «Đón dọc đường · 🚏 Dừng đón ở Ninh Thuận · 3 người lên», 3 người hẹn
  cùng tỉnh gom một điểm, biển «🚏 ĐIỂM ĐÓN · Ninh Thuận», lơ xe «Ghé điểm đón Ninh Thuận rước Hoa, Mai, Đào»; 0 lỗi JS.
