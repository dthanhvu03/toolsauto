# ADR-011 — Ngoại lệ cho Claude Code vá P0 concurrency

- **Ngày soạn**: 2026-09-05
- **Trạng thái**: ĐỀ XUẤT — **chờ Owner duyệt**, chưa có hiệu lực
- **Liên quan**: ADR-010 (đã hết hiệu lực sau PLAN-056), AUDIT-001, PLAN-057

## Bối cảnh

CLAUDE.md quy định Claude Code đóng vai UX/Refactor/Quality, **không được** viết
adapter, worker, core business logic hay database migration. ADR-010 từng cho ngoại
lệ nhưng đã hết hiệu lực sau PLAN-056.

Owner giao "nâng cấp hệ thống để chạy trơn tru" (2026-09-04). Việc 1 (hạ tầng) đã
xong ở PLAN-057 — nằm trong vai trò hiện tại. **Việc 2 thì không**: vá P0-1 phải
sửa SQL trong `app/core/queue/queue.py`, ngưỡng trong `app/config.py`, và **thêm một
migration** cho partial unique index. Cả ba đều nằm trong vùng cấm.

## Vì sao đáng làm bây giờ

P0-1 là **ba bất biến vỡ độc lập** (AUDIT-001 §P0-1), hậu quả là hai worker cùng
claim một job → **đăng trùng bài**. Đây là rủi ro *tài khoản*, không phải rủi ro kỹ
thuật: Facebook phạt là mất account, mất luôn hàng đang bán.

Hiện chưa xảy ra vì mới 1 account và 14 job. Nhưng **điều kiện kích hoạt chính là
tăng tải** — tức đúng thứ Owner vừa nói muốn làm.

## Phạm vi xin duyệt (không hơn)

| Mục | File | Thay đổi |
|---|---|---|
| P0-1a | `app/core/queue/queue.py` | Thêm `AND status='PENDING'` ở WHERE ngoài |
| P0-1c | `app/config.py` | `WORKER_CRASH_THRESHOLD_SECONDS` 120 → ≥1200 (phải > deadline 900) |
| P0-1b | `alembic/versions/` (file mới) | Partial unique index `(account_id, platform)` khi `status='RUNNING'` + bắt `IntegrityError` |
| Test | `tests/` (file mới) | TEST A, TEST B, TEST C theo đặc tả AUDIT-001 §19 |

**Không** đụng adapter, không đụng luồng đăng bài, không refactor tiện thể.

## Rủi ro và cách chặn

- Migration index: truy vấn live 2026-08-21 và 2026-09-04 đều cho **0 job RUNNING**
  và không cặp `(account_id, platform)` nào >1 RUNNING ⇒ tạo index được ngay, không
  cần dọn dữ liệu. Vẫn phải backup trước (`manage.py db backup` nay chạy thật, đã
  chứng minh restore được ở PLAN-057).
- **TEST B đỏ sau khi vá A là đúng như dự đoán**, không phải bản vá hỏng. Nếu hoãn
  index: giữ `xfail` có ghi lý do, không xoá test, không tuyên bố B đã đóng, và
  **chỉ chạy 1 publisher**.
- Nâng `WORKER_CRASH_THRESHOLD_SECONDS` lên ≥1200 s làm job crash thật nằm lâu hơn
  trước khi được recover. Đây là đánh đổi có chủ đích: thà recover chậm còn hơn cướp
  job đang chạy khoẻ rồi đăng trùng.

## Hiệu lực

Nếu duyệt: có hiệu lực cho **đúng 4 mục trong bảng trên**, hết hiệu lực khi TEST A
xanh và TEST B xanh-hoặc-xfail-có-lý-do. Mọi backend khác vẫn cần PLAN từ Antigravity.

## Quyết định của Owner

- [ ] Duyệt
- [ ] Không duyệt — chuyển sang Antigravity ra PLAN
