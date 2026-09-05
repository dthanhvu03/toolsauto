# PLAN-057 — Hạ tầng tự phục hồi: CI, compose Postgres, backup thật

- **Ngày**: 2026-09-05
- **Executor**: Claude Code (Owner giao trực tiếp 2026-09-04)
- **Trạng thái**: In Progress

## Vấn đề

Hệ thống không "chạy chưa trơn" — nó **không chạy liên tục được** và **không tự
phục hồi**. Ba bằng chứng:

1. **Không có gì lên VPS từ 2026-07-29** (5 tuần). CI đỏ 6 lần liên tiếp. Toàn bộ
   PLAN-049→056 nằm trên GitHub nhưng chưa từng chạy production một giây nào.
2. **Postgres tắt 2 lần không ai biết** — 10 ngày (phát hiện 2026-08-11) rồi 13 ngày
   (phát hiện 2026-09-04). Nguyên nhân: `RestartPolicy=no` và **không có
   `docker-compose.yml` trong repo** — container tạo tay bằng `docker run`, không ai
   dựng lại được.
3. **Backup không tồn tại dù tưởng là có.** `manage.py db backup` gọi
   `copy2(DB_PATH)` — copy file SQLite legacy, không phải Postgres đang chạy. Vẫn in
   `Backed up: ...` thành công ⇒ Owner tin là có backup.

## Scope — chỉ hạ tầng/config, KHÔNG chạm business logic

### A. Mở lại CI (2 nguyên nhân độc lập, phải sửa cả hai)
- `deploy.yml:30` `python-version: "3.10"` → `"3.12"`. `requirements.txt` ghim
  numpy 2.4.2 cần ≥3.11.
- `deploy.yml:45` `pytest tests/` collect luôn `tests/test_threads_world_news.py`,
  file này `ModuleNotFoundError: app.services` (module xoá ở `fd87077`) → collection
  error → CI đỏ **bất kể Python nào**. Thêm `--ignore`.
- **Sửa một trong hai vẫn đỏ.** Đây là đính chính so với nhận định "sửa 1 dòng" ở
  phiên 2026-09-04.

### B. Migration hỏng phải làm deploy ĐỎ
- `deploy.yml:112-113` `|| true` nuốt lỗi `db stamp-if-needed` + `db upgrade head`.
  Bỏ `|| true` ở `upgrade head`.

### C. Postgres tự sống lại + dựng lại được
- Thêm `docker-compose.yml`: `postgres:16-alpine`, port `5434:5432`,
  `restart: unless-stopped`, healthcheck, **named volume**.
- ⚠️ Container hiện dùng **anonymous volume** `9a3acb1502…`. Compose với named
  volume sẽ tạo volume RỖNG, data cũ mồ côi. Bắt buộc dump → restore → đối chiếu
  row count trước khi chuyển.

### D. Backup Postgres thật + chứng minh restore được
- `manage.py db backup` → `pg_dump` theo `DATABASE_URL`, không phải `copy2`.
- Chạy thử **restore một lần thật**, đối chiếu row count 26 bảng.

## Không làm trong PLAN này
- P0-1 concurrency, P0-2 affiliate → là backend, cần ADR mới (ADR-010 hết hiệu lực
  sau PLAN-056).
- Không refactor "tiện thể" ngoài 4 mục trên.

## Definition of Done
- [ ] A: CI xanh trên GitHub Actions (run thật, không phải suy luận)
- [ ] B: `|| true` gỡ khỏi `upgrade head`
- [ ] C: `docker-compose.yml` tồn tại; `docker compose up -d` sau `docker rm` dựng
      lại được; `restart: unless-stopped` xác nhận bằng `docker inspect`
- [ ] D: `manage.py db backup` sinh file `.sql` từ Postgres; restore vào DB tạm và
      row count 26 bảng khớp DB gốc
- [ ] Test suite vẫn 243 passed

---

## Proof (2026-09-05)

### Bằng chứng ngoài dự kiến: sự cố tái diễn ngay trong phiên
Đầu phiên container Postgres **lại tắt** (phiên trước start lúc 2026-09-04 06:23,
máy sang ngày là chết). Đây là lần thứ **3**, và là bằng chứng trực tiếp cho mục C.

### A — CI
- `deploy.yml:30` → `python-version: "3.12"`
- `deploy.yml:45` → thêm `--ignore=tests/test_threads_world_news.py`
- Xác nhận file hỏng thật: `pytest tests/test_threads_world_news.py` →
  `ModuleNotFoundError: No module named 'app.services'` → *collection error*, tức
  là làm đỏ toàn bộ run chứ không chỉ fail 1 test.

