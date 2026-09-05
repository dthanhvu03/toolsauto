# PLAN-058 — Vá P0-1: ba bất biến đồng thời của hàng đợi

- **Ngày**: 2026-09-05
- **Executor**: Claude Code theo **ADR-011** (Owner duyệt 2026-09-05)
- **Nguồn**: AUDIT-001 §10, §19
- **Trạng thái**: Done (chờ verify trên CI)

## Ba bất biến, ba bản vá khác nhau

| | Bất biến | Bản vá | Test |
|---|---|---|---|
| **A** | 1 job PENDING → đúng 1 worker | `AND status='PENDING'` ở qual NGOÀI (`queue.py`) | TEST A |
| **B** | 1 `(account, platform)` → tối đa 1 RUNNING | partial unique index + bắt `IntegrityError` | TEST B |
| **C** | Job đang chạy không bị recovery cướp | `WORKER_CRASH_THRESHOLD_SECONDS` 120 → 1200 | 2 test bất biến hằng số |

## Proof — đỏ trước, xanh sau

### TEST A
Chạy trên code **chưa vá**:
```
AssertionError: worker thua vẫn claim được job 250 đang RUNNING
assert 250 is None
```
Sau khi thêm `status='PENDING'` vào qual ngoài → **xanh**.

### TEST B
Chạy sau khi đã vá A, **chưa có index** — đỏ **đúng như AUDIT-001 dự đoán**:
```
AssertionError: 2 job cùng RUNNING trên một (account, platform);
claim nhận job 253 trong khi job 252 đang chạy
assert 2 <= 1
```
Sau migration `j8e5f6a7b8c9` + bắt `IntegrityError` → **xanh**.

Index đã tạo trên DB thật:
```
CREATE UNIQUE INDEX uq_jobs_one_running_per_account_platform
ON public.jobs USING btree (account_id, platform)
WHERE ((status)::text = 'RUNNING'::text)
```

### TEST C (ngưỡng)
`WORKER_CRASH_THRESHOLD_SECONDS=120 pytest` → **2 failed** (chốt bắt được hồi quy).
Với giá trị mới 1200 → **2 passed**.

### Suite
- Windows (có Postgres): **248 passed**
- Linux container: **49 passed, 2 skipped**

## Quyết định kỹ thuật đáng ghi

**Test race không dùng barrier.** Bản đầu dùng `threading.Barrier` cho 2 session và
**xanh giả trên code chưa vá** — cửa sổ race chỉ vài trăm micro-giây, `SessionLocal()`
lại kết nối lười nên sau barrier vẫn lệch vài ms. Đã đổi sang dựng **tất định** đúng
trạng thái mà race tạo ra: T1 `UPDATE → RUNNING` chưa commit, T2 chạy `claim_next_job`
và chặn ở khoá dòng (A) hoặc khoá index (B), rồi T1 commit. Không phụ thuộc lịch OS.

**Lệch có chủ ý so với §19.** Audit đề xuất TEST B đặt `schedule_ts` **bằng nhau** để
ép hoà khoá sắp xếp. Hoà thì claim chọn dòng nào là **không xác định** ⇒ test lúc đỏ
lúc xanh. Đặt job mục tiêu sớm hơn khiến nó luôn được chọn — vẫn đúng bất biến, mà
tất định. Đã ghi lý do trong docstring của test.

**`IntegrityError` trả `None`, không retry tại chỗ.** Hàng đợi không đổi trong vài
giây tới nên retry ngay chỉ tốn thêm một vòng tranh chấp; worker thử lại ở nhịp sau.

**Đánh đổi của ngưỡng 1200s.** Job crash thật nằm ~20 phút mới được recover thay vì
2 phút. Chủ ý: thà recover chậm còn hơn cướp job đang chạy khoẻ rồi đăng trùng.

## Hạn chế còn lại — cần Owner quyết

**CI không chạy TEST A/B.** Hai test mang `pytest.mark.integration` và tự skip khi
không có Postgres. Runner GitHub Actions **không có Postgres** ⇒ trên CI chúng luôn
skip, tức bất biến P0-1 **không được bảo vệ ở CI**, chỉ được kiểm khi chạy tay trên
máy có DB.

Cách đóng: thêm `services: postgres:16` vào job `test` trong `deploy.yml`. Đây là
`deploy.yml`, **ngoài phạm vi ADR-011** nên chưa làm.

## Không làm trong PLAN này
- P0-2 affiliate / TEST C của §19 — đã gỡ khỏi ADR-011 khi duyệt, cần quyết riêng.
- Không đụng adapter, không đụng luồng đăng bài.
