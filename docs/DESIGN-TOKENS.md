# Design Tokens — Cave theme

Nguồn sự thật: [`app/static/cave-tokens.css`](../app/static/cave-tokens.css)  
Load trong layout sau `app.css`. Body luôn có class `theme-cave`.

## Màu (semantic)

| Token | Dùng cho |
|-------|----------|
| `--color-bg` / `--color-void` | Nền app |
| `--color-surface` / `--color-stone` | Card, panel |
| `--color-surface-raised` / `--color-face` | Hover / raised |
| `--color-border` / `--color-edge` | Viền |
| `--color-text` / `--color-ink` | Chữ chính |
| `--color-text-muted` / `--color-mist` | Chữ phụ |
| `--color-primary` / `--color-torch` | CTA, focus, active nav |
| `--color-success` / `--color-moss` | Session OK, On |
| `--color-danger` | Lỗi / xóa |

Legacy: `--bg`, `--surface`, `--text`, `--muted`, `--border`, `--primary` map sang token trên.

## Type scale

| Class / token | Size | Use |
|---------------|------|-----|
| `.text-cave-2xs` / `--text-2xs` | 10px | Badge, label uppercase |
| `.text-cave-xs` / `--text-xs` | 11px | Caption, meta |
| `.text-cave-sm` / `--text-sm` | 12px | Secondary UI |
| `.text-cave-md` / `--text-md` | 14px | Body, nav |
| `.text-cave-lg` / `--text-lg` | 16px | Emphasis |
| `.text-cave-xl` / `--text-xl` | 20px | Section title |
| `.text-cave-2xl` / `--text-2xl` | 24px | Page title |
| `.label-cave` | 10px bold caps | Section labels |

Fonts: **Syne** (display), **Figtree** (UI) — `CDN_GOOGLE_FONTS` trong `app/config.py`.

## Spacing / radius / controls

- Spacing: `--space-1` … `--space-12` (bước 4px)
- Radius: `--radius-sm` … `--radius-2xl`, `--radius-pill`
- Control height: `--size-control-xs` (28) → `--size-control-lg` (40)
- Sidebar: `--size-sidebar` (256px); accounts rail: `--size-rail` / `--size-rail-lg`

## Components

Dùng class token thay vì hex:

- `.cave-btn` / `.cave-btn-primary` / `.cave-btn-danger` / `.cave-btn-success`
- `.cave-input` / `.cave-select` / `.cave-textarea`
- `.cave-card` / `.cave-badge*` / `.cave-banner*`
- `.cave-dot-torch` / `.cave-dot-moss`
- `.cave-chamber` / `.cave-rail` / `.cave-scrollbar`

## Quy ước migrate trang

1. Không thêm hex mới trong template — dùng `var(--color-*)` hoặc class `.cave-*`.
2. Nav active: class `is-active` (không dùng `bg-indigo-50`).
3. Bridge tạm trong `cave-tokens.css` map utility Tailwind sáng → cave (load **sau** Tailwind CDN). Tab active: `.tab-btn.is-active`.
4. Khi rebuild Tailwind từ `app/static/src/app.css`, giữ `:root` legacy đồng bộ với cave.
5. Accent chỉ còn: **torch** (CTA/warning), **moss** (ok), **danger** (lỗi), **info** (running) — không dùng indigo/purple/sky chói.
