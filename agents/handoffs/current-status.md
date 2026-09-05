# Current Status

## Phiên 2026-09-05 (b) — PLAN-057 xong; blocker cuối là SSH key

### Kết quả
- **CI test job XANH lần đầu kể từ 2026-07-29** (run `33937825138`, commit `9996f4c`).
- **PLAN-057 đóng cả 4 mục A/B/C/D.**
- Deploy vẫn chưa chạy được: `ssh: handshake failed: unable to authenticate`.
  Script deploy **chưa hề chạy** trên VPS. Secrets `VPS_HOST`/`VPS_USER`/`VPS_SSH_KEY`
  tồn tại nhưng đặt từ **2026-03-27**. Claude Code không có quyền truy cập VPS lẫn
  private key ⇒ **chỉ Owner xử được**.

### Vá lỗi attribution trên Linux (lỗi có sẵn từ PLAN-048)
`process_scan.py` `.resolve()` mọi `--user-data-dir`; trên POSIX `"C:/..."` là tương
đối nên bị rebase lên CWD = thư mục dự án ⇒ browser người khác bị nhận là của
ToolsAuto ⇒ orphan purge được phép kill. Vá bằng `is_absolute_elsewhere()` (thu hẹp,
không xoá `.resolve()` vì test đường-dẫn-tương-đối cần nó).

Proof nhân quả trong container Linux: code cũ **5 failed**, code mới **47 passed**;
Windows **244 passed**. Thêm test có nhánh theo nền tảng để Windows cũng bắt được.

### Quy trình mới
Lỗi lọt lưới 5 tuần vì máy dev Windows. Nay **chạy suite trong container Linux trước
khi push**, không đẩy lên rồi chờ CI đoán.

### Backup — xong trọn
PM2 `DB_Backup` cron `0 3 * * *`; `--keep 14` retention; `deploy.yml` dump Postgres
**ngay trước migration** (bước cũ chỉ `cp` file SQLite legacy — cùng lỗi nhầm đích).

### Next Action
1. **Owner: sửa SSH.** `ssh` tay vào VPS rồi cập nhật `VPS_SSH_KEY`. Đây là thứ duy
   nhất còn chặn lần deploy đầu tiên sau 5 tuần.
2. **Owner: duyệt ADR-011** để sang Việc 2 (P0-1 concurrency).
3. **Owner: đổi mật khẩu + đăng xuất phiên FB/IG/TikTok** — nợ từ PLAN-051, vẫn chưa làm.
4. Xoá `toolsauto_postgres_old_20260905` + volume `9a3acb1502…` sau vài ngày chạy ổn.
5. Verify live 4 luồng PLAN-053→056.

---

## Phiên 2026-09-05 — PLAN-057: hạ tầng tự phục hồi (Việc 1)

Owner giao "nâng cấp hệ thống để chạy trơn tru" → chia 3 việc, làm theo thứ tự.
**Việc 1 (hạ tầng) xong 3/4 mục.** Việc 2 (P0-1) chờ duyệt ADR-011.

### System State (2026-09-05)

- Postgres nay chạy bằng **`docker-compose.yml`**, `restart: unless-stopped`,
  healthcheck, **named volume `toolsauto_pgdata`**. `docker inspect` xác nhận
  `healthy | restart=unless-stopped`.
- Container cũ **còn nguyên làm đường lùi**: `toolsauto_postgres_old_20260905`
  (đã dừng) + anonymous volume `9a3acb1502…`. **Chưa xoá.**
- Alembic `i7d4e5f6a7b8 (head)`. 26 bảng / 440 row. jobs=14, accounts=1.
- Test local: **243 passed**. Test trên CI (Linux): **5 failed, 223 passed, 15 skipped**.
- Stack vẫn TẮT. 4 luồng live PLAN-053→056 vẫn chưa verify thật.

### Done This Session

| Mục | Việc | Proof |
|---|---|---|
| **B** | Gỡ `\|\| true` khỏi `db upgrade head` | `deploy.yml:113`; migration hỏng nay làm deploy đỏ |
| **C** | `docker-compose.yml` + `restart: unless-stopped` | Chuyển anonymous→named volume: 26 bảng/440 row, `diff` rỗng. `down`→`up -d`: healthy, jobs=14 còn nguyên |
| **D** | `manage.py db backup` dùng `pg_dump` thật | Dump 115.081 bytes; **restore thật vào DB tạm: 26 bảng/440 row, `diff` rỗng**; thất bại nay thoát khác 0 |
| A (một nửa) | Python 3.10→3.12 + `--ignore` file test hỏng | CI qua được **Install dependencies** — bước đã chết từ 2026-07-29 |

