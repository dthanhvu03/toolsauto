# Bảng màu — Foundations

Card tham chiếu, không phải component. Toàn bộ màu của ToolsAuto Cave là biến CSS trong `tokens/tokens.css`; **không hard-code hex** trong mockup.

- Nền/bề mặt theo độ sáng tăng dần: `--color-void` (= `--color-bg`, nền trang) → `--color-deep` (= `--color-surface-sunken`: sidebar, ô nhập, thead) → `--color-stone` (= `--color-surface`: thẻ, bảng) → `--color-face` (= `--color-surface-raised`: nút, thẻ settings, toast) → `--color-ledge` (code inline, khay toggle).
- Chữ: `--color-ink` (chính) · `--color-ink-soft` (nút) · `--color-mist` (phụ) · `--color-ash` (mờ nhất: nhãn nhóm, thead) · `--color-ink-inverse` (trên nền torch).
- Viền: `--color-border` (edge) · `--color-border-strong` · ring focus `--color-focus-ring`.
- Nhấn torch (cam): `--color-torch`, `--color-torch-dim` (nền 14%), `--color-torch-border` (viền 40%), `--gradient-torch` (nút primary, toggle bật).
- Trạng thái: ok = moss `--color-moss`/`--color-moss-dim`/`--color-moss-border` + chữ `--color-lichen`; lỗi = `--color-danger`/`-dim`/`-border`/`-deep`; thông tin `--color-info`/`-dim`.
- Bổ sung cho màn viral (không có trong tool gốc, thêm để badge đúng màu): NEW sky `--color-status-new*`; READY teal `--color-status-ready*`; job indigo `--color-job*`; Mega rose `--color-mega*`; Reup emerald `--color-reup`, `--color-reup-strong`, `--color-reup-border`; Boost amber `--color-boost*`; nền tảng `--color-pf-youtube*`, `--color-pf-tiktok*`; đề xuất `--color-fb`, `--color-ig-from`, `--color-ig-to`.

Quy tắc phối: mỗi trạng thái = bộ ba (chữ, `-dim` nền, `-border` viền) trên nền tối; chỉ một điểm nhấn torch đậm (primary) mỗi khu vực.
