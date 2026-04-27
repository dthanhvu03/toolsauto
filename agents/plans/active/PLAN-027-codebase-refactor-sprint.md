# PLAN-027: Refactoring Sprint — Chuẩn Hoá Kiến Trúc Theo Tiêu Chuẩn Quốc Tế

## Metadata
| Field | Value |
|---|---|
| **ID** | PLAN-027 |
| **Status** | Active |
| **Executor** | Codex (Phase 2,3,4,5) / Claude Code (Phase 1,6) |
| **Created by** | Antigravity |
| **Related Task** | TASK-027 |
| **Related ADR** | DECISION-006-codebase-refactor-rfc |
| **Created** | 2026-04-27 |
| **Updated** | 2026-04-27 |

---

## Goal
Loại bỏ toàn bộ vi phạm nguyên tắc thiết kế phần mềm quốc tế (SOLID, Clean Architecture, DRY) đã được phát hiện trong đợt Architecture Review ngày 27/04/2026. Biến codebase ToolsAuto thành hệ thống chuẩn Enterprise, sẵn sàng scale.

---

## Context
- Dự án ToolsAuto đạt ~50K LOC, kiến trúc phân tầng tốt nhưng ranh giới giữa các tầng bị mờ nhạt.
- Tài liệu tham chiếu: `agents/ARCHITECTURE_REVIEW.md`, `agents/CODING_STANDARDS.md`, `agents/decisions/DECISION-006-codebase-refactor-rfc.md`.
- Hệ thống đang chạy production ổn định — refactor phải đảm bảo ZERO downtime.

---

## Scope & Approach — 6 Phase

---

### Phase 1: Schema Centralization
**Executor:** Claude Code
**Effort:** ~2 giờ
**Nguyên tắc sửa:** Separation of Concerns

**Bước 1.1** — Quét tìm tất cả Pydantic BaseModel đang nằm sai chỗ:
```bash
grep -rn "class.*BaseModel" app/routers/ --include="*.py"
```

**Bước 1.2** — Tạo các file schema theo domain:
```
app/schemas/
├── __init__.py          # Re-export tất cả
├── compliance.py        # KeywordCreateBody, KeywordUpdateBody, TestCheckBody
├── jobs.py              # JobCreateSchema, JobFilterSchema...
├── accounts.py          # AccountSchema...
├── platform_config.py   # PlatformPayload...
├── threads.py           # ThreadsSchema...
└── log.py               # (đã có)
```

**Bước 1.3** — Di chuyển từng class BaseModel sang file schema tương ứng.

**Bước 1.4** — Cập nhật import trong các file router: `from app.schemas.compliance import KeywordCreateBody`

**Bước 1.5** — Verify: Chạy `python -c "from app.routers import compliance, jobs, accounts"` + grep confirm không còn BaseModel trong routers.

---

### Phase 2: Thin Controller
**Executor:** Codex
**Effort:** ~6 giờ
**Nguyên tắc sửa:** Single Responsibility, Fat Controller

**Ưu tiên theo kích thước file (lớn nhất trước):**

| # | Router | LOC | Vấn đề chính | Service mới tạo |
|---|---|---|---|---|
| 1 | `platform_config.py` | 1063 | subprocess, SQL thô | `services/platform_config_service.py` |
| 2 | `insights.py` | 883 | SQL analytics phức tạp | `services/insights_service.py` |
| 3 | `compliance.py` | 929 | SQL thô, AI logic | `services/compliance_service.py` |
| 4 | `syspanel.py` | 853 | System monitoring logic | `services/syspanel_service.py` |

**Bước 2.1** — Với mỗi router:
  1. Tạo file service mới trong `app/services/`
  2. Di chuyển toàn bộ logic nghiệp vụ (SQL queries, subprocess, tính toán) vào service
  3. Router chỉ giữ lại: route decorator + validate input + gọi service + trả response

**Bước 2.2** — Verify từng router:
```bash
wc -l app/routers/platform_config.py  # phải < 500
grep -c "db.execute\|text(" app/routers/platform_config.py  # phải = 0
grep -c "subprocess" app/routers/platform_config.py  # phải = 0
```

---

### Phase 3: Kill Duplicate AI Pathway
**Executor:** Codex
**Effort:** ~4-6 giờ
**Nguyên tắc sửa:** Single Source of Truth

