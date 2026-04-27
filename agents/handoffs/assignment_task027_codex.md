# Handoff — TASK-027 Expansion / 2026-04-27

## System State
| Item | State |
|---|---|
| **Environment** | WSL Ubuntu / Python 3.10 / PM2 |
| **Backend** | Running |
| **Git Branch** | develop |
| **Git Status** | Modified: ARCHITECTURE_REVIEW.md, PLAN-027, TASK-027, current-status.md |

---

## Done This Session
- ✅ **Research & Audit**: Đã quét toàn bộ `app/routers/` và phát hiện vi phạm SQL/Fat Controller tại 10+ file.
- ✅ **Planning**: Cập nhật PLAN-027-EXT với 5 Phase hành động triệt để.
- ✅ **Acceptance**: Anh Vu đã duyệt kế hoạch mở rộng.

---

## Active Tasks
| Task | Executor | Phase | Blocker |
|---|---|---|---|
| TASK-027 | Codex | Phase 1: God Router Eradication | None |

---

## Unfinished
- ⏳ **Phase 1: God Router Eradication** — trạng thái: Mới khởi tạo. Cần bắt đầu với `dashboard.py`.

---

## Blockers / Risks
- **Risk**: `dashboard.py` chứa nhiều logic lồng ghép với HTMX fragments. Mức độ: **High**. Cần đảm bảo `DashboardService` trả về đúng data structure cho templates.

---

## Next Action (FOR CODEX)

1. **Codex**: Tạo `app/services/dashboard_service.py`.
2. **Codex**: Di chuyển toàn bộ logic query từ các route `/app/logs/*`, `/app/viral/*`, `/app/jobs/*` bên trong `dashboard.py` sang `DashboardService`.
3. **Codex**: Cập nhật `app/routers/dashboard.py` để inject `DashboardService` và xóa bỏ `db: Session` nếu có thể (hoặc chỉ dùng service).
4. **Codex**: Chạy `python3 -m py_compile` để verify cú pháp sau refactor.

---

*Handoff written by: Antigravity — 2026-04-27 12:40*
