# ADR-007: Module Boundary — Feature-Based Architecture

## Status
Active

## Context

Codebase 30K LOC hiện tổ chức theo **technical layer** (adapters × platform, services × concern, routers × URL prefix, workers × process). Mỗi feature bị xé ra rải 4–5 thư mục layer (ví dụ: Threads pipeline đụng 7 file ở 5 thư mục). Hệ quả:

- Onboarding chậm: phải nhảy 4–5 thư mục để hiểu 1 feature.
- Khó delete feature: phải xoá rải rác, dễ sót.
- Cross-feature coupling ngầm: `orchestrator.py` 651 dòng trộn FB + cross-platform.
- Khó test isolated.

ADR-005 (services-layer reorg) đã gom nhóm theo domain dưới `app/services/` + re-export shim. ADR-007 đi tiếp: tách thành 3 lớp rõ ràng **core / features / platform** với import rule cứng.

## Decision

### 3 lớp module

```
app/
├── core/           ← shared infrastructure (no platform/feature knowledge)
├── features/       ← self-contained feature modules
├── platform/       ← cross-feature shell (auth, dashboard chrome, health)
├── adapters/       ← [PHASE 2+] migrated INTO respective features/
├── services/       ← [DEPRECATED after migration] legacy re-export shim (ADR-005)
├── routers/        ← [DEPRECATED after migration] legacy router files
└── ...
```

### Core modules (7)

| Module | From | Responsibility |
|---|---|---|
| `app/core/database/` | `app/database/` | ORM models, migrations, session factory |
| `app/core/queue/` | `app/services/jobs/` | Job queue, claim, cleanup, tracer |
| `app/core/observability/` | `app/services/observability/` | Logging, metrics, incidents, health check, audit |
| `app/core/ai/` | `app/services/ai/` | Brain factory, Gemini client, pipeline, fallback |
| `app/core/notifier/` | `app/services/telegram/notifier/` | Generic notification dispatch (base + formatting + service) |
| `app/core/settings/` | `app/services/platform/settings.py` + `app/config.py` | RuntimeSetting, global config |
| `app/core/db_admin/` | `app/services/db/` | DB management tools (ACL, SQL validator, database service) |
| `app/core/compliance/` | `app/features/facebook/compliance/` | Content compliance engine (keywords, regex, AI rewrite) |
| `app/core/strategic/` | `app/features/viral_intake/strategic.py` | Strategic growth analysis (page growth, strategic advice) |

> **Note**: `app/core/compliance/` và `app/core/strategic/` đã được chuyển lên core ở Phase 5 sau khi phát hiện có nhiều consumer (Cross-feature usage).

### Feature modules (9)

| Feature | Chứa gì | Workers |
|---|---|---|
| `app/features/threads_publisher/` | adapter + news_scraper + threads_news + topic_key + article_scorer + dashboard + router | threads_publisher, threads_news_worker, threads_auto_reply, threads_verifier |
| `app/features/facebook/` | adapter + media_processor + reup_pipeline + router | publisher (FB) |
| `app/features/instagram/` | adapter + router (minimal) | — |
| `app/features/tiktok/` | adapter (read-only viral discovery) | — |
| `app/features/viral_intake/` | orchestrator + discovery + scan + tiktok_scraper + video_protector + reup_processor | ai_generator |
| `app/features/insights/` | insights_service + router | — |
| `app/features/affiliates/` | affiliate_ai + affiliate_service + router | — |
| `app/features/telegram_bot/` | client + command_handler + event_router + poller + service | — |
| `app/features/system_panel/` | syspanel_service + workflow_registry + manage routes + ai_studio_service | maintenance, ai_reporter |

### Platform modules (3)

| Module | From | Responsibility |
|---|---|---|
| `app/platform/auth/` | `app/routers/auth.py` + login/session | Authentication, session |
| `app/platform/dashboard_shell/` | `app/services/dashboard/dashboard_service.py` + `app/routers/dashboard.py` | Main dashboard chrome, cross-feature layout |
| `app/platform/health/` | `app/routers/health.py` | Health check endpoints |

### Changes from original PLAN-037 proposal

