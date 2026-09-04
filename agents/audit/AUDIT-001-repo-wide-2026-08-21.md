# AUDIT-001 — Kiểm toán toàn diện repository ToolsAuto

**Ngày:** 2026-08-21
**Chế độ:** AUDIT ONLY — không sửa code, không đổi schema, không tạo PR.
**Phạm vi:** toàn bộ repo tại `main` + diff chưa commit (16 file sửa, 6 file mới, 1 migration).
**Trạng thái test lúc audit:** `243 passed` (`pytest tests/ -q --ignore=tests/test_threads_world_news.py`), Postgres `toolsauto_postgres:5434` đang bật, alembic head `i7d4e5f6a7b8`.

**Sửa đổi:** rev.2 — 2026-08-21, sau một vòng **final validation** tập trung vào
concurrency / transaction / recovery / security. Thay đổi chính: P0-1 được tách thành
**ba lỗi độc lập** (A/B/C) với ba bản vá khác nhau; bỏ phát biểu "hai P0 vá bằng một
dòng"; hạ P0-1B xuống **PLAUSIBLE**; nâng TD-18 lên **P1**; làm chặt lại wording về
backup và CSRF; bổ sung đặc tả TEST A/B/C bắt buộc. Chi tiết ở §10, §14, §17, §19,
§22, §27, §31, §32, §33, §35.

Báo cáo này thay thế `agents/ARCHITECTURE_REVIEW.md` (2026-04-27) — tài liệu đó
đánh giá `GenericAdapter` là "bước ngoặt no-code", nhưng ADR-009 và audit này xác
nhận đó là code không thể chạm tới.

---

## 1. Executive Summary

ToolsAuto **không phải** ứng dụng web CRUD. Nó là một **hệ điều phối RPA
(browser automation orchestrator)**: một hàng đợi job trong PostgreSQL, nhiều tiến
trình worker Playwright lái Chrome thật với profile người dùng thật để đăng bài lên
Facebook/Threads/Instagram/TikTok, cộng một dashboard admin FastAPI + HTMX để vận
hành. 54.1k dòng Python + 15k dòng template, một người dùng (Owner), chạy trên một
VPS + một máy Windows local.

**Kiến trúc thực tế: Modular Monolith theo feature + Job-Queue Pipeline + Adapter
Pattern.** Không phải Clean Architecture, không phải DDD, không phải microservices —
và **đó là lựa chọn đúng** cho bài toán này. Không có khuyến nghị nào trong báo cáo
này đề xuất đổi kiến trúc.

Vấn đề không nằm ở kiểu kiến trúc. Nó nằm ở ba chỗ:

1. **Hàng đợi không bảo vệ được hai bất biến độc lập về đồng thời**, và cả hai đều
   dẫn tới đăng trùng bài lên Facebook — loại lỗi làm chết account, không làm đỏ log.
   Đã xác nhận bằng `EXPLAIN` trên Postgres thật. Đây là **ba lỗi riêng biệt**, không
   phải một, và **không có một bản vá đơn lẻ nào đóng được cả ba** (§10).
2. **Tính năng "link affiliate có đếm click" — thứ đang được bán trong combo —
   sinh ra link chết trong production.** Khi `VERCEL_REDIRECT_URL` trống (đúng
   trạng thái `.env` hiện tại), hệ thống đăng chuỗi `/r/abc12345` lên Facebook.
   Đó không phải URL. Và endpoint `/r/{code}` lại nằm sau middleware auth nên kể
   cả có domain thì khách vẫn bị đá về `/login`.
3. **Deploy nuốt lỗi migration và không backup Postgres.** `alembic upgrade head ||
   true` — migration fail thì deploy vẫn chạy tiếp và restart worker trên schema cũ.
   Backup duy nhất trong pipeline là `cp` file SQLite legacy.

Ngoài ra: ~49% test là "đọc source rồi assert chuỗi" chứ không chạy hành vi; hợp
đồng import-linter đã khai báo nhưng **chưa bao giờ chạy** (không cài trong venv,
không có trong CI) và hiện đang có 2 vi phạm thật; CI đỏ từ 2026-07-29 nên 5+ commit
gần nhất chưa từng qua cổng test nào.

**Điểm mạnh thật sự cần giữ nguyên:** cơ chế bảo vệ media chống đăng trùng
(partial unique index ở DB, không chỉ code), `Dispatcher.finally: close_session()`,
suicide timer chống deadlock browser, incident logger có masking secret + gom
signature, và kỷ luật tài liệu ADR/PLAN/TASK ở mức hiếm thấy với dự án solo.

**Kết luận:** không cần refactor lớn. Nhưng cũng **không được coi đây là "hai lỗi vá
bằng một dòng"**. P0-1 là ba lỗi đồng thời riêng biệt cần ba biện pháp khác nhau;
P0-2 là một cụm ba lỗi nhỏ chỉ được coi là xong khi có một test end-to-end. Không
bất biến nào trong hai nhóm này được tuyên bố là đã đóng cho tới khi có test hành vi
chạy trên PostgreSQL thật chứng minh điều đó.

---

## 2. What This System Is

### Business view

| | |
|---|---|
| **Bài toán** | Tự động đăng nội dung + nuôi tài khoản MXH thay cho người, để bán dịch vụ theo combo (Auto Page 3tr5 / Page Master 5tr) |
| **Actor** | Một người: Owner, vừa là admin vừa là người vận hành. Không có multi-tenant, không có phân quyền |
| **Sản phẩm bán ra** | Đăng Reels/bài feed/tin theo lịch, tự comment link aff, reup video viral từ TikTok, nuôi account (idle engagement), báo cáo insight |
| **Ràng buộc sống còn** | Facebook không được phát hiện automation. Account bị checkpoint = mất tiền của khách |

### Technical view

```
Language      Python 3.12 (VPS) / 3.14 (Windows local)
Framework     FastAPI 0.125 + Jinja2 + HTMX (không có SPA, không có JSON API công khai)
Runtime       uvicorn (web) + 10 tiến trình PM2 (worker)
Database      PostgreSQL 16 (SQLAlchemy 2.0 ORM + Alembic, 26 migration)
Queue         Chính bảng `jobs` trong Postgres — không Redis, không RabbitMQ
Cache         Không có (in-memory dict cho compliance keyword + selector stats)
Object store  Filesystem cục bộ dưới storage/
Browser       Playwright 1.58 (chính) + undetected-chromedriver (Gemini RPA)
External      Facebook/Threads/IG/TikTok DOM, 9Router gateway, Google Gemini,
              Telegram Bot, yt-dlp, Vercel redirect, ffmpeg
Auth          1 admin cứng trong .env + cookie ký itsdangerous
Frontend      Jinja2 fragment + HTMX polling; Tailwind
CI/CD         GitHub Actions → SSH → git reset --hard → alembic → pm2
Observability logging file xoay vòng + incident_logs/incident_groups + audit_logs
Test          pytest 9.1, 245 test, không conftest, không fixture DB
```

### System boundary

**Sở hữu dữ liệu:** job, account (metadata + đường dẫn Chrome profile), viral
material, affiliate link, compliance keyword, incident, page insight, engagement
session, runtime setting.

**Không sở hữu, phụ thuộc hoàn toàn:** DOM và session của Facebook/Threads/IG/TikTok
(không có API chính thức — đây là rủi ro nền của cả sản phẩm), Gemini/9Router cho
caption, Telegram cho cảnh báo, Vercel cho redirect link, yt-dlp cho tải video nguồn.

---

## 3. Architecture Detected

Đọc dependency thật, không đọc tên thư mục:

**Modular Monolith theo feature (ADR-007) + Job-Queue Pipeline + Adapter Pattern,
với business logic viết theo Transaction Script.**

Chi tiết từng thành phần:

- **Job-Queue Pipeline là xương sống.** Mọi thứ đi qua bảng `jobs`. Web ghi job,
  worker `claim` job bằng một câu `UPDATE ... RETURNING` nguyên tử, dispatcher rẽ
  nhánh theo `job_type`, adapter thực thi. Đây là kiến trúc chủ đạo, không phải
  layered/MVC.
- **Adapter Pattern có thật nhưng port bị rò.** `AdapterInterface` (ABC) khai báo
  4 method (`open_session/publish/check_published_state/close_session`). Nhưng
  `post_comment`, `publish_feed`, `publish_story` **không** nằm trong ABC —
  dispatcher dò bằng `hasattr()` (`dispatcher.py:246`, `:271`). Và
  `PageMismatchError` — một exception rất Facebook — được import thẳng vào
  `dispatcher.py:15` và `publisher.py`.
- **Package-by-feature đã làm nghiêm túc.** `app/core` (hạ tầng dùng chung) /
  `app/features/<mxh|nghiệp vụ>` / `app/platform` (vỏ). Có file `.importlinter`
  khai báo contract. Feature nặng nhất: `facebook` 6.5k dòng, `viral_intake` 5.5k.
- **Transaction Script, không phải DDD.** `JobService` là 1352 dòng gồm 40 hàm
  `@staticmethod` nhận `db: Session` — đúng định nghĩa Transaction Script.
  Model SQLAlchemy anemic (chỉ có property resolve đường dẫn). Không aggregate,
  không value object, không domain event, không repository.
- **Hybrid ở tầng cấu hình:** một tầng "no-code" (WorkflowRegistry / GenericAdapter
  / 4 bảng DB / ~4.3k dòng) tồn tại song song nhưng **0 row dữ liệu** và
  `dispatcher.py:88` luôn ghi đè nó. Xem ADR-009.

### Architecture Scorecard

| Pattern | Score | Evidence |
|---|---:|---|
| **Pipeline / Job-Queue** | **9** | `queue.py:claim_next_job` là UPDATE...RETURNING nguyên tử; toàn bộ nghiệp vụ đi qua bảng `jobs`; 10 worker PM2 poll cùng một hàng đợi |
| **Package by Feature** | **8** | `app/features/{facebook,threads,viral_intake,...}` mỗi feature có adapter+service+router+workers; `.importlinter` khai báo contract |
| **Layered** | **7** | router → service → model nhất quán 236 route; nhưng `db.query()` xuất hiện thẳng trong router (vd `dashboard_service.py:37`) |
| **Transaction Script** | **8** | `JobService` 40 static method nhận `Session`; `DashboardService`, `AccountService` cùng kiểu |
| **Adapter / Ports** | **6** | `AdapterInterface` ABC có thật, 4 adapter implement; nhưng 3 method quan trọng nằm ngoài ABC, dispatcher dùng `hasattr`, import ngược `adapters → features.facebook` |
| **Modular Monolith** | **6** | Ranh giới module có, contract có; nhưng **contract chưa bao giờ được chạy** và module không sở hữu data riêng (một `Base` chung, một schema chung) |
| **Active Record** | **5** | Model có property nghiệp vụ (`resolved_media_path`, `is_sleeping`, `managed_pages_list`) nhưng không tự save |
| **SOLID** | **4** | DIP có qua `AdapterInterface`; SRP vỡ nặng ở `FacebookAdapter` (3029 dòng / ~8 trách nhiệm), `JobService` (1352), `maintenance.run_loop` (12 việc không liên quan) |
| **Hexagonal / Onion** | **3** | Có hình dạng port/adapter nhưng `app/core` import `app.features` (`metrics_checker.py:162`) — core không hề là lõi thuần |
| **Event Driven** | **2** | `feature_hooks` registry + `runtime_events.emit()` chỉ ghi log; không bus, không subscriber, không replay |
| **Clean Architecture** | **2** | Không có use-case layer, không entity thuần; SQLAlchemy model = domain |
| **DDD** | **2** | Không aggregate/value object/bounded context có ranh giới dữ liệu; "domain" chỉ là tên thư mục |
| **Repository Pattern** | **1** | `db.query(Job)` rải khắp service, router, worker |
| **CQRS** | **0** | — |
| **Microservices** | **0** | Nhiều tiến trình nhưng chung một DB, một codebase, một deploy |

---

## 4. System Map

### Runtime components (từ `ecosystem.config.js`)

```
┌─────────────────┐   HTMX poll 5–60s   ┌──────────────────────┐
│ Trình duyệt admin│ ──────────────────► │ Web_Dashboard        │
└─────────────────┘                      │ uvicorn / manage.py  │
                                         └──────────┬───────────┘
                                                    │ SQLAlchemy (NullPool)
                                                    ▼
                          ┌─────────────────────────────────────────┐
                          │        PostgreSQL 16 (26 bảng)          │
                          │  jobs ← hàng đợi + state machine        │
                          └───┬──────────┬──────────┬───────────┬───┘
              claim_next_job  │          │          │           │
        ┌─────────────────────┴──┐  ┌────┴──────┐ ┌─┴────────┐ ┌┴──────────────┐
        │ FB_Publisher_1 / _2    │  │ Threads_* │ │ AI_Gen   │ │ Maintenance   │
        │ (Playwright + Chrome)  │  │ x3        │ │ _1 / _2  │ │ (12 việc/tick)│
        └────────────┬───────────┘  └─────┬─────┘ └────┬─────┘ └───────┬───────┘
                     ▼                    ▼            ▼               ▼
              facebook.com          threads.net    9Router →      ffmpeg / yt-dlp
              (DOM, không API)                     Gemini          Telegram
```

10 tiến trình PM2. `9Router_Gateway` là process Node bên thứ ba chạy chung PM2.

### Bảng dữ liệu thật (đếm live 2026-08-21)

| Bảng | Row | Ghi chú |
|---|---:|---|
| jobs | 14 | 7 DRAFT/POST, 3 DONE/POST, 2 PENDING, 1 FAILED, 1 DONE/COMMENT |
| job_events | 186 | có retention 30 ngày |
| keyword_blacklist | 116 | compliance |
| page_insights | 81 | |
| viral_materials | 11 | |
| violation_log | 6 | |
| compliance_allowlist / regex_rules | 5 / 5 | |
| affiliate_links | 4 | |
| accounts | **1** | toàn hệ thống mới có 1 account |
| incident_logs / groups | 1 / 1 | |
| **platform_configs** | **0** | tầng no-code |
| **platform_selectors** | **0** | tầng no-code |
| **cta_templates** | **0** | tầng no-code |
| **workflow_definitions** | **0** | tầng no-code |
| audit_logs, news_articles, discovered_channels, engagement_sessions, threads_interactions, competitor_reels | 0 | |

Bốn bảng no-code **0 row** xác nhận lại ADR-009 bằng dữ liệu runtime.

---

## 5. Dependency Map

Trích từ phân tích AST toàn bộ 282 file `.py` (`app/`):

```
                    main.py / bootstrap_hooks.py      ← composition root (hợp lệ)
                              │
        ┌─────────────────────┼──────────────────────┐
        ▼                     ▼                      ▼
  app/platform/         app/features/*          app/core/*
  (auth, shell,          (facebook, threads,     (queue, database, ai,
   health)                viral_intake, ...)      observability, compliance)
        │                     │  │                    │
        └──────────┬──────────┘  │                    │
                   ▼             │                    ▼
            app/adapters/  ──────┘             app/core/database
            (dispatcher)   ◄── ✗ import ngược        (Base, models)
```

### Good dependency
- `features/* → core/*` — đúng chiều, 60+ cạnh.
- `core/queue → core/database` — hạ tầng gọi hạ tầng.
- `main.py → features/*` và `bootstrap_hooks.py → features/*` — composition root,
  hợp lệ theo ADR-008.
- `features/{instagram,tiktok,threads} → adapters` — feature dùng contract chung.

### Suspicious dependency
- **`adapters → features.facebook` (2 cạnh).** `dispatcher.py:15` import
  `FacebookAdapter, PageMismatchError` ở top-level; các adapter khác được import
  lazy trong hàm. Tầng dispatch dùng chung biết đích danh một feature.
- **`features.facebook → core.queue` (5 cạnh).** Worker Facebook gọi thẳng
  `JobService` — hợp lý, nhưng làm `core.queue` thành điểm fan-in cao nhất.
- **`system_panel → core.ai` (5 cạnh)** — panel hệ thống điều khiển AI config.

### Boundary violation (vi phạm chính contract đã khai báo)

