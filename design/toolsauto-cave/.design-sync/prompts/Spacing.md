# Khoảng cách — Foundations

- Space (bước 4px): `--space-1` 4 · `--space-2` 8 · `--space-3` 12 · `--space-4` 16 · `--space-5` 20 · `--space-6` 24 · `--space-8` 32 · `--space-10` 40 · `--space-12` 48. Padding trang `.page` = `--space-8`; body thẻ `.app-card-body` = `--space-4`; gap giữa control trong một hàng 8–12px.
- Radius: `--radius-sm` 6 (cave-badge) · `--radius-md` 8 (nút, ô nhập, thumbnail, app-badge) · `--radius-lg` 12 (thẻ settings, bảng, ô settings) · `--radius-xl` 16 (app-card, toast, banner, nút header) · `--radius-2xl` 20 (khối section settings) · `--radius-pill` 999. Badge viral `.st`, `.pill`, `.pf`, `.src`, `.row-btn`, `.cnt` dùng 4px cố định (giữ đúng template gốc).
- Bóng: `--shadow-soft` (thẻ), `--shadow-panel` (toast, thanh bận, panel nổi). Tối, dùng ít.
- Cỡ control: `--size-control-xs` 28 · `-sm` 32 · `-md` 36 (`.app-btn`, `.app-chip`) · `-lg` 40 (`.app-input`, `.app-select`, nút header). Icon `--size-icon-sm/md/lg` 14/16/20. Sidebar `--size-sidebar` 256.
- Chuyển động: `--dur-fast` / `--dur-base` / `--dur-slow` với `--ease-standard`, `--ease-out`; spinner `.spin`, nhấp nháy `.pulse`, toast trượt vào `.toast-enter`.
- Lớp z: `--z-base` < `--z-sticky` < `--z-sidebar` < `--z-overlay` < `--z-toast`.

Nguyên tắc: touch target tối thiểu 36px (nút hàng bảng) / 44px (nút icon xoá).
