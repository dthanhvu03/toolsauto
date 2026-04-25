# PLAN-003: Chiến lược Quy chuẩn hóa Kho lưu trữ (Storage Consolidation)

## Trạng thái: Active
**Người lập**: @Antigravity
**Ngày**: 2026-04-18

## 1. Bối cảnh (Context)
Hiện tại, tài nguyên dự án (Videos, Profiles, Thumbnails) đang bị phân tán ở thư mục gốc và các thư mục con trong `content/`. Điều này gây ra sự nhập nhằng trong quản lý và khó khăn khi scale hệ thống.

## 2. Mục tiêu (Objectives)
- Hợp nhất toàn bộ dữ liệu vào một thư mục `storage/` duy nhất.
- Cập nhật `app/config.py` để sử dụng cấu trúc mới.
- Đảm bảo Worker (Publisher, Maintenance) không bị gián đoạn hoạt động.

## 3. Kiến trúc Đề xuất (Proposed Data Schema)
```text
storage/
├── db/          # Các file SQLite
├── profiles/    # Browser Profiles (facebook_*, instagram_*)
└── media/       # Tài nguyên đa phương tiện
    ├── reup/    # Videos gốc
    ├── thumbs/  # Ảnh Thu nails
    └── content/ # Media đã xử lý/done/failed
```

## 4. Kịch bản Thực thi (Execution Strategy) - @Codex chủ trì
1. **Giai đoạn chuẩn bị**: Tạm dừng PM2 workers để tránh xung đột dữ liệu.
2. **Giai đoạn Di chuyển**: 
   - Sử dụng lệnh `mv` để gộp các thư mục từ `content/` về `storage/`.
   - Ưu tiên giữ lại các bản record mới nhất (kiểm tra timestamp).
3. **Giai đoạn Refactor**: Thay đổi các biến đường dẫn trong `app/config.py`.
4. **Giai đoạn Test**: Chạy `dry-run` kiểm tra tính tồn tại của file qua script config.

## 5. Rủi ro & Giải pháp (Risks & Mitigations)
- **Rủi ro**: Mất session Facebook khi move profiles.
- **Giải pháp**: Copy thử nghiệm (cp) trước khi move hoàn toàn, kiểm tra phân quyền (permissions) sau khi move.

## 6. Tiêu chí Nghiệm thu (Acceptance Criteria)
- Thư mục root sạch sẽ (không còn profiles/, reup_videos/, thumbnails/).
- Toàn bộ 5GB+ dữ liệu nằm gọn trong storage/.
- App Frontend và Worker vẫn đọc được dữ liệu bình thường.