| # | Vi phạm | Evidence | Contract bị vi phạm |
|---|---|---|---|
| V1 | `app.core` import `app.features` | `app/core/observability/metrics_checker.py:162` → `from app.features.facebook.pages.reels import FacebookReelsPage` | `.importlinter` → `core-isolated` |
| V2 | Feature import feature khác | `app/features/insights/router.py:149` → `from app.features.viral_intake.reup_variants import list_variant_stats` | `.importlinter` → `features-independent` |

**Cả hai không bị bắt** vì `import-linter` có trong `requirements.txt` nhưng
**không cài trong venv** và **không có bước nào trong `deploy.yml` chạy nó**.
Kiến trúc được viết ra giấy nhưng không có cổng gác.

### Circular dependency
Không phát hiện vòng lặp import ở mức module. Có "vòng lặp mềm" cố ý:
`dispatcher → features.facebook.adapter` và `features.facebook.workers.publisher →
adapters.dispatcher`, được gỡ bằng import lazy trong hàm. Hoạt động, nhưng là dấu
hiệu port chưa đủ chặt.

---

## 6. Domain / Module Map

| Module | Purpose | Owned data | Public API | Depends on | Cohesion | Coupling | Risk |
|---|---|---|---|---|---|---|---|
| `core/queue` | Vòng đời job: tạo, claim, retry, recover | `jobs`, `job_events` | `JobService`, `QueueService`, `publisher_runtime` | database, notifier, observability | Trung bình — trộn validate media + phân trang UI + state machine | **Fan-in cao nhất** | **Cao** — P0 nằm đây |
| `features/facebook` | Adapter FB + worker + engagement + pro tasks | — (dùng `jobs`, `accounts`) | `FacebookAdapter`, `publisher.py` | queue, compliance, adapters, account | **Thấp** — 3029 dòng/1 class | Cao | **Cao** |
| `features/viral_intake` | Reup TikTok → job | `viral_materials`, `competitor_reels` | `service`, `reup_processor`, worker `ai_generator` | core.ai, core.media, account | Trung bình | Trung bình | Trung bình |
| `features/threads` | Adapter + 4 worker Threads | `threads_interactions`, `news_articles` | `ThreadsAdapter` | queue, ai, adapters | Trung bình | Thấp | Trung bình |
| `core/compliance` | Chặn nội dung vi phạm chính sách FB | `keyword_blacklist`, `compliance_*`, `violation_log` | `check_before_publish()` | ai, database | **Tốt** | Thấp | Thấp |
| `core/ai` | Gateway 9Router + fallback Gemini native | — | `AICaptionPipeline` | config, database | Tốt — có circuit breaker | Thấp | Trung bình |
| `core/observability` | Log, incident, metric, health | `incident_*`, `audit_logs` | `IncidentLogger`, `MetricsChecker` | database, notifier, **features.facebook (V1)** | Tốt | Trung bình | Thấp |
| `features/system_panel` | Điều khiển PM2/git/DB từ UI | `system_state` | router + `service.py` (1051 dòng) | hầu như mọi thứ | **Thấp** | **Fan-out cao nhất** | Trung bình |
| `features/insights` | Scrape + phân tích page | `page_insights` | `service.py` (1015 dòng) | database, **viral_intake (V2)** | Trung bình | Trung bình | Thấp |
| `core/workflow_registry` + `adapters/generic` | Tầng "no-code" | 4 bảng, **0 row** | `WorkflowRegistry` | database | — | — | **Nợ thuần** |

**Ownership clarity: yếu.** Không module nào thực sự sở hữu dữ liệu — tất cả cùng
một `Base`, cùng schema, ai cũng `db.query(Job)` được. Ranh giới là quy ước import,
không phải ranh giới dữ liệu. Với quy mô hiện tại điều này **chấp nhận được** và
không nên đổi.

---

## 7. Architecture Scorecard

Xem §3.

---

## 8. Engineering Scorecard

| Dimension | Score | Lý do |
|---|---:|---|
| Architecture | **6** | Chọn đúng mô hình cho bài toán; nhưng port rò, contract không được enforce |
| Domain Modeling | **4** | Anemic model + transaction script; enum chỉ tồn tại trong Python, DB không biết |
| Modularity | **6** | Cấu trúc feature tốt, 2 vi phạm thật, không có cổng gác |
| Maintainability | **5** | 5 file >1000 dòng; thêm 1 job_type phải sửa 13 file |
| Testability | **5** | 243 test xanh nhưng ~49% chỉ grep source; không conftest, không fixture DB |
| Data Integrity | **6** | Partial unique index bảo vệ invariant quan trọng nhất (**điểm sáng**); nhưng 0 CHECK constraint, `parent_job_id` không FK, JSON nhét trong cột String |
| Security | **6** | Single-admin, cookie ký, SQL console có AST validator, secret masking trong incident. Trừ điểm: đọc file tuỳ ý dưới repo root, không CSRF token, cookie đã rò lịch sử |
| Reliability | **5** | `finally: close_session` + suicide timer + self-heal rất tốt; nhưng race claim + maintenance loop kiểu all-or-nothing |
| Observability | **7** | Incident group + signature + masking + audit log + health check — mạnh hơn mặt bằng dự án solo |
| Performance | **6** | Index đầy đủ trên `jobs`; NullPool + HTMX poll hơi lãng phí nhưng quy mô nhỏ |
| Developer Experience | **7** | `manage.py` typer, 26 file docs, ADR/PLAN/TASK kỷ luật. Trừ điểm: Python 3.14 vs 3.10 CI, venv thiếu dependency đã khai báo |
| Deployment Safety | **3** | `\|\| true` nuốt lỗi migration; không backup Postgres; không rollback plan; CI đỏ 3 tuần |

**Overall Engineering Health: 5.5 / 10**

Không phải trung bình cộng. Lý do chấm 5.5: nền kiến trúc và quan sát hệ thống ở
mức 6–7, nhưng hai P0 (đăng trùng bài, link aff chết) đánh thẳng vào **giá trị đang
bán cho khách**, và cổng deploy ở mức 3 nghĩa là lỗi sẽ ra production mà không ai
chặn. Một hệ thống 7 điểm không thể có tính năng bán tiền mà chưa từng chạy đúng
một lần trong production.

---

## 9. What Is Done Well

Những thứ **không được phá**:

1. **Bảo vệ media chống đăng trùng bằng DB, không chỉ bằng code.**
   `idx_jobs_platform_content_hash_active` và `idx_jobs_viral_material_active` là
   *partial unique index* có `WHERE status IN (...)`. Đây là cách đúng: invariant
   nghiệp vụ được ép ở tầng thấp nhất, không thể lách bằng đường code khác. Rất ít
   dự án quy mô này làm được.

2. **`Dispatcher.dispatch()` có `finally: adapter.close_session()`.**
   `dispatcher.py:404`. Với hệ chạy Chrome thật, rò browser = tràn RAM = chết VPS.
   Comment trong code gọi đây là "MUST-HOLD INVARIANT" và code đúng như vậy.

3. **Suicide timer + heartbeat thread.** `kill_if_stuck()` gọi `os._exit(1)` để PM2
   restart khi Playwright treo; heartbeat thread giữ `last_heartbeat_at` tươi;
   `recover_crashed_jobs` đưa job mồ côi về PENDING **và có cap `tries`** để không
   quay vòng vô hạn. Đây là thiết kế reliability trưởng thành.

4. **Incident logging.** `incident_logger.py` normalize message (uuid/timestamp/số →
   token), hash thành signature, gom vào `incident_groups`, **và mask secret**
   (`SENSITIVE_KEYS` + regex bearer/basic/JWT). Đúng chuẩn production.

5. **SQL console dùng AST validator, không regex.** `sql_validator.py` parse bằng
   `sqlglot` dialect postgres, chặn multi-statement, **deny-by-default** cho loại
   câu lệnh lạ. Ghi write sau cờ `SQL_CONSOLE_WRITES_ENABLED`. Đây là cách làm đúng.

6. **Cổng media trước khi mở browser.** `assert_facebook_post_media` chặn PNG vào
   Reels *trước* khi tốn một phiên browser, và phân loại `error_type=VALIDATION` để
   **không** tính vào circuit breaker của account. Phân biệt "lỗi người nhập" và
   "account có vấn đề" là tư duy vận hành chín.

7. **Kỷ luật tài liệu.** 10 ADR, 16 PLAN active, 15 TASK, `current-status.md` cập
   nhật từng phiên, 26 file `docs/`. ADR-009 tự thừa nhận 4.3k dòng code của chính
   mình là ảo tưởng — mức trung thực kỹ thuật hiếm.

8. **Fair-share trong hàng đợi.** `ORDER BY COALESCE(lpp.last_ts,0) ASC` — account
   lâu chưa post lên trước. Chống một account chiếm cả hàng đợi. Đúng.

9. **Rollback batch upload sạch.** `bulk_create_jobs_from_uploads` có
   `except: db.rollback(); _discard_files(written_paths)` — không để lại file mồ côi
   khi lô fail giữa chừng.

10. **Data retention có thật.** `_cleanup_old_logs` xoá `job_events`/`incident_logs`
    quá 30 ngày. (Điểm yếu ghi trong review 2026-04 đã được vá.)

---

## 10. Critical Findings (P0 / P1)

### 🔴 P0-1 — Hàng đợi không bảo vệ được bất biến đồng thời: ba lỗi riêng biệt

**File:** `app/core/queue/queue.py:35-83`, `:150-230`; `app/config.py:106,285`;
`app/features/facebook/workers/publisher.py`

> ⚠️ **Đọc kỹ trước khi vá.** Đây là **ba lỗi độc lập**. Bản vá cho lỗi này
> **không** đóng lỗi kia. Coi chúng là một sẽ tạo cảm giác an toàn giả.

Hai bất biến khác nhau đang cùng bị vi phạm:

| | Bất biến | Trạng thái | Bản vá tối thiểu |
|---|---|---|---|
| **A** | Một job PENDING chỉ được đúng **một** worker claim | ❌ Vỡ — **CONFIRMED** | Outer predicate `AND status='PENDING'` |
| **B** | Một `(account, platform)` chỉ có tối đa **một** job RUNNING | ❌ Không được DB bảo vệ — **PLAUSIBLE** | **Partial unique index** — không phải outer predicate |
| **C** | Job đang chạy không bị recovery cướp mất | ❌ Vỡ — **CONFIRMED (cơ chế)** | Sửa nghịch đảo ngưỡng cấu hình |

---

#### P0-1A — Job exclusivity: hai worker cùng nhận **một** job

Câu SQL claim có dạng:

```sql
UPDATE jobs SET status = 'RUNNING', ...
WHERE id = ( SELECT j.id FROM jobs j ... WHERE j.status = 'PENDING' ... LIMIT 1 )
RETURNING *;
```

Điều kiện `status = 'PENDING'` **chỉ nằm trong subquery**, không nằm trong `WHERE` ngoài.

**Evidence — `EXPLAIN` chạy thật trên Postgres 16 của dự án:**

```
Update on jobs
  InitPlan 1 (returns $0)          <- subquery chọn ứng viên: chạy MỘT LẦN
    -> Limit -> Sort -> Nested Loop Anti Join ...
  ->  Seq Scan on jobs
        Filter: (id = $0)          <- qual ngoài CHỈ có id, không có status
```

**Cơ chế (Postgres READ COMMITTED):**

1. Worker A và B cùng chạy câu này; InitPlan của cả hai đọc snapshot trước khi ai
   commit → cùng trả `$0 = 7`.
2. A khoá row 7, đặt `status='RUNNING'`, commit.
3. B bị chặn ở row lock. Khi A commit, Postgres chạy **EvalPlanQual**: đánh giá lại
   *qual ngoài* trên phiên bản row mới. Qual ngoài là `id = 7` — vẫn đúng.
4. B **update lại chính row 7**; `RETURNING *` trả job 7 cho B.

**Xác nhận bản vá bằng `EXPLAIN` (đã chạy thật, read-only):** thêm
`AND status = 'PENDING'` vào `WHERE` ngoài làm plan đổi thành

```
->  Seq Scan on jobs
      Filter: (((status)::text = 'PENDING'::text) AND (id = $0))
```

Qual ngoài giờ chứa `status`, nên EvalPlanQual của B thấy `status='RUNNING'` → qual
fail → **0 row được update**, `RETURNING` rỗng, `claim_next_job` trả `None`.
**Bất biến A được bảo vệ. Confidence: HIGH.**

**Tác dụng phụ cần biết:** ứng viên đã được `Sort -> Limit 1` chốt trước khi khoá, nên
khi B thua nó **không thử ứng viên khác trong cùng câu lệnh** — B mất trắng một tick.
`claim_next_job_respecting_daily` chỉ lặp lại khi bị daily-limit postpone, không lặp
khi `claim_next_job` trả `None`. Đây là mất thông lượng, **không phải lỗi đúng đắn**.
Xem Option B ở §32 nếu muốn khắc phục.

---

#### P0-1B — Account/platform exclusivity: hai worker, **hai job khác nhau**, cùng một account

Đây là bất biến **khác** và **bản vá của P0-1A không chạm tới nó.**

Mutex hiện tại là mệnh đề anti-join **nằm bên trong InitPlan**:

```sql
AND NOT EXISTS (SELECT 1 FROM jobs j2
                WHERE j2.account_id = j.account_id
                  AND j2.platform   = j.platform
                  AND j2.status     = 'RUNNING')
```

**Kịch bản vi phạm:**

1. Worker A và B cùng đọc snapshot: account 1 chưa có job RUNNING nào.
2. A chọn job 7, B chọn job **8** — hai row **khác nhau**.
3. Vì hai row khác nhau nên **không có xung đột khoá**, B **không bị chặn**, và
   **EvalPlanQual không bao giờ chạy**. Outer predicate `status='PENDING'` của B vẫn
   đúng (row 8 chưa ai đụng).
4. Cả hai commit. Account 1 có **hai job RUNNING** → hai phiên Chrome cùng một profile.

**Điều kiện để A và B chọn hai row khác nhau:** thứ tự
`ORDER BY COALESCE(lpp.last_ts, 0) ASC, j.schedule_ts ASC` phải hoà. Khoá sắp xếp thứ
nhất `lpp.last_ts` được gom theo `account_id`, nên **mọi job của cùng một account luôn
hoà khoá thứ nhất**; chỉ `schedule_ts` phá hoà. Và `schedule_ts` có nguồn hoà thật:
`create_high_priority_manual_job` (`job.py:908`) đặt
`schedule_ts = int(time.time()) - 999999` cho **mọi** job thủ công ưu tiên — hai job
tạo trong cùng một giây hoà tuyệt đối. Với khoá sắp xếp hoà, thứ tự đầu ra của nút
`Sort` là **không xác định**.

**Confidence: MEDIUM — PLAUSIBLE, chưa CONFIRMED.** Cơ chế và điều kiện kích hoạt đọc
được từ code và plan; nhưng chưa chạy thí nghiệm hai session để chứng minh Postgres
thực sự trả hai row khác nhau trong cùng snapshot. **Không được tuyên bố bất biến B
đã đóng cho tới khi TEST B (§19) chạy xanh.**

**Bản vá tối thiểu — KHÔNG phải outer predicate.** Cách nhỏ nhất ép được B ở tầng DB
là **partial unique index**, đúng mẫu mà dự án đã làm tốt cho `content_hash`:

```sql
CREATE UNIQUE INDEX idx_jobs_one_running_per_account_platform
    ON jobs (account_id, platform) WHERE status = 'RUNNING';
```

**Khả thi ngay:** đã kiểm tra live — hiện có **0 job RUNNING** và không cặp
`(account_id, platform)` nào có >1 RUNNING, nên index tạo được không cần dọn dữ liệu.

**Không miễn phí:** khi index chặn, `UPDATE` ném `IntegrityError`. `claim_next_job`
hiện chỉ nuốt lỗi chứa chữ `"locked"` rồi **re-raise mọi thứ khác** (`queue.py:96-100`)
— sẽ làm crash vòng lặp worker. Phải bắt `IntegrityError` và trả `None` (coi như
"không claim được"). Đây là thay đổi code, không phải chỉ một migration.

---

#### P0-1C — Recovery cướp job đang chạy: nghịch đảo ngưỡng cấu hình

