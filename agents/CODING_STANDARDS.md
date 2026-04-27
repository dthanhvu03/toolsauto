# Coding Standards — ToolsAuto

**Cập nhật:** 2026-04-27
**Áp dụng cho:** Mọi AI Agent và Developer làm việc trong repo này.

Tài liệu này quy định các tiêu chuẩn code bắt buộc, được đúc kết từ đợt kiểm tra kiến trúc (Architecture Review) ngày 27/04/2026.

---

## 1. Quy tắc Tổ chức Thư mục (Directory Conventions)

### `app/routers/` — Tầng Controller (Thin Controller Rule)
| Được phép | CẤM |
|---|---|
| Nhận request, validate input | Viết câu lệnh SQL thô (`db.execute(text(...))`) |
| Gọi Service layer | Gọi subprocess / bash |
| Trả response (JSON / Template) | Chứa logic nghiệp vụ > 10 dòng |
| Import Schema từ `app/schemas/` | Định nghĩa Pydantic BaseModel ngay trong file router |

**Mẫu chuẩn:**
```python
# app/routers/compliance.py — ĐÚNG
from app.schemas.compliance import KeywordCreateBody
from app.services.compliance_service import ComplianceService

@router.post("/keywords")
def add_keyword(payload: KeywordCreateBody, db: Session = Depends(get_db)):
    result = ComplianceService.add_keyword(db, payload)
    return result
```

```python
# app/routers/compliance.py — SAI (Fat Controller)
@router.post("/keywords")
def add_keyword(payload: dict, db: Session = Depends(get_db)):
    keyword = payload.get("keyword", "").strip().lower()
    # ... 50 dòng logic nghiệp vụ ...
    db.execute(text("INSERT INTO keyword_blacklist ..."))
    db.commit()
    return {"success": True}
```

---

### `app/schemas/` — Tầng Validation (Schema Centralization Rule)
- Mọi Pydantic BaseModel PHẢI nằm trong thư mục này.
- Tổ chức theo domain: `compliance.py`, `jobs.py`, `accounts.py`, `threads.py`...
- Các file router và service chỉ được `import` schema, không được tự định nghĩa.

**Cấu trúc mục tiêu:**
```
app/schemas/
├── __init__.py
├── compliance.py      # KeywordCreateBody, KeywordUpdateBody, TestCheckBody
├── jobs.py            # JobCreateSchema, JobFilterSchema
├── accounts.py        # AccountCreateSchema, AccountUpdateSchema
├── threads.py         # ThreadsPostSchema
├── viral.py           # ViralMaterialSchema
└── log.py             # (đã có)
```

---

### `app/services/` — Tầng Business Logic (No God Service Rule)
| Quy tắc | Chi tiết |
|---|---|
| **Giới hạn LOC** | Không để 1 file service vượt quá 1000 dòng code. Nếu phát hiện — tách nhỏ theo domain. |
| **Single Source of Truth** | Mỗi hệ thống cốt lõi (AI, Notification, Compliance...) chỉ có 1 đường ống chính thức duy nhất. |
| **Cấm Duplicate Pathway** | Không tồn tại 2 file service cùng làm 1 việc (ví dụ: `ai_pipeline.py` + `gemini_api.py` cùng gọi AI). Một trong hai phải là canonical, cái còn lại phải được đánh dấu `@deprecated`. |
| **Lazy Import** | Khi Service A cần gọi Service B mà có nguy cơ Circular Import → dùng lazy import bên trong function body, không kéo lên top-level. |

**File vi phạm hiện tại cần refactor:**
| File | LOC | Vấn đề |
|---|---|---|
| `content_orchestrator.py` | ~45KB | God Service: ôm đồm caption, dịch thuật, hashtag, lọc từ khóa |
| `gemini_api.py` | ~12KB | Duplicate Pathway: song song với `ai_pipeline.py` |
| `settings.py` | ~37KB | Quá lớn, nên tách runtime_settings riêng |

---

### `app/adapters/` — Tầng Giao Tiếp External (Adapter Blind Rule)
| Quy tắc | Chi tiết |
|---|---|
| **Dispatcher Must Be Blind** | File `dispatcher.py` cấm hardcode rẽ nhánh theo tên platform (`if platform == "facebook"`). Phải gọi `WorkflowRegistry` để lấy Adapter. |
| **No God Object** | Một class Adapter không được vượt quá 1500 LOC. Nếu vượt — tách thành facade + module con. |
| **DRY Error Handling** | Luồng try/catch Playwright (timeout, screenshot, log) phải dùng Decorator hoặc Helper chung. Cấm copy-paste khối try-except giống nhau. |

