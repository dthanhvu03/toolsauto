# PLAN-018: AI Log Analyzer - Observability & Reporting MVP

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-018 |
| **Status** | Done (Archived) |
| **Executor** | Codex |
| **Created by** | Antigravity |
| **Related Task** | TASK-018 |
| **Related ADR** | DECISION-005 |
| **Created** | 2026-04-26 |
| **Updated** | 2026-04-26 |

---

## Goal
Implement a structured incident logging system at the job failure boundary (Dispatcher) and a daily AI-driven health report to summarize failures and identify root causes via Telegram.

---

## Context
- Hiện tại các lỗi của module (Facebook, Threads) chỉ được in ra console hoặc raw text logs, gây khó khăn cho việc phân tích và theo dõi tổng thể hệ thống.
- User yêu cầu thu thập lỗi có cấu trúc và gửi summary report hàng ngày thông qua Gemini AI.
- Quyết định (Decision-005) đã chốt: Không làm tính năng Auto-Healing ở giai đoạn này, chỉ tập trung Observability. Sử dụng DB chính (PostgreSQL) để lưu lỗi.

---

## Scope
*(Executor chỉ được làm những gì trong danh sách này)*

- `app/database/models.py` — Thêm model `IncidentLog` và `IncidentGroup`.
- `alembic/versions/` — Tạo file migration.
- `app/services/incident_logger.py` — Tạo file mới xử lý logic hash, redact, insert, upsert.
- `app/adapters/dispatcher.py` — Gọi hàm lưu lỗi trong block catch exception ngoài cùng.
- `workers/ai_reporter.py` — Tạo cron script tổng hợp dữ liệu, gọi LLM, gửi Telegram.

## Out of Scope
*(Executor KHÔNG được làm những điều này trong plan này)*

- Tự động khắc phục lỗi (Auto-Healing), khởi động lại worker, hay xóa data production.
- Thay đổi cấu trúc catch exception chi tiết bên trong adapter của Facebook/Threads.
- Xây dựng Web Dashboard UI cho log.

---

## Proposed Approach
*(Các bước thực hiện theo thứ tự — Executor đọc và làm từng bước)*

**Bước 1**: Tạo Database Models
- Bổ sung `IncidentLog` và `IncidentGroup` vào `models.py`.
- Tạo Alembic migration cho thay đổi trên.
- Run `alembic upgrade head`.

**Bước 2**: Implement Incident Logger Service
- Tạo `app/services/incident_logger.py`.
- Viết logic tạo `error_signature` bằng SHA1 hash (`error_type` + normalize `message`).
- Viết hàm `redact_context()` để che các dữ liệu nhạy cảm.
- Viết logic UPSERT vào `incident_groups` và INSERT vào `incident_logs`.

**Bước 3**: Integrate with Dispatcher
- Trong `app/adapters/dispatcher.py`, bắt exception tại vòng ngoài của `Dispatching to {platform} adapter`.
- Truyền đối tượng exception, platform, job_id, account_id vào `IncidentLogger.log_incident()`.

**Bước 4**: Implement AI Reporter Worker
- Tạo `workers/ai_reporter.py`.
- Viết query lấy top các incidents chưa resolve hoặc xảy ra trong 24h.
- Dựng prompt system, truyền data tổng hợp vào LLM Gemini Flash.
- Nhận response Markdown và gọi `NotifierService.send_message()` để gửi qua Telegram.

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| PostgreSQL upsert conflicts / locks | Medium | Sử dụng `ON CONFLICT` chuẩn của SQLAlchemy PostgreSQL dialiect. |
| Dữ liệu nhạy cảm lọt vào DB | High | Đảm bảo hàm `redact_context` lọc chặt `cookie`, `proxy`, `password`. |
| Token limits khi gửi prompt cho AI | Low | Chỉ query top 20 error groups đã aggregate, không gửi raw stacktrace quá dài. |

---

## Validation Plan
*(Executor phải thực hiện những check này và ghi kết quả vào Execution Notes)*

- [ ] Check 1: Chạy Alembic upgrade không lỗi.
- [ ] Check 2: Gây ra lỗi bằng một job ảo, kiểm tra `incident_logs` và `incident_groups` trong DB có data và không bị lọt cookie.
- [ ] Check 3: Chạy script `ai_reporter.py` thủ công và nhận được tin nhắn trên Telegram.

---

## Rollback Plan
Nếu execution fail → Downgrade alembic (`alembic downgrade -1`), xóa các file mới tạo `incident_logger.py`, `ai_reporter.py`, và revert `dispatcher.py` / `models.py` bằng git checkout.

---

## Execution Notes
*(Executor điền vào theo thứ tự từng bước — KHÔNG để trống khi Done)*

