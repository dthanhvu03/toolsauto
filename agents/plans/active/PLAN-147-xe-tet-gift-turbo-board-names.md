# PLAN-147 — Xe Tết: quà làm xe chạy nhanh (mỗi xu x2 thêm 3 giây) + ở bến đọc tên ai thì người đó bước lên

- Status: Code + test xong (03/11), chưa nạp 8810
- Executor: Claude Code (anh 03/11: «tặng quà để xe trước đi nhanh hơn» — chọn «mỗi xu cộng giây»; thắng gấp / chà bánh: bỏ;
  «ở bến xe thì khi lên xe cần phải đọc tên lên xe nhé, đồng bộ chỗ này»)

## Đổi
- Engine: `turbo` (giây) — mỗi xu +3 giây chạy x2, cộng dồn tối đa 180 giây, chỉ trừ khi xe đang chạy; tốc độ không quá x4
  (trừ khi tim đã cao hơn). Snapshot `turbo {left, by}`; thẻ quà «🚀 xe chạy x2 thêm N giây»; lơ xe câu `turbo`.
  (Tên `rush` đã có nghĩa «cao điểm» nên đặt `turbo`.)
- Overlay: bảng quà ô «Mỗi xu 🚀 xe x2 thêm 3 giây»; thanh tuyến «🚀x2.3 · 116s»; chân bảng «🚀 x2 còn Ns nhờ X».
- Đọc tên lên xe: câu đọc tên ưu tiên trên câu lơ xe thường (không bị bỏ), tối đa 5 tên / câu, phòng đông thì câu sau đọc
  tiếp (trước: quá 8 giây thì bỏ lượt). Sự kiện `speak` kèm `names`; overlay cho người trong hàng bước lên đúng lúc tên mình
  được đọc (rải theo độ dài câu). Tắt giọng: mỗi giây một người; đứng đầu hàng 14 giây chưa được đọc thì vẫn lên.

## Proof (03/11)
- pytest 166 (`test_gift_makes_bus_run_twice_as_fast_for_seconds_per_xu`, `test_boarding_names_are_batched_and_everyone_is_read`).
- 8811: 7 người lên xe → 2 câu «Điểm danh An, Bình, Chi, Dũng và Em…» names=[5 tên], «Gấm và Hà…» names=[2 tên]; quà 40 xu →
  thanh tuyến «🚀x2.3 · 116s», chân bảng «🚀 x2 còn 116s nhờ Bé»; 0 lỗi JS.