Commit: `a9a5267` (code), `2dada07` (proof + ADR-011).

### Sự cố tự chứng minh

Đầu phiên Postgres **lại tắt** — lần thứ **3** (10 ngày → 13 ngày → qua đêm).
Chính là thứ mục C sửa.

### ⚠️ CHẶN — CI vẫn đỏ vì lỗi CÓ SẴN, không phải lỗi hạ tầng

Run `33936616449`: 5 test **xanh trên Windows, đỏ trên Linux** — mà **VPS chạy Linux**.

`process_scan.py:553` thêm ứng viên `Path(user_data_dir).resolve()`. Trên POSIX,
`.resolve()` giải đường dẫn **tương đối theo CWD**, mà CWD là thư mục dự án ⇒ browser
của **người khác** bị nhận nhầm là của ToolsAuto ⇒ orphan purge PLAN-048 **được phép
kill nó**. Đúng bất biến mà chính test đó lập ra để bảo vệ.

Chứng minh trong container `python:3.12-slim` (không suy đoán):
`C:/Users/.../User Data` → `/repo/C:/Users/.../User Data` → `within(project_root)=True`.

Nằm im từ PLAN-048 vì CI chết ở bước cài dependency nên **chưa từng chạy test trên
Linux**; máy dev Windows nên `.resolve()` không relativize ⇒ test xanh, che mất lỗi.

**Đã DỪNG theo quy tắc escalation** — `process_scan.py` là core logic, ngoài vai trò
Claude Code. **Không tự sửa, không dán `--ignore` để CI xanh giả.**

### Chờ Owner quyết — 3 việc

1. **Lỗi `process_scan` trên Linux**: cho Claude Code vá, hay chuyển Antigravity ra
   PLAN? Hướng vá tối thiểu: chỉ `.resolve()` khi đường dẫn đã tuyệt đối, hoặc giải
   tương đối theo project root tường minh thay vì theo CWD.
2. **ADR-011** (đã soạn, trạng thái ĐỀ XUẤT): xin ngoại lệ vá P0-1 concurrency —
   `queue.py` outer predicate, `config.py` ngưỡng recovery, migration partial unique
   index, + TEST A/B/C.
3. **Đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok** — nợ từ PLAN-051, cookie phiên
   thật đã phơi public 3,5 tháng và **đến giờ vẫn chưa vô hiệu hoá**.

### Next Action

1. Owner quyết 3 việc trên.
2. Sau khi vá `process_scan` → CI phải **xanh trên run thật** thì mục A mới đóng,
   và đó cũng là lần deploy đầu tiên kể từ 2026-07-29.
3. Lên lịch backup định kỳ (hiện mới có lệnh chạy tay đã chứng minh đúng).
4. Xoá `toolsauto_postgres_old_20260905` + volume `9a3acb1502…` sau khi chạy ổn vài ngày.
5. Verify live 4 luồng PLAN-053→056 (cần Owner mở trình duyệt).

---

## Phiên 2026-09-04 — kiểm tra dự án + đưa diff treo lên main

### System State (2026-09-04)

- Python 3.14.7 + venv: chạy tốt. Test suite **243 passed / 12.1s**
  (`--ignore=tests/test_threads_world_news.py`).
- `toolsauto_postgres` **đã tắt 13 ngày**, phiên này `docker start` lại. Alembic
  `i7d4e5f6a7b8` khớp DB.
- DB thật: 1 account · jobs: 7 DRAFT, 2 PENDING (#2, #4 — facebook/POST,
  `is_approved=false`), 4 DONE, 1 FAILED. **0 RUNNING.**
- Stack vẫn **TẮT**. Bốn luồng live PLAN-053→056 vẫn **chưa từng verify thật**.
- Working tree **sạch**, `main` == `origin/main`.

### Done This Session

| Việc | Proof |
|---|---|
| Kiểm tra lại toàn bộ kết luận audit sau 14 ngày | Cả 4 lỗi P0 + toàn bộ P1 **vẫn nguyên**, chưa vá dòng nào |
| Commit + push diff treo 2 tuần lên `main` | 3 commit `8ee49f8`, `5e9537d`, `12176de`; `ea57b4b..12176de main -> main` |

Ba commit đã đẩy:
- `8ee49f8` feat — PLAN-052→056 (24 file, +1908/−68), gồm migration
  `i7d4e5f6a7b8` và `story_composer.py`
- `5e9537d` docs(agents) — 5 PLAN, 6 TASK, ADR-010, AUDIT-001, handoff
- `12176de` chore(lint) — cấu hình Codacy CLI, `.gitignore` chặn `generated/`

