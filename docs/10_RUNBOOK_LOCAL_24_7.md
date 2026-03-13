# Runbook: chạy local 24/7 (tool cá nhân)

## Dev run
1) Install deps
2) Install playwright browsers
3) Run DB migration
4) Start app + worker

## Init FB login (one-time)
- Run init_login.py (opens persistent profile)
- User logs in manually
- Close

## Prod-like run (personal)
- Use systemd (Ubuntu) or Task Scheduler (Windows)
- Ensure auto-restart on crash
- Keep profile dir persistent

## Operational notes
- Keep cooldown & daily_limit conservative
- Always validate file exists before processing
- On repeated failures, stop/reschedule and alert (log)

## Acceptance criteria
- Reboot machine -> services auto start -> job continues