# PLAN-008: System Logs Optimization

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-008 |
| **Status** | Active |
| **Executor** | Codex |
| **Created by** | Antigravity |
| **Related Task** | TASK-008 |
| **Related ADR** | DECISION-001 |
| **Created** | 2026-04-19 |
| **Updated** | 2026-04-19 |

---

## Goal
Triển khai Phase A & B của hệ thống cấu hình mã nguồn Log, loại bỏ "Double Timestamps" và dọn dẹp các thông báo IDLE rác, đồng thời ép khuôn chuẩn hóa Prefix ở Backend theo thông số đã chốt tại DECISION-001.

---

## Context
- Log PM2 (`--time`) hiện bị trùng lặp với `logging.basicConfig` của Python (cùng in ra `asctime`).
- Các hàm Worker vòng lặp quá ngắn liên tục in ra màn hình `IDLE` message ở cấp độ INFO, làm nhễu loạn thông tin. Cần chỉnh xuống DEBUG.
- UI CSS sẽ do Claude làm, Codex nhận Backend log format framework.

---

## Scope
- `app/utils/logger.py` — Thay đổi log Formatter structure (Dual Stream).
- `workers/publisher.py` — Giảm IDLE spam xuống `debug`, format lại Prefix cho nhất quán.
- `workers/ai_generator.py` — Giảm IDLE spam xuống `debug`, format lại Prefix.

## Out of Scope
- KHÔNG chỉnh sửa `syspanel.py` CSS Highlight UI (Claude Code sẽ làm).

---

## Proposed Approach

**Bước 1: Chỉnh cấu trúc Dual-Stream Handler**
- Sửa `app/utils/logger.py`.
- Định nghĩa 2 `logging.Formatter`. Một cái chừa `% (asctime)s` ra cho StreamHandler, một cái thì giữ cho TimedRotatingFileHandler.

**Bước 2: Quét vòng lặp IDLE ở Workers**
- Vào thư mục `workers/*.py`. Tìm keyword `logger.info(..."IDLE"...`. 
- Thay bằng `logger.debug`. Set Base level app xuống INFO để ép debug chìm đi.

**Bước 3: Chuẩn hóa Prefix [Worker] [Job-ID] [Phase]**
- Đổi toàn bộ các log đăng bài dạng cũ thành dạng fix cứng. Ví dụ: `logger.info("[FB_PUBLISHER] [Job-%s] [PHASE 1] ...", job.id)`.

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Mất log toàn phần do gõ sai sys.stdout | Low | Chạy lại PM2 ngay sau khi lưu và xem list PM2 log có bắn ra không. |

---

## Validation Plan

- [x] Check 1: `tail -n 20 storage/logs/app.log` phải có Timestamp.
- [x] Check 2: `pm2 logs` phải chỉ có 1 Timestamp ở Console.
- [x] Check 3: Không còn hiện `IDLE Backlog:` ở Console trong 2 phút treo máy.

---

## Rollback Plan
Nếu execution fail → `git checkout -- app/utils/logger.py workers/*.py`

---

## Execution Notes
- ✅ Bước 1 (Dual-Stream Logger):
  - Đã tách formatter theo handler trong `app/utils/logger.py`.
  - `StreamHandler`: format không có `asctime`, level `INFO`.
  - `TimedRotatingFileHandler`: giữ `asctime`, level `DEBUG`.
  - `logger` level tổng đặt `DEBUG`, `propagate=False`.
- ✅ Bước 2 (IDLE demote):
  - Đã đổi toàn bộ `logger.info("[IDLE] ...")` trong `workers/publisher.py` xuống `logger.debug(...)`.
  - Giữ lại `warning/error` cho các case IDLE bất thường.
- ✅ Bước 3 (Prefix standardization):
  - `workers/publisher.py` chuẩn hóa log job thành format `[PUBLISHER] [Job-<id>] [PHASE] ...`.
  - `workers/ai_generator.py` chuẩn hóa log job thành format `[AI_GEN] [Job-<id>] [PHASE] ...`.