| Item | PLAN-037 đề xuất | ADR-007 quyết định | Lý do |
|---|---|---|---|
| `compliance/` | `core/compliance/` (generic) + FB tách feature | **Toàn bộ vào `features/facebook_publisher/compliance/`** | `fb_compliance.py` named `FBComplianceChecker`, prompt chứa "Facebook", `check_before_publish` raise `CompliancePublishError` cho FB context. `service.py` CRUD/router cũng ref `fb_compliance`. Chưa có compliance cho Threads/IG. Nếu sau cần generic → extract lên core lúc đó. |
| `notifier` position | `core/notifier/` từ `notifier_service.py` + telegram generic broadcast | `core/notifier/` từ `telegram/notifier/` (base + formatting + service) | `notifiers/` directory thực tế rỗng; logic notifier thật nằm trong `telegram/notifier/`. Tách notifier base khỏi telegram_bot feature. |
| `db_admin` | Không đề cập | `core/db_admin/` từ `services/db/` (ACL, sql_validator, database_service) | DB management tools là cross-feature shared infra. |
| `video_protector` | Không rõ placement | `features/viral_intake/` | Video protector dùng cho reup pipeline (watermark, video processing). |
| `media_processor` | Không rõ placement | `features/facebook_publisher/` | Media processor xử lý FB-specific media (image/video for FB post). |
| `ai_studio_service` | Không đề cập | `features/system_panel/` | AI Studio dashboard là admin panel feature. |

### Import rules (CỨNG — lint guard Phase 5)

```
RULE 1: features/X/ → CÓ THỂ import core/*
RULE 2: features/X/ → KHÔNG ĐƯỢC import features/Y/ (X ≠ Y)
RULE 3: core/*      → KHÔNG ĐƯỢC import features/* hoặc platform/*
RULE 4: platform/*  → CÓ THỂ import core/*
RULE 5: platform/*  → KHÔNG ĐƯỢC import features/* (trừ feature registration trong main.py)
RULE 6: features/X/ → CÓ THỂ import platform/* (chỉ auth/session nếu cần)
```

### Naming conventions

- Feature directory: `snake_case` noun mô tả nghiệp vụ (vd `threads_publisher`, `viral_intake`)
- Mỗi feature PHẢI có `__init__.py` export public API
- Worker entry point: `features/X/workers/Y.py` (giữ shim ở `workers/` cũ 1 sprint rồi xoá)
- Router: `features/X/router.py` (1 file hoặc `features/X/routers/` nếu nhiều prefix)

### `app/services/__init__.py` (ADR-005 re-export shim)

- Phase 1–3: giữ nguyên, thêm alias mới khi move modules.
- Phase 5 (lint guard): deprecation warning khi import qua shim.
- Phase follow-up (ngoài PLAN-037): xoá hoàn toàn shim, update tất cả caller.

## Rationale

### Tại sao compliance được chuyển lên core? (Phase 5 update)

1. **Đa kênh tiêu thụ**: Cả `facebook` feature và `affiliates` feature đều cần dùng engine này để kiểm duyệt nội dung.
2. **Hạ tầng hóa**: Engine này dựa trên DB keywords/regex dùng chung, không còn thuần túy chỉ cho Facebook.
3. **Phá vỡ dependency vòng**: Giữ compliance ở Facebook feature khiến các feature khác bị phụ thuộc chéo vào Facebook (vi phạm Rule 2).

### Tại sao giữ re-export shim (ADR-005)?

- ~200 import statement dùng `app.services.X` path cũ.
- Move 1 module mà break 200 caller = risk quá lớn.
- Shim cho phép migration incremental: move physical file → update shim alias → caller không biết.
- Sau PLAN-037 hoàn tất → plan riêng xoá shim + update caller trực tiếp.

## Alternatives

1. **Big-bang move**: di chuyển tất cả 1 lần. → **Rejected**: 30K LOC, risk quá lớn, không rollback từng phần được.
2. **Vertical slice per platform** (FB module chứa cả compliance + viral + insights FB-specific): → **Rejected**: insights / viral intake đủ lớn và cross-platform đủ rõ để tách riêng.
3. **Keep current + lint only**: không move file, chỉ thêm lint rule. → **Rejected**: không giải quyết onboarding, discoverability, feature deletion.

## Impact

- **Tích cực**: Feature discoverability, delete feature = `rm -rf features/X/`, isolated testing, clear dependency direction.
- **Tiêu cực**: Migration effort 10–14 ngày, temporary double-path (shim), Codex/Claude Code cần update commit message conventions.
- **Breaking**: Import path changes — mitigated by re-export shim.

## Related
- Plan: PLAN-037
- Task: TASK-037
- Supersedes: ADR-005 (partially — shim stays but modules move to features/)
