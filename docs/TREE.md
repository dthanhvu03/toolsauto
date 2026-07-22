# Project tree (onboarding)

ToolsAuto tổ chức theo **ADR-007**: `core` (infra) · `features` (nghiệp vụ) · `platform` (shell HTTP) · `adapters` (contracts + dispatcher dùng chung).

## `app/` ở mức cao

```
app/
├── main.py                 # FastAPI app + cookie auth middleware
├── config.py / constants.py
├── core/                   # Shared infra — KHÔNG import features/
│   ├── database/           # ORM, session
│   ├── queue/              # claim job, cleanup, tracer
│   ├── ai/                 # Gemini / caption pipeline
│   ├── notifier/           # Telegram notify (generic)
│   ├── observability/      # logs, health, audit
│   ├── db_admin/           # SQL explorer + ACL
│   ├── compliance/         # keyword / rewrite engine
│   └── *.py                # settings, account, orchestrator, strategic, …
├── features/               # Mỗi feature tự chứa router / adapter / workers
│   ├── threads/
│   ├── facebook/
│   ├── viral_intake/
│   ├── system_panel/
│   ├── telegram_bot/
│   ├── insights/
│   ├── affiliates/
│   ├── accounts/
│   ├── jobs/
│   ├── instagram/
│   └── tiktok/
├── platform/               # Auth, dashboard shell, health
├── adapters/               # contracts, common/*, dispatcher, generic
├── templates/ static/ schemas/ utils/
```

**Đã xóa:** `app/services/` (legacy shim ADR-005). Import thẳng `app.core.*` / `app.features.*` / `app.platform.*`.

## Convention trong `features/<name>/`

```
__init__.py
README.md          # bắt đầu đọc ở đây
router.py          # HTTP (nếu có)
adapter.py         # Playwright platform (nếu có)
service/ hoặc *.py # business — flat OK nếu feature nhỏ
workers/           # PM2 entry
```

## “Muốn hiểu X thì mở đâu?”

| Mục tiêu | Bắt đầu |
|----------|---------|
| Đăng Threads | `features/threads/README.md` → `workers/publisher.py` → `adapter.py` |
| Đăng Facebook | `features/facebook/README.md` → `workers/publisher.py` → `adapter.py` |
| Claim / cooldown job | `core/queue/queue.py` |
| AI caption | `core/ai/` + `features/viral_intake/workers/ai_generator.py` |
| Login dashboard | `platform/auth/` + middleware trong `main.py` |
| PM2 / logs UI | `features/system_panel/` |
| Health / cookie sync | `platform/health/` |
| Route map | `main.py` (include_router) |

## Import rules (tóm tắt ADR-007)

1. `features/X` → được import `core/*`
2. `features/X` → **không** import `features/Y`
3. `core/*` → **không** import `features/*` hoặc `platform/*`
4. `platform/*` → được import `core/*`

Contract file: [`.importlinter`](../.importlinter).

## Root repo (giữ cố ý)

| File | Lý do |
|------|--------|
| `manage.py` | CLI / alembic helpers |
| `mcp_server.py` | MCP Inspector (path cố định) |
| `ecosystem.config.js` | PM2 process list |
| `start.sh` / `stop.sh` / `smoke.sh` | Ops |

Scratch one-off scripts thuộc `scratch/` hoặc `scripts/archive/` — không để ở root.
