# ADR-047: Admin áp dụng phí và thuế dự phòng cho báo giá khách

Ngày: 2026-10-23. Trạng thái: chủ bot duyệt. Kế hoạch: PLAN-062.

Trước đây admin chỉ lưu bản nháp `customer_effect=none`; muốn đổi số khách thấy phải sửa `.env` và restart. Chủ bot cần đổi mức dự phòng khi chuyển cá nhân, cá nhân kinh doanh hay hộ kinh doanh mà không sửa code.

Quyết định: admin được áp dụng **phí dự phòng và thuế dự phòng** của báo giá V1.2 từ Telegram. Tỷ lệ chia và hạng thành viên vẫn không đổi được từ Telegram.

Mức áp dụng nằm trong bảng `reserve_policies`, chỉ thêm dòng. Bot đọc dòng mới nhất đã tới `effective_at` mỗi lần báo giá. Chưa có dòng nào thì dùng `.env`. Không sửa `policy_versions` và ràng buộc `customer_effect='none'` của nó.

Loại hình chỉ là nhãn đi kèm, không tự chọn thuế suất. Dự phòng vẫn không phải thuế luật định. Link đã báo giữ số đã lưu và ghi mã mức đã dùng (`+r{id}`).

Hồ sơ thuế cho đối soát và chi trả (TAX_PROFILES.md) chưa nối, làm khi có đơn thật.
