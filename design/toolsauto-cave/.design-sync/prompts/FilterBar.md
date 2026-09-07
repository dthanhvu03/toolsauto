# Thanh bộ lọc

Đầu màn "Nội dung viral": một `.app-card` padding 16 gồm (1) hàng lọc, (2) hàng dán link, (3) link cấu hình, (4) chip đếm trạng thái nối liền với bảng bên dưới.

```html
<div class="app-card" style="padding:16px">
  <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap">
    <div style="display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap">
      <div class="field"><label>Tìm URL</label><input class="app-input" style="width:288px" placeholder="tiktok.com / reel / …"></div>
      <div class="field"><label>Trạng thái</label><select class="app-select">…</select></div>
      <div class="field"><label>Nền tảng</label><select class="app-select">…</select></div>
      <div class="field"><label>Views tối thiểu</label><input class="app-input" type="number" value="0" style="width:128px"></div>
      <div class="field"><label>Mỗi trang</label><select class="app-select"><option selected>100</option></select></div>
    </div>
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <button class="app-btn">Mới</button><button class="app-btn">Lỗi</button>
      <button class="app-btn app-btn-primary">Áp dụng</button>
      <label class="chk"><input type="checkbox"> Tự làm mới</label>
      <button class="app-btn app-btn-torch">Quét ngay</button>
      <button class="app-btn app-btn-job">Xử lý 1 mới</button>
    </div>
  </div>
  <div style="margin-top:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
    <input class="app-input" style="width:384px" type="url" placeholder="Dán link TikTok / YouTube Shorts / Facebook Reel / Instagram Reel">
    <label class="chk"><input type="checkbox"> Xử lý ngay</label>
    <button class="app-btn app-btn-torch">Thêm</button>
    <span style="flex-basis:100%;font-size:var(--text-xs);color:var(--color-mist)">Chỉ dán video bạn được phép dùng lại.</span>
  </div>
  <div class="counts" style="margin-top:16px">
    <button class="cnt cnt-new">Mới 0</button><button class="cnt cnt-processing">Đang xử lý 0</button>
    <button class="cnt cnt-drafted">Đã tạo job 11</button><button class="cnt cnt-ready">Sẵn sàng đăng tay 9</button>
    <button class="cnt cnt-failed">Lỗi 0</button><button class="cnt cnt-all">Tất cả</button>
  </div>
  <!-- ngay dưới: thanh meta + .data-table -->
</div>
```

`.counts` có viền trên/trái/phải và bo góc trên — nó nối thẳng vào thanh meta/bảng (bo góc dưới). Chip `.cnt-*` là bộ lọc nhanh: chip đang chọn có thể tô đậm hơn bằng `.app-chip-active` không áp dụng ở đây — giữ nguyên màu theo trạng thái.
