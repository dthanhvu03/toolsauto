# ToolsAuto Cave — thư viện component cho Claude Design

Bundle tự chứa để đẩy lên Claude Design (claude.ai/design) làm design system
**ToolsAuto Cave**, sao cho mockup sinh ra đúng màu / nút / font của tool.

Nguồn trích: `app/static/cave-tokens.css`, `app/static/src/app.css`,
`app/templates/layouts/app.html`, `pages/app_viral.html`, `fragments/viral_row.html`,
`fragments/app_viral_table.html`, `fragments/viral_sources.html`, `pages/app_settings.html`,
`fragments/job_row.html`, `ui/badge.html`. Ảnh đối chiếu: `docs/design/2026-09-07-*.png`.

## Quy ước

- **Mỗi component = một file HTML độc lập**, mở trực tiếp là render. Không tham chiếu
  `/static/...`; CSS chung import từ `../tokens.css` + `../components.css`; font Google qua `<link>`
  (`Figtree:wght@400;500;600;700` + `Syne:wght@600;700;800` — đúng `config.CDN_GOOGLE_FONTS`).
- `components.css`: lớp component dùng chung (`.st-*`, `.pill-*`, `.pf-*`, `.src-*`, `.row-btn*`,
  `.icon-btn`, `.settings-*`, `.sec`/`.scard`, `.data-table`, `.thumb`, `.toast`, `.busy-bar`,
  `.counts`/`.cnt-*`, `.shell`/`.page-head`, `.gemini`, `.health`…). Tách ra từ `<style>` của từng
  card để design agent nhận được đúng vốn class mà card minh hoạ. Trong card chỉ còn class demo
  (`.section`, `.row`, `.spec`, `.cap`, `.grid2`).
- **Dòng đầu mỗi file** là marker Claude Design:
  `<!-- @dsCard group="Foundations|Components|Patterns" name="…" subtitle="…" width="…" height="…" -->`
  `height` đặt theo chiều cao render thật (đo bằng Playwright) để thẻ không bị cắt.
- `tokens.css`: khối `:root` giữ **nguyên tên biến** như `cave-tokens.css`. Class `.app-*`
  gốc viết bằng Tailwind `@apply` → đã "giải" thành CSS thuần (gộp override của
  `body.theme-cave`). Cuối `:root` có nhóm **Bổ sung** `--color-status-*`, `--color-pf-*`,
  `--color-job*`, `--color-reup*`, `--color-mega*`, `--color-boost*`: mã màu Tailwind
  (sky/teal/indigo/emerald/rose/amber/red/pink) mà template viral dùng thẳng — không có
  trong `cave-tokens.css`, thêm vào để badge render đúng như tool.
- Chữ hiển thị tiếng Việt có dấu. Nền mọi card là `--color-bg` (#0c0b0a). Không JS —
  hover/checked mô phỏng bằng CSS.
- `_preview/`: ảnh chụp headless Chrome từng card (kiểm tra, không cần upload).

## Danh sách card

| File | Group | Name | Kích thước |
|---|---|---|---|
| `foundations/colors.html` | Foundations | Bảng màu | 960×1980 |
| `foundations/type.html` | Foundations | Chữ | 960×1110 |
| `foundations/spacing.html` | Foundations | Khoảng cách | 960×950 |
| `components/buttons.html` | Components | Nút | 960×720 |
| `components/badges.html` | Components | Badge | 960×900 |
| `components/forms.html` | Components | Form | 960×1060 |
| `components/cards.html` | Components | Thẻ | 960×1160 |
| `components/table.html` | Components | Bảng dữ liệu | 1180×800 |
| `components/toast.html` | Components | Toast | 760×640 |
| `components/filter-bar.html` | Components | Thanh bộ lọc | 1180×460 |
| `patterns/sidebar.html` | Patterns | Sidebar | 280×1040 |
| `patterns/page-shell.html` | Patterns | Khung trang | 1280×800 |

## Những chỗ phải "đoán" hoặc chuẩn hoá (khác với tool đang chạy)

1. **Nút torch-outline / indigo trong viral** (`Quét ngay`, `Xử lý 1 mới`, `Xử lý 3 mới`,
   `Thêm`): template gán class Tailwind `bg-[var(--color-torch)]`, `bg-indigo-500/15`…
   nhưng rule `body.theme-cave .app-btn` (specificity cao hơn) đè lại → ngoài đời chúng
   hiện như nút xám mặc định (khớp ảnh chụp). Bundle này vẽ theo **ý đồ** (`.app-btn-torch`,
   `.app-btn-job`) và ghi rõ; muốn tool khớp mockup thì phải sửa CSS specificity.
2. **Toast warning**: JS `showToast` gộp `warning` vào nhánh `isError` → cùng viền danger,
   chỉ khác thời gian (8s). Card toast vẽ đúng thực tế + thêm một biến thể "đề xuất" viền torch.
3. **Toggle settings**: khay `bg-slate-200`→ledge, knob `bg-white`→surface (bridge remap) nên
   knob tối hơn khay — vẽ đúng như tool. Bật = gradient torch (bridge map `bg-indigo-500`).
4. **Pill DEFAULT / header section settings**: ảnh chụp cho thấy vài chỗ Tailwind chưa được
   bridge (`bg-slate-50/60` header section sáng, pill DEFAULT sáng). Bundle **chuẩn hoá** về
   palette cave (raised + mist) thay vì tái hiện lỗ hổng.
5. **Gemini badge** trên header: fragment trả từ `/health/gemini/ping` (Python) — dựng lại
   theo ảnh chụp (dot + "Gemini: Hết hạn" + chip COOKIE + "Panel hệ thống").
6. **Badge Facebook / Instagram**: tool chỉ có badge YouTube/TikTok trong `viral_sources`;
   Facebook/Instagram dùng `--color-fb` / `--color-ig-*` (đề xuất).
7. **Thumbnail** trong bảng: ảnh thật là jpeg 1 khung từ `_reup`; ở đây thay bằng SVG inline.
8. Hover của `.app-btn` gốc là `hover:bg-slate-50` (Tailwind, không remap) → bundle dùng
   hover viền/chữ torch như `.cave-btn`.

## Đẩy lên Claude Design (/design-sync)

Thư viện là HTML tĩnh nên đi đường "off-script" của skill: `.design-sync/build.mjs` sinh
`ds-bundle/` (styles.css → tokens/{tokens,components}.css, `components/<Nhóm>/<Tên>/<Tên>.html`
+ `.prompt.md`, README = `.design-sync/conventions.md` + chỉ mục, `_ds_sync.json` anchor).

```
node .design-sync/build.mjs                       # sinh ds-bundle/
DS_CHROMIUM_PATH=<chrome.exe> node .ds-sync/package-validate.mjs ./ds-bundle
```

- `.design-sync/config.json`: projectId, tên thư mục ASCII cho từng card (`componentNames`).
- `.design-sync/prompts/<Tên>.md`: hướng dẫn dùng từng card cho design agent (commit).
- `.design-sync/NOTES.md`: ghi chú re-sync. `.ds-sync/` và `ds-bundle/` gitignored.

## Kiểm tra lại

Chụp từng card bằng Playwright + Chrome headless (viewport theo marker), báo lỗi console /
request ≥400 / font; đối chiếu pixel với lần chụp trước khi sửa CSS. Script `shoot.py` nằm ở
scratchpad phiên (không commit) — ý tưởng: mở file, `document.fonts.ready`, `screenshot(full_page)`.
