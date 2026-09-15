# ToolsAuto Admin — React SPA

Stack: **Vite · React 18 · TypeScript · React Router · TanStack Query · Tailwind · lucide-react**

## Cấu trúc `src/`

```
src/
  main.tsx                 # entry
  app.css
  app/
    App.tsx                # routes + providers
    nav.ts                 # sidebar nav
  layouts/
    AppShell.tsx
  shared/
    api/http.ts            # fetch JSON helper
    api/adminApi.ts        # /api/admin/*
    lib/cn.ts
  features/
    overview/pages/
    jobs/pages/
    accounts/pages/
    viral/pages/
    settings/              # metadata-driven Settings (api, hooks, components…)
    classic/pages/         # bridge → Jinja chưa port
```

Quy ước: **1 feature = 1 thư mục** (`pages` / `api` / `components` / `hooks`). Code dùng chung → `shared/`. Shell & route → `app/` + `layouts/`.

## Production

```bash
npm run build:admin
# → app/static/admin/
```

Open **`/app`** (logged in). Assets: `/static/admin/`.

| Path | Meaning |
|------|---------|
| `/app` | React overview |
| `/app/settings` | React Settings |
| `/app/go/jobs\|accounts\|viral` | React native lists |
| `/app/go/*` (còn lại) | Bridge → Jinja |
| `/app/classic` | Jinja overview |
| `/app/jobs` etc. | Jinja (giữ nguyên) |

## Dev

```bash
PYTHONPATH=. venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

## Porting roadmap

1. Settings ✅  
2. Overview ✅  
3. Jobs / Accounts / Viral ✅  
4. Module còn lại: thay `classic` bridge dần  
