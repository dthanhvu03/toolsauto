# Archived one-off scripts

These were moved from `scripts/` root to keep the repo tidy. Prefer:

- **`python manage.py`** — DB migrations, worker status, viral scan/process/clean, `pages scrape`, `insights scrape`, `serve`
- **`PYTHONPATH=<project root>`** — if you run a script here directly:  
  `cd <repo> && PYTHONPATH=. python scripts/archive/<name>.py`

Legacy DB one-off migrations (`database_migration_*.py`, `012_*.py`, …) are kept for history; **new** schema changes use Alembic (`python manage.py db revision -m "..."`).
