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

## ⚡ 5. Kỷ luật Token & Micro-tasking (AI Resource Discipline)
Để tránh việc Agent bị quá tải context hoặc hết token giữa chừng:
1.  **Micro-tasking**: Chia nhỏ các task lớn (Refactor, Feature) thành các sub-tasks < 300 dòng code.
2.  **Context Cleaning**: Sau mỗi task `Done`, phải cập nhật `handoff` và khuyến khích User lưu trữ (archive) task/plan cũ để giải phóng bộ nhớ cho Agent.
3.  **Atomic Execution**: Mỗi phiên làm việc chỉ tập trung giải quyết 1 mục tiêu cụ thể. Không làm nhiều việc khác domain cùng lúc.

---

> **Nguyên tắc vàng**: Nếu nghi ngờ → DỪNG LẠI → HỎI Ý KIẾN → Làm tiếp.
