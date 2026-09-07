# ToolsAuto Cave — quy ước dựng giao diện

ToolsAuto là tool nội bộ (FastAPI + Jinja + HTMX), theme tối "Cave". Design system này là
**HTML + CSS thuần** — không có component React. `window.ToolsAutoCave` rỗng: đừng import gì
từ đó. Dựng mockup bằng markup tĩnh với đúng vốn class và biến CSS dưới đây; mọi thứ khác
(layout glue) viết inline style hoặc class riêng nhưng **chỉ dùng biến `var(--*)`**, không
hard-code màu/cỡ chữ.

## 1. Bọc & nền

- Trang: `<body class="theme-cave">`. Nền trang `var(--color-bg)` (#0c0b0a), chữ `var(--color-ink)`.
- Font đã nạp qua `styles.css`: Figtree (`--font-sans`, thân), Syne (`--font-display`, tiêu đề),
  mono (`--font-mono`). Tiêu đề dùng `.page-title` / `.font-display`.
- Chữ hiển thị **tiếng Việt có dấu**. Bảng số liệu dùng `font-variant-numeric: tabular-nums`.

## 2. Vốn từ (chỉ những tên có thật trong styles.css)

| Việc | Dùng |
|---|---|
| Bề mặt | `--color-bg` → `--color-surface` (thẻ) → `--color-surface-raised` (nút, thẻ settings) → `--color-ledge`; sunken `--color-surface-sunken` (ô nhập, sidebar) |
| Chữ | `--color-ink` chính · `--color-ink-soft` nút · `--color-mist` phụ · `--color-ash` mờ nhất · `--color-ink-inverse` trên nền torch |
| Viền | `--color-border` (edge) · `--color-border-strong` · focus `--color-focus-ring` |
| Nhấn | torch (cam) `--color-torch` / `-dim` / `-border` · `--gradient-torch` cho primary |
| Trạng thái | moss/lichen (ok) `--color-moss-*`, `--color-lichen` · danger `--color-danger-*` · info `--color-info` · status viral `--color-status-new-*`, `--color-status-ready-*` · job indigo `--color-job-*` · mega `--color-mega-*` · reup emerald `--color-reup-*` · boost `--color-boost-*` |
| Cỡ chữ | `--text-2xs` 10 · `--text-xs` 11 · `--text-sm` 12 · `--text-md` 14 · `--text-lg` 16 · `--text-xl` 20 · `--text-2xl` 24 |
| Khoảng cách | `--space-1`…`--space-12` (4px bước) · radius `--radius-sm/md/lg/xl/2xl/pill` (6/8/12/16/20/999; badge, pill, nút hàng bảng dùng 4px cố định) · `--shadow-soft`, `--shadow-panel` |
| Cỡ control | `--size-control-xs/sm/md/lg` (28/32/36/40) · icon `--size-icon-sm/md/lg` (14/16/20) · `--size-sidebar` 256 |

**Class thành phần** (định nghĩa trong `tokens/tokens.css` + `tokens/components.css`):

- Thẻ: `.app-card` + `.app-card-header` + `.app-card-body`; `.cave-card`, `.cave-card-raised`.
- Nút: `.app-btn` (36px) + `.app-btn-primary` | `.app-btn-torch` | `.app-btn-job` | `.app-btn-danger` |
  `.app-btn-ghost` | `.app-btn-sm` | `.app-btn-xl`; bận HTMX: `.viral-busy-btn` với `.btn-idle` /
  `.btn-busy` (thêm `.htmx-request` để hiện trạng thái bận). Nút hàng bảng: `.row-btn` +
  `.row-btn-torch/-danger/-ready/-job`; xoá: `.icon-btn`. Settings: `.save-all`, `.reset-link`.
- Form: `.app-input`, `.app-select` (40px), nhãn `.field > label`; `.chk` (checkbox);
  `.settings-toggle` + `.settings-toggle-knob` (`aria-checked`); ô trong thẻ settings:
  `.settings-num`, `.settings-text`, `.settings-select`, `.settings-textarea`, `.settings-key`, `.settings-unit`.
- Badge: job `.app-badge` + `-green/-amber/-blue/-red/-slate`; viral `.st` + `.st-new/-processing/
  -drafted/-ready/-failed/-boost` (processing kèm `<span class="dot pulse">`); pill `.pill` +
  `-job/-aff/-mega/-reup`; nền tảng `.pf` + `-youtube/-tiktok/-facebook/-instagram`; nguồn giá trị
  `.src` + `-database/-override/-env/-restart/-torch`; `.cave-badge-torch/-moss/-danger`; `.cave-dot-torch/-moss`.
- Khối settings: `.sec` > `.sec-head` (h2 + `.dot` + `.count`) + `.sec-body`; thẻ `.scard` > `.scard-top`
  (`.title`, `.k`, `.d`, `.pills`) + `.scard-input` + `.scard-foot`. Thanh tin: `.info-bar`.
- Bảng: `.data-table` bọc `<table>`; ô `td.id/.center/.right/.views/.acc`; cột tiêu đề `.title` (`a`,
  `.reup`, `.tries`); `.sub`, `.err`, `.actions`, `.reup-again`; ảnh `.thumb` (+ `.tag`) / `.thumb-plain`.
- Thanh bộ lọc: chip đếm `.counts` > `.cnt` + `.cnt-new/-processing/-drafted/-ready/-failed/-all`.
- Thông báo: `.toast` + `.toast-error` | `.toast-warning` (`.ico`, `.msg`, `.close`); `.cave-banner` +
  `-ok/-warn/-err`; thanh bận nền `.busy-bar` (+ `<svg class="spin">`).
- Khung trang: `.shell` > `aside#sidebar` (`.sidebar-brand`, `.sidebar-nav`, `.nav-section-label`,
  `.nav-item` + `.is-active` / `.nav-item-sub` / `.nav-item-danger`, `.nav-divider`) + `main` > `.page` >
  `.page-head` (`.left`: `.silo-breadcrumb` (`.crumb-silo`, `.crumb-sep`, `.crumb-current`), `.page-title`,
  `.page-subtitle`; `.right`: `.gemini`, `.health`).

## 3. Nguồn sự thật — đọc trước khi tạo kiểu

`styles.css` → `tokens/tokens.css` (biến + lớp nền `.app-*`, `.cave-*`, shell) và
`tokens/components.css` (badge, nút hàng, form settings, bảng, toast). Mỗi card có
`components/<Nhóm>/<Tên>/<Tên>.prompt.md` mô tả cách ghép và lưu ý; `<Tên>.html` là markup mẫu
copy được. Phần "Những chỗ phải đoán" bên dưới liệt kê chỗ bundle vẽ theo ý đồ khác tool đang chạy.

## 4. Mẫu dựng một màn hình

```html
<body class="theme-cave">
<div class="shell">
  <aside id="sidebar"> …copy từ card Sidebar… </aside>
  <main><div class="page">
    <div class="page-head">
      <div class="left">
        <nav class="silo-breadcrumb"><span class="crumb-silo">Facebook</span><span class="crumb-sep">›</span><span class="crumb-current">Nội dung viral</span></nav>
        <h1 class="page-title">Nội dung viral</h1>
        <p class="page-subtitle">Quét → xử lý → job duyệt.</p>
      </div>
      <div class="right"><a class="health" href="#">Sức khỏe hệ thống</a></div>
    </div>
    <div class="app-card" style="padding:16px">
      <div style="display:flex;gap:12px;align-items:flex-end">
        <div class="field"><label>Trạng thái</label><select class="app-select"><option>Tất cả</option></select></div>
        <button class="app-btn app-btn-primary">Áp dụng</button>
        <button class="app-btn app-btn-torch">Quét ngay</button>
      </div>
      <div class="counts" style="margin-top:16px"><button class="cnt cnt-new">Mới 3</button><button class="cnt cnt-all">Tất cả</button></div>
      <div class="data-table"><table>
        <thead><tr><th>ID</th><th>Tiêu đề</th><th>Trạng thái</th><th style="text-align:right">Thao tác</th></tr></thead>
        <tbody><tr>
          <td class="id">66</td>
          <td class="title"><a href="#">Bí quyết gấp quần áo gọn 3 giây</a></td>
          <td><span class="st st-new">Mới quét</span></td>
          <td class="right"><div class="actions"><button class="row-btn row-btn-torch">Xử lý</button></div></td>
        </tr></tbody>
      </table></div>
    </div>
  </div></main>
</div>
</body>
```

Ràng buộc HTMX khi thiết kế: mỗi thao tác đổi **một mảnh** (một hàng bảng, một thẻ, một toast) —
tránh mockup đòi re-render cả trang; trạng thái bận thể hiện bằng `.viral-busy-btn` / `.busy-bar`.
