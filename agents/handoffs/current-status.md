# Current Status

## System State

- Local: **http://127.0.0.1:8002**
- Latest: harden poll + Threads checkpoint + daily claim skip (working tree → commit)

## Done This Session [2026-07-23]

- Reup VIP A+B+C (`ee2d45d`) + gate cleanup / overview storm (`e8fb193`)
- Poll softer: worker 30s, jobs 15s, queue/viral 60s
- Threads: checkpoint URL/content markers + `checkpointed` → INVALID
- Claim: `claim_next_job_respecting_daily` skip tới 5 job đã full daily trong cùng tick

## Next Action

1. Owner F5 overview/jobs (ít GET hơn)
2. Optional push remote khi cần deploy