- ✅ Bước 1: Đã thêm `IncidentLog` và `IncidentGroup` vào `app/database/models.py`; đã tạo migration `alembic/versions/c9d0e1f2a3b4_add_incident_tables.py`; đã chạy `alembic upgrade head` thành công trên PostgreSQL. DB current revision: `c9d0e1f2a3b4 (head)`. Inspect DB xác nhận hai bảng `incident_logs`, `incident_groups` đã tồn tại với đúng cột chính.
- ✅ Bước 2: Đã tạo `app/services/incident_logger.py`; service tạo `error_signature` SHA1 từ `error_type + normalized_message`, redact `cookie/token/password/proxy_auth`, insert `incident_logs`, UPSERT `incident_groups` bằng SQLAlchemy PostgreSQL `ON CONFLICT`.
- ✅ Bước 3: Đã tích hợp `IncidentLogger.log_incident()` vào catch boundary của `app/adapters/dispatcher.py` cho `PageMismatchError` và exception ngoài cùng; logging dùng session riêng nên không phá transaction publisher.
- ✅ Bước 4: Đã tạo `workers/ai_reporter.py`; script query top 20 incident groups 24h, gọi `GeminiAPIService`, dựng report, đăng ký `TelegramNotifier`, gửi qua `NotifierService`.

**Verification Proof**:
```
# Output thực tế của validation checks

## Check 1 / Bước 1 - DB models + migration

$ wsl -d Ubuntu -- bash -lc 'cd /home/vu/toolsauto && venv/bin/python -m py_compile app/database/models.py alembic/versions/c9d0e1f2a3b4_add_incident_tables.py'
# exit 0

$ wsl -d Ubuntu -- bash -lc 'cd /home/vu/toolsauto && venv/bin/alembic heads'
c9d0e1f2a3b4 (head)

$ wsl -d Ubuntu -- bash -lc 'cd /home/vu/toolsauto && venv/bin/alembic current'
c9d0e1f2a3b4 (head)
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.

$ wsl -d Ubuntu -- bash -lc 'cd /home/vu/toolsauto && venv/bin/alembic upgrade head'
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade f2a3b4c5d6e8 -> c9d0e1f2a3b4, add incident logging tables

$ @'
from sqlalchemy import inspect
from app.database.core import engine
insp = inspect(engine)
for table in ("incident_logs", "incident_groups"):
    exists = insp.has_table(table)
    print(f"{table}: exists={exists}")
    if exists:
        print("columns=" + ",".join(c["name"] for c in insp.get_columns(table)))
'@ | wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && venv/bin/python -"
incident_logs: exists=True
columns=id,occurred_at,platform,feature,category,worker_name,job_id,account_id,severity,error_type,error_signature,error_message,stacktrace,context_json,source_log_ref,resolved
incident_groups: exists=True
columns=error_signature,first_seen_at,last_seen_at,occurrence_count,last_job_id,last_account_id,last_platform,last_worker_name,last_sample_message,severity_max,status,acknowledged_by,acknowledged_at,notes

## Compile - Bước 2/3/4

$ wsl -d Ubuntu -- bash -lc 'cd /home/vu/toolsauto && venv/bin/python -m py_compile app/database/models.py app/services/incident_logger.py app/adapters/dispatcher.py workers/ai_reporter.py alembic/versions/c9d0e1f2a3b4_add_incident_tables.py'
# exit 0

## Check 2 - Synthetic dispatcher failure + redact validation

$ @'
from app.adapters import dispatcher as dispatcher_mod
from app.adapters.contracts import AdapterInterface
from app.database.core import SessionLocal
from app.database.models import Account, IncidentGroup, IncidentLog, Job
from app.services.incident_logger import IncidentLogger

class BrokenAdapter(AdapterInterface):
    def open_session(self, profile_path: str) -> bool:
        raise RuntimeError("Synthetic dispatcher failure selector .btn-12345 after 30000ms")
    def publish(self, job):
        raise RuntimeError("should not publish")
    def check_published_state(self, job):
        raise RuntimeError("should not check")
    def close_session(self):
        pass

original_get_adapter = dispatcher_mod.get_adapter
dispatcher_mod.get_adapter = lambda platform: BrokenAdapter()
try:
    account = Account(id=999901, name="incident_test_account", profile_path="/tmp/incident_test")
    job = Job(id=999902, platform="facebook", account_id=999901, account=account, job_type="POST", status="RUNNING")
    result = dispatcher_mod.Dispatcher.dispatch(job)
    print("dispatcher_result_ok=", result.ok)
    print("dispatcher_result_error=", result.error)
finally:
    dispatcher_mod.get_adapter = original_get_adapter

sig = IncidentLogger.log_incident(
    exception=RuntimeError("Synthetic redact validation failure 12345"),
    platform="facebook",
    job_id="999903",
    account_id="999901",
    feature="POST",
    worker_name="validation",
    context={
        "cookie": "SECRET_COOKIE",
        "token": "SECRET_TOKEN",
        "safe": "visible",
        "nested": {"proxy_auth": "SECRET_PROXY", "url": "https://example.test"},
    },
)
print("direct_signature=", sig)

with SessionLocal() as db:
    direct = db.query(IncidentLog).filter(IncidentLog.error_signature == sig).order_by(IncidentLog.id.desc()).first()
    group = db.query(IncidentGroup).filter(IncidentGroup.error_signature == sig).first()
    print("direct_context=", direct.context_json)
    print("direct_group_count=", group.occurrence_count)
    print("secret_in_context=", any(secret in str(direct.context_json) for secret in ("SECRET_COOKIE", "SECRET_TOKEN", "SECRET_PROXY")))
    latest = db.query(IncidentLog).order_by(IncidentLog.id.desc()).first()
    print("latest_incident_id=", latest.id)
    print("latest_tables_ok=", bool(direct and group))
'@ | wsl -d Ubuntu -- bash -lc "cd /home/vu/toolsauto && venv/bin/python -"
dispatcher_result_ok= False
dispatcher_result_error= Unhandled Adapter Exception: Synthetic dispatcher failure selector .btn-12345 after 30000ms
direct_signature= 124a8788f77ad921
direct_context= {'safe': 'visible', 'nested': {'url': 'https://example.test'}}
direct_group_count= 1
secret_in_context= False
latest_incident_id= 2
latest_tables_ok= True
/home/vu/toolsauto/app/adapters/facebook/adapter.py:1630: SyntaxWarning: invalid escape sequence '\d'
  return self.page.evaluate("""
[Job 999902] Unhandled adapter exception: Synthetic dispatcher failure selector .btn-12345 after 30000ms
Traceback (most recent call last):
  File "/home/vu/toolsauto/app/adapters/dispatcher.py", line 175, in dispatch
    if not adapter.open_session(job.account.resolved_profile_path):
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<stdin>", line 9, in open_session
RuntimeError: Synthetic dispatcher failure selector .btn-12345 after 30000ms

## Check 3 - AI Reporter manual run / Telegram send

$ wsl -d Ubuntu -- bash -lc 'cd /home/vu/toolsauto && venv/bin/python workers/ai_reporter.py'
[INFO] app.services.gemini_api: 🔥 [API Fallback] Đang gửi text prompt lên API (có rotation support)
[INFO] app.services.gemini_api: [Gemini] Using model: gemini-2.5-flash
[INFO] app.services.gemini_api: 🔥 [Gemini] Trả kết quả thành công qua gemini-2.5-flash (18.0s)
[INFO] app.services.notifier_service: Registered notifier: TelegramNotifier
[INFO] ai_reporter: [AI Reporter] Sent daily health report. groups=2
```

