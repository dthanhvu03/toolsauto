# [Bàn giao] Contextual Logging (Job ID) cho FacebookAdapter

Tài liệu này hướng dẫn cách thay đổi cơ chế Logging trong `FacebookAdapter` để mọi dòng log tự động đính kèm `[Job ID]`, giúp việc vận hành nhiều worker song song trở nên minh bạch và dễ quản lý.

## Mục tiêu
- **Phân biệt Log**: Đảm bảo mỗi dòng log trong `logs/app.log` đều bắt đầu bằng `[Job XXX]` để không bị lẫn lộn giữa các Job chạy cùng lúc.
- **Tối ưu Vận hành**: Cho phép dùng lệnh `grep "[Job 402]"` để xem toàn bộ lịch sử của một Job duy nhất.
- **Giữ sạch Code**: Không cần sửa hàng trăm dòng `logger.info`, chỉ cần sửa ở tầng khởi tạo.

---

## Chi tiết thay đổi Kỹ thuật

### 1. Định nghĩa JobLoggerAdapter
**File**: `app/adapters/facebook/adapter.py`

```python
class JobLoggerAdapter(logging.LoggerAdapter):
    """Tự động chèn [Job ID] vào đầu mỗi thông điệp log."""
    def process(self, msg, kwargs):
        job_id = self.extra.get('job_id', 'Unknown')
        return f"[Job {job_id}] {msg}", kwargs
```

### 2. Khởi tạo Contextual Logger
**File**: `app/adapters/facebook/adapter.py`

- Trong phương thức `publish(self, job: Job, ...)`:
    - Khởi tạo `self.logger = JobLoggerAdapter(logger, {'job_id': job.id})`.
- **Quan trọng**: Cần chuyển đổi toàn bộ các lệnh `logger.info`, `logger.warning`, `logger.error` trong class thành `self.logger.info`, `self.logger.warning`, v.v.

### 3. Cập nhật các phương thức bổ trợ
Các phương thức như `_normalize_post_url`, `_capture_failure_artifacts`, hoặc các hàm helper trong `FacebookReelsPage` cũng cần được truyền hoặc truy cập vào logger có ngữ cảnh này để đảm bảo tính đồng bộ.

---

## Các bước thực hiện

1.  **Bước 1**: Thêm định nghĩa `JobLoggerAdapter` vào đầu file `adapter.py`.
2.  **Bước 2**: Tại hàm `publish` của `FacebookAdapter`, dòng đầu tiên phải là thiết lập `self.logger`.
3.  **Bước 3**: Chạy lệnh tìm kiếm và thay thế (Search & Replace) toàn bộ `logger.` thành `self.logger.` bên trong phạm vi class `FacebookAdapter`.
4.  **Bước 4**: Kiểm tra các class Page (như `FacebookReelsPage`) xem có đang dùng global `logger` hay không. Nếu có, cần sửa để nhận logger từ Adapter truyền vào.

---

## Kế hoạch Kiểm tra (UAT)
1.  **Kiểm tra Job đơn**: Chạy 1 Job, mở file `logs/app.log`, xác nhận mọi dòng log từ `FacebookAdapter` đều có tiền tố `[Job XXX]`.
2.  **Kiểm tra Job song song**: Chạy 2 Job khác nhau cùng lúc bằng PM2, xác nhận các dòng log xen kẽ nhau nhưng vẫn phân biệt được nhờ ID ở đầu dòng.
3.  **Kiểm tra Lọc (Grep)**: Chạy lệnh `tail -f logs/app.log | grep "[Job 402]"` và xác nhận chỉ thấy log của đúng Job đó.