**Bước 3.1** — Tạo helper wrapper (adapter signature cũ → mới):
```python
# app/services/ai_runtime.py
def ask_via_pipeline(prompt: str, **kwargs) -> Optional[str]:
    """Drop-in replacement cho GeminiAPIService().ask(prompt)"""
    result, _meta = pipeline.generate_text(prompt, **kwargs)
    return result
```

**Bước 3.2** — Migrate từng caller (8 file, theo thứ tự an toàn):
| # | File | Pattern cũ | Pattern mới |
|---|---|---|---|
| 1 | `services/affiliate_ai.py` | `GeminiAPIService().ask()` | `ask_via_pipeline()` |
| 2 | `routers/affiliates.py` | `GeminiAPIService().ask()` | `ask_via_pipeline()` |
| 3 | `routers/ai_studio.py` | lazy import | `ask_via_pipeline()` |
| 4 | `routers/compliance.py` | lazy import | `ask_via_pipeline()` |
| 5 | `services/fb_compliance.py` | lazy import | `ask_via_pipeline()` |
| 6 | `services/threads_news.py` | lazy import | `ask_via_pipeline()` |
| 7 | `workers/threads_auto_reply.py` | top-level import | `ask_via_pipeline()` |
| 8 | `services/content_orchestrator.py` | fallback | Giữ lại làm emergency fallback, thêm `@deprecated` warning |

**Bước 3.3** — Đánh dấu `gemini_api.py` là deprecated:
```python
# Đầu file gemini_api.py
import warnings
warnings.warn(
    "gemini_api.py is deprecated. Use app.services.ai_pipeline instead.",
    DeprecationWarning, stacklevel=2
)
```

**Bước 3.4** — Verify: `grep -rn "from app.services.gemini_api" app/ workers/ --include="*.py"` — chỉ còn `content_orchestrator.py` (fallback).

---

