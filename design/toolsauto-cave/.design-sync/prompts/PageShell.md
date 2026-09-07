# Khung trang

Bố cục mọi màn hình trong tool (`layouts/app.html`): sidebar dính trái + `main` cuộn; trong `main` là `.page` (padding 32) với `.page-head` rồi nội dung.

```html
<body class="theme-cave">
<div class="shell">
  <aside id="sidebar">…card Sidebar…</aside>
  <main>
    <div class="page">
      <div class="page-head">
        <div class="left">
          <nav class="silo-breadcrumb" aria-label="Ngữ cảnh nền tảng"><span class="crumb-silo">Facebook</span><span class="crumb-sep">›</span><span class="crumb-current">Nội dung viral</span></nav>
          <h1 class="page-title">Nội dung viral</h1>
          <p class="page-subtitle">Luồng VIP: quét → xử lý → job duyệt. Bộ đếm + thử lại + kiểm tra ffmpeg.</p>
        </div>
        <div class="right">
          <span class="gemini"><span class="cave-dot cave-dot-torch"></span>Gemini: Hết hạn<span class="mode">COOKIE</span><span>Panel hệ thống</span></span>
          <a class="health" href="#"><svg …></svg>Sức khỏe hệ thống</a>
        </div>
      </div>
      <!-- nội dung: .app-card / thanh bộ lọc / .data-table / .sec … -->
    </div>
  </main>
</div>
</body>
```

- Breadcrumb `.silo-breadcrumb`: 10px uppercase; silo (Facebook / Threads / Chung) màu mist, mục hiện tại màu torch.
- `.page-title` Syne 24/700; `.page-subtitle` 11px mist, tối đa 42rem.
- Góc phải header: chỉ báo Gemini (`.gemini`) + nút `.health` "Sức khỏe hệ thống" (40px, radius 16, icon torch). Có thể thêm nút primary của trang vào `.right` nhưng giữ tối đa 3 phần tử.
- Nội dung rộng tối đa theo `main`; card 1280px là kích thước desktop chuẩn của tool.
