# TASK-018: AI Log Analyzer - Observability & Reporting MVP

## Metadata
| Field | Value |
|---|---|
| **ID** | TASK-018 |
| **Status** | Done |
| **Priority** | P1 |
| **Owner** | Antigravity |
| **Executor** | Codex |
| **Related Plan** | PLAN-018 |
| **Created** | 2026-04-26 |
| **Updated** | 2026-04-26 (Done — APPROVED by Anti, archived by Claude Code) |

---

## Objective
Xây dựng hệ thống thu thập lỗi có cấu trúc từ Dispatcher và tổng hợp báo cáo sức khỏe hàng ngày (Daily Health Report) qua Telegram bằng Gemini AI, không bao gồm tính năng Auto-Healing.

---

## Scope
- Tạo DB models `IncidentLog` và `IncidentGroup` bằng Alembic.
- Cập nhật `dispatcher.py` để catch exception và ghi vào DB.
- Tạo service `incident_logger.py` để băm lỗi, lọc dữ liệu nhạy cảm và UPSERT vào bảng group.
- Viết cron script `workers/ai_reporter.py` để lấy 20 lỗi nhiều nhất trong ngày, gọi Gemini Flash, và đẩy qua Telegram.

## Out of Scope
- Auto-Healing (Tự động sửa lỗi, restart worker tự động).
- Thiết kế Dashboard UI trên web.

---

## Blockers
- Đang chờ User xác nhận cấu hình `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` và `GEMINI_API_KEY`.

---

## Acceptance Criteria
- [x] Bảng `incident_logs` và `incident_groups` được tạo đúng theo thiết kế.
- [x] Bắt được lỗi tại vòng ngoài của Dispatcher và lưu vào DB thành công.
- [x] Dữ liệu nhạy cảm (cookie, token, proxy_auth) trong `context_json` phải bị loại bỏ.
- [x] Báo cáo Telegram được gửi đi với format Markdown đẹp, tổng hợp đúng danh sách lỗi bằng AI.

---

## Execution Notes
*(Executor điền vào trong khi làm — không để trống khi Done)*

- [x] Bước 1: Setup DB Models — đã thêm models, tạo migration `c9d0e1f2a3b4_add_incident_tables.py`, chạy `alembic upgrade head` thành công; proof chi tiết nằm trong `agents/plans/active/PLAN-018.md`.
- [x] Bước 2: Tạo `incident_logger.py` — hash signature, redact context, insert/upsert DB đã compile và validate bằng synthetic incident.
- [x] Bước 3: Tích hợp vào `dispatcher.py` — synthetic dispatcher failure đã tạo incident thành công.
- [x] Bước 4: Tạo `ai_reporter.py` — Gemini report + Telegram send chạy thành công thủ công.
- [x] Bước 5: Verify hệ thống — proof chi tiết nằm trong `agents/plans/active/PLAN-018.md`.

---

## Verification Proof
*(Bắt buộc điền trước khi chuyển Status → Verified)*

Proof chi tiết được lưu trong `PLAN-018.md` mục **Execution Notes → Verification Proof** (đã archive). Tóm tắt:

- Migration `c9d0e1f2a3b4_add_incident_tables.py` đã chạy `alembic upgrade head` thành công trên PostgreSQL — `incident_logs` và `incident_groups` tồn tại với đầy đủ cột.
- Synthetic dispatcher failure đã ghi 1 incident với `error_signature=124a8788f77ad921`, `dispatcher_result_ok=False`, group `occurrence_count=1`.
- Redact validation: cả 3 secret (`SECRET_COOKIE`, `SECRET_TOKEN`, `SECRET_PROXY`) bị loại khỏi `context_json` (`secret_in_context=False`); field `safe` và `nested.url` được giữ.
- `workers/ai_reporter.py` chạy thủ công thành công: Gemini 2.5 Flash trả về (~18s), `TelegramNotifier` đăng ký và `[AI Reporter] Sent daily health report. groups=2`.

---

## Status History
| Date | Status | Note |
|---|---|---|
| 2026-04-26 | New | Task được tạo bởi Anti |
| 2026-04-26 | Planned | PLAN-018 được tạo và chờ review |
| 2026-04-26 | Done | Codex execute hoàn tất, Anti APPROVED tại Sign-off Gate, Claude Code Phase 7 handoff & archive |
