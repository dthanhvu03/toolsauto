# PLAN-005: Quy hoạch tập trung Host & Configuration

## Trạng thái: Proposed
**Người lập**: @Antigravity
**Ngày**: 2026-04-18

## 1. Bối cảnh (Context)
Hiện tại, nhiều đường dẫn (URLs) của các nền tảng (Facebook, TikTok, Instagram) và các dịch vụ nội bộ (VNC, Proxy) đang bị viết cứng (hardcoded) trực tiếp trong code adapter và template. Điều này gây khó khăn khi cần thay đổi hạ tầng hoặc chuyển đổi môi trường.

## 2. Mục tiêu (Objectives)
- Tập trung 100% Hostnames và Endpoints vào `app/config.py`.
- Cho phép ghi đề các Host này thông qua biến môi trường (.env).
- Xóa bỏ mọi chuỗi `https://...` cứng trong logic nghiệp vụ.

## 3. Các bước thực hiện (Execution Strategy)

### Phase 1: Cấu trúc lại `app/config.py` - @Antigravity
Thêm các nhóm hằng số mới:
- **Platforms**: `FACEBOOK_HOST`, `TIKTOK_HOST`, `INSTAGRAM_HOST`.
- **Infrastructure**: `VNC_HOST`, `VNC_PORT`, `MCP_PROXY_PORT`.
- **CDN Assets**: `CDN_HTMX`, `CDN_TAILWIND`, `CDN_CHARTJS`.

### Phase 2: Refactor Adapters - @Codex
- Thay thế các chuỗi cứng trong `app/adapters/facebook/`, `tiktok/`, `instagram/` bằng hằng số từ config.
- Ví dụ: `self.page.goto(config.FACEBOOK_HOST)` thay vì `self.page.goto("https://www.facebook.com")`.

### Phase 3: Refactor Routers & Templates - @Codex
- Cập nhật các link VNC/Proxy trong `syspanel.py` và `platform_config.py`.
- Thay các thẻ `<script src="...">` trong layout HTML bằng biến từ config (truyền qua template context).

### Phase 4: Kiểm chứng (Verification) - @Antigravity
- Chế độ "Dry-run": Kiểm tra log xem các request có đi đúng host mới không.
- Smoke test: Mở dashboard và kiểm tra các thư viện CDN có load thành công không.

## 4. Rủi ro & Giải pháp (Risks & Mitigations)
- **Rủi rơ**: Quên dấu `/` ở cuối host làm hỏng việc nối chuỗi (URL join).
- **Giải pháp**: Sử dụng hàm chuẩn hóa `.rstrip("/")` trong file config để đảm bảo tính nhất quán.

## 5. Tiêu chí Nghiệm thu (Acceptance Criteria)
- `grep "https://www.facebook.com"` không còn xuất hiện trong thư mục `app/adapters/`.
- Mọi Host bên ngoài đều có thể cấu hình được qua `.env`.