### B — migration
`deploy.yml:113` `python manage.py db upgrade head` (đã gỡ `|| true`).
Giữ `|| true` ở `stamp-if-needed` (dòng 112) có chủ đích: đó là bước dò điều kiện,
nếu nó sai thì `upgrade head` ngay sau sẽ đỏ.

### C — compose + tự khởi động lại
- `docker-compose.yml` mới: `postgres:16-alpine`, `restart: unless-stopped`,
  healthcheck `pg_isready`, named volume `toolsauto_pgdata`, port `5434:5432`.
- `docker compose config --quiet` → hợp lệ.
- **Chuyển volume ẩn danh → named volume, không mất dữ liệu:**
  container cũ chỉ *dừng + đổi tên* `toolsauto_postgres_old_20260905`, **không xoá**,
  giữ làm đường lùi.
- `docker inspect` container mới: `healthy | restart=unless-stopped`.
- Đối chiếu sau chuyển: **26 bảng / 440 row, `diff` rỗng — khớp 100%**.
- Dựng lại được: `docker compose down` (container biến mất) → `up -d` → `healthy`,
  jobs=14, accounts=1 **còn nguyên**.
- App kết nối được: `alembic current` = `i7d4e5f6a7b8 (head)`.

### D — backup thật + restore đã chứng minh
- `manage.py db backup` viết lại: `pg_dump` trên PATH, fallback `docker exec`
  (`POSTGRES_CONTAINER`, mặc định `toolsauto_postgres`); SQLite legacy vẫn copy như cũ.
- Thất bại nay **thoát khác 0** và xoá file dở — trước đây `copy2(DB_PATH)` backup
  nhầm SQLite mà vẫn in thành công.
- Chạy thật: `storage/db/backups/toolsauto_db_20260905_083201.sql`, 115.081 bytes.
- **Restore thật vào DB tạm `toolsauto_restore_test`**: 26 bảng / 440 row,
  `diff` với DB gốc **rỗng**. DB tạm đã drop sau khi đối chiếu.
- Dump nằm trong `storage/` nên đã bị `.gitignore:83` chặn, không lọt vào git.

### Test suite
`pytest tests -q --ignore=tests/test_threads_world_news.py` → **243 passed**.

## Còn lại
- [ ] A chưa đóng hẳn: cần **CI xanh trên GitHub Actions thật**, chưa suy luận được.
- [ ] Chưa lên lịch backup định kỳ (mới có lệnh chạy tay chạy đúng).
- [ ] Container cũ `toolsauto_postgres_old_20260905` + volume ẩn danh
      `9a3acb1502…` vẫn giữ. Chỉ xoá khi Owner xác nhận đã chạy ổn vài ngày.

---

## Mục A CHƯA ĐÓNG — CI lộ ra lỗi thứ ba, là lỗi có sẵn trong code production

Run `33936616449` (commit `a9a5267`): **`5 failed, 223 passed, 15 skipped`**.

Tiến bộ có thật: trước đây fail ở bước **Install dependencies** (Python 3.10),
nay qua được và fail ở **Run unit tests** ⇒ bản vá Python + `--ignore` đã đúng.

Nhưng lộ ra **nguyên nhân thứ ba**, không liên quan hạ tầng:

```
FAILED tests/test_orphan_browser_purge.py::test_other_project_chromium_is_left_alone
FAILED tests/test_orphan_browser_purge.py::test_personal_chrome_is_left_alone
FAILED tests/test_orphan_browser_purge.py::test_counts_separate_instances_from_helper_processes
FAILED tests/test_process_scan.py::test_other_project_playwright_chromium_is_not_attributed
FAILED tests/test_process_scan.py::test_personal_chrome_is_not_attributed
```

**Xanh trên Windows, đỏ trên Linux — mà VPS chạy Linux.**

### Nguyên nhân (đã chứng minh trên container Linux thật, không suy đoán)

`process_scan.py:553` thêm ứng viên `str(Path(user_data_dir).resolve())` để bắt
được profile của chính mình khi đường dẫn là tương đối. Nhưng trên POSIX,
`.resolve()` giải một đường dẫn **tương đối** theo **CWD**, mà CWD chính là thư mục
dự án ToolsAuto.

Chạy thật trong `python:3.12-slim`:

```
cmdline của trình duyệt NGƯỜI KHÁC : C:/Users/Admin/AppData/Local/Google/Chrome/User Data
sau .resolve() trên Linux          : /repo/C:/Users/Admin/AppData/Local/Google/Chrome/User Data
path_is_within(resolved, proj_root): True
=> BỊ NHẬN NHẦM LÀ BROWSER TOOLSAUTO
```

`_attribute_browser_root` trả `"profile"` cho trình duyệt của người khác ⇒ orphan
purge của PLAN-048 **được phép kill nó**. Đây đúng là bất biến mà chính test đó lập
ra để bảo vệ ("never touch what you cannot attribute").

