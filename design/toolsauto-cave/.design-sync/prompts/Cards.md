# Thẻ

**`.app-card`** — nền stone, viền edge, radius 16, shadow soft. Header có viền dưới, body padding 16:

```html
<div class="app-card">
  <div class="app-card-header"><span style="font-weight:600">Nguồn tự động</span><span class="app-badge app-badge-amber">2 kênh</span></div>
  <div class="app-card-body">…</div>
</div>
```
Thẻ số liệu: body chứa số lớn `font-family:var(--font-display);font-size:var(--text-xl);font-weight:700` + chú thích 11px mist.

**Khối section settings `.sec`** — radius 20, header raised với chấm torch và bộ đếm; body là lưới 2 cột thẻ `.scard`:

```html
<div class="sec">
  <div class="sec-head"><h2><span class="dot"></span>Reup — lớp thêm<span class="count">10 items</span></h2></div>
  <div class="sec-body">
    <div class="scard">
      <div class="scard-top">
        <div><div class="title">Cỡ chữ phụ đề</div><div class="k">reup.subtitle_font_size</div><div class="d">Cỡ chữ trên khung 1080×1920.</div></div>
        <div class="pills"><span class="src">default</span></div>
      </div>
      <div class="scard-input"><span class="settings-key">reup.subtitle_font_size</span>
        <div style="flex:1;display:flex;justify-content:flex-end;align-items:center"><input class="settings-num" type="number" value="64"><span class="settings-unit">px</span></div></div>
      <div class="scard-foot"><div>Mặc định: <code>64</code><span class="range">(24–120)</span></div><button class="reset-link" disabled>Reset</button></div>
    </div>
  </div>
</div>
```
Thẻ có override: viền `--color-torch-border` + pill `.src src-torch` "Override" + Reset bật. Thẻ chỉ sửa qua .env: nền pha torch-dim, pill "env only", ô giá trị `••••••••`.

**Banner** `.cave-banner` + `-ok` / `-warn` / `-err` (radius 16, 11px) cho cảnh báo trong trang; **thanh thông tin** `.info-bar` (raised, 12px mist, link torch) đặt đầu trang settings.