**Không tách được 5 commit theo từng PLAN**: `facebook/adapter.py` (+405 dòng) và
`core/queue/job.py` bị PLAN-053/054/055/056 sửa đan xen, tách hunk sẽ tạo commit
trung gian không chạy được test.

### Rủi ro đã đóng trong phiên này

**Lệch pha migration.** Trước phiên này DB đang ở `i7d4e5f6a7b8` nhưng revision đó
**không tồn tại trong git** — deploy `main` sẽ khiến `alembic upgrade head` gặp
revision lạ, mà `deploy.yml` có `|| true` nuốt lỗi ⇒ deploy vẫn báo xanh trong khi
migration hỏng. Commit `8ee49f8` đóng khoảng lệch này.

### Còn nguyên — KHÔNG có gì được vá trong phiên này

- **P0-1a** `queue.py` outer predicate vẫn thiếu `AND status='PENDING'`
- **P0-1b** không có partial unique index nào trong `alembic/versions/`
- **P0-1c** `WORKER_CRASH_THRESHOLD_SECONDS=120` < `PUBLISHER_PUBLISH_DEADLINE_SEC=900`
- **P0-2** `tracking_url` vẫn ghi `/r/{code}` tương đối; route vẫn sau tường auth
- P1: `deploy.yml:30` vẫn `python-version: "3.10"`; 2 vi phạm import-linter;
  `manage.py db backup` vẫn `copy2(DB_PATH)` (backup nhầm SQLite); drift `.webp`
- **243 test xanh KHÔNG chứng minh gì cho P0** — TEST A/B/C (§19 của AUDIT-001)
  chưa ai viết.

### CI vẫn đỏ — lần thứ 6

Run `33844459654` (2026-09-04) fail y hệt: workflow cài Python **3.10.21** trong khi
`requirements.txt` ghim numpy 2.4.2 (cần ≥3.11). Push phiên này **chưa deploy được**.

### Nhánh chưa xử

`origin/develop`: đi sau main **78 commit**, đi trước **4 commit** (mới nhất
2026-05-05, ~4 tháng): sidebar accordion, refactor sidebar SaaS, fix worker crash /
imports / playwright `/dev/shm`, fix backlog count đa nền tảng. **Chưa merge** — cần
Owner quyết vì 4 commit này nằm trên base đã cũ 78 commit, merge mù dễ kéo lùi UI.

### Next Action

1. Sửa `deploy.yml:30` → Python 3.12 để mở lại CI (1 dòng, chặn mọi deploy).
2. Vá P0-1a + P0-1c (hai thay đổi nhỏ, độc lập), viết TEST A.
3. P0-1b partial unique index + bắt `IntegrityError` → TEST B (hiện 0 RUNNING nên
   tạo index được ngay, không cần dọn dữ liệu).
4. P0-2 cụm affiliate → TEST C; nếu chưa xong thì **gỡ "link aff đếm click" khỏi mô
   tả combo trước khi bán tiếp**.
5. Owner: đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (nợ từ PLAN-051).
6. Owner mở phiên trình duyệt verify live 4 luồng PLAN-053→056.
7. Quyết số phận `origin/develop`.

---

## Phiên 2026-08-21 (b) — AUDIT toàn diện repo (AUDIT ONLY, không sửa code)

Báo cáo đầy đủ: `agents/audit/AUDIT-001-repo-wide-2026-08-21.md`

### Đã làm
- Kiểm toán toàn repo: dependency graph bằng AST (282 file), schema + row count trên
  Postgres đang chạy, `EXPLAIN` câu SQL claim, chạy test suite (243 passed), đối chiếu
  ADR với code thật. **Không sửa file nào ngoài báo cáo.**

### Đã qua vòng FINAL VALIDATION (rev.2) — kết luận đã được siết lại

Vòng validation tập trung concurrency/transaction/recovery/security. Thay đổi quan
trọng nhất: **P0-1 không phải một lỗi mà là BA lỗi độc lập**, và **không bản vá đơn
lẻ nào đóng được cả ba**. Bản rev.1 nói "hai P0 vá bằng một dòng" — điều đó **sai**
và đã được gỡ.

### P0-1 — ba bất biến đồng thời, ba bản vá khác nhau

