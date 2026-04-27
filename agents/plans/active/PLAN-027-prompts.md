# Prompt Ra Lệnh Cho Agents — PLAN-027: Refactoring Sprint

**Tạo bởi:** Antigravity — 2026-04-27
**Mục đích:** Copy-paste từng prompt dưới đây gửi cho đúng Agent để thực thi PLAN-027.

> **Thứ tự thực hiện:** Phase 1 (Claude Code) → Phase 6 (Claude Code) → Phase 2 (Codex) → Phase 3 (Codex) → Phase 4 (Codex)
> Phase 5 bỏ qua cho đến khi có bug/feature chạm Facebook Adapter.

---

## 🟢 PROMPT 1 — Gửi cho Claude Code (Phase 1: Schema Centralization)

```
Act as Claude Code for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 1

Nhiệm vụ: Dời toàn bộ Pydantic BaseModel đang nằm sai chỗ trong app/routers/ sang app/schemas/

Quy trình bắt buộc:
1. Đọc PLAN-027 Phase 1 trước khi viết 1 dòng code
2. Chạy: grep -rn "class.*BaseModel" app/routers/ --include="*.py"
   → Liệt kê tất cả class cần dời
3. Tạo các file schema theo domain trong app/schemas/:
   - compliance.py (KeywordCreateBody, KeywordUpdateBody, TestCheckBody)
   - jobs.py (nếu có)
   - accounts.py (nếu có)
   - platform_config.py (nếu có)
   - threads.py (nếu có)
   - __init__.py (re-export tất cả)
4. Di chuyển từng class BaseModel sang file schema tương ứng
5. Cập nhật import trong các file router: from app.schemas.xxx import YYY
6. KHÔNG đổi tên class, KHÔNG đổi field, KHÔNG thêm logic mới
7. Verify:
   - grep -rn "class.*BaseModel" app/routers/ → phải = 0 kết quả
   - python -c "from app.main import app; print('OK')"
   - pm2 restart Web_Dashboard && sleep 5 && pm2 status
8. Ghi kết quả verify vào PLAN-027 > Execution Notes > Phase 1

Quy tắc:
- Minimal diff — chỉ dời, không refactor "tiện thể"
- Giữ nguyên behavior 100%
- Nếu phát hiện circular import → dùng lazy import trong function body
- Mỗi file schema tách = 1 commit riêng

Output: Báo cáo danh sách file đã tạo/sửa + verification proof.
```

---

## 🟢 PROMPT 2 — Gửi cho Claude Code (Phase 6: Enum & Constants)

```
Act as Claude Code for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 6

Nhiệm vụ: Gom tất cả Magic Strings rải rác trong dự án vào các Enum class tập trung.

Quy trình bắt buộc:
1. Đọc PLAN-027 Phase 6 trước khi viết 1 dòng code
2. Mở rộng file app/constants.py (đã tồn tại) — thêm các Enum class:
   - Platform(str, Enum): FACEBOOK, THREADS, TIKTOK, INSTAGRAM
   - JobType(str, Enum): POST, COMMENT, STORY
   - WorkflowAction(str, Enum): navigate, click, type, wait, wait_visible, upload, scroll, select
3. Quét tìm magic strings:
   - grep -rn '"facebook"' app/ workers/ --include="*.py"
   - grep -rn '"POST"' app/ workers/ --include="*.py" (loại trừ HTTP method)
   - grep -rn 'VALID_ACTIONS' app/ --include="*.py"
4. Replace từng magic string bằng Enum tương ứng
5. KHÔNG đổi logic, KHÔNG đổi behavior, chỉ thay chuỗi bằng Enum
6. Lưu ý: str(Enum) trong Python trả về "Platform.FACEBOOK", nhưng vì dùng (str, Enum) nên .value tự động là "facebook" — tương thích ngược 100%
7. Verify:
   - grep -rn '"facebook"' app/adapters/dispatcher.py → phải = 0 (ngoại trừ comment)
   - python -c "from app.constants import Platform; assert Platform.FACEBOOK == 'facebook'; print('OK')"
   - python -c "from app.main import app; print('OK')"
   - pm2 restart Web_Dashboard && sleep 5 && pm2 status
8. Ghi kết quả verify vào PLAN-027 > Execution Notes > Phase 6

Quy tắc:
- Minimal diff — chỉ replace string, không refactor logic
- Chia thành nhiều commit nhỏ (1 commit per domain: platform, job_type, actions)
- Nếu 1 file dùng magic string ở > 5 chỗ → dùng alias ở đầu file: `FACEBOOK = Platform.FACEBOOK`

Output: Báo cáo số lượng magic strings đã thay thế + verification proof.
```

---

## 🔵 PROMPT 3 — Gửi cho Codex (Phase 2: Thin Controller)

