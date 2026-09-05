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