| | Bất biến | Trạng thái | Bản vá tối thiểu |
|---|---|---|---|
| **A** | 1 job PENDING → đúng 1 worker | ❌ **CONFIRMED vỡ** | `AND status='PENDING'` ở WHERE ngoài (`queue.py:44`) |
| **B** | 1 `(account, platform)` → tối đa 1 job RUNNING | ❌ **PLAUSIBLE vỡ** (MEDIUM) | **Partial unique index** + bắt `IntegrityError`. Bản vá của A **không** chạm tới B |
| **C** | Job đang chạy không bị recovery cướp | ❌ **CONFIRMED (cơ chế)** | `WORKER_CRASH_THRESHOLD_SECONDS` (120 s) phải **>** `PUBLISHER_PUBLISH_DEADLINE_SEC` (900 s) |

**Evidence mới thu được trong vòng này (read-only, không ghi DB):**

- `EXPLAIN` bản vá A trên Postgres thật: qual ngoài đổi thành
  `Filter: (status='PENDING' AND id=$0)` → EvalPlanQual của worker thua fail → 0 row.
  **A được đóng. HIGH.**
- `EXPLAIN` phương án `FOR UPDATE OF j SKIP LOCKED`: **plan hợp lệ**, xuất hiện nút
  `LockRows` giữa `Sort` và `Limit` → worker thua lấy ứng viên kế tiếp thay vì về tay
  không. Là cải thiện thông lượng, **không thay thế** bản vá A.
- B: khi hai worker chọn **hai row khác nhau** thì **không có xung đột khoá**, nên
  EvalPlanQual không bao giờ chạy → outer predicate vô tác dụng. Điều kiện kích hoạt:
  khoá sắp xếp hoà — `lpp.last_ts` luôn hoà trong cùng account, và
  `create_high_priority_manual_job` (`job.py:908`) đặt `schedule_ts = now - 999999`
  cho mọi job thủ công → hai job tạo cùng giây hoà tuyệt đối.
  **Chưa chạy thí nghiệm 2 session ⇒ giữ ở PLAUSIBLE, không nâng lên CONFIRMED.**
- C: `120 s` (ngưỡng recovery) < `900 s` (deadline job) < `420 s` (trần chờ upload
  một video, PLAN-056). Hai nhịp heartbeat lỡ liên tiếp (60 s × 2) đủ để job khoẻ bị
  đặt về PENDING rồi bị worker khác claim. Cửa chặn `check_published_state` chỉ chạy
  khi `tries > 0` và **không phủ hết job type** (Instagram trả thẳng `ok=False`;
  Facebook chỉ quét Reels, không quét feed/story).
- Truy vấn live: hiện **0 job RUNNING**, không cặp `(account_id, platform)` nào >1
  RUNNING ⇒ partial unique index tạo được ngay, không cần dọn dữ liệu. Cũng **chưa
  thấy dấu vết đăng trùng** trong 14 job hiện có — nhưng đó là "chưa xảy ra", không
  phải "không thể xảy ra".

### P0-2 — là một CỤM ba lỗi, không phải một dòng

(a) URL tương đối khi thiếu base URL · (b) `/r/{code}` sau tường auth ·
(c) `tracking_url` ghi rồi mất vì không commit. Ba tầng khác nhau; sửa đúng hai trong
ba vẫn để lại tính năng hỏng. **Điều kiện đóng: test end-to-end với client KHÔNG đăng
nhập** (TEST C, §19 của report).

### Ba test bắt buộc (đặc tả đầy đủ ở §19 của report)

- **TEST A** — 1 job PENDING, 2 session claim đồng thời → đúng 1 nhận được.
- **TEST B** — 2 job khác nhau **cùng account+platform**, `schedule_ts` bằng nhau,
  2 session claim đồng thời → tối đa 1 RUNNING. ⚠️ **TEST B đỏ sau khi vá A là đúng
  như dự đoán**, không phải bản vá hỏng. Nếu hoãn index: giữ `xfail` có ghi lý do,
  **không xoá test, không tuyên bố B đã đóng, và chỉ chạy 1 publisher**.
- **TEST C** — affiliate end-to-end tới `click_count`.

### Phát hiện mới trong vòng validation

- **`manage.py db backup` backup nhầm SQLite**, không phải Postgres (`manage.py:141`
  `copy2(DB_PATH)`) — nhưng vẫn in `Backed up: ...` thành công. Bẫy vận hành thật.
- **TD-18 nâng P2 → P1:** `serve_screenshot` đọc được `.env` ⇒ lộ `SECRET_KEY`, mà
  `SECRET_KEY` chính là khoá **ký cookie phiên** (`auth/router.py:11`). Nghĩa là lỗ
  này biến một phiên bị chiếm có thời hạn thành **quyền truy cập bền vững**. Lập luận
  cũ "admin đã có SQL console nên vô hại" là sai — SQL console không đọc được file.
