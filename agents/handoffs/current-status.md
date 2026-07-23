# Current Status

## System State

- Local: **http://127.0.0.1:8002**
- Reup VIP A+B+C: `ee2d45d`
- Overview HTMX load-storm + publish gate cleanup — committing

## Done This Session [2026-07-23]

- Reup VIP A+B+C
- Overview: stats poll không còn load-storm (`load` 1 lần → `every 60s`)
- Gate cleanup: `postpone_if_daily_limit` FB+Threads, reup via runtime_settings, ETA=finished_at, Settings gate copy

## Next Action

1. Owner F5 Tổng quan + Jobs ETA + Settings descriptions
2. Optional: giảm worker_status `every 5s` nếu vẫn thấy ồn
