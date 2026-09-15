# Settings UI (Vite + React) — deployed into FastAPI

## Production (served by FastAPI)

```bash
# from repo root
npm run build:settings
# → writes app/static/settings-ui/
```

Then open **`/app/settings`** (logged-in). Assets load from `/static/settings-ui/`.

- Classic Jinja UI remains at **`/app/settings/classic`**
- If build folder missing, `/app/settings` falls back to classic with a notice

## Dev (hot reload)

```bash
# terminal 1 — API
PYTHONPATH=. venv/bin/uvicorn app.main:app --reload --port 8000

# terminal 2 — Vite
cd frontend && npm run dev
# http://127.0.0.1:5173  (proxies /api → :8000)
```

Offline mock: `VITE_SETTINGS_USE_MOCK=true npm run dev`

## API

- `GET /api/settings/metadata`
- `GET /api/settings/values`
- `PATCH /api/settings/sections/{section}`
- `POST /api/settings/test/{test_id}`