- **`claim_next_verify_job`** (`threads/workers/verifier.py:259` + `:213`) là
  read-then-act không nguyên tử. Giảm nhẹ: worker này **không được supervisor nào
  khởi động** (không có trong `ecosystem.config.js`/`start.sh`/`start.ps1`/
  `local_supervisor.py`). Phải vá **trước khi** bật.

### Wording đã siết lại (evidence > assumption)

- ~~"Mất DB thì không restore được"~~ → **"Không có PostgreSQL recovery path nào được
  định nghĩa và kiểm chứng trong phạm vi hệ thống đang audit."** Snapshot hạ tầng của
  nhà cung cấp VPS nằm ngoài phạm vi — "không tìm thấy" ≠ "không tồn tại".
- ~~CSRF "đủ trên thực tế"~~ → **"Chấp nhận được dưới threat model một-admin hiện
  tại"**, kèm 4 giả định và điều kiện phải review lại (thêm user, thêm JSON API,
  tách subdomain, đổi `SameSite`, hoặc thêm GET có side-effect).

### Next Action — thứ tự đã chốt lại sau validation

**P0 (trước khi mở rộng tải / giao khách):**
1. TD-01a outer predicate → TEST A xanh.
2. TD-01c ngưỡng recovery ≥1200 s (> deadline 900 s).
3. TD-01b partial unique index + bắt `IntegrityError` → TEST B xanh (hoặc `xfail` +
   chỉ chạy 1 publisher).
4. TD-02 cụm affiliate → TEST C xanh; nếu chưa xong → **gỡ "link aff đếm click" khỏi
   mô tả combo trước khi bán tiếp**.
5. Owner đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (nợ từ PLAN-051).

**P1 (an toàn production):** bỏ `|| true` ở deploy · bump CI 3.12 · `lint-imports` ·
`pg_dump` theo lịch + **thử restore một lần** · sửa TD-23 (`manage.py db backup`) ·
TD-18 siết `serve_screenshot` · TD-09 bọc try/except từng bước maintenance · TD-08
vòng đời media dùng chung · verify live 4 luồng PLAN-053→056 · TASK-055 · review +
commit diff đang treo.

**P2 (kiến trúc):** SR-4 conftest + chuyển test theo 8 bước ưu tiên · ADR-009 →
SR-5 xoá tầng no-code · SR-2 port cho job type · TD-24 vá verifier trước khi bật.

### Phát hiện P1 đáng chú ý
- `alembic upgrade head || true` trong `deploy.yml:112` nuốt lỗi migration; **không có
  backup PostgreSQL tự động** (pipeline chỉ `cp` file SQLite legacy; `pg_dump` là nút bấm tay).
- ~49% test (13 file) là `read_text()` + `assert "chuỗi" in src`. `test_claim_mutex_is_per_platform`
  đang XANH trong khi mutex thực sự vỡ vì race ở trên.
- `import-linter` khai báo trong requirements + có `.importlinter` nhưng **không cài trong venv
  và không có trong CI** ⇒ chưa từng chạy. Đang có 2 vi phạm thật:
  `app/core/observability/metrics_checker.py:162` → `app.features.facebook`;
  `app/features/insights/router.py:149` → `app.features.viral_intake`.
- Job DONE xoá **cả file gốc** vô điều kiện; partial unique index chỉ chặn trùng trong cùng
  platform ⇒ job facebook xong trước xoá file, job threads cùng file fail với lý do sai.
- `maintenance.run_loop()` all-or-nothing: 12 việc trong một `try`, một scraper gãy chặn luôn
  `recover_crashed_jobs` + purge zombie + insights.
- UI `manual_job_form.html:140,146` quảng cáo `.webp` nhưng `JobService.IMAGE_EXTENSIONS`
  không có `.webp` ⇒ drift thật, chặn oan người dùng.

### Xác nhận lại bằng dữ liệu runtime
- 4 bảng tầng no-code (`platform_configs`, `platform_selectors`, `cta_templates`,
  `workflow_definitions`) đều **0 row** — ADR-009 vẫn đúng, vẫn chờ Owner chốt.
- Alembic head `i7d4e5f6a7b8` khớp DB. 26 bảng, `accounts`=1 row, `jobs`=14 row.

### Next Action — thứ tự đề xuất
1. Vá P0-1 (`AND status='PENDING'`) + viết test concurrency thật (2 session Postgres).
2. Vá P0-2 hoặc **gỡ "link aff đếm click" khỏi mô tả combo** cho tới khi chạy được.
3. Owner: đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (việc còn nợ từ PLAN-051).
4. Quick win 1 dòng: bỏ `|| true` ở deploy, bump CI lên Python 3.12, thêm `lint-imports`.
5. Lên lịch `pg_dump` + **thử restore một lần**.
6. Việc cũ chưa xong: verify live 4 luồng PLAN-053→056; TASK-055 khảo sát giỏ hàng;
   review + commit diff đang treo.