Lỗi này **không được vá bởi cả P0-1A lẫn P0-1B**, vì tại thời điểm worker thứ hai
claim, row **thật sự đang ở trạng thái `PENDING`** — mọi predicate đều đúng.

**Evidence — các hằng số đọc thẳng từ config:**

| Hằng số | Giá trị | Nguồn |
|---|---:|---|
| `WORKER_CRASH_THRESHOLD_SECONDS` | **120 s** | `app/config.py:106` |
| Chu kỳ heartbeat | **60 s** | `publisher_runtime.start_heartbeat_thread(interval=60)` |
| `PUBLISHER_PUBLISH_DEADLINE_SEC` | **900 s** | `app/config.py:285` |
| Trần chờ upload một video | **420 s** | `feed_composer.py:86` `VIDEO_UPLOAD_MAX_MS` |
| `MAINT_LOOP_SLEEP_SEC` | **300 s** | `app/config.py:289` |

**Ngưỡng recovery (120 s) nhỏ hơn deadline hợp lệ của job (900 s) gấp 7,5 lần.**
Đây là một nghịch đảo cấu hình: cơ chế tự chữa lành đang chạy đua với job khoẻ mạnh.

**Cơ chế:**
1. Job dài hợp lệ đang chạy (PLAN-056 cho phép chờ upload tới 420 s).
2. Heartbeat thread mở **kết nối Postgres mới mỗi 60 s** (NullPool). Lỗi được nuốt
   ở mức `log.debug` (`publisher_runtime.py:60-64`) rồi ngủ tiếp 60 s.
3. **Hai nhịp lỡ liên tiếp = 120 s** → `last_heartbeat_at` quá hạn.
4. `Maintenance` (mỗi 300 s) gọi `recover_crashed_jobs(120)` → đặt job về **PENDING**,
   `tries += 1`, xoá `locked_at`.
5. Worker gốc **vẫn đang lái Chrome và đăng bài**. Publisher còn lại claim đúng job đó
   — hợp lệ theo mọi predicate — và mở phiên thứ hai.
6. Worker gốc kết thúc, gọi `mark_done` trên object trong bộ nhớ, ghi đè `DONE`.

**Giảm nhẹ một phần:** vì `tries` đã tăng, dispatcher sẽ chạy `check_published_state`
trước khi đăng (`dispatcher.py:214`) — nên **có** một cửa chặn. Nhưng nó phụ thuộc
adapter dò được dấu vết trên timeline, và `InstagramAdapter.check_published_state`
(`instagram/adapter.py:364`) trả thẳng `ok=False` ("not implemented yet"); Facebook chỉ
quét Reels, không quét bài feed hay story. **Cửa chặn không phủ hết job type.**

**Confidence: HIGH cho cơ chế** (hằng số + đường code đọc được). **MEDIUM cho tần
suất** — phụ thuộc heartbeat có lỡ hai nhịp liên tiếp hay không, chưa đo trên production.

**Bản vá tối thiểu:** đặt `WORKER_CRASH_THRESHOLD_SECONDS` **lớn hơn**
`PUBLISHER_PUBLISH_DEADLINE_SEC` cộng biên (ví dụ 1200 s). Lý do: suicide timer đã bảo
đảm không job nào sống quá 900 s, nên bất cứ job nào quá 1200 s **chắc chắn** là tiến
trình đã chết. Bổ sung nên có: trước `mark_done`, worker kiểm tra job còn thuộc về
mình không (so `started_at`/token claim đã giữ) rồi mới ghi.

---

#### Điều kiện kích hoạt chung — có thật, không giả định

- `ecosystem.config.js` khai báo `FB_Publisher_1` **và** `FB_Publisher_2`
  (cùng `AI_Generator_1/_2`, `Threads_Publisher`).
- `publish.max_concurrent_accounts` mặc định `2` (`publisher_runtime.py:143`).
- `claim_precheck` đếm RUNNING trước khi claim — read-then-act, không nguyên tử,
  không đóng cửa sổ race nào ở trên.
- Stagger khởi động 1–5 s chỉ **giảm** xác suất trùng tick, không loại bỏ.

**Hậu quả chung:** cùng một Reels/bài feed đăng hai lần lên cùng một Page trong vài
giây. Với Facebook đây là tín hiệu automation rõ ràng → nguy cơ hạn chế Page /
checkpoint account. Idempotency `external_post_id` chỉ chạy khi `tries > 0`
(`dispatcher.py:214`) nên **không** bắt được double-claim đồng thời của A và B.

**Chưa thấy dấu vết trong dữ liệu hiện có:** đã truy vấn live — không cặp job DONE nào
cùng `(account, platform)` cách nhau <60 s trong 14 job đang có. DB mới có 1 account.
**Đây là bằng chứng "chưa xảy ra", không phải bằng chứng "không thể xảy ra".**

---

### 🔴 P0-2 — Link affiliate đăng lên Facebook là chuỗi không phải URL, và endpoint redirect nằm sau tường đăng nhập

**File:** `app/core/queue/job.py:488, 1057, 1211`; `app/main.py:110-115`;
`app/platform/dashboard_shell/router.py:380`

Ba lỗi cộng dồn thành một tính năng chết:

**(a) Link tương đối bị đăng lên mạng xã hội.**
```python
# job.py:1057 và 1211
vurl = (VERCEL_REDIRECT_URL or "").strip().rstrip("/")
full_turl = f"{vurl}/r/{tracking_code}" if vurl else f"/r/{tracking_code}"
comment = template.replace("{tracking_url}", full_turl)
```
`.env` hiện tại **không có** `VERCEL_REDIRECT_URL` (đã kiểm tra: 0 dòng khớp).
Nên `full_turl = "/r/abc12345"` — chuỗi này được ghi vào `auto_comment_text` rồi
worker gõ thẳng vào ô bình luận Facebook. Facebook không nhận đó là link. Khách
thấy một chuỗi rác dưới bài.

Cùng vấn đề ở tin (story): `adapter.py:1654 story_overlay_text()` ưu tiên
`job.tracking_url` — tức phủ chuỗi `/r/abc12345` lên story.

**(b) `/r/{code}` yêu cầu đăng nhập.**
`main.py` middleware cho qua đúng `{"/health", "/health/json", "/health/ui",
"/health/gemini/cookie-sync"}` và prefix `("/static", "/login", "/favicon.ico")`.
`/r/` không nằm trong đó. Người lạ bấm link → 302 về `/login`. Kể cả có domain
đúng, redirect vẫn không hoạt động cho công chúng.

**(c) Ghi mất `tracking_url` khi có Vercel.**
`create_job` gọi `_register_vercel_tracking(new_job)` ở bước 6 (`job.py:534`), hàm
này gán `job.tracking_url = f"{vercel_url}/r/{code}"` (`job.py:592`) rồi **không
commit**. `get_db()` (`core/database/core.py:20`) chỉ `close()`, không commit. Giá
trị bị vứt. Nên nếu Owner cấu hình Vercel để vá (a), (c) sẽ âm thầm vô hiệu hoá nó
ở luồng tạo job đơn lẻ.

**Hậu quả:** `click_count` vĩnh viễn 0. Dashboard hiển thị "N clicks" (
`job_row.html:182`), báo cáo Telegram cộng `total_clicks` (`notifier/service.py:202`)
— tất cả đều là số 0 giả. Tính năng "link aff có đếm click" đang nằm trong mô tả
combo bán 3tr5–5tr.

**Confidence: HIGH** — đọc được cả 3 đoạn code, `.env` xác nhận biến trống,
danh sách public path xác nhận `/r/` không được miễn auth.

**Phạm vi bản vá — đây là một CỤM ba lỗi, không phải một dòng.** Cả ba đều nhỏ nhưng
nằm ở ba tầng khác nhau (sinh URL / middleware auth / vòng đời transaction), và sửa
đúng hai trong ba vẫn để lại tính năng hỏng:

| | Lỗi | Tầng | Vá |
|---|---|---|---|
| a | URL tương đối khi thiếu base URL | `job.py:1057,1211`, `attach_affiliate_to_job` | Bắt buộc có base URL tuyệt đối; **fail-fast** khi thiếu thay vì sinh chuỗi rác |
| b | `/r/{code}` sau tường auth | `main.py:114` | Thêm vào `public_prefixes` |
| c | `tracking_url` ghi rồi mất | `job.py:534,592` + `core.py:20` | Commit sau khi gán |

**Không được coi P0-2 là xong nếu chỉ test từng hàm riêng lẻ.** Điều kiện đóng là
một test end-to-end đi hết chuỗi ở §19 — vì chính bản chất của lỗi này là *ba mảnh
đều "đúng" khi nhìn riêng, chỉ sai khi ghép lại*.

---

### 🟠 P1-1 — Deploy nuốt lỗi migration và không backup PostgreSQL

**File:** `.github/workflows/deploy.yml:110-113, 92-94`

```bash
python manage.py db stamp-if-needed || true
python manage.py db upgrade head   || true      # ← migration fail vẫn deploy tiếp
...
bash ./start.sh                                  # ← restart worker trên schema cũ
```

Migration hỏng → script chạy tiếp → worker khởi động lại trên schema cũ → mọi câu
query chạm cột mới ném `UndefinedColumn` → job FAILED hàng loạt, và không có bước
nào phát hiện.

Backup duy nhất:
```bash
cp "$DB_SOURCE" "$BACKUP_DIR/auto_publisher_$(date ...).db" || true
```
`$DB_SOURCE` là file **SQLite legacy**. Dữ liệu thật nằm ở PostgreSQL. `pg_dump`
tồn tại trong repo nhưng **chỉ là một nút bấm tay** trong syspanel
(`system_panel/service.py:654`) — không có trong pipeline, không có cron, không có
lịch. **Không có backup Postgres tự động nào.**

Thiếu luôn: health check sau restart, kế hoạch rollback (rollback = `git reset` về
SHA cũ nhưng migration không được downgrade → schema và code lệch nhau), và cả
`main` lẫn `develop` deploy vào cùng một đường dẫn VPS.

**Confidence: HIGH**

---

### 🟠 P1-2 — CI đỏ 3 tuần; kiến trúc contract chưa bao giờ chạy

- `deploy.yml` đặt `python-version: "3.10"` nhưng `requirements.txt` ghim
  `numpy==2.4.2` (cần ≥3.11) → job `test` fail → job `deploy` (needs: test) không
  chạy. Đỏ từ 2026-07-29, ghi trong `current-status.md`.
- Hệ quả: từ `d8a7e88` tới `ea57b4b`, **5 commit trên `main` chưa từng qua cổng test
  nào** và chưa từng deploy.
- `import-linter==2.11` có trong `requirements.txt`, có file `.importlinter` với 2
  contract, nhưng **không cài trong venv** (`pip list` không có) và **không có bước
  nào chạy `lint-imports`** trong CI. Hai vi phạm V1/V2 (§5) đang tồn tại không ai
  biết.
- CI **không có service Postgres** → 3 file test `@pytest.mark.integration`
  (`test_comment_image`, `test_feed_post_url`, `test_queue_claims_all_job_types`)
  tự skip. Chính test chứng minh bản vá PLAN-052 (job FEED bị kẹt PENDING vĩnh viễn)
  **không chạy trong CI**.

**Confidence: HIGH**

---

## 11. Architecture Debt

| # | Nợ | Bản chất |
|---|---|---|
| A1 | **Tầng no-code chết** — `GenericAdapter` + `ActionExecutor` + `workflow_definitions` + phần scaffolding của `config_service.py` (~1015+ dòng không thể chạm tới; `dispatcher.py:88` luôn ghi đè vì `_DEDICATED_ADAPTERS` phủ toàn bộ enum `Platform`) | ADR-009 đã đề xuất khai tử, **chờ Owner chốt** |
| A2 | **Port adapter không đầy đủ** — `publish_feed`/`publish_story`/`post_comment` ngoài ABC, dispatcher dò `hasattr` | Thêm job_type mới = sửa dispatcher + N adapter, compiler không giúp gì |
| A3 | **`app/adapters` biết đích danh `features.facebook`** (`dispatcher.py:15`, `PageMismatchError` rò lên tận worker) | Tầng dùng chung phụ thuộc một feature cụ thể |
| A4 | **Contract kiến trúc không có cổng gác** — 2 vi phạm đang sống | Quy tắc không được enforce sẽ trôi |
| A5 | **Enum nghiệp vụ chỉ tồn tại trong Python** — `jobs.status`/`job_type`/`platform`/`error_type` không có CHECK constraint, không default ở DB | DB nhận mọi rác; sửa tay hoặc script cũ ghi được trạng thái không hợp lệ |
| A6 | **JSON nhét trong cột `String`** — `target_pages`, `niche_topics`, `page_niches`, `competitor_urls`, `engagement_page_urls`, `managed_pages` (Account); `meta_json` (JobEvent) | Postgres có JSONB; hiện không query được, không validate được, drift âm thầm |
| A7 | **`parent_job_id` không có FOREIGN KEY** (`models/jobs.py:73`) — khác hẳn `viral_material_id` vốn có FK + `ondelete=SET NULL` | COMMENT job có thể trỏ vào job đã bị xoá |
| A8 | **Model và DB lệch nhau** — hai partial unique index quan trọng nhất chỉ nằm trong migration, `__table_args__` không khai báo | Ai đó dựng DB từ `Base.metadata` sẽ mất invariant chống đăng trùng |

---

## 12. Business Logic & Invariants

### Business rule nằm ở đâu

| Loại | Ở đâu | Đánh giá |
|---|---|---|
| **Domain policy** | `JobService` constants (`NON_REELS_JOB_TYPES`, `COMMENTABLE_JOB_TYPES`, `VIDEO_EXTENSIONS`) | Có ý thức gom về một chỗ — comment ghi rõ "single source of truth". Tốt |
| **Application workflow** | `Dispatcher.dispatch()` rẽ nhánh `job_type`; `publisher.process_single_job()` | Trộn nhiều tầng: validate + compliance + timer + publish + cleanup trong một hàm 200 dòng |
| **SQL predicate** | `claim_next_job` chứa cooldown, fair-share, mutex, due-check | Quy tắc nghiệp vụ quan trọng nhất viết bằng SQL thô — nhanh và nguyên tử, nhưng chỉ test được khi có Postgres |
| **Validation** | `assert_feed_media` / `assert_story_media` / `assert_comment_image` / `assert_facebook_post_media` | Rõ ràng, thông điệp lỗi khớp với danh sách chấp nhận |
| **Database constraint** | 2 partial unique index (chống đăng trùng media) | **Điểm mạnh nhất của hệ** |
| **Frontend logic** | `create_job_form.html:217` `ACCEPTED_VIDEO_EXT`; `manual_job_form.html:140` | **Bản sao thủ công** của hằng số backend |
| **Configuration rule** | `runtime_settings` trong DB + `.env` + `config.py` | Ba nguồn; `apply_runtime_overrides_to_config` hoà giải |

### ⚠️ MULTIPLE SOURCES OF TRUTH — danh sách đuôi file media

Cùng một sự thật nghiệp vụ ("Facebook nhận đuôi nào") tồn tại ở 4 chỗ:

| Nơi | Nội dung |
|---|---|
| `app/core/queue/job.py:130-131` | `VIDEO = ('.mp4','.mov','.webm','.mkv')`, `IMAGE = ('.jpg','.jpeg','.png')` |
| `create_job_form.html:217` | `const ACCEPTED_VIDEO_EXT = ['.mp4','.mov','.webm','.mkv']` — copy tay |
| `create_job_form.html:62,120` | chữ hiển thị `.mp4/.mov/.webm/.mkv` và `.jpg/.jpeg/.png` |
| `manual_job_form.html:140,146` | chữ hiển thị **`.jpg/.png/.webp`** |

**Đã drift thật:** `.webp` được UI quảng cáo cho FEED/STORY nhưng
`JobService.IMAGE_EXTENSIONS` **không có** `.webp`. Người dùng kéo file `.webp`
vào form theo đúng hướng dẫn trên màn hình → backend `assert_story_media` ném
`ValueError`. Đây chính xác là kiểu lỗi mà nhiều-nguồn-sự-thật sinh ra.

`tests/test_media_ui_consistency.py` đã cố khoá sự đồng bộ này — nhưng bằng cách
grep chuỗi `accept="video/*"`, nên nó bắt được `accept` mà **không** bắt được chữ
hiển thị `.webp`.

