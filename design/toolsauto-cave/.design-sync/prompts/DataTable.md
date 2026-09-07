# Bảng dữ liệu

Bảng material viral (`app_viral_table.html` + `viral_row.html`). Bọc trong `.data-table`; thead 11px uppercase ash trên nền deep; hàng có viền dưới, hover nền torch-dim; ô padding 12, canh trên.

Cột chuẩn: ID · Ảnh · Tiêu đề / URL · Lượt xem · Tài khoản · Trạng thái / Job · Thao tác.

```html
<div class="data-table"><table>
  <thead><tr><th style="width:48px">ID</th><th style="width:104px;text-align:center">Ảnh</th><th>Tiêu đề / URL</th><th style="width:130px">Lượt xem</th><th style="width:130px;text-align:center">Tài khoản</th><th style="width:220px">Trạng thái / Job</th><th style="width:120px;text-align:right">Thao tác</th></tr></thead>
  <tbody><tr>
    <td class="id">61</td>
    <td class="center"><a class="thumb" href="#"><img src="…"><span class="tag">Reup</span></a></td>
    <td class="title"><a href="#">#TikTokshopbacktoschool #sohochic</a><a class="reup" href="#">Mở _reup.mp4</a><div class="tries">Lần thử 1/3</div></td>
    <td class="views">1,240,500<span class="pill pill-mega">Mega</span></td>
    <td class="acc">Page Mẹo Vặt</td>
    <td><span class="st st-drafted">Đã tạo job</span><div class="sub">Reup xong</div>
        <div style="margin-top:6px;display:flex;gap:4px"><a class="pill pill-job" href="#">Job #12 · Nháp</a><span class="pill pill-aff">Aff</span></div></td>
    <td class="right"><div class="actions"><a class="row-btn row-btn-job" href="#">Mở job</a><span class="reup-again">Reup lại? ▾</span><button class="icon-btn" title="Xóa"><svg …></svg></button></div></td>
  </tr></tbody>
</table></div>
```

Theo trạng thái hàng:
- NEW: `.thumb-plain` (icon ảnh 64×64) · `.st-new` · nút `.row-btn-torch` "Xử lý".
- PROCESSING: `.thumb-plain` icon đồng hồ · `.st-processing` + `.dot.pulse` · nút disabled "Đang chạy…" với `.spin`.
- DRAFTED: thumbnail `.thumb` viền emerald + `.tag` Reup · `.st-drafted` + `.sub` + pill job/aff · "Mở job".
- READY: `.st-ready` · "Tải file" `.row-btn-ready` + "Thumbnail" `.row-btn`.
- FAILED: `.st-failed` + `.err` (dòng lỗi truncate 240px) · "Thử lại" `.row-btn-danger`.

Tiêu đề link torch gạch chân, truncate 320px. Tài khoản trống hiện "—". Thanh meta trên bảng ("20 mục · Trang 1 / 1", nút ← Trước / Sau →) là hàng flex 12px mist trên nền face.
