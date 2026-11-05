# PLAN-151 — Xe Tết: đối kháng xoay quanh quà (PK có giờ vàng, lật kèo phút cuối)

- Status: Code + test xong (04/11), chưa nạp 8810
- Executor: Claude Code (anh 04/11: «live mà không có tiền chán quá» → «kế hoạch» → «em triển khai cho anh đi em»)
- Nền: chế độ đối kháng đã có (commit 1055918): hai hướng đầu hàng chờ đấu điểm theo quê, hướng nhiều điểm chạy chuyến sau.

## Vì sao
Số liệu 4 buổi (02–03/11): ~46 người xem trung bình, 1.265 bình luận + 23 nghìn tim / 78 phút nhưng chỉ 69 xu cả 4 buổi,
gần như toàn quà 1 xu. Game có người chơi, thiếu lý do tặng nhiều hơn 1 xu. Điểm đối kháng hiện tại: 1 xu = 5 điểm = 100 tim
→ tim quyết thắng thua, quà gần như không đổi được kết quả.

## Phạm vi

### 1. Quà quyết trận
- 1 xu = 20 điểm (nay 5). Bình luận 1 điểm / 15 giây / người, 20 tim = 1 điểm: giữ nguyên để người không tặng vẫn góp được.
- Hệ số chỉnh được trên /control (mục «⚔️ Đối kháng»), không phải sửa code khi muốn đổi.

### 2. Khoá cặp đấu đầu chuyến
- Hai hướng đấu được chốt lúc xe xuất bến, không đổi giữa chừng (nay cặp tính lại liên tục — quà «lên đầu hàng» của hướng thứ
  ba có thể đẩy một bên ra khỏi trận giữa chừng, điểm đang có mất ý nghĩa).
- Hướng bị khoá hết người chờ giữa trận (lên xe tăng cường…) → trận huỷ, chuyến sau theo thứ tự đặt vé.

### 3. Giờ vàng
- GIỜ VÀNG = 60 giây cuối trước khi xe về bến (dùng giờ dự tính `_arrivals()` có sẵn): điểm từ quà x2.
- Màn hình: thanh PK đổi màu vàng nhấp nháy + đồng hồ đếm ngược «⏱ 0:42 · quà x2».
- Lơ xe hô khi vào giờ vàng và một lần ~20 giây cuối: «Cà Mau còn thua 40 điểm, 20 giây nữa».
- Xe đang bị chặn / xem video / dừng thả khách thì đồng hồ đứng theo (như câu đố), không mất giờ vàng.

### 4. Người góp nhiều nhất bên thắng
- Mỗi bên ghi người góp điểm nhiều nhất trận. Hết trận: thẻ «⚔️ Cà Mau thắng · 👑 MVP Út Ráng 120 điểm», tên MVP lên băng rôn
  chuyến đó (băng rôn xuất bến) và lơ xe đọc tên.
- Thanh PK hiện tên người đang góp nhiều nhất mỗi bên (dòng nhỏ dưới thanh, thay dòng gợi ý hiện tại).

### 5. Người chưa có quê
- Người tặng quà mà chưa gõ tỉnh / chưa từng về quê: nay quà không tính điểm cho bên nào.
- Đề xuất: tính cho bên đang thua (giữ trận sát, ai cũng góp được) + thông báo «🎁 Bé Su tiếp sức Cà Mau». Cần anh chọn.

## Không làm
- Không đổi giá / bảng quà chung (lên đầu hàng 1 xu, xe chạy nhanh theo xu) — để kế hoạch riêng nếu anh muốn.
- Không thêm thẻ bật lên mới ngoài thanh PK và thẻ kết quả (giữ màn gọn theo sửa 2956d7f).

## Đã chốt (anh bảo triển khai, dùng mức đề xuất)
1. 1 xu = 20 điểm; 2. giờ vàng 60 giây — cả hai chỉnh trên /control «⚔️ Đối kháng» (versus_xu 1–200, versus_golden_s 0–180).
3. Quà người không thuộc bên nào (chưa có quê HOẶC quê hướng thứ ba) → bên đang thua, thông báo «🎁 X tiếp sức …».

## Kiểm tra (khi làm)
- Test engine: quà đổi kết quả thắng thua; cặp khoá không đổi khi hướng thứ ba được quà; giờ vàng nhân đôi đúng cửa sổ và
  đứng khi xe dừng; MVP đúng người; quà người chưa có quê vào bên thua.
- 8811: chụp thanh PK lúc thường / giờ vàng / thẻ kết quả, phòng đông giả lập 15/giây, 0 lỗi JS.
- Không nạp 8810 khi anh chưa bảo.

## Proof (04/11)
- pytest 217 (`test_versus_gifts_decide_golden_minute_mvp_and_locked_pair`: 10 xu thắng 2000 tim; hướng thứ ba được quà
  không chen vào cặp; quà người lạ + người quê thứ ba vào bên thua; giờ vàng x2 + lơ xe hô; MVP lên băng rôn), ruff sạch.
- 8811: Cà Mau 120 / Đà Nẵng 201 + dòng «Góp nhiều nhất»; giờ vàng 0:53, Út Cà Mau 5 xu = 200 điểm lật kèo 320; Cà Mau thắng,
  băng rôn «Út Cà Mau»; 0 lỗi JS. Ảnh scratchpad pk_normal.png, pk_golden.png, pk_win.png.
