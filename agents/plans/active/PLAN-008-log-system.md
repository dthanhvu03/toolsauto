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

- [ ] Check 1: `tail -n 20 storage/logs/app.log` phải có Timestamp.
- [ ] Check 2: `pm2 logs` phải chỉ có 1 Timestamp ở Console.
- [ ] Check 3: Không còn hiện `IDLE Backlog:` ở Console trong 2 phút treo máy.

---

## Rollback Plan
Nếu execution fail → `git checkout -- app/utils/logger.py workers/*.py`

---

## Execution Notes
- ⏳ Bước 1: 
- ⏳ Bước 2: 
- ⏳ Bước 3: 

**Verification Proof**:
```
```

---

## Anti Sign-off Gate ⛔
**Reviewed by**: Antigravity — [TBD]

### Acceptance Criteria Check
| # | Criterion | Proof có không? | Pass? |
|---|---|---|---|
| 1 | Hết Double Timestamp Console | TBD | ⏳ |
| 2 | Hết IDLE Backlog Spam UI | TBD | ⏳ |
| 3 | Có Timestamp File Backup cục lượng | TBD | ⏳ |

### Scope & Proof Check
- [ ] Executor làm đúng Scope
- [ ] Proof là output thực tế

### Verdict
> **TBD**