```
Act as Codex for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 2

Nhiệm vụ: Tách logic nghiệp vụ (SQL thô, subprocess, tính toán) ra khỏi app/routers/ sang app/services/

Quy trình bắt buộc:
1. Đọc PLAN-027 Phase 2 trước khi viết 1 dòng code
2. Xử lý theo thứ tự ưu tiên (file lớn nhất trước):

   a) routers/platform_config.py (1063 LOC) → tạo services/platform_config_service.py
      - Dời toàn bộ subprocess.run (tmux), SQL queries
      - Router chỉ giữ: route decorator + gọi service + trả response

   b) routers/compliance.py (929 LOC) → tạo services/compliance_service.py
      - Dời: SQL analytics, AI keyword suggestion logic, CSV export logic
      - Router chỉ giữ: validate input + gọi service

   c) routers/insights.py (883 LOC) → tạo services/insights_service.py
      - Dời: SQL analytics phức tạp, aggregation logic

   d) routers/syspanel.py (853 LOC) → tạo services/syspanel_service.py
      - Dời: System monitoring queries, PM2 interaction logic

3. Mỗi service file PHẢI:
   - Dùng @staticmethod hoặc classmethod
   - Nhận db: Session làm tham số
   - Trả về dict/list (không trả Response object — đó là việc của router)

4. KHÔNG đổi route URL, KHÔNG đổi response format, KHÔNG đổi behavior
5. Verify SAU MỖI router (không đợi làm hết mới verify):
   - wc -l app/routers/<file>.py → phải < 500
   - grep -c "db.execute\|text(" app/routers/<file>.py → phải = 0 (hoặc < 3)
   - grep -c "subprocess" app/routers/<file>.py → phải = 0
   - python -c "from app.main import app; print('OK')"
   - pm2 restart Web_Dashboard && sleep 5 && curl -s http://localhost:8000/health
6. Mỗi router tách = 1 commit riêng
7. Ghi kết quả verify vào PLAN-027 > Execution Notes > Phase 2

Quy tắc:
- Không mở rộng scope — chỉ dời logic, không refactor logic
- Nếu router < 300 LOC → bỏ qua, không cần tách
- Nếu gặp logic phức tạp khó tách → DỪNG → báo Anti

Output: Báo cáo từng router đã tách (LOC trước/sau) + verification proof.
```

---

## 🔵 PROMPT 4 — Gửi cho Codex (Phase 3: Kill Duplicate AI Pathway)

```
Act as Codex for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 3

Nhiệm vụ: Deprecate gemini_api.py, migrate 8 caller sang ai_pipeline.py thông qua helper wrapper.

Quy trình bắt buộc:
1. Đọc PLAN-027 Phase 3 trước khi viết 1 dòng code
2. Tạo helper wrapper trong app/services/ai_runtime.py:
   ```python
   def ask_via_pipeline(prompt: str, **kwargs) -> Optional[str]:
       """Drop-in replacement cho GeminiAPIService().ask(prompt)"""
       from app.services.ai_pipeline import pipeline
       result, _meta = pipeline.generate_text(prompt, **kwargs)
       return result
   ```

3. Migrate từng caller theo thứ tự an toàn (dễ nhất trước):
   - services/affiliate_ai.py → thay GeminiAPIService().ask() bằng ask_via_pipeline()
   - routers/affiliates.py → tương tự
   - routers/ai_studio.py → tương tự
   - routers/compliance.py → tương tự (hàm ai_suggest_keywords)
   - services/fb_compliance.py → tương tự
   - services/threads_news.py → tương tự (giữ lazy import pattern)
   - workers/threads_auto_reply.py → tương tự

4. ĐẶC BIỆT — services/content_orchestrator.py:
   - KHÔNG xoá import gemini_api ở đây
   - Đây là fallback CÓ CHỦ ĐÍCH khi 9Router fail
   - Chỉ thêm comment: # DEPRECATED FALLBACK — sẽ chuyển vào pipeline khi 9Router có multi-provider
   
5. Đánh dấu gemini_api.py là deprecated:
   - Thêm DeprecationWarning ở đầu file
   - Thêm docstring: "Use app.services.ai_pipeline instead"

6. Verify:
   - grep -rn "from app.services.gemini_api" app/ workers/ --include="*.py"
     → chỉ còn content_orchestrator.py (fallback)
   - python -c "from app.services.ai_runtime import ask_via_pipeline; print('OK')"
   - python -c "from app.main import app; print('OK')"
   - pm2 restart all && sleep 10 && pm2 status
7. Ghi kết quả verify vào PLAN-027 > Execution Notes > Phase 3

Quy tắc:
- Giữ lazy import pattern ở những file đang dùng (5/8 caller)
- KHÔNG xoá file gemini_api.py — chỉ deprecate
- KHÔNG động vào gemini_rpa.py — nằm ngoài scope
- Mỗi caller migrate = 1 commit riêng

Output: Báo cáo từng caller đã migrate + grep proof + verification proof.
```

---

## 🔵 PROMPT 5 — Gửi cho Codex (Phase 4: DRY Error Handling)