### Bảng invariant

| Invariant | Enforce ở đâu | Mức bảo vệ |
|---|---|---|
| Một file media không được đăng 2 lần trên cùng platform | **DB partial unique index** + `assert_media_not_blocked` + `IntegrityError` handler | ✅ **Mạnh** |
| Một viral material chỉ sinh 1 job đang sống | **DB partial unique index** | ✅ **Mạnh** |
| **(A)** Một job PENDING chỉ được đúng một worker nhận | Chỉ trong SQL subquery của `claim_next_job`; qual ngoài chỉ có `id` | ❌ **Vỡ — CONFIRMED** (P0-1A). Vá bằng outer predicate |
| **(B)** Một `(account, platform)` chỉ có tối đa 1 job RUNNING | Chỉ là anti-join bên trong cùng InitPlan — **không có ràng buộc DB nào** | ❌ **Không được bảo vệ — PLAUSIBLE** (P0-1B). Outer predicate **không** vá được; cần partial unique index |
| **(C)** Job đang chạy không bị recovery cướp | `recover_crashed_jobs` dựa trên heartbeat; ngưỡng 120 s < deadline 900 s | ❌ **Vỡ — CONFIRMED cơ chế** (P0-1C). Cần sửa nghịch đảo ngưỡng |
| Reels Facebook bắt buộc là video | `assert_facebook_post_media` gọi ở **2 chỗ** (dispatcher + worker) | ✅ Tốt (chủ ý double-gate) |
| Story bắt buộc có media | `assert_story_media` khi tạo job | ⚠️ Chỉ ở tầng tạo; DB cho phép NULL |
| Nội dung vi phạm chính sách không được đăng | `check_before_publish` — **chỉ trong `features/facebook/workers/publisher.py`** | ⚠️ Threads publisher **không** gọi; và `Dispatcher._inject_cta` chèn CTA **sau** khi kiểm tra → CTA từ DB không qua compliance |
| Vượt daily limit thì không đăng | `postpone_if_daily_limit` sau claim | ⚠️ Đếm `COUNT(DONE hôm nay)` không nguyên tử với claim — hai worker cùng vượt được 1 đơn vị |
| Account fail 3 lần liên tiếp thì tắt | `mark_failed_or_retry` + `NON_ACCOUNT_ERROR_TYPES` | ✅ Tốt, phân loại đúng |
| `status` chỉ nhận giá trị trong `JobStatus` | Không ở đâu ở tầng DB | ❌ Không có CHECK constraint |

---

## 13. Data Architecture

**Tốt:**
- 26 migration Alembic tuyến tính, 23/25 có `downgrade()` thật.
- Index đầy đủ trên `jobs`: 18 index gồm composite `(status, schedule_ts)`,
  `(account_id, status)`, `(status, metrics_checked, finished_at)` — khớp đúng
  pattern truy vấn của claim và metrics checker.
- FK có `ondelete` chủ đích: `jobs.viral_material_id → SET NULL`.
- Timestamp thống nhất kiểu Unix epoch `Integer` toàn hệ (`now_ts()`), tránh bẫy
  timezone. Nhất quán là điểm cộng.
- Partial unique index cho invariant nghiệp vụ — cách làm đúng, đã nói ở §9.

**Yếu:**

| Vấn đề | Evidence |
|---|---|
| **0 CHECK constraint trên `jobs`** | Query `pg_constraint` chỉ ra CHECK ở `incident_logs`/`incident_groups`, không có ở `jobs` |
| **Mọi cột `jobs` đều nullable, không default DB** | `information_schema.columns`: `status` `is_nullable=YES`, `column_default=None` — default `'PENDING'` chỉ ở Python |
| **`parent_job_id` không FK** | `models/jobs.py:73` |
| **JSON trong `String`** | 6 cột ở `Account`, `meta_json` ở `JobEvent`; Postgres 16 có JSONB nhưng không dùng |
| **`Job` là bảng quá tải** | 40 cột trộn: định danh, media, lịch, state machine, retry, idempotency, metrics, tracking affiliate, auto-comment, khoá. Ít nhất 3 concern (publish / metrics / affiliate) có thể tách |
| **Derived field có nguy cơ drift** | `accounts.last_post_ts` cập nhật trong `mark_done`, nhưng `claim_next_job` lại tự tính `MAX(finished_at)` — hai nguồn cho cùng một sự thật |
| **Model/DB lệch** | 2 partial unique index không có trong `__table_args__` |
| **Migration rủi ro** | `4215e86b6614_add_platform_config_tables.py` có `downgrade()` **rỗng** → không rollback được |
| **`blocking_status_sql_list()` nối chuỗi SQL** | `content_hash.py:112` — hiện chỉ nhận hằng số nội bộ nên an toàn, nhưng là mẫu nguy hiểm để lại |

---

## 14. Transaction & Concurrency Audit

| Chủ đề | Kết luận |
|---|---|
| **Claim job — bất biến A** (một job / một worker) | ❌ **CONFIRMED vỡ** (P0-1A). Qual ngoài chỉ có `id`; EvalPlanQual không kiểm `status`. Vá: `AND status='PENDING'` ở WHERE ngoài — đã xác nhận bằng `EXPLAIN` |
| **Claim job — bất biến B** (một job RUNNING / account+platform) | ❌ **PLAUSIBLE vỡ** (P0-1B). Anti-join nằm trong InitPlan; khi hai worker chọn **hai row khác nhau** thì không có xung đột khoá nên không có recheck nào. **Bản vá của A không chạm tới B.** Cần partial unique index `(account_id, platform) WHERE status='RUNNING'` |
| **Claim engagement account** | ⚠️ `_maybe_idle_engagement` (`publisher.py:648-690`) đọc danh sách account ACTIVE → chọn ngẫu nhiên → mới `commit()` `login_status=ENGAGING`. Hai publisher rảnh cùng lúc có thể chọn cùng account → **hai phiên Chrome mở cùng một profile** → hỏng profile/checkpoint. `_last_engagement_ts` là dict in-memory, không chia sẻ giữa tiến trình |
| **Daily limit** | ⚠️ `COUNT` rồi `postpone` — read-then-act, hai worker cùng vượt được cap. Sai lệch tối đa = số worker đồng thời (hiện 2), **không** tích luỹ. Ưu tiên thấp hơn A/B/C |
| **Idempotency** | ⚠️ Chỉ chạy khi `tries > 0` (`dispatcher.py:214`). Không bảo vệ double-claim đồng thời |
| **Recover stale — bất biến C** | ❌ **CONFIRMED vỡ về cơ chế** (P0-1C). `WORKER_CRASH_THRESHOLD_SECONDS=120` **nhỏ hơn** `PUBLISHER_PUBLISH_DEADLINE_SEC=900` — recovery đang chạy đua với job khoẻ mạnh. Hai nhịp heartbeat lỡ liên tiếp (60 s × 2) đủ để job đang chạy bị đặt về PENDING và bị worker khác claim. **Không bản vá nào của A/B chạm tới C** vì row lúc đó thật sự là PENDING. ✅ Cap `tries` vẫn đúng |
| **Lost update `tracking_url`** | ❌ `_register_vercel_tracking` ghi rồi không commit (§10 P0-2c) |
| **Xoá file media** | ❌ Xem §24 SF-2 — job DONE xoá file gốc vô điều kiện, phá job platform khác dùng chung file |
| **Partial write batch upload** | ✅ Có rollback + `_discard_files` |
| **Optimistic locking** | Không có cột version. Với mô hình một-worker-một-job thì không cần — miễn là claim đúng nguyên tử. ⚠️ Nhưng P0-1C cho thấy cần **một** dạng CAS: worker phải xác nhận job còn thuộc về mình trước `mark_done` |
| **Claim job VERIFY_THREADS** | ❌ `claim_next_verify_job` (`threads/workers/verifier.py:259`) là `SELECT ... first()` rồi `job.status = RUNNING` ở `:213` — read-then-act, **không nguyên tử chút nào**. Giảm nhẹ: worker này **không được khởi động bởi bất kỳ supervisor nào** (không có trong `ecosystem.config.js`, `start.sh`, `start.ps1`, `local_supervisor.py`) nên hiện là code ngủ. Phải vá **trước khi** bật |

---

## 15. Integration Architecture

| Integration | Auth | Timeout | Retry | Circuit breaker | Fallback | Đánh giá |
|---|---|---|---|---|---|---|
| **Facebook / Threads / IG / TikTok (DOM)** | Chrome profile trên đĩa | `_safe_goto` 60s, retry 3 | ✅ | ❌ | Selector động (DB) → heuristic | ⚠️ Nền tảng không có hợp đồng — DOM đổi là gãy |
| **9Router → Gemini** | API key | `(5.0, 90.0)` connect/read | ✅ | ✅ `CircuitBreaker` (5 fail / TTL 15s) | ✅ Native Gemini (ADR-006 phương án A) | ✅ **Tốt nhất trong các integration** |
| **Telegram** | Bot token | — | ❌ | ❌ | `except: pass` khắp nơi | ⚠️ Cảnh báo có thể mất im lặng |
| **Vercel redirect** | không | 5s | ❌ | ❌ | ghi log rồi bỏ qua | ❌ Ghi mất kết quả (P0-2c) |
| **yt-dlp / ffmpeg** | — | có timeout | một phần | ❌ | ffmpeg fail → đăng file gốc | ✅ Hợp lý |
| **PM2 / shell** | — | 10–120s | ❌ | — | — | ✅ Tên process có whitelist (`PM2_SAFE_NAMES`) |

### External vocabulary rò vào domain

Không nghiêm trọng. `Platform` là StrEnum sạch. Không thấy `status = 63` hay
`platform_id = 8195` rải trong business code. Nhưng có rò cục bộ:

- `PageMismatchError` (rất Facebook) xuất hiện ở `adapters/dispatcher.py:15` và
  `features/facebook/workers/publisher.py`.
- Chuỗi DOM/GraphQL của Facebook (`_walk_for_post_ids`, `_post_url_from_payload`,
  `_fb_aria_switch_label_is_carousel_noise`) nằm trong `FacebookAdapter` — **đúng
  chỗ**, đây chính là vai trò anti-corruption layer.

**Kết luận:** ACL hiện tại **đủ dùng**, không cần thêm tầng normalization. Việc cần
làm là hoàn thiện *port* (§11 A2), không phải xây ACL mới.

### Câu hỏi bắt buộc: nếu một external service chết 6 giờ?

| Service chết | Điều gì xảy ra |
|---|---|
| **9Router + Gemini** | Circuit breaker mở, `AI_Generator` không sinh được caption; job DRAFT chất đống với marker `[AI_GENERATE]`; publisher **có guard** đưa về DRAFT thay vì đăng nguyên placeholder (`publisher.py:151`). ✅ Xuống cấp an toàn |
| **Facebook** | `_safe_goto` retry 3 lần rồi fail; `mark_failed_or_retry` backoff 5/15 phút; sau 3 `tries` → FAILED; sau 3 FATAL liên tiếp → **circuit breaker tắt account**. ⚠️ Facebook down 6h có thể tắt account dù account hoàn toàn khoẻ — cần phân biệt "platform down" và "account chết" |
| **Telegram** | Mất toàn bộ cảnh báo, im lặng (`except: pass`). ⚠️ Không có kênh dự phòng |
| **Postgres** | Toàn bộ dừng. Worker log lỗi vòng lặp và ngủ. ✅ Không mất dữ liệu, nhưng ❌ không có backup tự động để phục hồi |
| **Vercel** | Không ảnh hưởng gì thêm — link vốn đã hỏng (P0-2) |

---

## 16. API Audit

Đây **không phải** REST API — nó là ứng dụng HTMX server-rendered. Đánh giá theo
đúng bản chất đó:

- **236 route**, phần lớn trả HTML fragment. Không có `openapi_url` (đã tắt chủ ý —
  đúng cho app nội bộ).
- **Nhất quán:** prefix theo feature (`/syspanel`, `/app/...`, `/jobs`), fragment
  trả về khớp hợp đồng ghi trong `docs/13_HTML_PARTIAL_CONTRACTS.md`.
- ✅ **Không có route GET nào gây side-effect** — đã grep toàn bộ, mọi hành động
  phá huỷ đều là POST. Đây là điểm tốt, cũng chính là thứ khiến `SameSite=Lax`
  đủ để chống CSRF.
- ⚠️ **Business logic trong handler.** `jobs/router.py:167-178` tự parse
  `schedule_time`, tự dựng timezone, rồi `except Exception as e:` trả `str(e)`
  thẳng ra template — thông điệp lỗi nội bộ hiển thị cho người dùng.
- ⚠️ **Không có versioning** — chấp nhận được vì client duy nhất là template của
  chính app.
- ⚠️ **Phân trang không đồng đều:** `get_jobs_paged` có, nhưng
  `DashboardService.get_overview_data` gọi `db.query(Account).all()` không giới hạn.
  Hiện 1 account nên vô hại.

---

## 17. Security

Bối cảnh: **một người dùng duy nhất, một admin duy nhất**. Đánh giá theo bối cảnh đó
— không áp chuẩn SaaS multi-tenant.

| Mục | Trạng thái | Phân loại |
|---|---|---|
| Authentication | 1 admin trong `.env`, `secrets.compare_digest`, cookie `itsdangerous` ký, HttpOnly, `SameSite=Lax`, `Secure` khi HTTPS, hạn 7 ngày | ✅ Đúng chuẩn cho quy mô này |
| Query-param login | Có, nhưng mặc định **tắt** (`ALLOW_QUERY_LOGIN=false`), comment ghi rõ lý do rò credential | ✅ Xử lý đúng |
| Authorization / RBAC | Không có — mọi request đã auth đều là superuser | ⚠️ Chấp nhận được (1 user), nhưng nghĩa là chiếm được session = chiếm cả hệ thống |
| Tenant isolation | Không áp dụng | — |
| CSRF | Không có token. `SameSite=Lax` + không có GET gây side-effect ⇒ chặn được form POST cross-site | ⚠️ **Chấp nhận được dưới threat model hiện tại — không phải "đã có CSRF protection"**. Xem giả định + điều kiện review lại bên dưới |
| SQL injection | ORM + bind param ở mọi truy vấn nghiệp vụ. SQL console có AST validator + deny-by-default | ✅ **CONFIRMED an toàn** |
| Command injection | `shell=True` ở `system_panel/service.py:67` và `:148`. Tham số người dùng duy nhất là tên PM2, đã whitelist qua `PM2_SAFE_NAMES`; `action` whitelist `("start","stop","restart")` | ✅ **CONFIRMED chặn** |
| Hành động phá huỷ | `git reset --hard`, `pm2 delete all`, `pm2 restart all` nằm sau cờ `SYSPANEL_DESTRUCTIVE_ENABLED` (mặc định tắt) | ✅ Có kỷ luật |
| **Đọc file tuỳ ý** | `serve_screenshot` (`service.py:576`) resolve path rồi kiểm `relative_to(APP_DIR)` — chống traversal ra ngoài repo, **nhưng gốc là cả repo**, không giới hạn thư mục screenshot, không giới hạn đuôi file. `GET /syspanel/screenshot?path=.env` đọc được `SECRET_KEY`, `ADMIN_PASSWORD`, `DATABASE_URL` | ⚠️ **LIKELY** — cần đã auth; mức thiệt hại thấp vì admin đã có SQL console. Vẫn nên siết về `logs/debug_steps` + whitelist `.png/.jpg` |
| XSS | Jinja2 autoescape mặc định bật; chỉ **2** chỗ dùng `\|safe`, cả hai là icon do hệ thống sinh. Log viewer escape thủ công trước khi tô màu | ✅ **CONFIRMED sạch** |
| Upload file | Validate **đuôi** trước khi ghi đĩa, tên file thay bằng `uuid4().hex` → không path traversal qua filename. ⚠️ Không giới hạn dung lượng, không kiểm magic bytes | ⚠️ **POTENTIAL** — rủi ro thấp (1 admin), nhưng upload file khổng lồ có thể lấp đĩa VPS |
| Secret trong log | `incident_logger.SENSITIVE_KEYS` + regex mask bearer/basic/JWT | ✅ Tốt |
| Secret trong repo | `.env` đã ignore; `.gitignore` chặn `*cookies*.json`, `*_session.json`; `git ls-files` không còn secret | ✅ Đã sạch |
| **Cookie phiên đã rò lịch sử** | `scratch/threads_cookies.json` commit ở `a723c0f`, public ~3.5 tháng. Đã purge + force-push nhưng **object mồ côi vẫn tải được theo SHA**. Owner chọn giữ repo public, chấp nhận rủi ro | 🔴 **CONFIRMED** — việc bắt buộc còn lại: **đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok** |
| `/health/gemini/cookie-sync` public | Miễn auth, bảo vệ bằng header `X-Api-Secret` (`COOKIE_SYNC_SECRET`) | ⚠️ Cần xác nhận `.env` production không để giá trị mẫu `change_me_to_something_secure` |

