# PLAN-052 — Hàng đợi nhận mọi job_type (P0, chặn FEED và STORY)

## Status: Done (2026-08-21)

## Goal

`QueueService.claim_next_job` liệt kê cứng hai loại job trong SQL:

```sql
(UPPER(j.job_type) = 'POST'    AND COALESCE(j.schedule_ts, 0)  <= now)
OR
(UPPER(j.job_type) = 'COMMENT' AND COALESCE(j.scheduled_at, 0) <= now)
```

`FEED` không khớp nhánh nào ⇒ **job feed nằm PENDING vĩnh viễn**, không worker nào nhặt.
PLAN-049 đăng được bài feed là do gọi adapter trực tiếp, không đi qua hàng đợi — nên lỗi
này chưa từng lộ. `STORY` sắp thêm sẽ dính đúng cái bẫy đó.

## Scope

- Đổi điều kiện "đến hạn" trong `claim_next_job` sang dạng không phụ thuộc danh sách job_type
- Test khoá hành vi cho cả POST / COMMENT / FEED / STORY
- Không đổi thứ tự fair-share, mutex, cooldown, daily cap

## Out of scope

- Đổi cách các worker khác claim (`claim_draft_job`, threads verifier)
- Đổi schema jobs

## Cách làm

Một job đến hạn khi **mọi mốc thời gian có mặt trên nó đều đã tới**:

```sql
AND COALESCE(j.schedule_ts,  j.scheduled_at, 0) <= now
AND COALESCE(j.scheduled_at, j.schedule_ts,  0) <= now
```

- POST: `schedule_ts` có, `scheduled_at` NULL → đúng như cũ
- COMMENT: cả hai cùng đặt `now + delay` → đúng như cũ
- FEED / STORY: chỉ `schedule_ts` → nay được nhặt

Giữ nguyên `ORDER BY COALESCE(lpp.last_ts, 0) ASC, j.schedule_ts ASC`.

## Verify — 2026-08-21

`tests/test_queue_claims_all_job_types.py` chạy **câu SQL thật trên Postgres**, không
soi chuỗi source như `test_queue_claim_guards.py` (chính vì soi chuỗi nên bug lọt).
Cô lập bằng `platform='__pytest_q_<uuid>'` + dọn sạch account/job trong `finally`,
nên không chạm job production.

| Ca | Kết quả |
|---|---|
| POST / COMMENT / FEED / STORY đến hạn → được claim | 4/4 PASS |
| Cả 4 loại chưa đến hạn → không bị claim | 4/4 PASS |
| COMMENT có `schedule_ts` quá khứ nhưng `scheduled_at` tương lai → vẫn bị chặn | PASS |

**Chứng minh test bắt đúng bug:** `git stash` code mới → chạy lại → đỏ đúng 2 ca
`FEED` và `STORY` (7 passed, 2 failed). Khôi phục code mới → 9/9 xanh.

Full suite: **184 passed** (baseline 175 + 9 test mới), `--ignore=tests/test_threads_world_news.py`.

## Ghi chú

Thêm `pytest.ini` để đăng ký mark `integration` (test tự skip khi không có Postgres).
