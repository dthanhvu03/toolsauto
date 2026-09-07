# Form

**Ô nhập chuẩn** (bộ lọc, dán link): `.app-input` / `.app-select` — cao 40, radius 8, nền sunken, viền edge, chữ 12 ink, placeholder ash; focus viền torch + ring 3px. Nhãn 12px mist đặt trên:

```html
<div class="field"><label>Trạng thái</label>
  <select class="app-select"><option>Tất cả</option><option>Mới (NEW)</option></select></div>
<div class="field"><label>Tìm URL</label><input class="app-input" style="width:288px" placeholder="tiktok.com / reel / …"></div>
```
Đặt width bằng inline style (288 / 128 px); `.app-select` tự co theo nội dung.

**Checkbox** `.chk`: input gốc 16px, accent torch, chữ 14 ink-soft: `<label class="chk"><input type="checkbox" checked> Xử lý ngay</label>`.

**Toggle** `.settings-toggle` (khay 48×32 ledge, knob 24 surface; bật = gradient torch):
`<button type="button" class="settings-toggle" role="switch" aria-checked="true"><span class="settings-toggle-knob"></span></button>`

**Ô nhập trong thẻ settings** (cao 36, radius 12, nền sunken):
- số: `<span class="settings-key">reup.subtitle_font_size</span> … <input class="settings-num" type="number" value="64"><span class="settings-unit">px</span>` (mono, canh phải);
- chuỗi: `.settings-text` (mono, full width); secret: `type="password"` + placeholder "•••••••• (đã có — để trống giữ nguyên)";
- enum: `.settings-select`; văn bản dài: `.settings-textarea` (mono 11px, min-height 96, resize dọc).

Mỗi ô settings đi trong `.scard` (xem card Thẻ): tiêu đề 14/600 → key mono 10px → mô tả 11px → hàng nhập. Trạng thái disabled: `disabled` + opacity .55.