### Phase 4: DRY Error Handling
**Executor:** Codex
**Effort:** ~3 giờ
**Nguyên tắc sửa:** DRY (Don't Repeat Yourself)

**Bước 4.1** — Tạo file decorator:
```python
# app/adapters/common/decorators.py
import functools, logging
from playwright.sync_api import TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

def playwright_safe_action(timeout_ms=5000, take_screenshot=True, description=""):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except PlaywrightTimeout as e:
                if take_screenshot and hasattr(self, 'page') and self.page:
                    try:
                        self.page.screenshot(path=f"logs/error_{func.__name__}.png")
                    except Exception:
                        pass
                logger.error("[%s] Playwright Timeout: %s", description or func.__name__, e)
                return None  # hoặc raise tuỳ context
            except Exception as e:
                logger.exception("[%s] Unexpected error: %s", description or func.__name__, e)
                raise
        return wrapper
    return decorator
```

**Bước 4.2** — Apply decorator vào các hàm lặp lại trong `facebook/adapter.py`:
- `_click_locator`, `_safe_goto`, `_wait_and_locate_array`...

**Bước 4.3** — Apply tương tự vào `generic/adapter.py`.

**Bước 4.4** — Verify: Đếm số khối try-except Playwright trước/sau:
```bash
grep -c "except.*Timeout" app/adapters/facebook/adapter.py  # phải giảm > 50%
```

---

### Phase 5: Facebook Adapter Split (Opportunistic)
**Executor:** Codex
**Effort:** ~4 giờ
**Nguyên tắc sửa:** Single Responsibility, No God Object
**Điều kiện kích hoạt:** Chỉ thực hiện khi có bug/feature tiếp theo chạm `facebook/adapter.py`

**Bước 5.1** — Tách theo 3 public method:
```
app/adapters/facebook/
├── adapter.py           ← Facade ~200 LOC, delegate sang module con
├── session.py           ← open_session() + auth helpers (~500 LOC)
├── publish_flow.py      ← publish() + upload/caption/click (~700 LOC)
├── verify.py            ← check_published_state() + post_comment() (~1000 LOC)
├── errors.py            ← PageMismatchError + checkpoint detection
├── selectors.py         ← (giữ nguyên)
└── engagement.py        ← (giữ nguyên)
```

**Bước 5.2** — Facade pattern: `adapter.py` chỉ giữ class `FacebookAdapter` implement `AdapterInterface`, mỗi method gọi xuống module con.

**Bước 5.3** — Verify: `wc -l app/adapters/facebook/adapter.py` phải < 500 LOC.

---

### Phase 6: Enum & Constants
**Executor:** Claude Code
**Effort:** ~3 giờ
**Nguyên tắc sửa:** No Magic Strings

**Bước 6.1** — Tạo file constants tập trung:
```python
# app/constants.py (mở rộng file đã có)
from enum import Enum

class Platform(str, Enum):
    FACEBOOK = "facebook"
    THREADS = "threads"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"

class JobType(str, Enum):
    POST = "POST"
    COMMENT = "COMMENT"
    STORY = "STORY"

class WorkflowAction(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    WAIT = "wait"
    WAIT_VISIBLE = "wait_visible"
    UPLOAD = "upload"
    SCROLL = "scroll"
    SELECT = "select"
```

**Bước 6.2** — Replace magic strings trên toàn dự án:
```bash
# Tìm tất cả magic strings
grep -rn '"facebook"' app/ workers/ --include="*.py" | grep -v "test\|#\|comment"
grep -rn '"POST"' app/ workers/ --include="*.py" | grep -v "test\|#\|comment"
```

**Bước 6.3** — Verify: Grep xác nhận không còn magic string trong code chính.

---

## Risks
| Risk | Mức độ | Cách xử lý |
|---|---|---|
| Circular Import khi dời Schema | Medium | Dùng lazy import trong function body |
| Break existing API khi tách Router | High | Không đổi route URL, chỉ dời logic sang service |
| Regression khi tách Adapter | High | Phase 5 là Opportunistic, chỉ làm khi chạm adapter |
| Mất fallback AI khi xoá gemini_api | Medium | Giữ lại trong content_orchestrator, đánh dấu deprecated |

---

## Validation Plan
*(Executor phải thực hiện SAU MỖI Phase)*

- [ ] `python -c "from app.main import app; print('OK')"` — App khởi động không lỗi
- [ ] `grep` proof cho từng Phase (xác nhận không còn vi phạm)
- [ ] `pm2 restart Web_Dashboard && sleep 5 && pm2 status` — Dashboard chạy OK
- [ ] Truy cập Web Dashboard qua browser — UI hoạt động bình thường
- [ ] `pm2 logs --lines 10 --nostream` — Không có error mới

---

## Rollback Plan
Mỗi Phase là 1 commit riêng biệt. Nếu Phase nào fail:
```bash
git revert <commit-hash-of-failed-phase>
pm2 restart all
```

---

## Execution Notes
*(Executor điền vào theo thứ tự từng bước — KHÔNG để trống khi Done)*

- ⏳ Phase 1: Schema Centralization — Chưa bắt đầu
- ⏳ Phase 2: Thin Controller — Chưa bắt đầu
- ⏳ Phase 3: Kill Duplicate AI Pathway — Chưa bắt đầu
- ⏳ Phase 4: DRY Error Handling — Chưa bắt đầu
- ⏳ Phase 5: Facebook Adapter Split — Chờ trigger (Opportunistic)
- ⏳ Phase 6: Enum & Constants — Chưa bắt đầu

**Verification Proof**:
```
# Output thực tế của validation checks — điền khi thực hiện
```

---

## Anti Sign-off Gate ⛔
*(Anti điền vào — BLOCKING. Không có section này = Claude Code không được archive)*

**Reviewed by**: Antigravity — [YYYY-MM-DD]

### Acceptance Criteria Check
*(Copy từ TASK — điền từng dòng, không bỏ qua)*

| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Schema Centralization | Pending | ⏳ |
| 2 | Thin Controller | Pending | ⏳ |
| 3 | Kill Duplicate AI | Pending | ⏳ |
| 4 | DRY Error Handling | Pending | ⏳ |
| 5 | Facebook Adapter Split | Pending | ⏳ |
| 6 | Enum & Constants | Pending | ⏳ |
| 7 | System Stability | Pending | ⏳ |

### Scope & Proof Check
- [ ] Executor làm đúng Scope, không mở rộng âm thầm
- [ ] Proof là output thực tế, không phải lời khẳng định
- [ ] Proof cover hết Validation Plan

### Verdict
> **Pending** — Chờ thực hiện từng Phase

---

## Handoff Note
*(Claude Code điền vào sau khi Anti APPROVED)*

- Trạng thái sau execution: Chưa bắt đầu
- Những gì cần làm tiếp: Bắt đầu Phase 1
- Archived: No