```
Act as Codex for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 4

Nhiệm vụ: Tạo Playwright Decorator @playwright_safe_action và apply vào các Adapter để loại bỏ code try-catch bị copy-paste.

Quy trình bắt buộc:
1. Đọc PLAN-027 Phase 4 trước khi viết 1 dòng code
2. Tạo file app/adapters/common/decorators.py:
   ```python
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
                   return None
               except Exception as e:
                   logger.exception("[%s] Unexpected: %s", description or func.__name__, e)
                   raise
           return wrapper
       return decorator
   ```

3. Quét các hàm có try-except Playwright lặp lại:
   - grep -n "except.*Timeout" app/adapters/facebook/adapter.py
   - grep -n "except.*Timeout" app/adapters/generic/adapter.py

4. Apply decorator vào các hàm helper (KHÔNG apply vào public method publish/open_session):
   - facebook/adapter.py: _click_locator, _safe_goto, _wait_and_locate_array, _find_first_visible
   - generic/adapter.py: các hàm step execution

5. QUAN TRỌNG: Chỉ apply decorator cho các hàm mà try-except pattern GIỐNG NHAU.
   Nếu hàm có error handling đặc thù (ví dụ: checkpoint detection) → KHÔNG đụng.

6. Verify:
   - Đếm số khối try-except trước/sau:
     grep -c "except.*Timeout" app/adapters/facebook/adapter.py
     → phải giảm ít nhất 50%
   - python -c "from app.adapters.facebook.adapter import FacebookAdapter; print('OK')"
   - python -c "from app.main import app; print('OK')"
   - pm2 restart FB_Publisher_1 && sleep 5 && pm2 status
7. Ghi kết quả verify vào PLAN-027 > Execution Notes > Phase 4

Quy tắc:
- KHÔNG đổi behavior của bất kỳ hàm nào
- Decorator chỉ wrap, không thêm logic mới
- Nếu hàm có return value đặc biệt khi lỗi → phải điều chỉnh decorator hoặc bỏ qua hàm đó
- 1 commit: tạo decorator file, 1 commit: apply vào facebook, 1 commit: apply vào generic

Output: Báo cáo số try-except trước/sau + danh sách hàm đã apply + verification proof.
```

---

## 🟡 PROMPT 6 — Gửi cho Codex (Phase 5: Facebook Adapter Split) — CHỈ DÙNG KHI CÓ BUG

```
Act as Codex for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 5

⚠️ ĐIỀU KIỆN: Phase này chỉ được thực hiện khi có bug hoặc feature mới chạm file app/adapters/facebook/adapter.py. Nếu không có trigger → DỪNG, không làm.

Nhiệm vụ: Tách God Object FacebookAdapter (2373 LOC) thành facade + module con.

Quy trình bắt buộc:
1. Đọc PLAN-027 Phase 5 trước khi viết 1 dòng code
2. Tạo các module con:
   - facebook/session.py ← open_session() + _is_session_alive, _try_recover_session, _ensure_authenticated_context, _switch_to_personal_profile
   - facebook/publish_flow.py ← publish() + intercept_graphql, upload/caption/click helpers
   - facebook/verify.py ← check_published_state() + post_comment() + page identity helpers
   - facebook/errors.py ← PageMismatchError + checkpoint detection helpers

3. Facade pattern cho adapter.py:
   ```python
   class FacebookAdapter(AdapterInterface):
       def open_session(self, profile_path):
           from .session import open_session
           return open_session(self.page, profile_path, self.logger)
       
       def publish(self, job):
           from .publish_flow import publish
           return publish(self.page, job, self.logger)
   ```

4. KHÔNG đổi public interface (AdapterInterface)
5. KHÔNG đổi behavior của bất kỳ method nào
6. Verify:
   - wc -l app/adapters/facebook/adapter.py → phải < 500
   - python -c "from app.adapters.facebook.adapter import FacebookAdapter, PageMismatchError; print('OK')"
   - python -c "from app.main import app; print('OK')"
7. Ghi kết quả verify vào PLAN-027 > Execution Notes > Phase 5

Output: Báo cáo LOC trước/sau cho từng file + verification proof.
```

---

## Checklist tổng hợp cho anh Vu

| Thứ tự | Prompt | Gửi cho | Khi nào |
|---|---|---|---|
| 1 | PROMPT 1 — Schema Centralization | **Claude Code** | Bắt đầu ngay |
| 2 | PROMPT 2 — Enum & Constants | **Claude Code** | Sau Phase 1 xong |
| 3 | PROMPT 3 — Thin Controller | **Codex** | Sau Phase 1 xong |
| 4 | PROMPT 4 — Kill Duplicate AI | **Codex** | Sau Phase 2 xong |
| 5 | PROMPT 5 — DRY Error Handling | **Codex** | Sau Phase 3 xong |
| 6 | PROMPT 6 — Adapter Split | **Codex** | Chỉ khi có bug chạm adapter |

> **Lưu ý quan trọng:** Sau mỗi Phase, kiểm tra PM2 status + Web Dashboard hoạt động bình thường trước khi chuyển sang Phase tiếp theo!