### CSRF — giả định phải ghi rõ

Kết luận "chấp nhận được" **chỉ đúng khi cả bốn điều sau còn đúng**:

1. Đúng **một** tài khoản admin, không có người dùng khác trong cùng browser profile.
2. Cookie giữ `SameSite=Lax` (đang đúng — `auth/router.py:64`).
3. **Không** có route GET nào gây side-effect (đã grep toàn bộ 236 route — hiện đúng).
4. Không có API JSON nhận `Content-Type: application/json` từ origin khác, không có
   subdomain dùng chung cookie.

**Phải review lại security posture khi bất kỳ điều nào thay đổi:** thêm người dùng
thứ hai, thêm JSON API cho client ngoài, tách subdomain, đổi `SameSite`, hoặc thêm
một route GET có side-effect. Ở thời điểm đó `SameSite=Lax` **không còn** là biện
pháp đủ và cần token CSRF thật.

**Không được đọc dòng này thành "hệ thống đã chống CSRF".** Nó đang *không có* cơ chế
chống CSRF; nó đang *không cần* một cơ chế, vì bốn giả định trên.

### Đọc file tuỳ ý sau khi auth — phân tích lại theo threat model

Bản audit trước ghi "mức thiệt hại thấp vì admin đã có SQL console". **Lập luận đó
sai và đã được sửa.** Hai khả năng không tương đương:

| | SQL console | `GET /syspanel/screenshot?path=.env` |
|---|---|---|
| Đọc được | dữ liệu trong DB | **file trên đĩa**, gồm `.env` |
| Lộ ra | job, account, keyword… | `SECRET_KEY`, `ADMIN_PASSWORD`, `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `COOKIE_SYNC_SECRET`, khoá AI |
| Sau khi phiên hết hạn | mất quyền | **`SECRET_KEY` cho phép tự ký cookie phiên mới → giữ quyền vô thời hạn** |

Điểm mấu chốt: `SECRET_KEY` là thứ dùng để **ký** cookie phiên
(`auth/router.py:11` → `URLSafeTimedSerializer(config.SECRET_KEY)`). Ai đọc được nó
có thể tự phát hành token admin hợp lệ mà không cần mật khẩu. Nghĩa là lỗ này
**biến một phiên bị chiếm có thời hạn thành quyền truy cập bền vững**, cộng thêm
credential của các dịch vụ ngoài (Telegram, AI, DB) dùng lại được ở nơi khác.

**Phân loại đúng:** không phải RCE không cần auth — cần một phiên admin hợp lệ trước
đã, nên **không được phóng đại**. Nhưng cũng **không vô hại**: nó là bước leo thang
từ "mất phiên" thành "mất toàn bộ credential". Vì vậy **TD-18 được nâng P2 → P1**
và đưa vào nhóm NOW.

---

## 18. Reliability

**Mạnh:** `finally: close_session()`; suicide timer; heartbeat thread có `finally`
dừng ở mọi đường thoát sớm; `recover_crashed_jobs` có cap `tries`; graceful
shutdown xử lý cả `SIGBREAK` (Windows); backoff idle tăng dần tới 60s; auto-tắt
idle engagement khi backlog cao (bảo vệ máy 8GB).

**Yếu:**

1. **`maintenance.run_loop()` là all-or-nothing.** 12 việc không liên quan chạy tuần
   tự trong một `try`; `except: db.rollback(); raise` đẩy lên vòng ngoài → **cả
   sweep bị bỏ**. Nếu bước 2 (`MetricsChecker.check_pending` — scrape Facebook, dễ
   gãy khi DOM đổi) ném liên tục, thì bước 3 (`recover_crashed_jobs`), bước 6
   (purge zombie Chrome), bước 8 (insights) **không bao giờ chạy**. Tức là cơ chế
   tự chữa lành bị vô hiệu bởi một tính năng scrape không liên quan.
   *Evidence:* `maintenance.py:490-545`.

2. **Setting đọc lúc import.** `PURGE_INTERVAL_SEC` (`maintenance.py:221`) và
   `DISCOVERY_INTERVAL_SEC` (`:247`) gọi `runtime_settings.get_int()` ở **module
   level**. Đổi giá trị trên UI không có tác dụng cho tới khi restart worker — và
   UI không hề nói vậy.

3. **Circuit breaker không phân biệt "platform down" và "account chết"** — xem §15.

4. **Telegram là kênh cảnh báo duy nhất**, mọi lỗi gửi đều `except: pass`.

---

## 19. Testing

**Số liệu:** 28 file, 245 test, 2930 dòng, chạy hết trong **10.8 giây**.

### Test đang bảo vệ điều gì?

| Loại | Số test (xấp xỉ) | Nhận xét |
|---|---:|---|
| **Grep source rồi assert chuỗi** | **~120 (49%)** | 13 file dùng `read_text()` rồi `assert "..." in src` |
| Unit hành vi thật | ~100 | validator, sql_validator, storage_paths, process_scan, article_scorer |
| Integration DB thật | ~25 (3 file) | Chạy SQL thật trên Postgres, cô lập bằng `platform='__pytest_q_*'` |
| E2E / browser | **0** | — |
| Contract / performance / security scan | 0 / 0 / 3 (grep) | — |

### Vấn đề cốt lõi

`tests/test_queue_claim_guards.py` là ví dụ điển hình:

```python
def test_claim_mutex_is_per_platform():
    src = QUEUE_PY.read_text(encoding="utf-8")
    assert "j2.platform = j.platform" in src
    assert "Per-platform mutex" in src   # assert cả comment tiếng Anh!
```

Test này **xanh** trong khi mutex thực tế không được bảo vệ ở tầng DB (P0-1B). Nó khoá *văn bản*
chứ không khoá *hành vi*. Đổi tên biến hợp lệ sẽ làm test đỏ; một race condition
thật thì không.

Chính dự án đã tự nhận ra: docstring của `test_queue_claims_all_job_types.py` viết
*"Test cũ chỉ soi chuỗi trong source nên không bắt được — nên test này chạy thẳng
câu SQL thật trên Postgres."* Đó là hướng đúng và cần nhân rộng.

### Test bắt buộc — đặc tả, không phải gợi ý

Ba test dưới đây là **điều kiện đóng** cho P0-1 và P0-2. Không có chúng thì bản vá
chỉ là giả thiết. Cả ba phải chạy trên **PostgreSQL thật**, không mock.

#### TEST A — Job exclusivity (bất biến A)

```
Setup    1 job PENDING (account X, platform P), account is_active + login_status=ACTIVE
Act      2 DB session độc lập cùng gọi claim_next_job(platform=P) đồng thời
         (dùng threading.Barrier để hai câu UPDATE chạm DB trong cùng cửa sổ)
Assert   Đúng 1 session nhận job; session còn lại nhận None
         Sau đó: SELECT count(*) FROM jobs WHERE id=<job> AND status='RUNNING' = 1
```

Đây là test khoá bản vá outer predicate. **Chạy nó trên code CHƯA vá trước** — nếu
nó không đỏ, test sai chứ không phải code đúng.

#### TEST B — Account/platform exclusivity (bất biến B)

```
Setup    2 job PENDING KHÁC NHAU, CÙNG account X, CÙNG platform P
         schedule_ts BẰNG NHAU (ép hoà khoá sắp xếp — xem P0-1B)
Act      2 session cùng claim đồng thời
Assert   Tổng số job RUNNING của (X, P) <= 1
```

⚠️ **TEST B là một race RIÊNG.** Nó **không** được bảo vệ bởi bản vá của TEST A.
Nếu TEST B đỏ sau khi đã vá outer predicate — đó là hành vi **đúng như dự đoán**
(§10 P0-1B), không phải bản vá hỏng. TEST B chỉ xanh sau khi có partial unique index
`(account_id, platform) WHERE status='RUNNING'` **và** `claim_next_job` bắt được
`IntegrityError` trả `None`.

Nếu Owner quyết định **chưa** làm partial unique index: giữ TEST B ở trạng thái
`xfail` có ghi lý do, **không được xoá test và không được tuyên bố B đã đóng.**

#### TEST C — Affiliate end-to-end (P0-2)

Test từng hàm riêng **không** đóng được P0-2, vì lỗi nằm ở chỗ ghép các mảnh.
Phải đi hết chuỗi:

```
1. Tạo job có affiliate_url
2. Assert tracking_url là URL TUYỆT ĐỐI (có scheme + host), không phải "/r/..."
   — và assert giá trị đó đã được COMMIT xuống DB (đọc lại bằng session mới)
