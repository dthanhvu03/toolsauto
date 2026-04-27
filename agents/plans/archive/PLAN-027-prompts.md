# Prompt Ra Lệnh Cho Agents — PLAN-027: Refactoring Sprint

**Tạo bởi:** Antigravity — 2026-04-27
**Cập nhật:** Đã loại scope trùng lặp (AI Pathway đã xong ở TASK-023/024)

> **Thứ tự thực hiện:** Phase 1 (Claude Code) → Phase 2 (Codex) → Phase 3 (Codex) → Phase 4 (Claude Code)

---

## 🟢 PROMPT 1 — Gửi cho Claude Code (Phase 1: Schema Centralization)

```
Act as Claude Code for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 1

Startup sequence bắt buộc:
1. Đọc agents/handoffs/current-status.md
2. Đọc agents/plans/active/PLAN-027-codebase-refactor-sprint.md
3. Đọc agents/CODING_STANDARDS.md (mục Schema Centralization Rule)

Nhiệm vụ: Dời toàn bộ Pydantic BaseModel đang nằm sai chỗ trong app/routers/ sang app/schemas/

Quy trình:
1. Chạy: grep -rn "class.*BaseModel" app/routers/ --include="*.py"
   → Liệt kê tất cả class cần dời
2. Tạo các file schema theo domain trong app/schemas/:
   - compliance.py, jobs.py, accounts.py, platform_config.py, threads.py
   - __init__.py (re-export tất cả)
3. Di chuyển từng class BaseModel sang file schema tương ứng
4. Cập nhật import trong các file router
5. KHÔNG đổi tên class, KHÔNG đổi field, KHÔNG thêm logic mới
6. Verify:
   - grep -rn "class.*BaseModel" app/routers/ → phải = 0 kết quả
   - python -c "from app.main import app; print('OK')"
   - cd /home/vu/toolsauto && venv/bin/pytest tests/ -x
7. Ghi kết quả verify vào PLAN-027 > Execution Notes > Phase 1
8. Cập nhật agents/handoffs/current-status.md

Quy tắc: Minimal diff. Giữ nguyên behavior 100%. Mỗi file schema = 1 commit riêng.
```

---

## 🔵 PROMPT 2 — Gửi cho Codex (Phase 2: Thin Controller)

```
Act as Codex for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 2

Startup sequence bắt buộc:
1. Đọc agents/handoffs/current-status.md
2. Đọc agents/plans/active/PLAN-027-codebase-refactor-sprint.md
3. Xác nhận Phase 1 (Schema Centralization) đã Done — nếu chưa → DỪNG, báo Anti

Nhiệm vụ: Tách logic nghiệp vụ (SQL thô, subprocess) ra khỏi app/routers/ sang app/services/

Xử lý theo thứ tự (file lớn nhất trước):
a) routers/platform_config.py (1063 LOC) → tạo services/platform_config_service.py
b) routers/compliance.py (929 LOC) → tạo services/compliance_service.py
c) routers/insights.py (883 LOC) → tạo services/insights_service.py
d) routers/syspanel.py (853 LOC) → tạo services/syspanel_service.py

Quy trình mỗi router:
1. Tạo file service mới trong app/services/
2. Di chuyển SQL queries, subprocess, tính toán phức tạp vào service
3. Router chỉ giữ: route decorator + validate input + gọi service + trả response
4. KHÔNG đổi route URL, KHÔNG đổi response format

Verify SAU MỖI router:
- wc -l app/routers/<file>.py → phải < 500
- grep -c "db.execute\|text(" app/routers/<file>.py → phải = 0
- python -c "from app.main import app; print('OK')"
- Mỗi router tách = 1 commit riêng

Ghi kết quả vào PLAN-027 > Execution Notes > Phase 2
Nếu gặp logic phức tạp khó tách → DỪNG → báo Anti
```

---

## 🔵 PROMPT 3 — Gửi cho Codex (Phase 3: DRY Error Handling)

