# TASK-020: Schedule AI Reporter Cron Job

**Status:** Done  
**Priority:** P0  
**Type:** Operations  
**Owner:** Antigravity  
**Created:** 2026-04-26  
**Reference:** DECISION-006 §2.5, Vote 3/3 nhất trí  

---

## Objective
Thiết lập cron job để `workers/ai_reporter.py` chạy tự động hàng ngày lúc 08:00 (Asia/Ho_Chi_Minh), gửi Daily Health Report qua Telegram.

## Acceptance Criteria
- [x] Cron entry hoạt động đúng giờ 08:00 daily (01:00 UTC trên VPS)
- [x] Log output ghi vào `logs/ai_reporter.log`
- [x] Report gửi thành công kể cả khi không có incident (heartbeat)
- [x] Không ảnh hưởng PM2 processes hiện tại

## Verification Proof
```
$ crontab -l
# TASK-020: AI Reporter Daily Health Report (08:00 Asia/Saigon = 01:00 UTC)
0 1 * * * cd /home/vu/toolsauto && /home/vu/toolsauto/venv/bin/python workers/ai_reporter.py >> logs/ai_reporter.log 2>&1

$ python workers/ai_reporter.py
[INFO] ai_reporter: [AI Reporter] Sent daily health report. groups=2
```

## Status History
- 2026-04-26: `Planned` — Created by Antigravity
- 2026-04-26: `Done` — Cron installed, dry-run verified, Telegram report sent