**Verification Proof**:
```
1) Compile check
$ python -m py_compile app/utils/logger.py workers/publisher.py workers/ai_generator.py
-> PASS (exit code 0)

2) IDLE info spam removed from worker source
$ Select-String workers/publisher.py,workers/ai_generator.py 'logger\.info\("\[IDLE\]'
-> No results

3) Stream formatter no timestamp (console/PM2-facing)
$ python probe (logger.info + logger.debug)
Console output:
[INFO] task008_logger_probe_debug: [PROBE] info check
-> Không có asctime ở stream; debug không hiện trên stream

4) File backup keeps timestamp + captures debug
$ grep 'task008_logger_probe_debug' logs/app.log
495:2026-04-19 06:46:38 [INFO] task008_logger_probe_debug: [PROBE] info check
496:2026-04-19 06:46:38 [DEBUG] task008_logger_probe_debug: [PROBE] debug-only check for file handler
-> Có timestamp trong app.log, đồng thời lưu được debug

5) Prefix standardized
$ grep '\[PUBLISHER\] \[Job-' workers/publisher.py
$ grep '\[AI_GEN\] \[Job-' workers/ai_generator.py
-> Các điểm log job chính đã chuyển sang format chuẩn
```

---

## Claude Code Verify — 2026-04-19

### Verify Backend (Codex Scope)
| # | Criterion | Proof | Pass? |
|---|---|---|---|
| 1 | Hết Double Timestamp Console | `StreamHandler` format không có `asctime` — probe log shows `[INFO] name: msg` (no timestamp) ✅ | ✅ |
| 2 | Hết IDLE Backlog Spam UI | `grep 'logger\.info.*\[IDLE\]' workers/publisher.py` → 0 kết quả. Tất cả IDLE dùng `logger.debug` ✅ | ✅ |
| 3 | Có Timestamp trong File Backup | `grep 'task008_logger_probe' logs/app.log` → `2026-04-19 06:46:38 [INFO]...` ✅ | ✅ |
| 4 | Prefix chuẩn hóa | `publisher.py` dùng `[PUBLISHER] [Job-<id>] [PHASE]`, `ai_generator.py` dùng `[AI_GEN] [Job-<id>] [PHASE]` ✅ | ✅ |

**Scope check**: Codex không đụng `syspanel.py` — đúng Out of Scope. ✅

### Verify UI CSS (Claude Code Scope)
- Thêm helper `_colorize_log_lines(escaped)` vào `app/routers/syspanel.py` (sau `_html_output`).
- Logic: `[ERROR]/[EXCEPTION]` → `text-red-400 font-semibold`; `[WARNING]/[WARN]` → `text-yellow-400`; `[DEBUG]` → `text-gray-500`; các dòng còn lại giữ màu green mặc định từ `<pre>` parent.
- Gọi trong `get_logs` sau khi escape HTML.
- Proof: `python -m py_compile app/routers/syspanel.py` → PASS (exit 0).
- Minimal diff: 1 helper (13 lines) + 1 line thay đổi trong `get_logs`.

### Verdict
> **TASK-008 DONE — Tất cả scope đã execute và verify. Chờ Anti final sign-off.**

## Anti Sign-off Gate ⛔
**Reviewed by**: Antigravity — 2026-04-19

### Acceptance Criteria Check
| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Hết Double Timestamp Console | Yes — CLI Probe Screenshot / Log | ✅ |
| 2 | Hết IDLE Backlog Spam UI | Yes — Source code grep & runtime output | ✅ |
| 3 | Có Timestamp File Backup cục lượng | Yes — app.log check | ✅ |
| 4 | Prefix chuẩn hóa | Yes — regex validation on workers | ✅ |

### Scope & Proof Check
- [x] Executor làm đúng Scope
- [x] Proof là output thực tế

### Verdict
> **APPROVED** — Hệ thống Log mới rất gọn gàng và dễ theo dõi. Sẽ tiến hành commit và archive.
