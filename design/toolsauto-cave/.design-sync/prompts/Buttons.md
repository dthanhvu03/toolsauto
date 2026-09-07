# Nút

**Nút chuẩn `.app-btn`** — cao 36, radius 8, chữ 12/500, nền raised, viền edge, chữ ink-soft; hover viền + chữ torch; `:disabled` opacity .55.

```html
<button class="app-btn">Mới</button>
<button class="app-btn app-btn-primary">Áp dụng</button>      <!-- gradient torch, chữ ink-inverse: 1 nút/khu vực -->
<button class="app-btn app-btn-torch">Quét ngay</button>       <!-- viền torch, nền torch-dim: hành động chính phụ -->
<button class="app-btn app-btn-job">Xử lý 1 mới</button>       <!-- indigo: tạo/mở job -->
<button class="app-btn app-btn-danger">Xoá</button>
<button class="app-btn app-btn-ghost">Tất cả</button>          <!-- nền trong suốt (chip lọc) -->
<a class="app-btn app-btn-xl" href="#"><svg …></svg>Sức khỏe hệ thống</a>   <!-- header: cao 40, radius 16 -->
```

**Trạng thái bận (HTMX)** — nút có 2 nhãn, thêm `.htmx-request` để hiện nhãn bận + spinner và disable:

```html
<button class="viral-busy-btn app-btn app-btn-torch htmx-request" disabled>
  <span class="btn-idle">Quét ngay</span>
  <span class="btn-busy"><svg class="spin" width="14" height="14" …></svg> Đang quét…</span>
</button>
```

**Nút trong hàng bảng `.row-btn`** — nhỏ hơn: chữ 11/700, min-height 36, radius 4, nền trong suốt, hover nền dim theo màu. Biến thể theo trạng thái material: `.row-btn-torch` (NEW → Xử lý), `.row-btn-danger` (FAILED → Thử lại), `.row-btn-job` (DRAFTED → Mở job), `.row-btn-ready` (READY → Tải file), mặc định (Thumbnail). Xoá = `.icon-btn` 44×44 màu danger, chỉ icon thùng rác.

**Nút đặc biệt**: `.save-all` (Lưu tất cả — gradient torch, radius 16, rộng 224); `.reset-link` (chữ 10px uppercase ash, hover danger, `disabled` opacity .3 khi không có override).

Lưu ý: trong tool đang chạy, `.app-btn-torch`/`.app-btn-job` bị CSS theme đè thành nút xám — card này vẽ theo ý đồ.