3. Assert auto_comment_text / story overlay chứa đúng URL tuyệt đối đó
4. GET /r/{code} bằng HTTP client KHÔNG có cookie phiên
5. Assert 302 tới affiliate_url  (KHÔNG phải 302 tới /login)
6. Assert jobs.click_count tăng 1
7. Assert dashboard/report đọc ra 1 click
```

Bước 4 là bước quan trọng nhất và cũng là bước dễ bị bỏ nhất: **client phải không
đăng nhập**. Test bằng session admin sẽ xanh giả.

---

### Luồng critical chưa có test

| Luồng | Rủi ro |
|---|---|
| **Hai worker claim cùng MỘT job** | P0-1A — không có test concurrency nào (TEST A) |
| **Hai worker claim HAI job cùng account** | P0-1B — không có test nào (TEST B) |
| **Recovery reset job đang chạy** | P0-1C — không có test nào |
| **Link affiliate end-to-end** (tạo job → comment → click → count) | P0-2 — không test nào chạm |
| `mark_done` → tự tạo COMMENT job | Không test hành vi |
| Circuit breaker account (3 FATAL → `is_active=False`) | Không test |
| `postpone_if_daily_limit` | Không test |
| `recover_crashed_jobs` cap `tries` | Chỉ có grep source |
| Rollback batch upload | Không test |
| Migration up/down | Không test |

### Vấn đề hạ tầng test

- **Không có `conftest.py`**, không fixture DB dùng chung, không `create_all` →
  test integration chạy trên **chính DB dev có dữ liệu thật**, cô lập bằng quy ước
  đặt tên platform.
- CI **không có service Postgres** → toàn bộ test integration skip trong CI.
- `test_threads_world_news.py` phải `--ignore` thủ công (chưa xử).

### Thứ tự chuyển sang test hành vi

Không cần viết lại toàn bộ test suite. Chuyển theo đúng thứ tự này, dừng lại khi
hết ngân sách — mỗi bước đều tự nó có giá trị:

1. **Concurrent claim — cùng một job** (TEST A) — khoá bản vá P0-1A
2. **Affiliate end-to-end** (TEST C) — khoá cụm P0-2
3. **Account/platform mutex** (TEST B) — khoá P0-1B; được phép `xfail` nếu chưa vá
4. **Recover stale job** — job đang chạy không bị cướp; ngưỡng > deadline (P0-1C)
5. **Daily limit dưới đồng thời** — sai lệch không vượt số worker
6. **`mark_done` → tự tạo COMMENT job** — gồm cả trường hợp không có `post_url`
7. **Circuit breaker account** — 3 FATAL → `is_active=False`; VALIDATION/COMPLIANCE **không** tính
8. **Vòng đời media dùng chung** — job platform A xong không được xoá file mà job platform B còn cần

Các test grep-source hiện có **không xoá vội**: giữ nguyên cho tới khi test hành vi
tương ứng xanh, rồi mới bỏ để tránh mất vùng phủ trong lúc chuyển tiếp.

---

## 20. Observability

| Hạng mục | Trạng thái |
|---|---|
| Structured log | ⚠️ Một phần — `runtime_events.emit()` ghi JSON dưới prefix `[RT:event]`, nhưng log chính là text thuần `[LEVEL] name: message` |
| Request ID / Correlation ID | ❌ Không có. Truy vết chỉ theo `job_id` (có `JobLoggerAdapter` gắn `[Job-N]` — hữu ích) |
| Metrics | ⚠️ Đếm trong bộ nhớ (`_selector_stats`), mất khi restart. Không Prometheus |
| Tracing | ⚠️ `job_tracer.start_job_trace/finish_job_trace` — trace theo node trong một job, không phải distributed tracing |
| **Audit log nghiệp vụ** | ✅ `audit_logs` + `runtime_settings_audit` (ai đổi setting nào, khi nào) |
| **Incident** | ✅ Điểm mạnh — `incident_logs` + `incident_groups`, normalize + signature + severity + mask secret + ack từ UI |
| Health / readiness | ✅ `/health`, `/health/json`, `/health/ui` (miễn auth). ❌ Không dùng làm cổng gác sau deploy |
| Slow query log | ❌ Không có |
| Alert | ⚠️ Telegram, có cooldown (`maybe_alert_queue_and_resources`), nhưng một kênh duy nhất và lỗi gửi bị nuốt |
| Dashboard vận hành | ✅ Tốt — syspanel + health + queue panel + log viewer có tô màu |

Phân biệt ba tầng đã rõ ràng: **business audit** (`audit_logs`) / **application
logging** (`app.log`, incident) / **infrastructure** (`SystemMonitorService`: RAM,
số tiến trình Chrome). Đây là điểm chín hơn mặt bằng chung.

---

## 21. Performance

Không micro-optimize. Chỉ nêu vấn đề mức kiến trúc:

| Vấn đề | Mức | Chi tiết |
|---|---|---|
| **NullPool** | **Observed** | `core.py:7` — mỗi request/tick mở kết nối Postgres mới. Với HTMX poll 5–60s trên ~10 fragment + 10 worker poll 20s ⇒ hàng nghìn lần bắt tay TCP+TLS mỗi giờ. Chọn NullPool có lý do (nhiều tiến trình, tránh kết nối treo) nhưng **web process** thì nên có pool nhỏ |
| **HTMX polling** | **Observed** | 11 fragment tự làm mới; 1 cái mỗi 5s. Không dùng SSE/WebSocket dù đã có `websockets` trong deps |
| **`_dir_file_stats` quét `rglob("*")`** | **Likely** | `service.py:170` — duyệt toàn bộ cây thư mục media để hiển thị dung lượng, không cache. Khi `storage/media` lớn dần, trang syspanel sẽ chậm tuyến tính |
| **`get_overview_data` không giới hạn** | **Potential** | `db.query(Account).all()` |
| **`sha256_file` đọc toàn bộ file video** | **Observed** | Chấp nhận được (chunk 1MB), nhưng chạy đồng bộ trong request tạo job — upload video 500MB sẽ chặn worker uvicorn vài giây |
| **N+1** | **Không phát hiện** | `dashboard_service` dùng `selectinload`; các truy vấn nóng đều group-by/aggregate ở SQL |
| **Thiếu index** | **Không phát hiện** | 18 index trên `jobs`, khớp pattern truy vấn |
| **Hàng đợi không giới hạn** | **Potential** | Không có cap số job PENDING; `MAINT_SKIP_HEAVY_WHEN_PENDING` chỉ giảm tải maintenance |

---

## 22. Deployment & Operations

Xem P1-1 (§10). Trả lời ba câu hỏi bắt buộc:

**Deploy lỗi thì rollback thế nào?**
Không có quy trình. Deploy là `git reset --hard origin/<branch>` + `bash start.sh`.
Rollback = `git reset --hard <sha cũ>` thủ công trên VPS, nhưng **migration không
được downgrade** → code cũ chạy trên schema mới. Không có tag release, không có
thư mục release trước đó, không có health gate.

**Migration lỗi thì sao?**
`|| true` nuốt lỗi, deploy tiếp, worker restart trên schema cũ, job fail hàng loạt.
Và một migration (`4215e86b6614`) có `downgrade()` rỗng nên không lùi được.

**Mất DB thì restore thế nào?**

Phải phân biệt ba mệnh đề khác nhau — audit này chỉ chứng minh được hai mệnh đề đầu:

| Mệnh đề | Trạng thái |
|---|---|
| Không tìm thấy backup PostgreSQL nào trong repo hoặc pipeline | ✅ **CONFIRMED** — `deploy.yml` chỉ `cp` file SQLite; không cron, không scheduler, không script |
| Không có quy trình restore nào được định nghĩa và kiểm chứng | ✅ **CONFIRMED** — không tài liệu runbook restore, không dấu vết đã thử restore |
| Không thể phục hồi trong mọi trường hợp | ❌ **KHÔNG kết luận được** — snapshot của nhà cung cấp VPS, backup volume Docker hay bản sao thủ công của Owner nằm **ngoài phạm vi audit này** |

**Phát biểu đúng:** *Không có PostgreSQL recovery path nào được định nghĩa và kiểm
chứng trong phạm vi hệ thống đang audit.* Có thể tồn tại đường phục hồi ở tầng hạ
tầng mà repo không biết — nhưng một đường phục hồi không được viết ra và chưa từng
thử thì không được tính là backup.

**Bẫy cần biết ngay:** `manage.py db backup` (`manage.py:141`) **không** backup
PostgreSQL. Nó `shutil.copy2(DB_PATH)` — tức file **SQLite** legacy. Một người vận
hành chạy lệnh này rồi tin rằng đã sao lưu production sẽ nhầm hoàn toàn. Đường
`pg_dump` duy nhất đang chạy được là nút bấm trong syspanel
(`system_panel/service.py:654`), không lịch, chưa kiểm chứng restore lần nào.

**Khác:**
- `main` và `develop` deploy vào **cùng một đường dẫn VPS**.
- `.env` bị `sed -i` sửa trong lúc deploy (chèn `STORAGE_LAYOUT_MODE`) — deploy
  script sửa file cấu hình production.
- Zero-downtime: không. `bash start.sh` restart tất cả.
- Cron: không có crontab; mọi việc định kỳ nằm trong vòng lặp `Maintenance` — nên
  Maintenance chết = mất self-heal, mất cleanup, mất insight (xem §18).

---

## 23. Developer Experience

**Tốt:**
- `manage.py` (typer): `db upgrade/downgrade/history/current/stamp/revision/backup`,
  `worker status/restart`, `viral scan/process/clean`, `serve`, `stack`.
- `docs/` 26 file có đánh số theo chủ đề + `TREE.md` + `CONFIG.md`.
- `README.md` có lệnh chạy cho cả Windows và Linux, kèm cảnh báo Python 3.14.
- `scripts/seed.py`, `seed_fb_compliance_keywords.py` — có seed data.
- Kỷ luật agent (`CLAUDE.md`, `ANTIGRAVITY.md`, `WORKFLOW.md`, `RULES.md`,
  `agents/handoffs/current-status.md`) rất mạnh.

**Yếu:**
- **Environment parity vỡ:** local Python 3.14, CI 3.10, VPS khuyến nghị 3.12.
  README tự thừa nhận `pip install -r requirements.txt` có thể fail trên Windows.
- **venv không khớp `requirements.txt`:** `import-linter` được khai báo nhưng không
  cài → kiểm tra kiến trúc không chạy được kể cả khi muốn.
- Không có `conftest.py`, không lệnh dựng DB test.
- Không lint/format tự động trong CI (Codacy có config nhưng không nằm trong
  workflow).
- Không có `Makefile`/`tasks.py` cho lệnh hay dùng.

**Một dev mới cần bao lâu?** Đọc hiểu: khoảng **1–2 ngày** nhờ docs + ADR (nhanh
hơn mặt bằng cho 54k dòng). Chạy được đủ stack: **vài ngày**, vướng ở Playwright +
Chrome profile + Postgres + PM2 + biến môi trường.

---

## 24. God Objects / Hotspots

| Đối tượng | Dòng | Trách nhiệm trộn lẫn | Fan-in/out |
|---|---:|---|---|
| **`FacebookAdapter`** | **3029** | phiên browser + phân giải selector + xác minh danh tính Page + chuyển profile/Page + đăng Reels + đăng feed + đăng story + comment + đính ảnh comment + parse URL + duyệt payload GraphQL + chụp artifact lỗi ⇒ **~12 trách nhiệm** | Fan-in cao |
| **`JobService`** | **1352** | state machine + validate media + upload file + affiliate + phân trang UI + humanize text tiếng Việt cho template + tracking + retry | **Fan-in cao nhất hệ** |
| **`app/core/settings.py`** | 1272 | định nghĩa setting + đọc/ghi DB + áp vào `config` module toàn cục + audit | Fan-in cao |
| **`config_service.py`** | 1041 | scaffolding no-code (phần lớn **chết**, ADR-009) + tmux + config platform | — |
| **`system_panel/service.py`** | 1051 | PM2 + git + backup DB + log viewer + screenshot + VNC + persona AI + 9router tuner | **Fan-out cao nhất hệ** |
| **`maintenance.run_loop()`** | ~120 | 12 việc không liên quan trong một vòng lặp tuần tự | Xem §18 |
| **`platform_config.html`** | **1777** | template của tầng no-code 0 row | — |
| **`insights.html`** | 1813 | — | — |
| **Bảng `jobs`** | 40 cột | publish + metrics + affiliate + comment + khoá | God table |

`FacebookAdapter` là hotspot số 1: diff chưa commit của phiên trước sửa **+405 dòng**
chỉ riêng file này. Đó là file được sửa nhiều nhất và cũng rủi ro nhất.

---

## 25. Change Amplification

### CA-1 — Thêm một `job_type` mới: **13 file production**

Đo trực tiếp từ diff PLAN-054 (thêm `STORY`):

| File | Vì sao phải sửa |
|---|---|
| `app/constants.py` | thêm enum |
| `app/core/queue/job.py` | `assert_story_media`, `NON_REELS_JOB_TYPES`, `COMMENTABLE_JOB_TYPES`, hàm tạo job |
| `app/core/queue/queue.py` | comment due-check |
| `app/core/database/models/jobs.py` | cột mới |
| `alembic/versions/...` | migration |
| `app/adapters/dispatcher.py` | nhánh `if job_type == JobType.STORY` |
| `app/features/facebook/adapter.py` | `publish_story()` |
| `app/features/facebook/pages/story_composer.py` | page object mới |
| `app/features/instagram/adapter.py` | ký tự ký cho khớp |
| `app/features/tiktok/adapter.py` | ký tự ký cho khớp |
| `app/adapters/generic/adapter.py` | ký tự ký cho khớp |
| `app/features/facebook/manual_job_router.py` | route |
| `app/templates/fragments/manual_job_form.html` | UI + JS `accept` |

Từ khoá `job_type` xuất hiện ở **19 file**.

**Rủi ro bỏ sót:** cao và **đã xảy ra thật** — PLAN-052 phát hiện `claim_next_job`
liệt kê cứng `POST`/`COMMENT` nên **mọi job FEED nằm PENDING vĩnh viễn**. Bài feed
của PLAN-049 chỉ chạy được vì gọi adapter trực tiếp, không qua hàng đợi. Một chỗ bị
sót đã làm cả một tính năng bán tiền im lặng không hoạt động.

**Nguyên nhân gốc:** không có *port* cho job type. Nếu `AdapterInterface` khai báo
`supports(job_type)` + `execute(job_type, job)`, dispatcher sẽ không cần nhánh `if`
và adapter thiếu method sẽ hỏng lúc import chứ không phải lúc chạy.

### CA-2 — Đổi danh sách đuôi file: **4 nơi** (§12) — đã drift `.webp`

### CA-3 — Thêm một platform mới: **~8 file** + 1 adapter viết tay
`_DEDICATED_ADAPTERS`, `Platform` enum, `_PLATFORM_ALIASES`, adapter, router, sidebar
template, `bootstrap_hooks`, `.importlinter`. Tầng no-code hứa "thêm platform không
cần code" nhưng cả 4 platform hiện có đều phải viết adapter tay (ADR-009).

---

## 26. Silent Failure Risks

Ưu tiên cao nhất: **hệ thống sai nhưng không báo đỏ.**

| # | Silent failure | Cơ chế | Phát hiện được không? |
|---|---|---|---|
| **SF-1a** | **Đăng trùng bài — hai worker cùng một job** | P0-1A double-claim | ❌ Không log, không alert. Cả hai job đều `DONE`. Chỉ phát hiện khi nhìn Page bằng mắt |
| **SF-1b** | **Hai job cùng account chạy song song** | P0-1B mutex không có ràng buộc DB | ❌ Không log. Hai phiên Chrome cùng profile |
| **SF-1c** | **Recovery cướp job đang chạy** | P0-1C ngưỡng 120 s < deadline 900 s | ⚠️ Có log `WARN` "Recovered stale RUNNING job" + alert Telegram — nhưng **đọc như self-heal thành công**, không ai biết worker gốc vẫn đang chạy |
| **SF-2** | **Job platform B chết vì platform A xoá mất file** | `publisher.py finally` xoá **cả file gốc** khi job DONE (`os.remove(m_path)`). Partial unique index chỉ chặn trùng **trong cùng platform** ⇒ một file hợp lệ có job facebook + job threads. FB xong trước → xoá file → job threads fail "media file not found" | ⚠️ Job FAILED có log, nhưng thông điệp lỗi trỏ sai nguyên nhân |
| **SF-3** | **Link affiliate chết + số click luôn 0** | P0-2 | ❌ Dashboard hiển thị "0 clicks" trông y hệt "chưa ai bấm" |
| **SF-4** | **Self-heal không chạy vì MetricsChecker gãy** | §18 all-or-nothing | ❌ Log chỉ có exception của MetricsChecker; không ai biết `recover_crashed_jobs` bị bỏ |
| **SF-5** | **Đổi setting không có tác dụng** | `PURGE_INTERVAL_SEC` / `DISCOVERY_INTERVAL_SEC` đọc lúc import | ❌ UI báo lưu thành công |
| **SF-6** | **`tracking_url` Vercel bị vứt** | Không commit sau khi gán | ❌ Hoàn toàn im lặng |
| **SF-7** | **Vi phạm kiến trúc trôi dần** | import-linter không chạy | ❌ 2 vi phạm đã sống mà không ai biết |
| **SF-8** | **UI nói `.webp` được, backend từ chối** | Multiple sources of truth | ⚠️ Người dùng thấy lỗi nhưng không hiểu vì sao |
| **SF-9** | **Hai phiên Chrome cùng một profile** | Idle engagement không claim nguyên tử (§14) | ❌ Hỏng profile biểu hiện muộn, dưới dạng checkpoint account |
| **SF-10** | **CTA chèn sau khi kiểm compliance** | `_inject_cta` chạy trong dispatcher, `check_before_publish` chạy ở worker trước đó | ❌ Nội dung CTA không bao giờ được kiểm |
| **SF-11** | **Deploy trên schema cũ** | `alembic upgrade \|\| true` | ⚠️ Job fail hàng loạt, nhưng lý do bị chôn trong log |
| **SF-12** | **`accounts.last_post_ts` lệch với `MAX(finished_at)`** | Hai nguồn cho một sự thật | ❌ Ảnh hưởng cooldown, không ai kiểm chứng |
| **SF-13** | **`manage.py db backup` không backup Postgres** | Nó `copy2(DB_PATH)` = file SQLite legacy (`manage.py:141`) | ❌ Lệnh in ra `Backed up: ...` **thành công** — người vận hành tin là đã sao lưu production |

---

## 27. Technical Debt Register

| ID | Debt | Evidence | Impact | Prob. | Sev | Effort | Recommendation |
|---|---|---|---|---|---|---|---|
| TD-01a | **Bất biến A** — job exclusivity vỡ | `queue.py:35-83` + `EXPLAIN` (qual ngoài chỉ `id`) | Đăng trùng → risk khoá Page | Cao | **P0** | **XS** | Thêm `AND status='PENDING'` vào WHERE ngoài. Đã xác nhận bằng `EXPLAIN` là đủ cho A. **Không đủ cho B hay C** |
| TD-01b | **Bất biến B** — account/platform mutex không có ràng buộc DB | `queue.py:66-72` anti-join trong InitPlan; hoà khoá sort do `job.py:908` | Hai Chrome cùng profile → checkpoint | Trung bình (**PLAUSIBLE**) | **P0** | S | Partial unique index `(account_id, platform) WHERE status='RUNNING'` **+** bắt `IntegrityError` trong `claim_next_job` trả `None` |
| TD-01c | **Bất biến C** — nghịch đảo ngưỡng recovery | `config.py:106` (120 s) vs `config.py:285` (900 s) | Recovery cướp job khoẻ → double-publish | Trung bình | **P0** | **XS** | `WORKER_CRASH_THRESHOLD_SECONDS` > `PUBLISHER_PUBLISH_DEADLINE_SEC` + biên (≥1200 s); thêm CAS ownership trước `mark_done` |
| TD-02 | Link affiliate là path tương đối + `/r/` sau auth | `job.py:1057,1211`; `main.py:110` | Tính năng đang bán không chạy | **Chắc chắn** | **P0** | S | Bắt buộc có base URL tuyệt đối; đưa `/r/` vào `public_prefixes` |
| TD-03 | Deploy nuốt lỗi migration | `deploy.yml:112` | Chạy production trên schema sai | Trung bình | **P1** | XS | Bỏ `\|\| true`, fail deploy |
| TD-04 | Không backup Postgres tự động | `deploy.yml:94` chỉ cp SQLite | Mất toàn bộ dữ liệu | Thấp/Chí mạng | **P1** | S | `pg_dump` theo lịch + kiểm chứng restore |
| TD-05 | CI đỏ 3 tuần | `python-version: "3.10"` vs numpy 2.4.2 | Không có cổng gác nào | **Chắc chắn** | **P1** | XS | Bump 3.12 |
| TD-06 | import-linter không cài, không chạy | `pip list`; `deploy.yml` | 2 vi phạm đang sống | **Chắc chắn** | **P1** | XS | Cài + thêm bước CI |
| TD-07 | ~49% test là grep source | 13 file `read_text()` | Test xanh giả | **Chắc chắn** | **P1** | M | Chuyển dần sang test hành vi; ưu tiên concurrency + link aff |
| TD-08 | Xoá file gốc phá job platform khác | `publisher.py finally` | Job platform 2 fail bí ẩn | Trung bình | **P1** | S | Chỉ xoá khi không còn job sống nào tham chiếu `content_hash` |
| TD-09 | Maintenance loop all-or-nothing | `maintenance.py:490-545` | Self-heal chết theo scraper | Trung bình | **P1** | S | Bọc try/except từng bước |
| TD-10 | Tầng no-code chết ~4.3k dòng | ADR-009 + 4 bảng 0 row | Đọc nhầm, bảo trì thừa | — | **P2** | M | Owner chốt ADR-009 rồi xoá |
| TD-11 | `FacebookAdapter` 3029 dòng | file | Hotspot sửa nhiều nhất | Cao | **P2** | L | Tách page object theo luồng (đã bắt đầu với `feed_composer`, `story_composer`) |
| TD-12 | Không CHECK constraint / default DB | `pg_constraint` | Trạng thái rác lọt vào DB | Thấp | **P2** | S | Thêm CHECK cho `status`, `job_type`, `platform` |
| TD-13 | `parent_job_id` không FK | `models/jobs.py:73` | Bản ghi mồ côi | Thấp | **P2** | XS | Thêm FK `ondelete=SET NULL` |
| TD-14 | Đuôi file có 4 nguồn, `.webp` đã drift | `job.py:131` vs `manual_job_form.html:140` | Người dùng bị chặn oan | **Đang xảy ra** | **P2** | S | Đẩy hằng số ra template qua context |
| TD-15 | Setting đọc lúc import | `maintenance.py:221,247` | Đổi setting vô tác dụng | Trung bình | **P2** | XS | Đọc trong vòng lặp |
| TD-16 | JSON trong cột `String` | 6 cột `Account` | Không query/validate được | Thấp | **P2** | M | Chuyển JSONB |
| TD-17 | Idle engagement claim không nguyên tử | `publisher.py:648-690` | Hai Chrome cùng profile | Trung bình | **P2** | S | `UPDATE ... WHERE login_status='ACTIVE' RETURNING` |
| TD-18 | `serve_screenshot` đọc mọi file trong repo | `service.py:576` | Đọc `.env` → `SECRET_KEY` cho phép **tự ký cookie admin** ⇒ phiên bị chiếm biến thành quyền truy cập bền vững + lộ credential dịch vụ ngoài | Thấp (cần phiên admin) | **P1** *(nâng từ P2)* | XS | Giới hạn về `logs/` + `storage/` và whitelist đuôi ảnh |
| TD-19 | Compliance chỉ ở FB worker; CTA chèn sau kiểm | `publisher.py:163` vs `dispatcher.py:295` | Nội dung không kiểm được đăng | Thấp | **P2** | S | Chuyển kiểm tra xuống ngay trước khi gõ text |
| TD-20 | 2 partial index không có trong model | `models/jobs.py` vs `pg_indexes` | Dựng DB từ model mất invariant | Thấp | **P3** | XS | Khai báo trong `__table_args__` |
| TD-21 | `4215e86b6614` downgrade rỗng | migration | Không rollback được | Thấp | **P3** | XS | Viết downgrade |
| TD-22 | NullPool cho web process | `core.py:7` | Lãng phí kết nối | Thấp | **P3** | S | Pool nhỏ cho web, giữ NullPool cho worker |
| TD-23 | `manage.py db backup` backup nhầm SQLite, không phải Postgres | `manage.py:141` | Người vận hành tin nhầm là đã sao lưu production | **Chắc chắn** | **P1** | XS | Trỏ sang `pg_dump`, hoặc fail rõ ràng khi `DATABASE_URL` là Postgres |
| TD-24 | `claim_next_verify_job` read-then-act, không nguyên tử | `threads/workers/verifier.py:259,213` | Double-claim job VERIFY_THREADS | Thấp — **worker chưa được supervisor nào khởi động** | **P2** | S | Vá **trước khi** bật worker; dùng cùng mẫu `UPDATE ... RETURNING` |

---

## 28. Risk Register

| Risk | Trigger | Consequence | Likelihood | Impact | Detection | Mitigation |
|---|---|---|---|---|---|---|
| **R1 — Account/Page bị Facebook hạn chế** | **Ba đường độc lập:** TD-01a (hai worker / một job), TD-01b (hai job / một account), TD-01c (recovery cướp job); cộng TD-17 (hai Chrome cùng profile lúc idle engagement) | Mất account khách trả tiền; mất uy tín | **Trung bình–Cao** | **Chí mạng** | ❌ Không có | Vá **cả ba** TD-01a/b/c — vá một đường không đóng hai đường kia; vá TD-17; thêm alert khi 2 job DONE cùng account trong <60 s |
| **R2 — Mất toàn bộ dữ liệu** | Đĩa VPS hỏng / container xoá | Không phục hồi được | Thấp | **Chí mạng** | ❌ Không có | TD-04 |
| **R3 — Giao khách tính năng không chạy** | Bán combo có "link aff đếm click" / "giỏ hàng" / "tìm video theo từ khoá" | Hoàn tiền, mất uy tín | **Cao** | Cao | ⚠️ `current-status.md` đã tự liệt kê cảnh báo | Vá TD-02; hoàn thành TASK-055; **gỡ mục chưa kiểm chứng khỏi mô tả combo trước khi bán tiếp** |
| **R4 — Facebook đổi DOM** | Meta cập nhật giao diện | Toàn bộ publish gãy | **Cao** (chắc chắn xảy ra) | Cao | ✅ Job FAILED + incident | Giữ `platform_selectors` (vá selector không cần deploy) — **đây là lý do ADR-009 đề xuất GIỮ phần selector** |
| **R5 — Deploy hỏng production** | Migration fail bị nuốt | Job fail hàng loạt, khó chẩn đoán | Trung bình | Cao | ⚠️ Muộn | TD-03 + health gate |
| **R6 — Cookie đã rò bị dùng** | Object git mồ côi còn public | Chiếm quyền FB/IG/TikTok | Trung bình | **Chí mạng** | ❌ | **Đổi mật khẩu + đăng xuất mọi phiên** (việc bắt buộc còn lại) |
| **R7 — Nợ kiến trúc trôi** | Không có cổng gác | Chi phí sửa tăng dần | **Cao** | Trung bình | ❌ | TD-06 |
| **R8 — Sót một nơi khi thêm job type** | CA-1 | Tính năng im lặng không chạy (**đã xảy ra với FEED**) | **Cao** | Cao | ❌ | Đưa job type vào port của adapter |
| **R9 — Self-heal chết ngầm** | MetricsChecker gãy khi DOM đổi | Job kẹt RUNNING vĩnh viễn | Trung bình | Trung bình | ❌ | TD-09 |
| **R10 — Đĩa VPS đầy** | Upload không giới hạn + media tích tụ | Toàn hệ dừng | Thấp | Cao | ✅ `SystemMonitorService` cảnh báo | Giới hạn dung lượng upload |

---

## 29. KEEP / IMPROVE / REMOVE

### KEEP — không được phá
1. Partial unique index chống đăng trùng media (bảo vệ invariant ở tầng DB).
2. `Dispatcher` với `finally: close_session()`.
3. Suicide timer + heartbeat + `recover_crashed_jobs` có cap `tries`.
4. `IncidentLogger` (normalize + signature + mask secret).
5. `sql_validator` dùng AST + deny-by-default.
6. Phân loại `error_type=VALIDATION/COMPLIANCE` không tính vào circuit breaker.
7. Kiến trúc feature-based của ADR-007 và kỷ luật ADR/PLAN/TASK/handoff.
8. `platform_selectors` + `WorkflowRegistry.get_selectors()` — vá selector không cần deploy (đúng như ADR-009 đề xuất giữ).
9. Hàng đợi bằng Postgres. **Không** thay bằng Redis/Kafka.
10. HTMX + Jinja2. **Không** thay bằng SPA.

### IMPROVE
1. Claim job nguyên tử thật — **cả ba** bất biến (TD-01a job / TD-01b account+platform / TD-01c ngưỡng recovery).
2. Link affiliate end-to-end (TD-02).
3. Cổng gác deploy: migration fail = deploy fail; backup Postgres; health gate (TD-03/04).
4. Bật lại CI + chạy import-linter (TD-05/06).
5. Chuyển test từ grep-source sang test hành vi, ưu tiên concurrency (TD-07).
6. Hoàn thiện *port* cho `job_type` để dập CA-1 (TD-11 kèm theo).
7. Bọc từng bước maintenance để self-heal không chết theo (TD-09).
8. Một nguồn sự thật cho đuôi file media (TD-14).

### REMOVE / AVOID
1. `GenericAdapter` + `ActionExecutor` + `workflow_definitions` + scaffolding no-code của `config_service` — **sau khi Owner chốt ADR-009**.
2. `platform_config.html` (1777 dòng) phần thuộc tầng đã khai tử.
3. Test kiểu `assert "<chuỗi>" in source` — không viết thêm; thay dần cái đang có.
4. Mẫu `|| true` cho lệnh làm thay đổi trạng thái.
5. Đọc setting ở module level.
6. Sao chép hằng số nghiệp vụ vào template/JS.

---

## 30. Target Architecture

**Kiến trúc hiện tại phù hợp. Không đổi. Chỉ siết 3 ranh giới.**

Đây là hệ solo-operator, 1 account, 14 job, mục tiêu bán dịch vụ cho vài chục
khách. Microservices, Kafka, CQRS, event sourcing đều **NOT NOW** — chúng thêm chi
phí vận hành mà không giải quyết bất kỳ vấn đề nào trong báo cáo này.

### Ranh giới cần siết #1 — Port cho job type

```
HIỆN TẠI                              MỤC TIÊU
                                      