### Vì sao tới giờ mới lộ

CI chết ở bước cài dependency từ 2026-07-29 nên **chưa bao giờ chạy tới test trên
Linux**. Lỗi nằm im từ PLAN-048. Máy dev là Windows nên `.resolve()` không
relativize ⇒ test xanh, che mất lỗi.

### Đánh giá rủi ro thật trên VPS

Điều kiện kích hoạt là một browser có `--user-data-dir` **tương đối**. Worker của
ToolsAuto truyền đường dẫn tuyệt đối, và VPS hiếm khi có browser lạ ⇒ rủi ro hiện
tại **thấp**, nhưng code sai và bất biến an toàn đang vỡ trên đúng nền tảng
production.

### ESCALATION

`app/core/process_scan.py` là core logic — ngoài vai trò Claude Code theo CLAUDE.md.
Theo quy tắc "Phát hiện lỗi backend → DỪNG và báo Anti": **dừng ở đây, chờ Owner
quyết**. Không tự sửa, và **không** dán `--ignore` lên 5 test này để CI xanh giả.

Hướng vá tối thiểu (khi được duyệt): chỉ thêm ứng viên `.resolve()` khi
`user_data_dir` **đã là đường dẫn tuyệt đối**, hoặc giải tương đối theo project root
một cách tường minh thay vì theo CWD.

---

## Cập nhật 2026-09-05 (b) — mục A ĐÓNG phần test; lộ blocker cuối là SSH

Commit `9996f4c`. Run `33937825138`:

```
job "test"   : success   <-- LẦN ĐẦU XANH kể từ 2026-07-29
job "deploy" : failure   <-- ssh: handshake failed: unable to authenticate
```

### Lỗi attribution đã vá + chứng minh nhân quả

`process_scan.py` gọi `.resolve()` cho mọi `--user-data-dir`. Trên POSIX
`"C:/Users/.../Chrome"` là **tương đối**, nên `.resolve()` rebase nó lên CWD (thư mục
dự án) ⇒ browser người khác thành `"profile"` của ToolsAuto ⇒ orphan purge được phép
kill. Vá bằng `is_absolute_elsewhere()`: **thu hẹp** chứ không xoá `.resolve()`, vì
`test_browser_with_relative_profile_path_is_attributed` cần nó cho đường dẫn tương
đối thật.

Chạy trong container `python:3.12-slim`:
- code cũ → **5 failed, 41 passed** (đúng 5 test CI báo)
- code mới → **47 passed**
- Windows → **244 passed**, không hồi quy

Thêm `test_foreign_absolute_path_is_never_resolved_onto_our_cwd`, có nhánh theo nền
tảng nên **Windows cũng bắt được** — trước đây máy dev Windows không thể lộ lỗi này.

### Quy trình mới: verify trên Linux trước khi push
Lỗi lọt lưới 5 tuần vì máy dev là Windows. Nay chạy suite trong container Linux
trước, không đẩy lên rồi chờ CI đoán.

### Backup: xong cả lịch lẫn retention
- PM2 app `DB_Backup`, `cron_restart "0 3 * * *"`, `autorestart:false`.
- `db backup --keep 14` dọn dump cũ (đã chạy thật: prune đúng file cũ nhất).
- `deploy.yml` thêm `manage.py db backup` **ngay trước migration**. Bước cũ dòng 85
  chỉ `cp` file SQLite legacy — **cùng đúng lỗi backup nhầm đích**. Migration nay
  fail-hard nên deploy đỏ mà không có dump dùng được là mất đường lui.

## BLOCKER cuối — chỉ Owner xử được

`ssh: handshake failed: unable to authenticate, attempted methods [none publickey]`

Kết nối SSH **không xác thực được**, script deploy **chưa hề chạy** trên VPS.
`VPS_HOST` / `VPS_USER` / `VPS_SSH_KEY` đều tồn tại nhưng đặt từ **2026-03-27**.
Nguyên nhân khả dĩ: key đã xoay trên VPS, VPS dựng lại, hoặc user đổi.

Claude Code **không có quyền truy cập VPS lẫn private key** ⇒ không kiểm chứng được
từ đây. Cần Owner: thử `ssh` tay vào VPS, rồi cập nhật `VPS_SSH_KEY` (và
`VPS_HOST`/`VPS_USER` nếu đổi).

## Trạng thái Definition of Done
- [x] A — CI **test job xanh** (run 33937825138). Pipeline đầy đủ còn chờ SSH.
- [x] B — `|| true` đã gỡ khỏi `upgrade head`
- [x] C — compose + `restart: unless-stopped`, dựng lại được, dữ liệu khớp 100%
- [x] D — `pg_dump` thật, restore đã chứng minh, có lịch + retention