---

## Phiên 2026-08-21 — bổ sung tính năng còn thiếu của Combo 2 (PLAN-052 → 056)

Owner duyệt cho Claude Code execute cả backend đợt này — ghi ở **ADR-010**, hết hiệu
lực sau PLAN-056.

### System State (2026-08-21)

- **Máy chạy lại được**: Python 3.14.7 hoạt động (handoff 2026-08-11 ghi interpreter
  mất — nay đã khác). `pytest` chạy bình thường.
- Container `toolsauto_postgres` đang **BẬT** (port 5434), đã `alembic upgrade head`
  tới `i7d4e5f6a7b8`.
- Test suite: **243 passed** (baseline đầu phiên 175), `--ignore=tests/test_threads_world_news.py`.
- Stack vẫn **TẮT**. Chưa đăng thử bất cứ thứ gì lên Facebook trong phiên này.
- Diff chưa commit: 16 file sửa, 6 file mới (2 page/adapter, 4 test), 1 migration.

### Done This Session

| Việc | Proof |
|---|---|
| **PLAN-052** Hàng đợi nhận mọi job_type — job FEED trước đây nằm PENDING vĩnh viễn | `git stash` code cũ → 2 test FEED/STORY đỏ; code mới → 9/9 xanh (SQL thật trên Postgres) |
| **PLAN-053** Lấy `post_url` bài feed + auto-comment cho bài feed | 14 test; vá luôn rủi ro bắt nhầm link bài người khác lúc cuộn feed |
| **PLAN-054** Đăng Story + phủ link aff lên tin | 23 test; `story_composer.py` mới; chặn đăng nhầm danh nghĩa Page |
| **PLAN-055** Đính ảnh vào comment | 12 test; cột `comment_image_path` + migration; 4 adapter cùng chữ ký |
| **PLAN-056** Video dài: chờ upload theo dung lượng thật thay vì cứng 20s | 9 test; có trần 7 phút, dừng sớm khi thấy preview |
| **TASK-055** Giỏ hàng: chuyển thành khảo sát live, **không code mù** | Lý do + 7 bước khảo sát trong task |

### Lỗi có sẵn phát hiện được trong lúc làm

1. `claim_next_job` liệt kê cứng `POST`/`COMMENT` ⇒ **mọi job FEED không bao giờ chạy**.
   Bài feed của PLAN-049 lên được là do gọi adapter trực tiếp, không qua hàng đợi.
2. `_normalize_fb_text` chỉ NFD nên còn dấu tổ hợp — dùng để so tên Page sẽ **chặn oan**
   khi tên lệch dấu. Đã thêm `_identity_key` riêng cho phép so danh tính.

### Next Action — theo thứ tự

1. **Owner mở phiên trình duyệt** để verify live 4 thứ chưa từng chạy thật:
   - Đăng tin ảnh + tin video lên Page nháp (PLAN-054)
   - Chữ trên tin có bấm được thành link không → quyết định có bán mục "link aff story" hay không
   - Comment kèm ảnh dưới một Reels thật (PLAN-055)
   - Đăng bài feed thật, xem log có bắt được `post_url` không (PLAN-053)
   - Đăng video > 5 phút (PLAN-056)
2. **TASK-055**: khảo sát giỏ hàng. Nếu Facebook không cho → **gỡ mục đó khỏi mô tả
   combo Page Master trước khi bán tiếp**.
3. Review + commit diff đang treo.
4. Việc cũ chưa xong: bump `python-version` trong `deploy.yml` để mở lại CI (đỏ từ 2026-07-29).

### Cảnh báo bán hàng (chưa được hứa với khách)

- "Link aff bấm được trong story" — chưa kiểm chứng.
- "Gắn giỏ hàng" — chưa có dòng code nào, chưa khảo sát.
- "Tìm video theo từ khóa" — mới chỉ đúng với TikTok. **Douyin: 0%.** YouTube Short và
  Facebook Page chỉ tải được khi dán link.


## ⚠️ CẢNH BÁO BẢO MẬT (2026-08-11) — chờ Owner xử lý

`scratch/threads_cookies.json` chứa **cookie phiên thật** (FB `xs`/`c_user`,
IG `sessionid`, TikTok `msToken`) bị commit ở `a723c0f` ngày 2026-04-25 trên repo
**PUBLIC** `github.com/dthanhvu03/toolsauto` → phơi công khai ~3,5 tháng.

