# ToolsAuto Admin — React SPA

Stack: **Vite · React 18 · TypeScript · React Router · TanStack Query · Tailwind · lucide-react**

## Production

```bash
npm run build:admin
# → app/static/admin/
```

Open **`/app`** (logged in). Assets: `/static/admin/`.

| Path | Meaning |
|------|---------|
| `/app` | React overview |
| `/app/settings` | React Settings (native) |
| `/app/go/*` | React bridge → link to Jinja classic |
| `/app/classic` | Jinja overview |
| `/app/settings/classic` | Jinja settings |
| `/app/jobs` etc. | Jinja pages (unchanged) |

## Dev

```bash
# API
PYTHONPATH=. venv/bin/uvicorn app.main:app --reload --port 8000
# UI
cd frontend && npm run dev
```

## Porting roadmap

1. Settings ✅  
2. Overview (richer API)  
3. Jobs / Accounts / Viral — replace ClassicBridge with native React pages  
