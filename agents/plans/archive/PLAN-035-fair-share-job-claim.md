# PLAN-035 — Fair-share job claim ordering

**Status**: Active
**Owner**: Claude Code (full execute authority granted by anh Vu [2026-05-01])
**Related task**: [TASK-035](../../tasks/active/TASK-035-fair-share-job-claim.md)

## Problem

Khi 1 account có nhiều PENDING jobs (vd Threads news scraper batch tạo 30 article cho cùng 1 account), worker `Threads_Publisher` (và Publisher FB) claim job theo `ORDER BY j.schedule_ts ASC` ([app/services/jobs/queue.py:70](../../../app/services/jobs/queue.py#L70)). Tất cả 30 job có `schedule_ts ≈ now` → FIFO theo created order → account A "chiếm hết" queue: account A publish → cooldown → publish job kế tiếp của A → cooldown → ... khiến account B/C có job mới phải chờ account A drain hết queue của nó.

## Goal

Đổi thứ tự claim sao cho **luân phiên giữa các account**: account nào lâu chưa post nhất sẽ được ưu tiên next.

## Scope

**Single file**: [app/services/jobs/queue.py](../../../app/services/jobs/queue.py) — 1 dòng `ORDER BY` trong `claim_next_job()`.

**Out of scope**:
- `claim_draft_job` (AI processing) — không liên quan account fairness, vẫn FIFO theo `created_at`.
- COMMENT job ordering — schema dùng `scheduled_at` riêng, không bị ảnh hưởng.

## Change

```sql
-- BEFORE
ORDER BY j.schedule_ts ASC

-- AFTER
ORDER BY COALESCE(a.last_post_ts, 0) ASC, j.schedule_ts ASC
```

**Cơ chế**:
- `a.last_post_ts NULL` (account chưa post bao giờ) → `COALESCE=0` → ưu tiên cao nhất.
- Account vừa post xong → `last_post_ts` lớn → tụt cuối queue.
- Tie-break bằng `schedule_ts` cho các account cùng tier.
- Account đang trong cooldown vẫn bị `WHERE` filter loại trước → không phá logic cooldown.

**Hiệu ứng**: queue luân phiên A→B→A→B thay vì A→A→A→...→B.

## Acceptance Criteria

1. [ ] `py_compile app/services/jobs/queue.py` PASS.
2. [ ] `from app.main import app` PASS, route count không đổi (207).
3. [ ] Simulate test trên DB live: tạo 2 account (A có 3 PENDING, B có 1 PENDING, cả 2 cùng platform, cooldown đã expire) → claim 4 lần liên tiếp → thứ tự phải là A, B, A, A (B được xen vào sau lần claim đầu, không phải đợi A drain).
4. [ ] Bulk-existing test suite không regress: `pytest tests/test_threads_world_news.py tests/test_article_scorer.py -q` PASS.
5. [ ] Không file nào khác thay đổi (`git diff --stat` chỉ list `app/services/jobs/queue.py`).

## Risks

- **Account starvation đảo chiều**: nếu account X vừa setup, `last_post_ts=NULL` → COALESCE=0 → luôn priority cao nhất, có thể "ăn" hết slot trong vài chu kỳ đầu. Mitigation: tự nhiên giải quyết sau lần post đầu (last_post_ts được populate). Không cần fix thêm.
- **Stale `last_post_ts`**: nếu publish thành công nhưng pipeline không update `last_post_ts` (bug khác) → account đó luôn priority cao nhất, vô hạn. Em đã verify trong [workers/threads_publisher.py](../../../workers/threads_publisher.py) và `JobService.mark_done` có update `last_post_ts` → không phải concern.

## Verify Plan

```bash
cd /home/vu/toolsauto && \
  venv/bin/python -m py_compile app/services/jobs/queue.py && \
  venv/bin/python -c "from app.main import app; print(len(app.routes))" && \
  venv/bin/pytest tests/test_threads_world_news.py tests/test_article_scorer.py -q
```

Simulate fair-share trên DB sandbox bằng INSERT 2 account giả + 4 job giả + gọi `QueueService.claim_next_job(db, platform='threads')` 4 lần.

## Deploy

1. Commit develop với message: `fix(queue): fair-share job claim by account last_post_ts`.
2. VPS pull → `pm2 restart Threads_Publisher Publisher AI_Generator` (mọi worker dùng QueueService đều cần restart vì module cache).
3. Theo dõi 1-2 chu kỳ scrape Threads: confirm log `[claim_next_job]` claim xen kẽ giữa các account thay vì 1 account dồn dập.