Dispatcher                            Dispatcher
  if job_type == COMMENT: ...           adapter.execute(job)   ← một đường
  if job_type == FEED:                        │
     if not hasattr(a,'publish_feed')         ▼
  if job_type == STORY:                 AdapterInterface (ABC)
     if not hasattr(a,'publish_story')    + supports(job_type) -> bool
  else: adapter.publish(job)             + execute(job) -> PublishResult
                                                │
     ↓ thiếu method = lỗi lúc CHẠY       ↓ thiếu method = lỗi lúc IMPORT
```
**Giá trị:** thêm job type sửa 2 file thay vì 13. Trình thông dịch bắt lỗi thay cho
người review. Dập trực tiếp R8 — rủi ro đã hiện thực hoá một lần với FEED.

### Ranh giới cần siết #2 — Nguyên tử ở tầng DB

Mọi thao tác "chọn rồi chiếm" phải là một câu SQL có điều kiện trạng thái trong
`WHERE` ngoài: claim job (TD-01a), claim account engagement (TD-17), claim VERIFY_THREADS
(TD-24), daily limit. Riêng bất biến account/platform (TD-01b) **không** giải được bằng
outer predicate — nó cần một ràng buộc DB (partial unique index), xem §32 SR-1.
**Giá trị:** dập R1 — rủi ro chí mạng duy nhất về mặt sản phẩm.

### Ranh giới cần siết #3 — Cổng gác tự động

`pytest` (đã xanh) + `lint-imports` + `alembic upgrade` không được nuốt lỗi +
`pg_dump` trước deploy + health check sau restart.
**Giá trị:** những thứ báo cáo này tìm ra bằng tay sẽ được máy tìm ra từ lần sau.

---

## 31. Quick Wins

Effort thấp, giá trị cao, rủi ro hồi quy thấp:

| # | Việc | File | Effort |
|---|---|---|---|
| QW-1 | Thêm `AND status = 'PENDING'` vào `WHERE` ngoài của `claim_next_job` — **chỉ đóng bất biến A** | `queue.py:44` | 1 dòng |
| QW-1c | `WORKER_CRASH_THRESHOLD_SECONDS` 120 → ≥1200 (phải > `PUBLISHER_PUBLISH_DEADLINE_SEC`) — đóng P0-1C | `config.py:106` / `.env` | 1 dòng |
| QW-2 | Thêm `"/r/"` vào `public_prefixes` | `main.py:114` | 1 dòng |
| QW-3 | Bỏ `\|\| true` sau `db upgrade head` | `deploy.yml:112` | 1 dòng |
| QW-4 | `python-version: "3.10"` → `"3.12"` | `deploy.yml:23` | 1 dòng |
| QW-5 | `pip install import-linter && lint-imports` vào CI | `deploy.yml` | 2 dòng |
| QW-6 | Đọc `PURGE_INTERVAL_SEC`/`DISCOVERY_INTERVAL_SEC` trong vòng lặp | `maintenance.py:221,247` | 4 dòng |
| QW-7 | Sửa chữ `.webp` trong `manual_job_form.html` cho khớp backend | `manual_job_form.html:140,146` | 2 dòng |
| QW-8 | Thêm FK cho `parent_job_id` | model + migration | XS |
| QW-9 | Giới hạn `serve_screenshot` về `logs/`+`storage/` và đuôi ảnh | `service.py:576` | ~6 dòng |
| QW-10 | Khai báo 2 partial unique index trong `__table_args__` | `models/jobs.py` | ~6 dòng |

⚠️ **Không đọc bảng này thành "hai P0 vá bằng một dòng".**

- **QW-1 đóng đúng bất biến A.** Bất biến B (TD-01b) cần partial unique index +
  xử lý `IntegrityError` — **không** phải quick win, xem SR-1.
- **QW-1c đóng P0-1C** và cũng chỉ một dòng, nhưng là một *hằng số khác*, ở một
  *file khác*, cho một *lỗi khác*. Ba lỗi, ba chỗ.
- **QW-2 mới là một phần ba của P0-2.** Hai phần còn lại (URL tuyệt đối + commit
  `tracking_url`) không nằm trong bảng quick win.

Mọi mục ở trên **chỉ được coi là xong khi test hành vi tương ứng ở §19 chạy xanh**.
Test grep-source không tính.

---

## 32. Strategic Refactors

### SR-1 — Nguyên tử hoá mọi thao tác "chọn rồi chiếm"

- **Problem:** claim job (ba bất biến A/B/C), claim account engagement, daily limit,
  claim VERIFY_THREADS — tất cả đều read-then-act ở mức độ khác nhau.
- **Evidence:** `EXPLAIN` §10; `publisher.py:648-690`; `publisher_runtime.py:230`;
  `threads/workers/verifier.py:259,213`.

#### So sánh phương án cho claim job

| | Phương án | Bảo vệ A | Bảo vệ B | Bảo vệ C | Chi phí | Ghi chú |
|---|---|:---:|:---:|:---:|---|---|
| **A** | Outer predicate `AND status='PENDING'` | ✅ | ❌ | ❌ | 1 dòng | **Đã xác nhận bằng `EXPLAIN`**: qual ngoài đổi thành `(status='PENDING' AND id=$0)`, EvalPlanQual của kẻ thua fail → 0 row. Kẻ thua mất trắng một tick (ứng viên đã bị `Sort→Limit` chốt trước) |
| **B** | `FOR UPDATE OF j SKIP LOCKED` trong subquery | ✅ | ❌ | ❌ | ~1 dòng | **Đã xác nhận plan hợp lệ** trên chính câu SQL này: xuất hiện nút `LockRows` giữa `Sort` và `Limit`, tức kẻ thua **bỏ qua ứng viên bị khoá và lấy ứng viên kế tiếp** thay vì về tay không. Cải thiện thông lượng, **không** thay thế A |
| **C** | Partial unique index `(account_id, platform) WHERE status='RUNNING'` | — | ✅ | ❌ | 1 migration + xử lý `IntegrityError` | Cách **nhỏ nhất** ép được B ở tầng DB. Đúng mẫu dự án đã dùng tốt cho `content_hash`. Khả thi ngay (hiện 0 job RUNNING) |
| **D** | Sửa ngưỡng recovery > deadline | — | — | ✅ | 1 hằng số | Không liên quan tới SQL claim. Xem P0-1C |

**Khuyến nghị — nhỏ nhất mà vẫn đúng, KHÔNG overengineer:**

1. **Bắt buộc: A.** Outer predicate là tuyến phòng thủ cuối, rẻ, ngữ nghĩa rõ ràng,
   không phụ thuộc chi tiết tinh vi của EvalPlanQual trong subquery.
2. **Bắt buộc: D.** Một hằng số, đóng một lỗ mà A và C đều không chạm tới.
3. **Bắt buộc nếu chạy >1 publisher: C.** Đây là bất biến mà Owner thực sự quan tâm
   ("một account không được có hai Chrome"). Nếu tạm hoãn thì phải ghi rõ B **chưa
   đóng** và giữ TEST B ở `xfail` — không được im lặng.
4. **Tuỳ chọn: B (SKIP LOCKED).** Chỉ thêm khi thấy mất thông lượng thật. Không thêm
   như "cho chắc" — nó làm câu SQL khó đọc hơn mà không mua thêm tính đúng đắn.

**Không khuyến nghị:** advisory lock, account row lock, hay bảng lease riêng. Chúng
lớn hơn partial unique index và chỉ bảo vệ những đường code nhớ gọi chúng — trong khi
index bảo vệ **mọi** đường ghi, kể cả script sửa tay.

- **Business value:** loại bỏ nguy cơ khoá Page — rủi ro sản phẩm lớn nhất.
- **Technical value:** bất biến được DB bảo vệ, không phải bằng may mắn về thời điểm.
- **Risk:** thấp cho A/D; trung bình cho C (phải xử lý `IntegrityError`, nếu quên sẽ
  làm crash vòng lặp worker — `queue.py:96-100` hiện re-raise mọi lỗi không chứa chữ
  `"locked"`).
- **Scope:** ~40 dòng + 1 migration + TEST A/B.
- **Rollback:** revert commit; index có thể `DROP INDEX` độc lập.
- **Điều kiện đóng:** TEST A xanh **và** TEST B xanh (hoặc `xfail` có ghi lý do).

### SR-2 — Port cho job type
- **Problem:** CA-1 — thêm job type sửa 13 file; đã sót một lần (FEED kẹt vĩnh viễn).
- **Evidence:** `dispatcher.py:246,271` dùng `hasattr`; `contracts.py` thiếu 3 method.
- **Target:** `AdapterInterface.supports(job_type)` + `execute(job)`; dispatcher không còn nhánh `if`.
- **Business value:** ra tính năng mới nhanh và ít lỗi hơn.
- **Developer value:** thêm job type sửa 2 file thay vì 13.
- **Risk:** trung bình — chạm cả 4 adapter.
- **Dependencies:** nên làm **sau** khi ADR-009 chốt (để khỏi sửa `GenericAdapter` sắp bị xoá).
- **Scope:** ~200 dòng. **Rollback:** revert (thuần cấu trúc, không đụng DB).

### SR-3 — Cổng gác deploy + backup có kiểm chứng
- **Problem:** không cổng gác, không backup Postgres, không rollback plan.
- **Target:** CI (pytest + lint-imports + Postgres service) → `pg_dump` → `alembic upgrade` (fail = dừng) → restart → health check → rollback tự động nếu health đỏ.
- **Operational value:** trả lời được cả ba câu hỏi ở §22.
- **Risk:** thấp. **Scope:** chỉ file `deploy.yml` + một script backup.
- **Điều kiện:** phải **kiểm chứng restore một lần** — backup chưa restore thử thì không phải backup.

### SR-4 — Đổi trục test: hành vi thay vì văn bản
- **Problem:** ~120 test khoá chuỗi source; `test_claim_mutex_is_per_platform` xanh trong khi mutex vỡ.
- **Target:** `conftest.py` + fixture Postgres cô lập; ưu tiên: claim đồng thời, link aff end-to-end, circuit breaker, daily limit, `mark_done` → COMMENT job.
- **Technical value:** test bắt được lỗi thật thay vì cản trở refactor.
- **Risk:** thấp (chỉ thêm test). **Scope:** M, làm dần.

### SR-5 — Khai tử tầng no-code (chờ Owner chốt ADR-009)
- **Problem:** ~4.3k dòng + 4 bảng 0 row + template 1777 dòng, không thể chạm tới.
- **Giữ:** `platform_selectors` + `cta_templates` (có giá trị vận hành thật — vá selector không cần deploy).
- **Xoá:** `GenericAdapter`, `ActionExecutor`, `workflow_definitions`, routing `adapter_class`, scaffolding "tạo platform mới".
- **Value:** giảm ~20% bề mặt bảo trì `app/core` + `app/adapters`; xoá một lời hứa sai trong UI.
- **Risk:** thấp (chứng minh được là không reachable) — nhưng **cần quyết định của Owner trước**.

---

## 33. Prioritized Roadmap

Xếp theo `Business Impact × Risk Reduction × Change Frequency × Confidence ÷ Cost`.

### P0 — bắt buộc xong TRƯỚC khi mở rộng tải hoặc giao khách

Nhóm này là điều kiện để hệ thống được phép chạy nhiều hơn một job đồng thời cho
khách trả tiền. Ba mục đầu là **ba lỗi khác nhau**, không được gộp.

1. **TD-01a** — outer predicate `AND status='PENDING'` → **TEST A xanh**.
2. **TD-01c** — `WORKER_CRASH_THRESHOLD_SECONDS` ≥ 1200 (> deadline 900 s) → test
   recovery không cướp job đang chạy.
3. **TD-01b** — partial unique index `(account_id, platform) WHERE status='RUNNING'`
   \+ bắt `IntegrityError` → **TEST B xanh**. Nếu hoãn: ghi rõ B chưa đóng, giữ
   TEST B `xfail`, **và không chạy quá 1 publisher**.
4. **TD-02** — cụm affiliate (URL tuyệt đối + `/r/` public + commit) → **TEST C xanh**.
   Nếu chưa vá xong: **gỡ "link aff đếm click" khỏi mô tả combo trước khi bán tiếp**.
5. **R6** — Owner đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (nợ từ PLAN-051).

### P1 — an toàn production

6. **TD-03** bỏ `|| true` sau `alembic upgrade`; **TD-05** bump CI lên Python 3.12;
   **TD-06** cài + chạy `lint-imports` trong CI.
7. **TD-04 + TD-23** `pg_dump` theo lịch, **kiểm chứng restore một lần**, và sửa
   `manage.py db backup` đang backup nhầm SQLite.
8. **TD-18** siết `serve_screenshot` (đọc được `.env` → `SECRET_KEY` → tự ký cookie admin).
9. **TD-09** bọc try/except từng bước trong maintenance loop (self-heal đang chết theo scraper).
10. **TD-08** không xoá file gốc khi job platform khác còn tham chiếu.
11. **Verify live** 4 luồng chưa từng chạy thật (story, comment kèm ảnh, `post_url`
    bài feed, video >5 phút) — đúng `Next Action` trong `current-status.md`.
12. **TASK-055** khảo sát giỏ hàng; nếu Facebook không cho → gỡ khỏi mô tả combo (R3).
13. **TD-15, TD-14, TD-17** setting đọc lúc import; drift `.webp`; claim engagement.
14. Review + commit diff đang treo (16 file sửa + 6 file mới).

### P2 — kiến trúc & bảo trì (1–3 tháng)
1. **SR-4** conftest + fixture Postgres; chuyển test theo đúng thứ tự 8 bước ở §19.
2. **Owner chốt ADR-009** → **SR-5** xoá tầng no-code.
3. **SR-2** port cho job type (sau SR-5).
4. **SR-3** hoàn thiện pipeline deploy + health gate + rollback.
5. **TD-12, TD-13, TD-20** siết constraint DB.
6. **TD-17** nguyên tử hoá claim account engagement.
7. **TD-24** vá `claim_next_verify_job` — **trước khi** bật worker verifier (hiện chưa
   có supervisor nào khởi động nó).

### LATER (3–12 tháng)
1. Tách `FacebookAdapter` theo page object (tiếp tục hướng `feed_composer` / `story_composer` đã bắt đầu).
2. Tách `JobService`: state machine / validation / query cho UI.
3. Chuyển 6 cột JSON sang JSONB.
4. Pool kết nối riêng cho web process; cân nhắc SSE thay HTMX polling ở fragment 5s.
5. Alert đa kênh (không chỉ Telegram).

### NOT NOW — hấp dẫn nhưng chưa tạo giá trị
| Thứ | Vì sao chưa |
|---|---|
| Microservices | 1 người vận hành, 1 DB. Chỉ thêm chi phí |
| Kafka / RabbitMQ / Redis queue | Postgres đang tải 14 job. Hàng đợi không phải nút thắt |
| CQRS / Event sourcing | Không có vấn đề đọc-ghi nào biện minh được |
| Clean Architecture / DDD đầy đủ | Transaction script đang phù hợp với độ phức tạp nghiệp vụ |
| Repository pattern toàn hệ | Chi phí lớn, lợi ích chủ yếu là test — mà test nên sửa bằng SR-4 rẻ hơn |
| Frontend SPA | HTMX đang đúng cho use case này |
| Kubernetes / service mesh | Một VPS |

---

## 34. Top 10 Findings

| # | Finding | Loại | Sev | Confidence |
|---|---|---|---|---|
| 1 | **Hàng đợi vi phạm ba bất biến đồng thời độc lập, và không bản vá đơn lẻ nào đóng được cả ba.** (A) qual ngoài chỉ có `id = $0` → hai worker cùng nhận một job; (B) mutex account/platform chỉ là anti-join trong InitPlan, không có ràng buộc DB → hai worker nhận hai job cùng account mà **không hề va khoá**; (C) ngưỡng recovery 120 s < deadline job 900 s → recovery cướp job đang chạy. Hậu quả chung: đăng trùng bài, nguy cơ khoá Page | Correctness / Reliability | **P0** | A: **HIGH** (EXPLAIN) · B: **MEDIUM/PLAUSIBLE** · C: **HIGH** cơ chế |
| 2 | **Link affiliate đang bán cho khách không hoạt động** — **cụm ba lỗi ở ba tầng**: đăng chuỗi tương đối `/r/xxxx` lên Facebook; `/r/` nằm sau tường đăng nhập; `tracking_url` ghi rồi mất vì không commit. `click_count` vĩnh viễn 0. Chỉ đóng được bằng test end-to-end, không phải test từng hàm | Business correctness | **P0** | **HIGH** |
| 3 | **Deploy nuốt lỗi migration; không có recovery path PostgreSQL nào được định nghĩa và kiểm chứng trong phạm vi repo** — `alembic upgrade \|\| true`; pipeline chỉ `cp` file SQLite legacy; `pg_dump` chỉ là nút bấm tay; và `manage.py db backup` **backup nhầm SQLite** rồi báo thành công | Data / Ops | **P1** | **HIGH** (không kết luận "không thể phục hồi" — snapshot hạ tầng nằm ngoài phạm vi audit) |
| 4 | **~49% test chỉ grep source** — `test_claim_mutex_is_per_platform` xanh trong khi mutex thực sự vỡ (finding #1). Test khoá văn bản, không khoá hành vi | Testing | **P1** | **HIGH** |
| 5 | **CI đỏ 3 tuần + import-linter chưa bao giờ chạy** — 5 commit trên `main` chưa qua cổng nào; 2 vi phạm contract đang sống (`core.observability → features.facebook`, `insights → viral_intake`) | Process / Architecture | **P1** | **HIGH** |
| 6 | **Change amplification: thêm 1 job type = 13 file production** — đã sót thật một lần khiến **mọi job FEED nằm PENDING vĩnh viễn** (PLAN-052). Nguyên nhân: không có port cho job type, dispatcher dò `hasattr` | Changeability | **P1** | **HIGH** |
| 7 | **Job DONE xoá file gốc vô điều kiện** — partial unique index chỉ chặn trùng trong cùng platform, nên một file có thể có job facebook + job threads; bên xong trước xoá file, bên kia fail với lý do sai | Silent failure | **P1** | **HIGH** |
| 8 | **Maintenance loop all-or-nothing** — 12 việc không liên quan trong một `try`; một scraper Facebook gãy sẽ chặn cả `recover_crashed_jobs`, purge zombie và insights | Reliability | **P1** | **HIGH** |
| 9 | **Tầng "no-code" ~4.3k dòng + 4 bảng 0 row không thể chạm tới** — `dispatcher.py:88` luôn ghi đè Registry cho toàn bộ enum `Platform`. Xác nhận lại bằng row count live | Architecture debt | **P2** | **HIGH** |
| 10 | **Business rule "đuôi file được chấp nhận" có 4 nguồn và đã drift** — UI quảng cáo `.webp`, backend từ chối `.webp`. Test đồng bộ hiện có grep `accept=` nên không bắt được | Multiple sources of truth | **P2** | **HIGH** |

---

## 35. Final Verdict

**Kiến trúc hiện tại là gì?**
Modular Monolith theo feature + Job-Queue Pipeline trên PostgreSQL + Adapter Pattern
cho từng mạng xã hội, business logic viết theo Transaction Script. Không phải Clean
Architecture, không phải DDD, không phải microservices — và không cố giả vờ là.

**Có phù hợp không?**
**Có.** Với một người vận hành, một VPS, một DB, và bài toán mà độ phức tạp thật nằm
ở *DOM của Facebook* chứ không ở mô hình nghiệp vụ, đây là kiến trúc đúng. Bất kỳ
tầng trừu tượng nào thêm vào cũng sẽ trả chi phí mà không mua được gì.

**Có cần refactor lớn không?**
**Không.** Nhưng **không được đọc điều đó thành "vá bằng một dòng"**:

- **P0-1 là ba lỗi đồng thời độc lập** (A: job exclusivity — CONFIRMED; B:
  account/platform exclusivity — PLAUSIBLE, **không** được vá bởi bản vá của A;
  C: nghịch đảo ngưỡng recovery — CONFIRMED). Bản vá tối thiểu của A là một dòng,
  nhưng nó **chỉ đóng A**. B cần một partial unique index cộng xử lý `IntegrityError`;
  C cần sửa một hằng số ở file khác. Ai vá A rồi tuyên bố "đã hết race" là sai.
- **P0-2 là một cụm ba lỗi nhỏ** ở ba tầng (sinh URL / middleware auth / vòng đời
  transaction). Phạm vi sửa thấp, nhưng chỉ được coi là xong khi test end-to-end
  ở §19 (TEST C) chạy xanh với một client **không đăng nhập**.

Nợ kiến trúc lớn nhất (tầng no-code) là **xoá đi**, không phải viết lại. Refactor
chiến lược duy nhất đáng làm là port cho job type (SR-2), phạm vi ~200 dòng.

**Không bất biến nào ở trên được tuyên bố là đã đóng cho tới khi test hành vi tương
ứng chạy xanh trên PostgreSQL thật.** Test grep-source không tính — chính
`test_claim_mutex_is_per_platform` đang xanh trong khi mutex vỡ.

**Điểm nào tuyệt đối không được phá?**
1. Partial unique index chống đăng trùng media — invariant nghiệp vụ duy nhất được
   bảo vệ ở tầng DB, làm rất đúng.
2. `Dispatcher.finally: close_session()` + suicide timer — đây là thứ giữ cho VPS
   không chết vì rò browser.
3. `platform_selectors` + heuristic fallback — vũ khí duy nhất khi Facebook đổi DOM
   mà không phải deploy.
4. Hàng đợi bằng Postgres và giao diện HTMX. Không thay.

**Điểm nào xử lý đầu tiên?**
Theo đúng thứ tự, và **không gộp bước 1–3 thành một**:

1. **`claim_next_job` — bất biến A.** Thêm `AND status='PENDING'` vào WHERE ngoài
   \+ TEST A. Đã xác nhận bằng `EXPLAIN` là đủ cho A.
2. **Ngưỡng recovery — bất biến C.** `WORKER_CRASH_THRESHOLD_SECONDS` phải **lớn
   hơn** `PUBLISHER_PUBLISH_DEADLINE_SEC`. Hiện 120 s vs 900 s — recovery đang chạy
   đua với job khoẻ mạnh.
3. **Mutex account/platform — bất biến B.** Partial unique index + bắt
   `IntegrityError` + TEST B. Nếu hoãn: **chỉ chạy một publisher** và ghi rõ B chưa
   đóng.
4. **Cụm affiliate.** Vá cả ba mảnh + TEST C, hoặc gỡ khỏi mô tả combo. Không được
   để nguyên trạng: đang thu tiền cho một tính năng đăng chuỗi rác lên Facebook.
5. **Đổi mật khẩu + đăng xuất mọi phiên MXH** — việc bắt buộc còn lại từ PLAN-051,
   không phụ thuộc code, và vẫn chưa xong.

Một nhận xét cuối, không phải về code: hồ sơ ADR/PLAN/handoff của dự án này trung
thực hơn mặt bằng chung rất nhiều — `current-status.md` tự liệt kê những tính năng
"chưa được hứa với khách", ADR-009 tự gọi 4.3k dòng của chính mình là ảo tưởng. Kỷ
luật đó là tài sản. Thứ còn thiếu không phải sự trung thực, mà là **cổng gác tự động**
để máy móc phát hiện những gì con người đã phát hiện được ở đây.

---

*Phương pháp (rev.1): đọc entrypoint → dựng dependency graph bằng AST trên 282 file →
truy vết luồng nghiệp vụ trọng yếu (tạo job → claim → dispatch → publish → cleanup)
→ kiểm chứng bằng schema và row count trên PostgreSQL đang chạy → `EXPLAIN` câu SQL
trọng yếu → chạy test suite → đối chiếu ADR với code thực tế.*

*Phương pháp (rev.2 — final validation): `EXPLAIN` cả câu SQL gốc lẫn hai phương án
vá (outer predicate; `FOR UPDATE OF j SKIP LOCKED`) trên Postgres thật → truy vấn
live kiểm tra tính khả thi của partial unique index và tìm dấu vết đăng trùng trong
lịch sử job → đọc lại toàn bộ hằng số timing (heartbeat / crash threshold / publish
deadline / upload cap / maintenance tick) → truy mọi nơi ghi `status='RUNNING'` →
kiểm tra worker verifier có được supervisor nào khởi động không → xác minh
`manage.py db backup` backup cái gì. **Không sửa file nào ngoài báo cáo này.
Không ghi một dòng nào vào database.***
