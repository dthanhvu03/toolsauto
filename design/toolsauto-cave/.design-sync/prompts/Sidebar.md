# Sidebar

Điều hướng cố định bên trái, rộng `--size-sidebar`, nền deep, viền phải edge, cuộn ẩn thanh cuộn. Brand "Auto Publisher" cao 64 (Syne 700). Copy nguyên cấu trúc thật của tool:

```html
<aside id="sidebar">
  <div class="sidebar-brand">Auto Publisher</div>
  <nav class="sidebar-nav">
    <p class="nav-section-label">Chung</p>
    <a class="nav-item" href="#"><svg …></svg><span>Tổng quan</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Hàng đợi job</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Tài khoản</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Kho affiliate</span></a>
    <p class="nav-section-label">Facebook</p>
    <a class="nav-item is-active" href="#"><svg …></svg><span>Nội dung viral</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Nguồn TikTok</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Phân tích &amp; tăng trưởng</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Nhiệm vụ FB</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Vi phạm Facebook</span></a>
    <p class="nav-section-label">Threads</p>
    <a class="nav-item" href="#"><svg …></svg><span>Threads</span></a>
    <a class="nav-item nav-item-sub" href="#"><span>Hàng đợi Threads</span></a>
    <p class="nav-section-label">Giám sát</p>
    <a class="nav-item" href="#"><svg …></svg><span>Nhật ký hệ thống</span></a>
    <p class="nav-section-label">Cấu hình</p>
    <a class="nav-item" href="#"><svg …></svg><span>Hub cấu hình</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Cài đặt vận hành</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>AI Studio</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Cấu hình nền tảng</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Panel hệ thống</span></a>
    <a class="nav-item" href="#"><svg …></svg><span>Cơ sở dữ liệu</span></a>
    <div class="nav-divider"></div>
    <button type="button" class="nav-item nav-item-danger"><svg …></svg><span>Đăng xuất</span></button>
  </nav>
</aside>
```

- `.nav-item`: 14px mist, icon 20px (heroicons outline, `stroke="currentColor"`), radius 8; hover nền torch-dim; `.is-active` chữ torch 600 trên torch-dim; `.nav-item-sub` thụt vào, 12px; `.nav-item-danger` màu danger.
- `.nav-section-label`: 10px uppercase ash. `.nav-divider`: đường kẻ edge.
- Đúng thứ tự & tên mục như trên (tool thật); mục đang mở = trang đang mockup.
