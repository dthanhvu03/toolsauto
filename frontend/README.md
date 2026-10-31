# ToolsAuto Admin — React SPA

Stack: **Vite · React 18 · TypeScript · React Router · TanStack Query · Tailwind · lucide-react**

## Cấu trúc `src/`

```
src/
  main.tsx
  app.css
  app/                     # routes + sidebar nav
    App.tsx
    nav.ts
  layouts/
    AppShell.tsx
  shared/
    api/http.ts
    lib/cn.ts
    lib/time.ts            # formatTs — giờ Việt Nam
    ui/                    # PageHeader, Pagination, QueryBody…
  features/                # PLAN-108: chỉ module đang chạy, nhóm theo sidebar (app/nav.ts)
    overview                 # Tổng quan: kênh Buffer còn bài, kho chờ, lỗi
    viral | viral-sources    # Video
    jobs                     # Buffer — Lịch đăng (chỉ xem)
    ai-studio | compliance   # Nội dung & AI (compliance = từ khoá cấm cho caption)
    logs | settings | syspanel | database | telegram   # Hệ thống
```

Quy ước: **1 feature = 1 thư mục** (`api` / `hooks` / `components` / `pages` / `types`). Thêm trang = thêm feature + 1 dòng trong `app/nav.ts` + 1 `Route` trong `app/App.tsx`. Sidebar Jinja (`app/templates/layouts/app.html`) dùng cùng nhóm.

## Production

```bash
npm run build:admin   # từ root repo
# hoặc: cd frontend && npm run build
# → app/static/admin/
```

Open **`/app`** (logged in). Assets: `/static/admin/`.

| Path | Meaning |
|------|---------|
| `/app` | React overview |
| `/app/settings` | React Settings |
| `/app/go/*` | React native lists (CRUD / lệnh nguy hiểm vẫn Classic) |
| `/app/classic` | Jinja overview (đầy đủ chrome) |
| `/app/jobs` etc. | Jinja standalone |

## Dev

```bash
PYTHONPATH=. venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

Mở **http://127.0.0.1:5173/login** (cùng cổng Vite) rồi vào `/app`. Cookie `:8000` không dùng được trên `:5173`.

## Porting roadmap

1. Settings ✅  
2. Overview ✅  
3. Jobs / Accounts / Viral ✅  
4. Affiliates / Nguồn video / Kho kênh cũ ✅ (list native; CRUD vẫn ở Classic)  
5. Insights ✅ · FB tasks ✅ · Compliance ✅ · Threads ✅ · Logs ✅ · Control plane ✅ · AI Studio ✅ · Platform config ✅ · Syspanel ✅ · Database ✅  