Đã xử (PLAN-051 §D): `filter-branch` purge cả 13 branch + force-push + gc.
**Nhưng object mồ côi vẫn tải được công khai theo SHA** (`gh api ...?ref=a723c0f`
→ 6908 bytes) cho tới khi GitHub tự GC.

Owner đã quyết: **giữ repo public, không mở ticket GC** — chấp nhận rủi ro còn lại.

Việc duy nhất còn lại và bắt buộc: **đổi mật khẩu + đăng xuất mọi phiên
FB/IG/TikTok**. Ai đã clone repo phải clone lại (mọi SHA đã đổi).

## System State (2026-08-11)

- **Máy không chạy được stack**: interpreter `pythoncore-3.14-64` biến mất,
  `venv\Scripts\python.exe` là stub trỏ vào đường dẫn đã mất → không chạy được
  `pytest` lẫn worker. Registry HKCU vẫn trỏ path cũ.
- Container `toolsauto_postgres` tắt 10 ngày, đã `docker start` lại để audit.
- **CI đỏ từ 2026-07-29**, 5 commit cuối trên `main` chưa từng deploy:
  workflow đặt Python 3.10 nhưng requirements ghim numpy 2.4.2 (cần ≥3.11).
- Hàng đợi tắc: 7 job DRAFT `[AI_GENERATE]` + 2 PENDING, tất cả `is_approved=false`;
  job #2 trỏ media đã bị xoá. `viral_materials` 11/11 kẹt DRAFTED.

## Done 2026-08-11 — audit tính năng + dọn nợ kỹ thuật (PLAN-051)

| Việc | Proof |
|---|---|
| Audit toàn bộ tính năng bằng DB thật + CI thật (không chỉ đọc doc) | Bảng row-count 26 bảng; `gh run list` 5 lần failure |
| Gỡ cookie phiên khỏi git index + `.gitignore` chặn `*cookies*.json` | `git ls-files \| xargs grep` secret pattern → rỗng |
| Xoá 731 dòng code chết (3 template, `gemini_api.py`, 2 shim) | grep 0 tham chiếu; ADR-006 §7 ghi closure |
| Sửa docstring `native_fallback.py` chỉ sai chỗ vision | vision nằm ở `call_native_gemini_vision` từ TASK-025 |
| ADR-009: `GenericAdapter` là code không thể chạm tới | `dispatcher.py:88` luôn ghi đè Registry cho cả 4 platform |

Diff đang chờ Owner review, **chưa commit**: 9 file, −750 dòng.

## Next Action (2026-08-11)

1. **Owner:** đổi mật khẩu + đăng xuất mọi phiên FB/IG/TikTok (vô hiệu cookie đã rò)
2. **Owner:** quyết repo private và/hoặc purge lịch sử git (thao tác phá huỷ)
3. Cài lại Python 3.14 + dựng venv → mở lại pytest
4. Bump `python-version` trong `deploy.yml` + xử `test_threads_world_news.py` → mở lại CI
5. Owner chốt ADR-009 trước khi động vào `GenericAdapter`

## System State (2026-07-31)

- PLAN-048 stack (supervisor + smart gate + orphan purge) đã qua vòng review/hardening
- **PLAN-049**: Facebook đăng được **bài feed** (chữ thuần / chữ + ảnh), không còn chỉ Reels
- FB **POST = Reels** vẫn chỉ video; **FEED** nhận ảnh/video/không media — hai loại tách bạch
- Job #6 (PNG vào Reels) bị chặn trước khi mở browser, tính là VALIDATION (không phạt account)
- Stack đang **TẮT**. Test suite: **161 passed**

## Done This Session — phần 2: luồng bài feed (PLAN-049)

| Việc | Proof |
|---|---|
| `JobType.FEED` + `assert_feed_media()` + rẽ nhánh dispatcher | `tests/test_facebook_feed_post.py` (17 pass) |
| `FacebookFeedComposer` — mở composer, gõ chữ, đính ảnh, Tiếp → Đăng | Đăng thật lên Page `kids0810`, owner đã xác nhận thấy bài |
| Form job thủ công chọn Reels / Bài feed, `accept` đổi theo | `test_media_ui_consistency` cập nhật theo chính sách mới |
| 2 lỗi chỉ lộ khi chạy live | Bước "Tiếp" của Page; `pre_post_delay()` thiếu tham số `page` |

Còn nợ: `post_url` của bài feed (Facebook Page không phơi permalink ra DOM). Chi tiết + hướng vá ghi trong PLAN-049.

