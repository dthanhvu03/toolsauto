# Chữ — Foundations

Ba họ font, nạp sẵn qua `styles.css`:

- `--font-display` **Syne** (600/700/800): tiêu đề trang `.page-title`, tiêu đề khối `.sec-head h2`, số lớn trong thẻ tổng quan. Không dùng cho thân bài.
- `--font-sans` **Figtree** (400–700): mọi chữ còn lại.
- `--font-mono`: key cấu hình (`.settings-key`, `.scard .k`), giá trị số (`.settings-num`), ID hàng (`td.id`), code inline.

Thang cỡ (biến → px): `--text-2xs` 10 · `--text-xs` 11 · `--text-sm` 12 · `--text-md` 14 (mặc định body) · `--text-lg` 16 · `--text-xl` 20 · `--text-2xl` 24 · `--text-3xl` 30. Tiện ích: `.text-cave-2xs` … `.text-cave-2xl` (đi kèm line-height), `.label-cave` (nhãn uppercase 10px/700 tracking rộng), `.font-display`, `.font-mono`.

Vai trò thường gặp:
- Tiêu đề trang: `.page-title` (Syne 24/700, tracking hẹp) + `.page-subtitle` (11px mist, tối đa 42rem).
- Nhãn trên ô nhập: 12px `--color-mist` (`.field > label`).
- Mô tả phụ trong thẻ: 11px mist, line-height 1.6 (`.scard .d`).
- Nhãn nhóm sidebar / thead: 10–11px uppercase `--color-ash`.

Chữ tiếng Việt có dấu ở mọi chỗ hiển thị. Số liệu canh phải + `tabular-nums`.