```
Act as Codex for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 3

Startup sequence bắt buộc:
1. Đọc agents/handoffs/current-status.md
2. Đọc agents/plans/active/PLAN-027-codebase-refactor-sprint.md

Nhiệm vụ: Tạo Playwright Decorator @playwright_safe_action và apply vào Adapter

Quy trình:
1. Tạo file app/adapters/common/decorators.py với decorator @playwright_safe_action
2. Quét các hàm có try-except Playwright lặp lại:
   - grep -n "except.*Timeout" app/adapters/facebook/adapter.py
   - grep -n "except.*Timeout" app/adapters/generic/adapter.py
3. Apply decorator vào helper functions (KHÔNG apply vào public method publish/open_session):
   - facebook/adapter.py: _click_locator, _safe_goto, _wait_and_locate_array
   - generic/adapter.py: các hàm step execution
4. CHỈ apply cho hàm có try-except pattern GIỐNG NHAU
   Nếu hàm có error handling đặc thù (checkpoint detection) → KHÔNG đụng

Verify:
- grep -c "except.*Timeout" app/adapters/facebook/adapter.py → phải giảm > 50%
- python -c "from app.adapters.facebook.adapter import FacebookAdapter; print('OK')"
- python -c "from app.main import app; print('OK')"

1 commit: tạo decorator, 1 commit: apply facebook, 1 commit: apply generic
Ghi kết quả vào PLAN-027 > Execution Notes > Phase 3
```

---

## 🟢 PROMPT 4 — Gửi cho Claude Code (Phase 4: Enum & Constants)

```
Act as Claude Code for ToolsAuto.
Execute: agents/plans/active/PLAN-027-codebase-refactor-sprint.md — Phase 4

Startup sequence bắt buộc:
1. Đọc agents/handoffs/current-status.md
2. Đọc agents/plans/active/PLAN-027-codebase-refactor-sprint.md

Nhiệm vụ: Gom Magic Strings vào Enum class tập trung

Quy trình:
1. Mở rộng app/constants.py — thêm:
   - Platform(str, Enum): FACEBOOK, THREADS, TIKTOK, INSTAGRAM
   - JobType(str, Enum): POST, COMMENT, STORY
   - WorkflowAction(str, Enum): navigate, click, type, wait, wait_visible, upload, scroll, select
2. Quét magic strings:
   - grep -rn '"facebook"' app/ workers/ --include="*.py"
   - grep -rn '"POST"' app/ workers/ --include="*.py"
3. Replace từng magic string bằng Enum
4. KHÔNG đổi logic, chỉ thay chuỗi bằng Enum
5. Vì dùng (str, Enum) nên Platform.FACEBOOK == "facebook" → tương thích ngược 100%

Verify:
- grep -rn '"facebook"' app/adapters/dispatcher.py → phải = 0 (ngoài comment)
- python -c "from app.constants import Platform; assert Platform.FACEBOOK == 'facebook'"
- python -c "from app.main import app; print('OK')"
- cd /home/vu/toolsauto && venv/bin/pytest tests/ -x

Chia commit: 1 per domain (platform, job_type, actions)
Ghi kết quả vào PLAN-027 > Execution Notes > Phase 4
Cập nhật agents/handoffs/current-status.md khi xong
```

---

## Checklist cho anh Vu

| Thứ tự | Prompt | Gửi cho | Phụ thuộc |
|---|---|---|---|
| 1 | PROMPT 1 — Schema Centralization | **Claude Code** | Không |
| 2 | PROMPT 2 — Thin Controller | **Codex** | Phase 1 xong |
| 3 | PROMPT 3 — DRY Error Handling | **Codex** | Không |
| 4 | PROMPT 4 — Enum & Constants | **Claude Code** | Không |

> Sau mỗi Phase: kiểm tra PM2 + Dashboard OK trước khi chuyển Phase tiếp!
