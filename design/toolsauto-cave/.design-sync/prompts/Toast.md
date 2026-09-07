# Toast & thanh bận

**Toast** (`showToast` trong layout): góc trên phải, rộng tối đa 384, nền face, radius 16, shadow panel, trượt vào từ phải 300ms (`.toast-enter`). Tự đóng sau 3s (warning 8s).

```html
<div class="toast toast-enter">
  <svg class="ico" …tick…></svg>
  <p class="msg">Đã lưu cấu hình thành công!</p>
  <button class="close" aria-label="Đóng"><svg …x…></svg></button>
</div>
```
- Mặc định (success): viền moss, icon lichen.
- `.toast-error` và `.toast-warning`: viền danger, icon "!" danger — tool hiện gộp warning vào kiểu error.
- `.toast-warn-proposed`: đề xuất warning viền torch, icon tam giác torch (chưa có trong tool; dùng khi mockup muốn phân biệt).

**Thanh bận nền** `.busy-bar` (`#viral-busy-bar`): cố định giữa đáy màn hình khi pipeline chạy nền; viền torch, spinner torch 16px, chữ 14 ink:
`<div class="busy-bar"><svg class="spin" …></svg><span>Đang xử lý nền (yt-dlp + reup)… bảng tự làm mới mỗi 10s.</span></div>`

Không xếp chồng nhiều toast cùng lúc trong mockup; ưu tiên một toast + thanh bận nếu có việc nền.
