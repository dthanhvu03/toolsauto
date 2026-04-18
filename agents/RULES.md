# 📜 Bộ quy tắc ứng xử & Kỷ luật dự án (Agent Rules)

Tài liệu này được tổng hợp từ hệ thống quy tắc cốt lõi của dự án, áp dụng cho mọi AI Agent làm việc trong repo này. **TUÂN THỦ LÀ BẮT BUỘC.**

---

## 🏗️ 1. Tư duy Solo Dev (Core Philosophy)
Dự án được vận hành bởi **1 developer duy nhất**. Mọi đề xuất của AI phải ưu tiên:
1.  **Stability (Ổn định)**: Tool phải chạy xuyên đêm không lỗi.
2.  **Simplicity (Đơn giản)**: Code dễ bảo trì, dễ hiểu, không lạm dụng kiến trúc phức tạp.
3.  **Free (Tối ưu chi phí)**: Ưu tiên giải pháp miễn phí/Open source.
4.  **Speed (Tốc độ)**: Giải quyết vấn đề nhanh và gọn là ưu tiên hàng đầu.

---

## 🛡️ 2. Kỷ luật Hệ thống & An toàn dữ liệu
-   **Database**: Tuyệt đối không thực hiện thao tác xóa (`DELETE`, `DROP`) trên DB sản xuất mà không có sự đồng ý trực tiếp của User. Sử dụng `:memory:` hoặc DB tạm khi test.
-   **Import Discipline**: Luôn đặt `import` ở đầu hàm/file để tránh lỗi `UnboundLocalError`.
-   **Browser Safety**: 
    -   Đóng browser ngay sau khi dùng (Sử dụng `finally` block).
    -   Mỗi tài khoản 1 browser session riêng biệt.
    -   Nghỉ ngẫu nhiên (`random.uniform`) giữa các thao tác để tránh bị Meta quét.
-   **Resource Hygiene**: Tự động xóa file video/ảnh tạm ngay sau khi Job hoàn thành.

---

## 🐙 3. Kỷ luật Git & Công việc (Anti-Improvise)
-   **Minimal Diff**: Chỉ sửa ĐÚNG những gì được giao. Không refactor "tiện thể", không đổi tên biến khi không yêu cầu.
-   **Stop & Ask**: Nếu thấy task mơ hồ hoặc cần sửa >3 file cho 1 bug, hãy DỪNG LẠI và hỏi User.
-   **Commit Quality**: Message rõ ràng (`feat`, `fix`, `refactor`). Không `commit` các file nhạy cảm (`.env`, secrets).
-   **Atomic Changes**: Mỗi commit chỉ giải quyết 1 vấn đề logic duy nhất.

---

## 📝 4. Cấu trúc phản hồi (Response Format)
Khi trao đổi với User, AI cần tuân thủ format:
-   **Fix bug**: Mô tả vấn đề → Giải pháp → Code → Cách test.
-   **Phân tích file**: Tên file → Mục đích → Luồng xử lý (Flow) → Rủi ro (Risk).

---

> **Nguyên tắc vàng**: Nếu nghi ngờ → DỪNG LẠI → HỎI Ý KIẾN → Làm tiếp.
