# Current Status

## System State

- **Product**: ToolsAuto — auto-publish (Facebook / Threads + related).
- **Architecture**: ADR-007 (`core` / `features` / `platform`).
- **Local Windows**: web up `http://127.0.0.1:8001`; Postgres Docker `toolsauto_postgres` → host `:5434`; `.env` + `venv` ready.
- **Onboarding**: [docs/TREE.md](../../docs/TREE.md), root [README.md](../../README.md), [start.ps1](../../start.ps1).
- **Active plans/tasks**: none.

## Done This Session [2026-07-22]

- Commit `5e33f87` — security harden + overlap cleanup + tests/docs.
- Local bootstrap: `.env`, Docker Postgres `:5434`, `venv` (web deps), schema `create_all` + alembic stamp, `start.ps1`, uvicorn `:8001`.

## Unfinished + Blockers

- Full `requirements.txt` trên Python 3.14 Windows fail (`uvloop`, gRPC/protobuf). Worker/AI stack → Python 3.12 hoặc VPS Linux.
- Chưa `git push`. Chưa start PM2 workers trên Windows (`ecosystem` dùng `venv/bin/python`).

## Next Action

1. Mở http://127.0.0.1:8001 — login `admin` / `admin123` (local `.env`).
2. Push commit khi cần deploy VPS.
3. Optional: cài Python 3.12 để `pip install -r requirements.txt` đầy đủ cho workers.
