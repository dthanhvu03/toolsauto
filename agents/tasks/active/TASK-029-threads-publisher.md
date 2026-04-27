# TASK-029: Threads Publisher Implementation

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-029 |
| **Status** | In Progress |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-029 |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Objective
Hoàn thiện luồng đăng bài tự động (backend publisher) cho Threads. Giải quyết triệt để tình trạng các job Threads_News sinh ra bị kẹt ở trạng thái PENDING mãi mãi. Thiết lập một PM2 worker độc lập (`Threads_Publisher`) để cô lập process với Facebook.

---

## Scope
- Tạo `app/adapters/threads/adapter.py` để xử lý logic thao tác browser trên `threads.net`.
- Update `app/adapters/dispatcher.py` để trỏ platform `threads` vào adapter mới.
- Khởi tạo script worker `workers/threads_publisher.py` chịu trách nhiệm pop các job Threads và xử lý.
- Cấu hình file `ecosystem.config.js` để PM2 có thể chạy và quản lý worker này.

## Out of Scope
- Tuyệt đối không thay đổi schema DB hay migration mới.
- Không chỉnh sửa scraper của `Threads_NewsWorker`.
- Không thay đổi `FB_Publisher` đang chạy ổn định.
- Không sửa `Threads_AutoReply` và `Threads_Verifier`.

---

## Blockers
- Không có (Các profile cookies/storage_state hiện tại đã có sẵn qua quá trình Account Linking và Verifier).

---

## Acceptance Criteria
- [ ] Job có `platform="threads"` và `status="PENDING"` được `Threads_Publisher` nhận và xử lý tự động.
- [ ] Bài viết lên sóng thành công với text caption và image đính kèm.
- [ ] Parse được URL/ID của bài post để update ngược lại Job (`external_post_id`, `post_url`).
- [ ] Flow trạng thái Job update chuẩn xác: PENDING → PROCESSING → COMPLETED (hoặc FAILED nếu lỗi mạng/timeout).
- [ ] Đảm bảo process chạy mượt mà trên VPS qua PM2, crash tự reset, không memory leak.
- [ ] Browser session không dẫm đạp/xung đột với Facebook publisher.

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [x] Bước 1: Threads adapter local implementation completed in `app/adapters/threads/` with Playwright session bootstrap, post URL capture, session-invalid signaling, and safer `check_published_state()`.
- [x] Bước 2: Dispatcher working tree already maps `Platform.THREADS` to `ThreadsAdapter`; local import smoke returns `ThreadsAdapter`.
- [x] Bước 3: Added isolated worker `workers/threads_publisher.py` that claims only Threads jobs and keeps heartbeat/cleanup/account invalidation paths.
- [x] Bước 4: Added PM2 entry `Threads_Publisher` in `ecosystem.config.js`.

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

```text
$ ./venv/bin/python -m py_compile app/adapters/threads/adapter.py app/adapters/threads/__init__.py app/adapters/dispatcher.py workers/threads_publisher.py
PY_COMPILE_THREADS_OK

$ python import smoke: get_adapter("threads")
ThreadsAdapter

$ python import smoke: workers.threads_publisher
THREADS_PUBLISHER_IMPORT_OK
```

Live verification remains pending:
- Chưa có `pm2 list` / `pm2 logs Threads_Publisher` trên VPS sau deploy.
- Chưa có console log claim job thật.
- Chưa có DB proof cho `post_url`, `external_post_id`, `PENDING -> RUNNING -> DONE/FAILED`.

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-27 | Planned | Created by Anti, decided on Option B (isolated worker) |
| 2026-04-27 | Assigned | Handoff to Codex |
| 2026-04-27 | In Progress | Code path implemented locally; live Threads/PM2 verification still pending |
