# ToolsAuto - Current Project Status

*Last updated by: Codex — 2026-04-24 (PLAN-016 account invalid + VNC recovery executed)*

---

## Latest Codex Execution (2026-04-24)

**PLAN-016: Account Invalid + VNC Recovery — Codex execution done, pending Claude Code verify.**

Changed:
- `app/services/account.py`: `invalidate_account()` now sets `is_active=false`, `login_status=INVALID`, clears `login_process_pid`, and keeps `login_error`.
- `app/services/job.py`: circuit breaker now sets `job.account.is_active=false` instead of writing `job.account.status`.
- `scripts/start_vps_vnc.py`: starts `Xvfb :99` if missing, starts `x11vnc/openbox/websockify` with detached process groups, and verifies real listening ports.

Proof:
```
$ ./venv/bin/python -m py_compile app/services/account.py app/services/job.py scripts/start_vps_vnc.py
# exit code: 0

$ ./venv/bin/python scripts/start_vps_vnc.py
Status:
[OK] x11vnc is listening on 5900
[OK] websockify is listening on 6080

$ ss -tlnp
LISTEN 0 32  0.0.0.0:5900 0.0.0.0:* users:(("x11vnc",pid=2364193,fd=4))
LISTEN 0 100 0.0.0.0:6080 0.0.0.0:* users:(("websockify",pid=2364199,fd=3))
```

*Last updated by: Claude Code — 2026-04-24 (đóng loop GraphQL direct — core adapter work đủ)*

---

## System State
| Item | State |
|---|---|
| **Environment** | WSL Ubuntu / Python 3.10 / Direct Server |
| **Backend** | Running (`manage.py serve`) |
| **Git Branch** | develop |
| **Git Status** | Untracked: `scratch/` (user), `scripts/query_jobs.py`, `agents/*` docs. Scripts GraphQL-path đã xoá sạch. |
| **Last Major Work** | Verify core adapter publish flow work cho cả Page lẫn multi-profile → đóng loop GraphQL direct |

---

## Key Finding (Verified Live)

**Core `FacebookAdapter` đã đủ để publish Reels. Không cần direct GraphQL.**

Test end-to-end qua `Dispatcher.dispatch(job, db)`:

| Job | Account | Target | Switch method | Post URL live |
|---|---|---|---|---|
| 737 | 4 (Nguyen Ngoc Vi) | maymacenter (Page) | Banner "Chuyển ngay" | ✅ `facebook.com/reel/1674851263553349` |
| 736 | 4 (Nguyen Ngoc Vi) | Thuỳ Dương Skincare (multi-profile `61579151682343`) | Avatar menu → "See all profiles" | ✅ `facebook.com/reel/1497469128715893` |

Runtime ~2 phút/job, verify live bằng profile logged-in Playwright (`UNAVAILABLE=False`, có `<video>`).

Core logic có sẵn:
- `_switch_to_page_context` (line 645 trong `adapter.py`)
- `_switch_to_personal_profile` (line 453) — flow: avatar menu → "Xem tất cả trang cá nhân" → scan profile items accent-insensitive → click.
- Bắt post_id qua GraphQL response listener trong `publish()` → nhận `122109704390971722` rồi redirect thành reel URL.

---

## Đóng loop GraphQL Direct Path

**Tất cả PLAN-011/012/013/014 đã xác nhận: Direct Fire GraphQL là dead end với account/page hiện tại.**
- Dù fix noncoercible (`thumbnailFileID=null`) + chain thêm `BusinessComposerVideoSetPublishedMutation` finalize → response 200 không errors nhưng post verify vẫn "Content unavailable".
- FB có thêm signal ẩn (websocket/poll/cookie state) mà direct fire không trigger — không reverse engineer thêm vì core UI flow đã work.

**TASK-015 (Anti đang kiêm nhiệm Codex để reverse-engineer GraphQL Business Suite)** — recommend **huỷ/obsolete**: core adapter đã xử lý đủ use case, không cần thêm direct GraphQL path để scale.

---

## Active Tasks

- [TASK-015](agents/tasks/TASK-015-reverse-engineer-business-suite.md) — **Recommend CLOSE (obsolete)**. Anti quyết định.

---

## Done This Session (Verified)

- ✅ Archive PLAN-011/012/013/014 + TASK-011/012/013/014 (đã làm trước đó).
- ✅ Test core Dispatcher end-to-end trên job 736 (multi-profile) và 737 (Page) — cả 2 LIVE.
- ✅ Verify URL live bằng Playwright với profile logged-in.
- ✅ Xoá 6 script GraphQL-path dead-end khỏi `scripts/`:
  - `graphql_publish_job.py`
  - `investigate_graphql.py`
  - `graphql_api_drill.py`
  - `graphql_page_switch_probe.py`
  - `graphql_probe.py`
  - `poc_business_suite_publish.py`

---

## Unfinished

- _(none)_

---

## Blockers / Risks

- **Account 3** đang nhiều FAILED liên tục (jobs 730-735, 738-740) — có thể profile chưa login hoặc bị checkpoint. Chưa verify với core adapter (mới test account 4). Rủi ro khi scale sang account khác.

---

## Next Action

1. **Anti**: Quyết định đóng/huỷ TASK-015 (reverse-engineer GraphQL) vì core đã work.
2. Test core Dispatcher trên **account 3** (job 738 hoặc 739) để verify có lỗi login/checkpoint không.
3. Nếu account 3 OK → setup worker loop / scheduler để chạy tự động nhiều job.
4. Nếu muốn scale concurrent: chạy nhiều Playwright context song song (mỗi profile dir riêng, ~400MB RAM/browser).

---

## Workflow Reference

- Workflow: `agents/WORKFLOW.md`
- Prompt standard: `agents/PROMPT_SYSTEM.md`
- Status tracking: `agents/handoffs/current-status.md`