---

## Anti Sign-off Gate ⛔
*(Anti điền vào — BLOCKING. Không có section này = Claude Code không được archive)*

**Reviewed by**: Antigravity — 2026-04-26

### Acceptance Criteria Check
*(Copy từ TASK — điền từng dòng, không bỏ qua)*

| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Bảng incident_logs và incident_groups được tạo | Yes — [Check 1] | ✅ |
| 2 | Bắt được lỗi tại vòng ngoài Dispatcher | Yes — [Check 2: Synthetic dispatcher failure] | ✅ |
| 3 | Dữ liệu nhạy cảm bị loại bỏ | Yes — [Check 2: redact validation] | ✅ |
| 4 | Báo cáo Telegram được gửi đi với Markdown | Yes — [Check 3: AI Reporter manual run] | ✅ |

### Scope & Proof Check
- [x] Executor làm đúng Scope, không mở rộng âm thầm
- [x] Proof là output thực tế, không phải lời khẳng định
- [x] Proof cover hết Validation Plan

### Verdict
> **APPROVED** — Đã đầy đủ bằng chứng kiểm thử (DB models, Dispatcher catch, context redact, Telegram report). Yêu cầu Claude Code tiến hành Phase 7 (Handoff) và archive.

---

## Handoff Note
*(Claude Code điền vào sau khi Anti APPROVED)*

- **Trạng thái sau execution**: Hệ thống Incident Logging MVP đã đi vào hoạt động.
  - DB: 2 bảng `incident_logs` + `incident_groups` đã được tạo trên PostgreSQL chính (revision `c9d0e1f2a3b4`).
  - Code: `app/services/incident_logger.py` (mới), `app/adapters/dispatcher.py` (đã wrap catch boundary), `workers/ai_reporter.py` (mới), `app/database/models.py` (thêm 2 model).
  - Vận hành: AI Reporter chạy thủ công OK, gửi qua Telegram OK với Gemini 2.5 Flash. Redact pipeline đã verify loại bỏ cookie/token/proxy_auth.
- **Những gì cần làm tiếp (NGOÀI scope TASK-018, đề xuất tạo task riêng nếu cần)**:
  - Đăng ký cron / PM2 cho `workers/ai_reporter.py` chạy 23:59 hằng ngày (hiện chỉ chạy thủ công).
  - Tier 1-2 alerting (real-time critical + burst alert) chưa có — đây là phạm vi giai đoạn 2 theo DECISION-005 §3.2.
  - Auto-Healing (Phase 2/3 trong DECISION-005 §3.5) — out of scope, chờ quyết định kế tiếp.
  - Monitor `incident_logs` 1-2 tuần để đo độ ồn của signature, tinh chỉnh thuật toán normalize nếu nhóm sai/bị phân mảnh.
- **Archived**: Yes — 2026-04-26 by Claude Code (Phase 7 Handoff per Anti's APPROVED Sign-off Gate).