**Mẫu Decorator bắt lỗi chuẩn (mục tiêu):**
```python
# app/adapters/common/decorators.py
import functools
from playwright.sync_api import TimeoutError as PlaywrightTimeout

def playwright_safe_action(timeout=5000, take_screenshot=True):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except PlaywrightTimeout as e:
                if take_screenshot and hasattr(self, 'page'):
                    self.page.screenshot(path=f"logs/error_{func.__name__}.png")
                logger.error("[%s] Timeout: %s", func.__name__, e)
                raise
            except Exception as e:
                logger.exception("[%s] Unexpected: %s", func.__name__, e)
                raise
        return wrapper
    return decorator
```

---

### `workers/` — Tầng Background Job
| Quy tắc | Chi tiết |
|---|---|
| **Hạn chế Database Polling** | Giảm thiểu `while True: sleep()` liên tục query DB. Ưu tiên Event-driven (Redis Pub/Sub, Message Queue). |
| **Graceful Shutdown** | Mọi worker phải bắt signal `SIGTERM` và cleanup đúng cách (đóng browser, commit DB, giải phóng lock). |
| **Heartbeat** | Worker chạy lâu phải cập nhật heartbeat để hệ thống phát hiện khi bị treo. |

---

## 2. Quy tắc Code Chung (General Coding Rules)

### Python Style
- **Import order**: stdlib → third-party → local (theo PEP 8).
- **Type hints**: Bắt buộc cho tất cả hàm public. Hàm private nên có nhưng không bắt buộc.
- **Docstring**: Mọi class và hàm public phải có docstring giải thích mục đích.

### Cấm Magic Strings
```python
# SAI — Magic String
if job.status == "DONE":
    ...
if platform == "facebook":
    ...

# ĐÚNG — Dùng Enum hoặc Constant
from app.database.models import JobStatus
if job.status == JobStatus.DONE:
    ...
```

### Logging
- Dùng format chuẩn: `[MODULE] [Job-ID] [PHASE] Message`
- Ví dụ: `logger.info("[PUBLISHER] [Job-%s] [CLAIM] Account='%s'", job.id, account.name)`
- KHÔNG dùng f-string trong logger (gây overhead khi log level bị tắt).

### Error Handling
- Không bắt `except Exception` trần trụi mà không log.
- Luôn `db.rollback()` trước khi retry hoặc raise lại.
- Các lỗi Playwright phải capture screenshot trước khi raise.

---

## 3. Quy tắc Database

### Models
- Tất cả model SQLAlchemy nằm trong `app/database/models.py` (hoặc package `models/` sau khi tách).
- Relationship dùng string: `relationship("Job")`, không import class trực tiếp.
- ForeignKey dùng string: `ForeignKey("accounts.id")`.

### Migrations
- Mọi thay đổi schema PHẢI đi qua Alembic migration (`python manage.py db migrate`).
- KHÔNG bao giờ sửa schema bằng tay trên production DB.
- Sau khi tạo migration, verify bằng: `python manage.py db upgrade head`.

### Data Retention
- Bảng `job_events` và `incident_logs` phải có cơ chế tự động xóa dữ liệu > 30 ngày.
- Không để bảng log phình to không kiểm soát trên VPS.

---

## 4. Quy tắc Frontend (HTMX + Jinja2)

### Template
- Không viết JavaScript inline > 30 dòng. Tách ra file `.js` riêng trong `static/`.
- HTMX trigger: Luôn kiểm tra race condition giữa `load` event và JS custom event.
- Không dùng emoji trong UI. Dùng inline SVG hoặc icon library.

### CSS
- Ưu tiên Tailwind utility classes.
- Custom CSS chỉ khi Tailwind không cover được.
- Dark mode phải được hỗ trợ ở mọi component mới.

---

## 5. Quy tắc DevOps

### Deploy
- Cấm `git pull` tay trên VPS. Mọi deploy phải đi qua CI/CD (`deploy.yml`).
- Workflow: Push code lên `develop` hoặc `main` → Github Actions tự kéo code + chạy DB upgrade + restart PM2.

### PM2
- Mọi process mới phải được khai báo trong `ecosystem.config.js`.
- Log phải được rotate (max 10MB per file).

---

> **Nguyên tắc vàng**: Code mới viết hôm nay phải tốt hơn code viết hôm qua. Không thêm nợ kỹ thuật mới.
