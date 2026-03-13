# Báo Cáo Phân Tích & Đề Xuất Kiến Trúc Multi-Worker

## Vấn Đề Hiện Tại Của `worker.py`

Hiện tại, `worker.py` đang sử dụng một **vòng lặp đồng bộ, đơn tuyến (Single-threaded Synchronous Loop)**.
Trình tự thực thi mỗi vòng lặp `tick` (mặc định 20-60s) diễn ra như sau:

1. Xác nhận Sinh tồn (Heartbeat).
2. Xử lý bài đăng lên Facebook (`process_single_job`).
3. Nếu không có bài đăng, thì sinh nội dung AI (`process_draft_job`).
4. Dọn dẹp rác (`CleanupService`).
5. Quét Views (`MetricsChecker`).
6. Gửi báo cáo ngày.

**Điểm Thắt Cổ Chai (Bottleneck):**

- Thao tác `process_single_job` (đẩy Video lên Facebook) và `process_draft_job` (điều khiển AI qua giao diện Gemini RPA) là những tác vụ **chạy RẤT LÂU** (có thể 1-3 phút).
- Vì nó chạy trên cùng 1 process đơn, khi Gemini RPA tốn 3 phút để phân tích video, hệ thống hoàn toàn **bị tê liệt**. Không có thao tác dọn dẹp, quét View, hay xử lý bài viết thứ 2 nào diễn ra trong 3 phút đó.
- Dashboard báo "Worker đang kẹt" vì không thể update Heartbeat.

---

## Kiến Trúc Đề Xuất Mới: Hệ Thống Multi-Worker Phân Tán

Thay vì 1 script chạy toàn bộ, chúng ta chia theo 3 vai trò (Role) độc lập chạy song song, có thể viết dưới dạng script con riêng hoặc Thread riêng (khuyên dùng Đa tiến trình - Multiprocess thay vì Thread do Python có GIL).

### 1. The "Publisher Worker" (Chuyên Trực Đăng Bài)

- **Nhiệm vụ:** Tìm Jobs ở trạng thái `PENDING` có hẹn giờ `<= now` để ném vào Facebook Adapter.
- **Tần suất lặp (Tick):** Chạy liên tục (Tick = 30s).
- **Điểm mạnh:** Giúp đảm bảo các bài viết sẽ được xuất bản đúng giờ nhất có thể mà không bị kẹt vì chờ AI sinh chữ.

### 2. The "AI Generator Worker" (Chuyên Trực Sinh Caption)

- **Nhiệm vụ:** Chuyên săn các job trạng thái `DRAFT` cần xin Idea từ Gemini.
- **Tần suất lặp:** Tuỳ chỉnh (Tick = 60s).
- **Điểm mạnh:** RPA Gemini có tỉ lệ gãy cao và chạy ngốn tài nguyên (browser ảo). Cô lập Worker này để chạy trên background không làm ảnh hưởng tính ổn định cốt lõi. Nếu Gemini crash, nó tự fail, các worker khác vẫn sống.

### 3. The "Maintenance & Metrics Worker" (Chuyên Quét Rác & Data)

- **Nhiệm vụ:** Gom các tác vụ Cleanup, MetricsChecker (quét view bài đăng sau 24h), và kích hoạt lệnh gửi Báo cáo Tổng kết Ngày.
- **Tần suất lặp:** Rất thư thả (Tick = 5 phút / lần).
- **Điểm mạnh:** Tác vụ quét dọn là I/O bound nhẹ, không nên nằm tranh giành tài nguyên tốc độ với Job Publish.

---

## Lộ Trình Triển Khai Thực Tế

### Bước 1: Refactor Codebase

- Bẻ file `worker.py` thành:
  - `workers/publisher.py`
  - `workers/ai_generator.py`
  - `workers/maintenance.py`
- Sửa lại Backend DB: Bảng `system_state` có thể cần mở rộng để lưu trạng thái của 3 Worker riêng rẽ thay vì chỉ 1 row duy nhất `current_job_id`.

### Bước 2: Quản Lý Process (Supervisor / Tmux)

- Nếu dùng Tmux, file khởi động `start_workers.sh` sẽ gọi:
  ```bash
  tmux new-session -d -s auto_pub "python workers/publisher.py"
  tmux new-session -d -s auto_ai "python workers/ai_generator.py"
  tmux new-session -d -s auto_maint "python workers/maintenance.py"
  ```
- _(Hoặc có thể build ra một Master Script Python dùng `multiprocessing.Process` quản lý vòng đời 3 con.)_

### Bước 3: Thay Đổi UI Dashboard

- Trên Web UI: Phân vùng **Worker Status** hiện tại thành 3 thẻ (Card) khác nhau: Trang thái của Bộ phận Đăng, Bộ phận AI và Bộ phận Dọn Rác. Bấm Pause (Tạm ngưng) riêng biệt.

## Lợi Ích & Rủi Ro

- **Lợi Ích**: Xóa sạch độ trễ kẹt lệnh. Một video 100MB xử lý AI sẽ không làm chậm các luồng Đăng bài Facebook được lên lịch song song.
- **Rủi Ro**: Phân mảnh cơ sở dữ liệu (Database Locking/Race Condition). Tính năng "Lock Job" (atomic update state sang RUNNING) hiện tại trên SQLAlchemy **phải vô cùng nghiêm ngặt** để 2 Worker không lôi nhầm 1 file. SQLite có độ trễ Lock. Có thể cần tăng Timeout cho DB hoặc xem xét PostgrSQL về lâu dài nếu scale lớn.
