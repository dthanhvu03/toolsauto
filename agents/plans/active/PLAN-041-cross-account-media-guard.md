# PLAN-041: Cross-account media publish guard

| Field | Value |
|---|---|
| **ID** | PLAN-041 |
| **Task** | TASK-042 |
| **Status** | Approved · Phase 1 In Progress (Owner locked policy) |
| **Executor** | Codex |
| **Created** | 2026-07-24 |

## Problem

Hiện có:

| Lớp | Phạm vi | Gap |
|---|---|---|
| `(account_id, dedupe_key)` unique | 1 account | Acc B vẫn đăng cùng file |
| Claim atomic + mutex | 1 job / account+platform | Không chặn nội dung trùng |
| Reup anti-dupe | Biến đổi vs bản gốc viral | Không chặn cross-account |
| Dispatcher idempotency | Retry cùng job | Không chặn job khác |

Owner muốn: video đã (sắp) đăng account A → account B không đăng lại / không bốc nhầm cùng nội dung.

## Recommended design (default nếu Owner không chọn khác)

**Policy mặc định đề xuất:**

- Unique key = `sha256(file bytes)` trên job media (sau reup nếu có).
- Scope = **cùng `platform`** (facebook vs threads tách silo).
- Trạng thái chặn = job `PENDING | RUNNING | DONE` (không chặn theo `FAILED` / `INVALID` cũ — cho phép retry path tạo mới nếu cần).
- Viral: thêm `jobs.viral_material_id` (nullable FK) + partial unique: 1 material → 1 active job.

### Phương án so sánh

| | A. File content hash | B. Chỉ `viral_material_id` | C. Hybrid (khuyến nghị) |
|---|---|---|---|
| Phức tạp | TB | Thấp | TB+ |
| Cover manual upload | Có | Không | Có |
| Cover viral | Có | Có | Có |
| Rủi ro false positive | File copy đổi 1 byte → khác hash (OK); reup khác hash theo design | Thấp | TB |
| Rollback | Drop index/cột | Drop FK | Drop cả hai |

**Chọn C.** Phase 1 ship B + hash gate ở `JobService.create_job` / viral processor (không bắt buộc unique index hash ngay nếu sợ lock; ưu tiên app-level check + unique index khi ổn).

## Scope (Codex)

### Phase 1 — App-level gate (ít rủi ro)

1. Helper `media_content_hash(path) -> str` (sha256 stream, chunked).
2. Cột nullable: `jobs.content_hash`, `jobs.viral_material_id` (+ Alembic).
3. Trước `db.add(job)`:
   - Nếu có `viral_material_id` và đã tồn tại job active cùng material → raise / skip rõ message.
   - Nếu có `content_hash` và đã tồn tại job active cùng `(platform, content_hash)` khác hoặc cùng account → skip.
4. Viral processor: set `viral_material_id=mat.id`, hash file `_reup` trước create job.
5. Manual / bulk create: hash sau copy file.
6. Tests: create 2 jobs same hash different accounts → job 2 bị chặn; different platforms → OK.

### Phase 2 — DB enforce (sau verify Phase 1)

- Unique index partial Postgres:  
  `(platform, content_hash) WHERE content_hash IS NOT NULL AND status IN ('PENDING','RUNNING','DONE')`  
  (cú pháp partial unique theo status — nếu Postgres version/limit khó: unique `(platform, content_hash)` + app chỉ set hash khi active, clear khi FAILED).
- Unique partial `(viral_material_id) WHERE viral_material_id IS NOT NULL AND status IN (...)`.

### Phase 3 — UI/Handoff (Claude Code)

- Badge / toast khi skip dup.
- Job details hiện `content_hash` ngắn + link material nếu có.
- Update `current-status.md`.

## Files (ước lượng)

- `alembic/versions/*_job_content_hash_viral_fk.py`
- `app/core/database/models/jobs.py`
- `app/core/queue/job.py`
- `app/features/viral_intake/processor.py`
- `tests/test_cross_account_media_guard.py`
- (Phase 3) templates job/viral

## Risks

| Rủi ro | Xác suất | Tác động | Mitigation |
|---|---|---|---|
| Reup đổi hash → cùng viral vẫn tạo 2 job nếu chỉ dựa hash | TB | TB | Bắt buộc `viral_material_id` gate |
| Backfill full disk chậm | TB | Nhẹ | Lazy hash, không full scan Phase 1 |
| Unique index conflict job DONE cũ trùng hash | TB | TB | Partial index / chỉ enforce job mới; Owner quyết định keep oldest |
| Claim “bốc nhầm” | Thấp | — | Không đổi claim; job vẫn bind `account_id` |

## Owner decisions (LOCKED 2026-07-24)

1. Scope unique: **platform** (facebook ≠ threads)
2. Cửa sổ: **mãi** — DONE (và active statuses) chặn vĩnh viễn
3. FAILED / CANCELLED: **cho tạo lại** cùng hash

Active blocking statuses: `PENDING | RUNNING | DONE | DRAFT | AI_PROCESSING | AWAITING_STYLE`

## Status

**Approved** — Owner theo đề xuất. Executor bắt đầu Phase 1.

## Verification (Phase 1)

```text
alembic upgrade head → f4a1b2c3d4e5 OK (local Postgres)
pytest tests/test_cross_account_media_guard.py -q → 4 passed
```

## Status

**Approved + Phase 1 implemented** (Owner locked policy 2026-07-24). Phase 3 UI optional.