## Done This Session (audit + fix 12 findings)

| Vùng | Thay đổi | Proof |
|---|---|---|
| Nhận diện process | `app/core/process_scan.py` mới — match cả `-m app.x.y` lẫn `app/x/y.py` (PM2), ancestry chống PID reuse, hydrate lazy | `tests/test_process_scan.py` (20 pass) |
| Orphan purge | Chỉ kill browser root có `--user-data-dir` nằm trong profile root chuẩn, không có ancestor worker sống, đã chạy > 120s | `tests/test_orphan_browser_purge.py` (13 pass) |
| Supervisor | State/lock tuyệt đối trong `storage/db/config/`, lock `O_CREAT|O_EXCL` + thu hồi stale, stop bằng CTRL_BREAK | `tests/test_local_supervisor.py` (10 pass) |
| Media gate | Một nguồn sự thật cho extension, caption-only manual job vẫn tạo được, upload bị từ chối không để lại file | `tests/test_facebook_media_gate.py` (14 pass) |
| Circuit breaker | `error_type=VALIDATION` không tăng `consecutive_fatal_failures` | như trên |
| Heartbeat | Mọi early return của publisher đều stop heartbeat (finally) | `tests/test_publisher_heartbeat.py` (3 pass) |
| ffmpeg | `app/core/media/ffmpeg_path.py` mới; thumbnail/DRM/orchestrator/reup đều resolve binary | `tests/test_ffmpeg_resolution.py` (10 pass) |
| UI | Form create/manual: video-only cả label, drag-drop lẫn `accept` | `tests/test_media_ui_consistency.py` (4 pass) |
| Hiệu năng | Quét process 8.3s → 0.02s (capture) + cache 30s cho đếm browser | đo trực tiếp trên máy (513 process) |

## Hardening vòng 2 (sau review)

| Rủi ro | Xử lý |
|---|---|
| Lệnh chỉ *nhắc tới* đường dẫn worker (`git diff`, `compileall`, editor) bị nhận là worker → supervisor không spawn | Parse argv thật (`-m` / positional script), argv[0] **và** tên process phải là interpreter |
| Browser mất ancestry khi job còn RUNNING → bị coi là orphan | Purge nhận `db`: profile của account có job RUNNING không bao giờ bị đụng; DB lỗi → tắt purge |
| PID reuse giữ lock | Lock ghi thêm `create_time`, lệch > 1s ⇒ stale |
| CTRL_BREAK khi không có process group riêng | Chỉ gửi khi `own_process_group=True`, còn lại dùng terminate |
| `count_chrome_processes` đổi contract | `ChromeProcessCounts` (NamedTuple): có tên field, vẫn unpack như tuple |
| Cache đếm browser bị đọc/ghi đa luồng | Bọc `threading.Lock` |

Full suite: `pytest tests -q --ignore=tests/test_threads_world_news.py` → **142 passed**.

Smoke process thật (Chromium thật, không đụng job production):
- Worker kiểu PM2 (script path) + Chromium của nó → **không** bị purge; orphan thật → bị kill (1/1)
- Topology Playwright thật `chrome ← node ← python worker` → attribution `worker`, an toàn
- Ancestry bị phá + job RUNNING trong DB thật → **không** bị kill; sau khi job DONE → mới purge được
- Lock: supervisor thứ 2 bị chặn bởi supervisor đang chạy thật (pid 33416)

## Unfinished + Blockers

- `tests/test_threads_world_news.py` hỏng từ trước — **đã chứng minh trên `origin/main`** (worktree sạch, cùng interpreter): cùng lỗi `ModuleNotFoundError: app.services`. Module bị xoá ở commit `fd87077` (refactor P028). Baseline không tính file này: 51 passed. Sửa cần dựng lại test theo module mới → tách task riêng.
- ~~Máy đang chạy 2 supervisor + 2 publisher...~~ **Đính chính:** đây KHÔNG phải trùng lặp. `venv\Scripts\python.exe` trong layout PyManager là **stub 3MB** re-exec interpreter thật (`AppData\Local\Python\pythoncore-3.14-64\python.exe`) làm process con **cùng cmdline** → mỗi worker hiện ra 2 pid. Đã sửa `ProcessSnapshot.find_pids` gộp chuỗi cha–con thành 1 instance (giữ nguyên 2 worker anh em thật, ví dụ FB_Publisher_1/2 của PM2).

## Next Action

- Restart `.\start.ps1 -Stack` và xác nhận log `[STACK] ensure web=... fb_publisher=... chrome_ta=`
- Hủy Job #6 hoặc thay media bằng .mp4
